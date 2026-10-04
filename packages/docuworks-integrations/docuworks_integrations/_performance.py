"""Opt-in observations for the local A/B kit; no changes to result contracts."""
from contextlib import contextmanager
from contextvars import ContextVar
import csv
import ctypes
import json
import os
from pathlib import Path
import threading
import time

_current = ContextVar('dw_ocr_performance', default=None)
_tags = ContextVar('dw_ocr_performance_tags', default={})


def _memory_reader():
    if os.name != 'nt':
        return lambda: None
    class Counters(ctypes.Structure):
        _fields_ = [('cb', ctypes.c_ulong), ('PageFaultCount', ctypes.c_ulong)] + [
            (name, ctypes.c_size_t) for name in ('PeakWorkingSetSize', 'WorkingSetSize',
            'QuotaPeakPagedPoolUsage', 'QuotaPagedPoolUsage', 'QuotaPeakNonPagedPoolUsage',
            'QuotaNonPagedPoolUsage', 'PagefileUsage', 'PeakPagefileUsage', 'PrivateUsage')]
    function = ctypes.WinDLL('psapi', use_last_error=True).GetProcessMemoryInfo
    function.argtypes = [ctypes.c_void_p, ctypes.POINTER(Counters), ctypes.c_ulong]
    function.restype = ctypes.c_int
    def read():
        data = Counters(); data.cb = ctypes.sizeof(data)
        if not function(ctypes.c_void_p(-1), ctypes.byref(data), data.cb):
            return None
        return data.WorkingSetSize
    return read


class Recorder:
    """Wall times include nested phases. RSS is current-process, sampled at 250 ms."""
    def __init__(self, **metadata):
        self.metadata = metadata
        self.events = []
        self.active = []
        self.lock = threading.RLock()
        self.stop = threading.Event()
        self.read_memory = _memory_reader()
        self.peak = None

    def sample(self):
        rss = self.read_memory()
        if rss is not None:
            with self.lock:
                self.peak = max(self.peak or 0, rss)
                for event in self.active:
                    event['rss_sampled_peak_bytes'] = max(event.get('rss_sampled_peak_bytes') or 0, rss)
        return rss

    def _sample_loop(self):
        while not self.stop.wait(.25):
            self.sample()

    def __enter__(self):
        self.started = time.perf_counter()
        self.token = _current.set(self)
        self.thread = threading.Thread(target=self._sample_loop, daemon=True)
        self.thread.start()
        self.sample()
        return self

    def __exit__(self, *_):
        self.sample()
        self.stop.set(); self.thread.join(timeout=2)
        self.elapsed = time.perf_counter() - self.started
        _current.reset(self.token)

    def write(self, directory, **summary):
        directory = Path(directory); directory.mkdir(parents=True, exist_ok=True)
        data = dict(schema='dw-ocr-ab-performance', schema_version='1.0',
                    **self.metadata, **summary, elapsed_seconds=self.elapsed,
                    memory=dict(kind='current_process_working_set', sample_interval_seconds=.25,
                                sampled_peak_bytes=self.peak, includes_gpu_memory=False),
                    events=self.events)
        target = directory / 'performance.json'
        temporary = directory / 'performance.json.tmp'
        temporary.write_text(json.dumps(data, ensure_ascii=False, indent=2, allow_nan=False)+'\n', encoding='utf-8')
        os.replace(temporary, target)
        with (directory/'performance.csv').open('w', encoding='utf-8-sig', newline='') as stream:
            fields = ('phase', 'document_id', 'page', 'item_count', 'seconds',
                      'rss_sampled_peak_bytes', 'status', 'error')
            writer = csv.DictWriter(stream, fieldnames=fields, extrasaction='ignore')
            writer.writeheader(); writer.writerows(self.events)
        return target


@contextmanager
def measure(phase, **tags):
    recorder = _current.get()
    if recorder is None:
        yield
        return
    combined = dict(_tags.get(), **tags)
    token = _tags.set(combined)
    event = dict(phase=phase, **combined, status='RUNNING', rss_sampled_peak_bytes=None)
    started = time.perf_counter()
    with recorder.lock:
        recorder.events.append(event); recorder.active.append(event)
    recorder.sample()
    try:
        yield
        event['status'] = 'SUCCEEDED'
    except BaseException as error:
        event.update(status='FAILED', error=f'{type(error).__name__}: {error}')
        if hasattr(error, 'add_note'):
            error.add_note(f'Performance phase: {phase}; context: {combined}')
        raise
    finally:
        recorder.sample()
        event['seconds'] = time.perf_counter() - started
        with recorder.lock:
            recorder.active.remove(event)
        _tags.reset(token)
