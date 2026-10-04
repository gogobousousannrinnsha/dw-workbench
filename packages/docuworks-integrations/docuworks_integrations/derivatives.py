"""Consumers of verified OCR bundles; backend imports are operation-local."""
from pathlib import Path
import math
import os
import shutil

from .results import load_ocr_result, bundle_path, sha256, write_json
from . import __version__
from ._storage import owned_directory, publish_new, cleanup_owned

COLORS = {'red': 0x0000ff, 'blue': 0xff0000, 'green': 0x008000,
          'black': 0, 'yellow': 0x00ffff, 'purple': 0x800080, 'teal': 0x808000}


class IntegrityError(RuntimeError):
    """A verified input changed while producing an artifact."""


def outside_bundle(result, output):
    output = Path(output).expanduser().resolve()
    if output.is_relative_to(result.root) or result.root.is_relative_to(output):
        raise ValueError('output must be outside the OCR bundle')
    if output.exists():
        raise FileExistsError(output)
    if not output.parent.is_dir():
        raise FileNotFoundError(output.parent)
    return output


def recheck(result):
    current = load_ocr_result(result.root)
    if current.manifest_sha256 != result.manifest_sha256:
        raise IntegrityError('OCR manifest changed during consumer execution')


def reference(result):
    return dict(run_id=result.run_id, manifest_sha256=result.manifest_sha256,
                integration_version=__version__)


def rectangle_settings(padding_mm, min_confidence, color, minimum_mm=3.0):
    for name, value in (('padding_mm', padding_mm), ('min_confidence', min_confidence),
                        ('minimum_mm', minimum_mm)):
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
            raise ValueError(f'{name} must be finite')
    if padding_mm < 0 or not 0 <= min_confidence <= 1 or minimum_mm < 3:
        raise ValueError('padding >= 0, confidence in [0,1], minimum >= 3 mm required')
    if color not in COLORS:
        raise ValueError('unsupported rectangle color')
    return dict(padding_mm=padding_mm, min_confidence=min_confidence, color=color,
                minimum_mm=minimum_mm, border_width_pt=1, fill_visible=False)


def fit_interval(start, length, limit, padding, minimum=3.0):
    if limit < minimum:
        raise ValueError('page is smaller than the minimum rectangle size')
    low, high = max(0., start-padding), min(limit, start+length+padding)
    if high-low < minimum:
        low = max(0., min(start+length/2-minimum/2, limit-minimum))
        high = low+minimum
    return low, high-low


def rectangle_plan(result, *, padding_mm=.5, min_confidence=0., color='red', minimum_mm=3.):
    settings = rectangle_settings(padding_mm, min_confidence, color, minimum_mm)
    regions = []
    for page in result.pages:
        for region in page.regions:
            if (region.confidence is None and min_confidence > 0) or (
                    region.confidence is not None and region.confidence < min_confidence):
                continue
            b = region.bbox_mm
            x, w = fit_interval(b['x'], b['width'], page.page_width_mm, padding_mm, minimum_mm)
            y, h = fit_interval(b['y'], b['height'], page.page_height_mm, padding_mm, minimum_mm)
            regions.append(dict(page=page.page, region_id=region.id,
                ocr_bbox_mm=dict(b), rectangle_mm=dict(x=x,y=y,width=w,height=h)))
    return dict(**reference(result), settings=settings, regions=regions)


def _snapshot(annotation):
    p, s = annotation.position, annotation.size
    return (int(annotation.type), p.x, p.y, None if s is None else (s.width, s.height))


