"""Host-side loop timings; never synchronize CUDA or change sampling order."""
import json
import time


def timed_batches(loader, phase):
    started = time.perf_counter()
    iterator = iter(loader)
    loading = time.perf_counter()-started
    batches = 0
    completed = False
    try:
        while True:
            before = time.perf_counter()
            try:
                batch = next(iterator)
            except StopIteration:
                loading += time.perf_counter()-before
                completed = True
                break
            loading += time.perf_counter()-before
            batches += 1
            yield batch
    finally:
        elapsed = time.perf_counter()-started
        print('LOOP_TIMING ' + json.dumps({'phase':phase,'batches':batches,'completed':completed,
              'wall_seconds':round(elapsed,3),'data_wait_seconds':round(loading,3),
              'step_host_seconds':round(max(0,elapsed-loading),3),
              'note':'host wall time; not isolated CUDA kernel time'},ensure_ascii=False),flush=True)
