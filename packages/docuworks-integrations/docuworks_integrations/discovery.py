"""Deterministic XDW discovery shared by folder OCR and the Portable workflow."""
import os
from pathlib import Path
import stat


def linked(path):
    info = path.lstat()
    return stat.S_ISLNK(info.st_mode) or bool(getattr(info, 'st_file_attributes', 0) & 0x400)


def check_source(source, root):
    for path in (source, *source.parents):
        if linked(path):
            raise PermissionError('Source path became a link or reparse point')
        if path == root: break
    if not source.is_file(): raise FileNotFoundError(source)


def sources(root, recursive, excluded=(), *, link_check=linked):
    excluded = tuple(Path(p).resolve() for p in excluded)
    found = []
    def visit(folder):
        with os.scandir(folder) as entries:
            for entry in entries:
                path = Path(entry.path)
                if link_check(path) or any(path.resolve().is_relative_to(p) for p in excluded):
                    continue
                if entry.is_dir(follow_symlinks=False):
                    if recursive: visit(path)
                elif entry.is_file(follow_symlinks=False) and path.suffix.lower() == '.xdw':
                    found.append(path)
    visit(root)
    return sorted(found, key=lambda p: (p.relative_to(root).as_posix().casefold(), p.relative_to(root).as_posix()))


def collect_documents(inputs, *, recursive=False, excluded=()):
    found = {}
    excluded = tuple(Path(p).resolve() for p in excluded)
    for target in inputs:
        target = Path(target).expanduser().absolute()
        if any(linked(p) for p in (target, *target.parents)):
            continue
        target = target.resolve()
        if any(target.is_relative_to(p) for p in excluded): continue
        if target.is_dir(): candidates = sources(target, recursive, excluded)
        elif target.is_file() and target.suffix.lower() == '.xdw': candidates = [target]
        else: raise ValueError(f'Expected an XDW file or directory: {target}')
        for p in candidates:
            # samefile also removes hard links to an already included file.
            if not any(p.samefile(other) for other in found.values()):
                found[str(p).casefold()] = p
    return sorted(found.values(), key=lambda p: (str(p).casefold(), str(p)))
