"""Per-stage cost logging: wall time, peak RAM, GPU memory, LLM calls and tokens, paid credits."""
import importlib.util
import statistics
import threading
import time
from contextlib import contextmanager

import psutil


class PeakMemorySampler:
    """Samples this process's RAM in a background thread and keeps the highest value."""

    def __init__(self, interval_seconds=0.05):
        self.process = psutil.Process()
        self.interval_seconds = interval_seconds
        self.peak_bytes = self.process.memory_info().rss
        self.stop_event = threading.Event()
        self.thread = threading.Thread(target=self.sample, daemon=True)

    def sample(self):
        while not self.stop_event.wait(self.interval_seconds):
            self.peak_bytes = max(self.peak_bytes, self.process.memory_info().rss)

    def __enter__(self):
        self.thread.start()
        return self

    def __exit__(self, *exc_info):
        self.stop_event.set()
        self.thread.join()
        self.peak_bytes = max(self.peak_bytes, self.process.memory_info().rss)


def cuda_torch():
    """Returns torch when a CUDA GPU is usable, else None (laptop: torch not installed)."""
    if importlib.util.find_spec("torch") is None:
        return None
    import torch
    return torch if torch.cuda.is_available() else None


class CostLogger:
    def __init__(self):
        self.stages = []
        self.current = None
        self.torch = cuda_torch()

    @contextmanager
    def stage(self, name):
        record = {"stage": name, "status": "failed", "llm_calls": 0, "input_tokens": 0, "output_tokens": 0, "paid_credits": 0.0}
        self.current = record
        if self.torch:
            self.torch.cuda.reset_peak_memory_stats()
        start = time.perf_counter()
        sampler = PeakMemorySampler()
        try:
            with sampler:
                yield record
            record["status"] = "ok"
        finally:
            record["wall_seconds"] = round(time.perf_counter() - start, 3)
            record["peak_ram_mb"] = round(sampler.peak_bytes / 2**20, 1)
            record["gpu_name"] = self.torch.cuda.get_device_name() if self.torch else "none"
            record["gpu_peak_mb"] = round(self.torch.cuda.max_memory_allocated() / 2**20, 1) if self.torch else 0.0
            self.stages.append(record)
            self.current = None

    def active_stage(self):
        if self.current is None:
            raise RuntimeError("LLM calls and credits must be recorded inside a stage")
        return self.current

    def record_llm_call(self, input_tokens, output_tokens):
        stage = self.active_stage()
        stage["llm_calls"] += 1
        stage["input_tokens"] += input_tokens
        stage["output_tokens"] += output_tokens

    def add_credits(self, credits):
        self.active_stage()["paid_credits"] += credits

    def summary(self):
        summed_fields = ("wall_seconds", "llm_calls", "input_tokens", "output_tokens", "paid_credits")
        totals = {field: round(sum(stage[field] for stage in self.stages), 3) for field in summed_fields}
        totals["peak_ram_mb"] = max((stage["peak_ram_mb"] for stage in self.stages), default=0.0)
        totals["gpu_peak_mb"] = max((stage["gpu_peak_mb"] for stage in self.stages), default=0.0)
        return {"stages": self.stages, "totals": totals}


def timed_call(function):
    start = time.perf_counter()
    function()
    return time.perf_counter() - start


def median_wall_seconds(function, timed_runs=3, warmup_runs=1):
    """Spec timing rule for final cost numbers: discard warm-up run(s), report the median of the timed runs."""
    durations = [timed_call(function) for run_index in range(warmup_runs + timed_runs)]
    return round(statistics.median(durations[warmup_runs:]), 3)