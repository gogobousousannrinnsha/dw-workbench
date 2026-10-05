from __future__ import annotations

import argparse
import inspect
import json
from enum import IntEnum
from pathlib import Path
from typing import Any

import docuworks_ctypes
import docuworks_ctypes.simple as simple


def _annotation(value: Any) -> str | None:
    if value is inspect.Signature.empty:
        return None
    if isinstance(value, str):
        return value
    return inspect.formatannotation(value)


def _default(value: Any) -> object:
    if value is inspect.Signature.empty:
        return {"required": True}
    if isinstance(value, IntEnum):
        return {"enum": type(value).__name__, "name": value.name, "value": int(value)}
    if value is None or isinstance(value, (bool, int, float, str)):
        return value
    return repr(value)


def _signature(callable_object: Any) -> dict[str, object]:
    signature = inspect.signature(callable_object)
    return {
        "parameters": [
            {
                "name": parameter.name,
                "kind": parameter.kind.name,
                "default": _default(parameter.default),
                "annotation": _annotation(parameter.annotation),
            }
            for parameter in signature.parameters.values()
        ],
        "return": _annotation(signature.return_annotation),
    }


def public_api_snapshot() -> dict[str, object]:
    callables = {
        "open_xdw": simple.open_xdw,
        "SimpleDocument.__init__": simple.SimpleDocument.__init__,
        "SimpleDocument.page": simple.SimpleDocument.page,
        "SimpleDocument.save": simple.SimpleDocument.save,
        "SimpleDocument.close": simple.SimpleDocument.close,
        "SimplePage.__init__": simple.SimplePage.__init__,
        "SimplePage.annotations": simple.SimplePage.annotations,
        "SimplePage.text": simple.SimplePage.text,
        "SimplePage.rectangle": simple.SimplePage.rectangle,
        "SimplePage.sticky": simple.SimplePage.sticky,
        "SimplePage.ellipse": simple.SimplePage.ellipse,
        "SimplePage.line": simple.SimplePage.line,
        "SimplePage.polygon": simple.SimplePage.polygon,
        "SimplePage.marker": simple.SimplePage.marker,
        "SimplePage.link": simple.SimplePage.link,
        "SimpleAnnotation.__init__": simple.SimpleAnnotation.__init__,
        "SimpleAnnotation.type": simple.SimpleAnnotation.type.fget,
        "SimpleAnnotation.position": simple.SimpleAnnotation.position.fget,
        "SimpleAnnotation.size": simple.SimpleAnnotation.size.fget,
        "SimpleAnnotation.core": simple.SimpleAnnotation.core.fget,
        "SimpleAnnotation.move_to": simple.SimpleAnnotation.move_to,
        "SimpleAnnotation.resize": simple.SimpleAnnotation.resize,
        "SimpleAnnotation.delete": simple.SimpleAnnotation.delete,
    }
    enum_types = {}
    for name in docuworks_ctypes.__all__:
        value = getattr(docuworks_ctypes, name)
        if inspect.isclass(value) and issubclass(value, IntEnum):
            enum_types[name] = {member.name: int(member) for member in value}
    return {
        "schema_version": 1,
        "release": "1.0.0",
        "top_level_exports": list(docuworks_ctypes.__all__),
        "simple_exports": list(simple.__all__),
        "simple_signatures": {
            name: _signature(value) for name, value in sorted(callables.items())
        },
        "enums": dict(sorted(enum_types.items())),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate the frozen 1.0 public API snapshot.")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    args.output.write_text(
        json.dumps(public_api_snapshot(), ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
