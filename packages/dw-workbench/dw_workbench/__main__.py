from pathlib import Path
import argparse
import json
import os
import sys
from .storage import FileLock
from . import __version__


def main():
    parser = argparse.ArgumentParser(description="DW-Workbench v" + __version__)
    parser.add_argument("--portable-root", type=Path)
    parser.add_argument("--project", type=Path)
    parser.add_argument("--diagnostics", action="store_true")
    args = parser.parse_args()
    portable = (args.portable_root or Path(sys.executable).parent.parent).resolve()
    for name in ("settings", "projects", "settings/temp", "settings/logs"):
        (portable/name).mkdir(parents=True, exist_ok=True)
    os.environ.update({"TEMP": str(portable/"settings/temp"), "TMP": str(portable/"settings/temp"), "PYTHONDONTWRITEBYTECODE": "1"})
    if args.diagnostics:
        from .workers import capabilities
        print(json.dumps(capabilities(portable), ensure_ascii=False, indent=2))
        return
    lock = FileLock(portable/"settings/.application.lock")
    try:
        import tkinter as tk
        from .ui import Window
        root = tk.Tk()
        window = Window(root, portable, args.project)
        root.mainloop()
    finally:
        lock.close()


if __name__ == "__main__":
    main()
