from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, ROUND_HALF_UP


def mm_to_xdw(value: float | int | Decimal) -> int:
    number = Decimal(str(value))
    if not number.is_finite():
        raise ValueError("coordinates must be finite")
    converted = number * 100
    return int(converted.quantize(Decimal("1"), rounding=ROUND_HALF_UP))


def position_to_xdw(value: float | int | Decimal) -> int:
    converted = mm_to_xdw(value)
    if not -240000 <= converted <= 240000:
        raise ValueError("position or vector must be between -2400 and 2400 mm")
    return converted


def xdw_to_mm(value: int) -> float:
    return value / 100.0


@dataclass(frozen=True)
class PointMM:
    x: float
    y: float


@dataclass(frozen=True)
class RawPoint:
    """XDW_POINT coordinate in the native 1/100 mm storage unit."""

    x: int
    y: int

    def to_mm(self) -> PointMM:
        return PointMM(xdw_to_mm(self.x), xdw_to_mm(self.y))


@dataclass(frozen=True)
class SizeMM:
    width: float
    height: float

    def __post_init__(self):
        if self.width <= 0 or self.height <= 0:
            raise ValueError("幅と高さは0より大きい必要があります")


@dataclass(frozen=True)
class RectMM:
    x: float
    y: float
    width: float
    height: float

    def __post_init__(self):
        if self.width <= 0 or self.height <= 0:
            raise ValueError("幅と高さは0より大きい必要があります")