def _verify_rectangle(annotation, item, color):
    from docuworks_ctypes import AnnotationType
    if annotation.type != AnnotationType.RECTANGLE:
        raise RuntimeError('save/reopen rectangle type mismatch')
    actual = dict(x=annotation.position.x, y=annotation.position.y,
                  width=annotation.size.width, height=annotation.size.height)
    error = max(abs(actual[k]-v) for k,v in item['rectangle_mm'].items())
    if error > .010001:
        raise RuntimeError(f'save/reopen rectangle geometry mismatch: {error} mm')
    for name, value in (('%BorderColor', COLORS[color]), ('%BorderWidth', 1),
                        ('%BorderStyle', True), ('%FillStyle', False)):
        if annotation.core.get_standard_attribute(name) != value:
            raise RuntimeError(f'save/reopen rectangle {name} mismatch')
    return error


def annotate_rectangles(run_dir, output_xdw, *, input_xdw=None, dry_run=False,
                        dll_path=None, padding_mm=.5, min_confidence=0., color='red',
                        minimum_mm=3., report_path=None):
    """Create and reopen-verify a separate XDW. Never runs OCR or alters a bundle."""
    result = load_ocr_result(run_dir)
    plan = rectangle_plan(result, padding_mm=padding_mm, min_confidence=min_confidence,
                          color=color, minimum_mm=minimum_mm)
    output = outside_bundle(result, output_xdw)
    report = outside_bundle(result, report_path or output.with_suffix('.rectangles.json'))
    if report == output:
        raise ValueError('report and XDW output must differ')
    source = Path(input_xdw).resolve() if input_xdw else bundle_path(result.root, result.source['path'])
    if source in (output, report) or sha256(source) != result.source['sha256']:
        raise IntegrityError('source does not match the recorded hash')
    payload = dict(**plan, status='DRY_RUN', output_xdw=output.name,
                   source_sha256=result.source['sha256'], viewer_status='NOT_CHECKED')
    if dry_run:
        return payload
    from docuworks_ctypes import Color
    from docuworks_ctypes.simple import SimplePage, open_xdw
    from ._rectangle_sdk import _RectangleAppendPage
    with owned_directory(output.parent, '.rectangles-') as temporary:
        working = temporary/'working.xdw'
        shutil.copyfile(source, working)
        if sha256(working) != result.source['sha256']:
            raise IntegrityError('source changed while copying')
        before, expected = {}, {}
        with open_xdw(working, writable=True, dll_path=dll_path) as document:
            count = document.core.page_count
            if result.source.get('page_count') not in (None, count):
                raise IntegrityError('source page count mismatch')
            for n in range(1, count+1):
                page = document.page(n)
                before[n] = [_snapshot(a) for a in page.annotations()]
                expected[n] = [i for i in plan['regions'] if i['page'] == n]
                if expected[n]:
                    page = SimplePage(_RectangleAppendPage(page.core, len(before[n])))
                for item in expected[n]:
                    page.rectangle(**item['rectangle_mm'], border_color=Color(COLORS[color]),
                        border_width=1, border_visible=True, fill_visible=False)
            document.save()
        max_error = 0.
        with open_xdw(working, writable=False, dll_path=dll_path) as document:
            if document.core.page_count != count:
                raise RuntimeError('save/reopen page count mismatch')
            for n in range(1, count+1):
                annotations = document.page(n).annotations()
                if len(annotations) != len(before[n])+len(expected[n]):
                    raise RuntimeError('save/reopen annotation count mismatch')
                if [_snapshot(a) for a in annotations[:len(before[n])]] != before[n]:
                    raise RuntimeError('existing annotation geometry changed')
                for a, item in zip(annotations[len(before[n]):], expected[n]):
                    max_error = max(max_error, _verify_rectangle(a, item, color))
        recheck(result)
        if sha256(source) != result.source['sha256']:
            raise IntegrityError('source changed during annotation')
        payload.update(status='VERIFIED', output_sha256=sha256(working),
            max_geometry_error_mm=max_error, annotations_before={str(k):len(v) for k,v in before.items()})
        write_json(temporary/'report.json', payload)
        # Windows rename is atomic and refuses an existing destination.
        if output.exists() or report.exists(): raise FileExistsError('output appeared during verification')
        publish_new(working, output)
        try:
            with report.open('x', encoding='utf-8') as stream:
                stream.write((temporary/'report.json').read_text(encoding='utf-8'))
        except BaseException as exc:
            cleanup_owned(output, primary=exc)
            raise
        return payload


