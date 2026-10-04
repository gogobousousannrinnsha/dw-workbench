"""Strict, portable configuration with no optional runtime dependencies."""
from configparser import ConfigParser
from dataclasses import dataclass, asdict
from pathlib import Path
from .derivatives import rectangle_settings


@dataclass(frozen=True)
class Settings:
    recursive: bool = False
    dpi: int = 300
    min_confidence: float = 0.
    padding_mm: float = .5
    minimum_mm: float = 3.
    color: str = 'red'
    font: str = ''
    jsonl: bool = False

    def __post_init__(self):
        if type(self.recursive) is not bool or type(self.jsonl) is not bool:
            raise ValueError('recursive and jsonl must be boolean')
        if type(self.dpi) is not int or self.dpi not in (300, 600):
            raise ValueError('dpi must be 300 or 600')
        rectangle_settings(self.padding_mm, self.min_confidence, self.color, self.minimum_mm)
        if not isinstance(self.font, str): raise ValueError('font must be a path string')

    def to_dict(self): return asdict(self)


def load_settings(path):
    parser = ConfigParser(interpolation=None, strict=True)
    with Path(path).open(encoding='utf-8-sig') as stream: parser.read_file(stream)
    if parser.defaults() or parser.sections() != ['ocr']:
        raise ValueError('settings.ini requires exactly [ocr], without DEFAULT values')
    unknown = set(parser['ocr']) - set(Settings.__dataclass_fields__)
    if unknown: raise ValueError(f'Unknown settings: {sorted(unknown)}')
    values = dict(parser['ocr'])
    for key in ('recursive','jsonl'):
        if key in values: values[key] = parser.getboolean('ocr',key)
    if 'dpi' in values: values['dpi'] = parser.getint('ocr','dpi')
    for key in ('min_confidence','padding_mm','minimum_mm'):
        if key in values: values[key] = parser.getfloat('ocr',key)
    return Settings(**values)
