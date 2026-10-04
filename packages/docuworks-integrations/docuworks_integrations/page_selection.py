"""Page selection independent of OCR and DocuWorks."""
import re
from .results import positive_int


def parse_pages(text):
    if not isinstance(text, str) or not text.strip():
        raise ValueError('page selection must not be empty')
    selected = set()
    for term in text.split(','):
        match = re.fullmatch(r'\s*([1-9][0-9]*)(?:\s*-\s*([1-9][0-9]*))?\s*', term)
        if not match: raise ValueError('expected page numbers or ascending ranges, e.g. 1,3-5')
        start = int(match[1]); end = int(match[2] or match[1])
        if start > end: raise ValueError('page range must be ascending')
        # Avoid unbounded expansion before the document can be opened.
        if end > 100000: raise ValueError('page number exceeds selection limit (100000)')
        selected.update(range(start, end + 1))
    return tuple(sorted(selected))


def resolve_pages(pages, page_count):
    positive_int(page_count)
    if pages is None: return tuple(range(1, page_count + 1))
    if isinstance(pages, (str, bytes)): raise ValueError('Python pages must be an integer sequence')
    selected = tuple(sorted(set(positive_int(p) for p in pages)))
    if not selected: raise ValueError('page selection must not be empty')
    if selected[-1] > page_count: raise ValueError('page outside document')
    return selected
