"""Scoped Windows native path encoding for Paddle's narrow file API.

Only the synchronous initialization of the two local PP-OCR models is adapted.
Installed Paddle/PaddleX files and dependency metadata are never changed.
"""
from contextlib import contextmanager
import os
from pathlib import Path
from threading import RLock

_lock = RLock()


def _encode_native_path(path):
    """Encode a filename using the Windows process's active ANSI code page."""
    return str(path).encode('mbcs')


@contextmanager
def local_model_paths(inference, model_root):
    root = Path(model_root).resolve()
    if os.name != 'nt' or str(root).isascii():
        yield
        return
    allowed = {root/name/'inference.json':root/name/'inference.pdiparams'
               for name in ('PP-OCRv6_medium_det','PP-OCRv6_medium_rec')}
    with _lock:
        original = inference.Config
        def config(*args, **kwargs):
            if len(args)==2 and not kwargs:
                model, params = (Path(a).resolve() for a in args)
                if allowed.get(model)==params:
                    # pybind's std::string accepts bytes. The Windows C++ file API
                    # expects the active ANSI code page, unlike Python's UTF-8 str binding.
                    try:
                        model_bytes = _encode_native_path(model)
                        params_bytes = _encode_native_path(params)
                    except UnicodeEncodeError as exc:
                        raise ValueError('Model path cannot be represented by the Windows code page; use a shorter ASCII installation path') from exc
                    return original(model_bytes, params_bytes)
            return original(*args,**kwargs)
        inference.Config=config
        try: yield
        finally: inference.Config=original
