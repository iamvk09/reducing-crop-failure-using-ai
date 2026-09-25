"""Lightweight memory diagnostics utility for monitoring process RSS memory.

Works seamlessly across Linux, Render (containerized), macOS, and Windows.
Uses psutil when available with zero-dependency fallbacks.
"""

import sys


def get_process_memory_mb() -> float:
    """Retrieve the current process Resident Set Size (RSS) in megabytes."""
    # 1. Try psutil (fastest and cross-platform)
    try:
        import psutil
        return round(psutil.Process().memory_info().rss / (1024.0 * 1024.0), 2)
    except Exception:
        pass

    # 2. Try Linux / Render container /proc filesystem
    try:
        with open("/proc/self/status", "r") as f:
            for line in f:
                if line.startswith("VmRSS:"):
                    return round(float(line.split()[1]) / 1024.0, 2)
    except Exception:
        pass

    # 3. Fallback to resource module (Unix/Linux/macOS)
    try:
        import resource
        return round(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024.0, 2)
    except Exception:
        pass

    return 0.0


def log_memory(stage: str, extra_info: str = "") -> float:
    """Log current process RSS memory with stage name to standard output."""
    mem_mb = get_process_memory_mb()
    suffix = f" ({extra_info})" if extra_info else ""
    if mem_mb > 0:
        print(f"[MEMORY DIAGNOSTIC] {stage:<38s} | RSS: {mem_mb:6.1f} MB{suffix}", flush=True)
    return mem_mb
