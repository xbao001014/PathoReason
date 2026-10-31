"""Bounded, read-only host telemetry. No daemon, GPU allocation, or model calls."""
import asyncio
import csv
import io
import math
import os
from pathlib import Path
import subprocess
import time
from pydantic import BaseModel, Field
from .persistence import now


class GpuDevice(BaseModel):
    index: int
    uuid: str
    name: str
    memory_total_mb: float | None = None
    memory_used_mb: float | None = None
    utilization_percent: float | None = None
    temperature_c: float | None = None


class HardwareSnapshot(BaseModel):
    sampled_at: str
    environment: str
    cpu_count: int | None = None
    cpu_percent: float | None = None
    memory_total_mb: float | None = None
    memory_used_mb: float | None = None
    gpus: list[GpuDevice] = Field(default_factory=list)
    cpu_error: str | None = None
    gpu_error: str | None = None
    refresh_seconds: int = 5


def number(value):
    try:
        result = float(value)
        return result if math.isfinite(result) and result >= 0 else None
    except (TypeError, ValueError):
        return None


def gpu_inventory():
    command = ['nvidia-smi', '--query-gpu=index,uuid,name,memory.total,memory.used,utilization.gpu,temperature.gpu', '--format=csv,noheader,nounits']
    result = subprocess.run(command, capture_output=True, text=True, timeout=3, check=True)
    rows = []
    for row in csv.reader(io.StringIO(result.stdout), skipinitialspace=True):
        if len(row) != 7:
            raise ValueError('gpu_inventory_invalid')
        index, uuid, name, total, used, utilization, temperature = [x.strip() for x in row]
        rows.append(GpuDevice(index=int(index), uuid=uuid, name=name,
            memory_total_mb=number(total), memory_used_mb=number(used),
            utilization_percent=number(utilization), temperature_c=number(temperature)))
    if len({g.uuid for g in rows}) != len(rows) or len({g.index for g in rows}) != len(rows):
        raise ValueError('gpu_inventory_ambiguous')
    return rows


def cpu_counters():
    # guest/guest_nice are already included in user/nice; do not double count.
    fields = Path('/proc/stat').read_text().splitlines()[0].split()
    if fields[0] != 'cpu':
        raise ValueError('cpu_metrics_unavailable')
    values = [int(x) for x in fields[1:9]]
    return sum(values), values[3] + values[4]


def sample(environment):
    view = HardwareSnapshot(sampled_at=now(), environment=environment, cpu_count=os.cpu_count())
    try:
        start, idle_start = cpu_counters()
        time.sleep(.15)
        end, idle_end = cpu_counters()
        view.cpu_percent = round(max(0, min(100, 100 * (1 - (idle_end-idle_start)/(end-start)))), 1) if end > start else None
        memory = {line.split(':')[0]:int(line.split()[1]) for line in Path('/proc/meminfo').read_text().splitlines()}
        view.memory_total_mb = memory['MemTotal']/1024
        view.memory_used_mb = (memory['MemTotal']-memory['MemAvailable'])/1024
    except (OSError, ValueError, KeyError, IndexError):
        view.cpu_error = 'cpu_metrics_unavailable'
    try:
        view.gpus = gpu_inventory()
    except (OSError, subprocess.SubprocessError, ValueError):
        view.gpu_error = 'gpu_metrics_unavailable'
    view.sampled_at = now()
    return view


class HardwareMonitor:
    def __init__(self, environment):
        self.environment = environment
        self.lock = asyncio.Lock()
        self.cached = None
        self.sample_time = 0

    async def snapshot(self):
        async with self.lock:
            if self.cached is None or time.monotonic()-self.sample_time >= 4:
                self.cached = await asyncio.to_thread(sample, self.environment)
                self.sample_time = time.monotonic()
            return self.cached
