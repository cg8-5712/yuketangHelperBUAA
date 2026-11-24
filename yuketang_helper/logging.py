import math
import threading
import time
from rich.console import Console


_output_lock = threading.Lock()
console = Console()
DEBUG = False


def debug(*values):
    if DEBUG:
        log(*values, level="Debug")


def log(*values, level="Info"):
    worker = threading.current_thread().name
    if worker == "MainThread":
        worker = "Main"
    message = " ".join(str(value) for value in values).replace("\n", "\\n")
    with _output_lock:
        console.print(f"| {worker} | {level} | {message}", markup=False)


def wait_for_platform(seconds, stop_event=None, on_tick=None):
    deadline = time.monotonic() + max(0, seconds)
    while True:
        remaining = max(0, deadline - time.monotonic())
        if on_tick is not None:
            on_tick(remaining, seconds)
        if remaining <= 0:
            return True
        if on_tick is None:
            log(f"由于平台限制，需等待 {math.ceil(remaining)} s")
        interval = min(1, remaining)
        if stop_event is None:
            time.sleep(interval)
        elif stop_event.wait(interval):
            return False
