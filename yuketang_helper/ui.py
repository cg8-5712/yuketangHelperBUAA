"""CLI prompts and the live video progress display."""

import threading

from rich.console import Group
from rich.live import Live
from rich.progress_bar import ProgressBar
from rich.table import Table
from rich.text import Text

from .logging import console


def choose(title, choices, default=0):
    """Return the zero-based index of a numbered choice."""
    if not choices:
        raise ValueError("choices cannot be empty")
    console.print(f"\n[bold]{title}[/bold]")
    for index, label in enumerate(choices, 1):
        console.print(f"  {index}. {label}", markup=False)
    while True:
        value = console.input(f"选择 [{default + 1}]: ").strip()
        if not value:
            return default
        if value.isdigit() and 1 <= int(value) <= len(choices):
            return int(value) - 1
        console.print("请输入列表中的编号。", style="yellow")


def ask_text(label, default=None):
    suffix = f" [{default}]" if default is not None else ""
    while True:
        value = console.input(f"{label}{suffix}: ").strip()
        if value:
            return value
        if default is not None:
            return default
        console.print("此项不能为空。", style="yellow")


class VideoDashboard:
    """One stable row per worker; workers only publish their own state."""

    def __init__(self, course_name, workers=4, on_update=None, live=True):
        self.course_name = course_name
        self._on_update = on_update
        self._lock = threading.Lock()
        self._rows = {
            f"Worker{i}": {
                "video": "-", "status": "待命", "progress": 0.0, "detail": ""
            }
            for i in range(1, workers + 1)
        }
        self._live = (
            Live(self, console=console, refresh_per_second=4, transient=False)
            if console.is_terminal and live else None
        )

    def __enter__(self):
        if self._live is not None:
            self._live.__enter__()
        return self

    def __exit__(self, exc_type, exc, tb):
        if self._live is not None:
            self._live.__exit__(exc_type, exc, tb)

    @property
    def is_live(self):
        return self._live is not None

    def update(self, video=None, status=None, progress=None, detail=None):
        worker = threading.current_thread().name
        with self._lock:
            row = self._rows.get(worker)
            if row is None:
                return
            if video is not None:
                row["video"] = str(video)
            if status is not None:
                row["status"] = status
            if progress is not None:
                row["progress"] = max(0.0, min(1.0, float(progress)))
            if detail is not None:
                row["detail"] = detail
        if self._live is not None:
            self._live.refresh()
        if self._on_update is not None:
            self._on_update(worker, row.copy())

    def __rich_console__(self, _console, _options):
        with self._lock:
            rows = [(name, row.copy()) for name, row in self._rows.items()]
        table = Table(expand=True, show_header=True, box=None, pad_edge=False)
        table.add_column("Worker", width=8, no_wrap=True)
        table.add_column("视频", ratio=3, overflow="ellipsis", no_wrap=True)
        table.add_column("进度", ratio=2, min_width=12)
        table.add_column("状态", ratio=2, overflow="ellipsis", no_wrap=True)
        for name, row in rows:
            bar = ProgressBar(total=100, completed=row["progress"] * 100)
            detail = row["detail"] or f"{row['progress']:.0%}"
            table.add_row(
                name,
                Text(row["video"], overflow="ellipsis"),
                bar,
                f"{row['status']} {detail}",
            )
        yield Group(Text(self.course_name, style="bold"), table)
