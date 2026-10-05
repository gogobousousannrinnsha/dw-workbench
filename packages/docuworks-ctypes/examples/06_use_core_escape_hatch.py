from __future__ import annotations

import argparse
from pathlib import Path

from docuworks_ctypes import AnnotationType
from docuworks_ctypes.simple import open_xdw

from _common import add_runtime_arguments, annotation_type_name, runtime_arguments


def main() -> None:
    parser = argparse.ArgumentParser(description="Read advanced data through the Core escape hatch.")
    parser.add_argument("input", type=Path)
    add_runtime_arguments(parser)
    args = parser.parse_args()

    with open_xdw(args.input, **runtime_arguments(args)) as document:
        for annotation in document.page(1).annotations(recursive=True):
            core = annotation.core
            details: dict[str, object] = {"custom_attributes": core.custom_attributes()}
            if annotation.type is AnnotationType.TEXT:
                details["text"] = core.get_standard_attribute("%Text")
            print(annotation_type_name(annotation.type), details)


if __name__ == "__main__":
    main()
