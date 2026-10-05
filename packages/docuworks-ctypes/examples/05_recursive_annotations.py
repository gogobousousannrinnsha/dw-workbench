from __future__ import annotations

import argparse
from pathlib import Path

from docuworks_ctypes.simple import open_xdw

from _common import add_runtime_arguments, annotation_type_name, runtime_arguments


def main() -> None:
    parser = argparse.ArgumentParser(description="Compare top-level and preorder snapshots.")
    parser.add_argument("input", type=Path)
    add_runtime_arguments(parser)
    args = parser.parse_args()

    with open_xdw(args.input, **runtime_arguments(args)) as document:
        page = document.page(1)
        top_level = page.annotations()
        recursive = page.annotations(recursive=True)
        print("top-level:", [annotation_type_name(item.type) for item in top_level])
        print("preorder:", [annotation_type_name(item.type) for item in recursive])


if __name__ == "__main__":
    main()