def resolve_font(font=None):
    from PIL import ImageFont
    fonts = [Path(font)] if font else [Path(os.environ.get('WINDIR', 'C:/Windows'))/'Fonts'/n
        for n in ('YuGothM.ttc', 'meiryo.ttc', 'msgothic.ttc', 'BIZ-UDGothicR.ttc')]
    for candidate in fonts:
        if candidate.is_file():
            f = ImageFont.truetype(str(candidate), 16)
            if bytes(f.getmask('漢')) == bytes(f.getmask('字')):
                raise ValueError('Selected font does not contain Japanese glyphs')
            return candidate.resolve()
    raise FileNotFoundError('Japanese font not found; set font in settings.ini or --font')


def render_text_maps(run_dir, output_dir, *, font=None, min_confidence=0., page=None,
                     draw_boxes=True):
    """Pillow-only review images, retaining the original image dimensions."""
    from PIL import Image, ImageDraw, ImageFont
    result = load_ocr_result(run_dir)
    output = outside_bundle(result, output_dir)
    rectangle_settings(0., min_confidence, 'red')
    pages = [p for p in result.pages if page is None or p.page == page]
    if not pages:
        raise ValueError('page is not present in the saved result')
    font_path = resolve_font(font)
    payload = dict(**reference(result), status='VERIFIED', font=font_path.name,
                   settings=dict(min_confidence=min_confidence, draw_boxes=draw_boxes), pages=[])
    with owned_directory(output.parent, '.text-maps-') as temporary:
        for p in pages:
            with Image.open(bundle_path(result.root, p.image)) as image:
                overlay = image.convert('RGB')
            if overlay.size != (p.image_width_px,p.image_height_px):
                raise IntegrityError('image dimensions differ from result')
            canvas = Image.new('RGB', overlay.size, 'white')
            selected = []
            for r in p.regions:
                if (r.confidence is None and min_confidence > 0) or (
                        r.confidence is not None and r.confidence < min_confidence):
                    continue
                b = r.bbox_px
                x,y = int(b['x']), int(b['y'])
                w = max(1, min(overlay.width-x, math.ceil(b['width'])))
                h = max(1, min(overlay.height-y, math.ceil(b['height'])))
                text = r.text.replace('\r\n','\n').replace('\r','\n')
                f = ImageFont.truetype(str(font_path), max(8,min(h,96)))
                bbox = f.getbbox(text)
                patch = Image.new('RGB',(max(1,bbox[2]-bbox[0]+2),max(1,bbox[3]-bbox[1]+2)), 'white')
                ImageDraw.Draw(patch).text((1-bbox[0],1-bbox[1]),text,font=f,fill='black')
                patch.thumbnail((w,h), Image.Resampling.LANCZOS)
                canvas.paste(patch,(x,y)); overlay.paste(patch,(x,y))
                box = (x,y,x+w-1,y+h-1)
                if draw_boxes: ImageDraw.Draw(canvas).rectangle(box,outline='#b0b0b0',width=1)
                ImageDraw.Draw(overlay).rectangle(box,outline='red',width=2)
                selected.append(r.id)
            folder = temporary/f'page-{p.page:04d}'; folder.mkdir()
            canvas.save(folder/'text-map.png'); overlay.save(folder/'overlay-text.png')
            payload['pages'].append(dict(page=p.page, region_ids=selected,
                width_px=overlay.width,height_px=overlay.height,
                files={n:sha256(folder/n) for n in ('text-map.png','overlay-text.png')}))
        recheck(result)
        write_json(temporary/'text-maps-report.json',payload)
        publish_new(temporary, output)
        return payload
