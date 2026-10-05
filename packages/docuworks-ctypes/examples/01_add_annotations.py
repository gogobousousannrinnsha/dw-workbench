from __future__ import annotations

import argparse
from pathlib import Path

from docuworks_ctypes import (
    ArrowheadStyle,
    ArrowheadType,
    BorderType,
    Color,
    LinkType,
    PointMM,
)
from docuworks_ctypes.simple import open_xdw

from _common import add_runtime_arguments, prepare_output, runtime_arguments


def main() -> None:
    parser = argparse.ArgumentParser(description="Add all eight Simple annotation types.")
    parser.add_argument("input", type=Path)
    parser.add_argument("output", type=Path)
    add_runtime_arguments(parser)
    args = parser.parse_args()
    output = prepare_output(args.input, args.output)

    with open_xdw(output, writable=True, **runtime_arguments(args)) as document:
        page = document.page(1)
        page.text("Simple API", x=15, y=15, font_size=12, fore_color=Color.BLUE)
        page.rectangle(
            x=15, y=35, width=30, height=18,
            border_color=Color.RED, fill_color=Color.YELLOW,
        )
        page.sticky(
            x=55, y=35, width=30, height=25,
            fill_color=Color.STICKY_YELLOW, text="付箋",
        )
        page.ellipse(
            x=95, y=35, width=30, height=18,
            border_color=Color.RED, fill_color=Color.YELLOW,
        )
        page.line(
            x1=15, y1=75, x2=50, y2=90,
            border_color=Color.BLUE, border_type=BorderType.DASH,
            arrowhead_type=ArrowheadType.ENDING,
            arrowhead_style=ArrowheadStyle.POLYGON,
        )
        page.polygon(
            (PointMM(60, 75), PointMM(90, 75), PointMM(80, 95)),
            border_color=Color.BLUE, fill_color=Color.YELLOW,
        )
        page.marker(
            (PointMM(105, 75), PointMM(125, 82), PointMM(140, 90)),
            border_color=Color.GREEN,
        )
        page.link(
            "This document", x=15, y=110,
            link_type=LinkType.THIS_DOCUMENT, fore_color=Color.BLUE,
        )
        document.save()
    print(f"Saved: {output}")


if __name__ == "__main__":
    main()
