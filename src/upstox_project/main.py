"""Facade for the legacy main.py entry point."""
from pathlib import Path
import runpy
if __name__ == "__main__":
    runpy.run_path(str(Path(__file__).resolve().parents[2] / "main.py"), run_name="__main__")
