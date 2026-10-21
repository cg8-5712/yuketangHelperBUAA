"""Compatibility launcher for the old standalone homework script."""

from pathlib import Path
import runpy


if __name__ == "__main__":
    runpy.run_path(
        str(Path(__file__).resolve().parent / "tools" / "legacy" / "homework_Helpers.py"),
        run_name="__main__",
    )
