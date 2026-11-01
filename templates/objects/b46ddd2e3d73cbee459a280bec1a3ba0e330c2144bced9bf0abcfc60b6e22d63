"""Bounded CPU feature cache. Stores immutable decoded bags, never fitted state."""
from collections import OrderedDict
import os
from pathlib import Path

import h5py
import numpy as np
import torch
from torch.utils.data import get_worker_info


def available_memory():
    """Best-effort Linux host/container headroom; cache cap remains mandatory."""
    limits = []
    try:
        mem = dict(line.split(':', 1) for line in Path('/proc/meminfo').read_text().splitlines())
        limits.append(int(mem['MemAvailable'].split()[0]) * 1024)
    except (OSError, ValueError, KeyError):
        pass
    try:
        maximum = Path('/sys/fs/cgroup/memory.max').read_text().strip()
        if maximum != 'max':
            limits.append(max(0, int(maximum) - int(Path('/sys/fs/cgroup/memory.current').read_text())))
    except (OSError, ValueError):
        pass
    return min(limits) if limits else float('inf')


class FeatureCache:
    def __init__(self, max_bytes=0):
        self.max_bytes = max(0, int(max_bytes))
        self.entries = OrderedDict()
        self.bytes = 0
        self.hits = self.misses = 0
        self.pid = os.getpid()

    def clear(self):
        self.entries.clear()
        self.bytes = 0

    def read(self, path, loader, identity=None):
        if self.pid != os.getpid():
            self.clear()  # Forked workers must not retain a parent's cache.
            self.pid = os.getpid()
        source = Path(path)
        stat = source.stat()
        key = (str(source.resolve()), stat.st_size, stat.st_mtime_ns, stat.st_ctime_ns, identity)
        # Remove older versions of this source immediately.
        for old in [item for item in self.entries if item[0] == key[0] and item[-1] == identity and item != key]:
            _, size = self.entries.pop(old)
            self.bytes -= size
        if key in self.entries:
            self.hits += 1
            payload, _ = self.entries[key]
            self.entries.move_to_end(key)
            return tuple(value.clone() if value is not None else None for value in payload)
        self.misses += 1
        payload = loader(source)
        size = sum(value.numel() * value.element_size() for value in payload if value is not None)
        if available_memory() < 2 * size + 256 * 1024**2:
            self.clear()
            return payload
        if not self.max_bytes or size > self.max_bytes:
            return payload
        # Account for owned compact storage, not views retaining a larger tensor.
        while self.entries and self.bytes + size > self.max_bytes:
            _, (_, removed) = self.entries.popitem(last=False)
            self.bytes -= removed
        self.entries[key] = (tuple(value.clone() if value is not None else None for value in payload), size)
        self.bytes += size
        return payload


def decode_feature(path):
    if str(path).endswith('.h5'):
        with h5py.File(path, 'r') as handle:
            feat = torch.from_numpy(handle['features'][:])
            coords = torch.from_numpy(handle['coords'][:]) if 'coords' in handle else None
    else:
        loaded = torch.load(path, map_location='cpu', weights_only=False)
        if isinstance(loaded, dict):
            feat = loaded.get('feats', loaded.get('features'))
            coords = loaded.get('coords')
        else:
            feat, coords = loaded, None
        if isinstance(feat, np.ndarray):
            feat = torch.from_numpy(feat)
        if isinstance(coords, np.ndarray):
            coords = torch.from_numpy(coords)
    if not isinstance(feat, torch.Tensor) or (coords is not None and not isinstance(coords, torch.Tensor)):
        raise ValueError('Feature source must contain feature tensors and optional coordinate tensors')
    return feat, coords


_cache = FeatureCache()


def read_feature(path, max_bytes=None):
    """Cap is per training process; worker processes divide their allotted cap."""
    if max_bytes is None:
        max_bytes = max(0, int(os.environ.get('AUTO_MIL_FEATURE_CACHE_MB', '0'))) * 1024**2
    worker = get_worker_info()
    if worker:
        # Three independently owned loader pools (train/validation/test).
        max_bytes //= max(1, worker.num_workers * 3)
    if _cache.max_bytes != max_bytes:
        _cache.clear()
        _cache.max_bytes = max_bytes
    return _cache.read(path, decode_feature)
