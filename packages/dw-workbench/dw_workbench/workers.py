"""Persistent local subprocesses, JSON protocol. Workers never open project SQLite."""
from pathlib import Path
import ctypes
import json
import os
import subprocess
import sys
import threading
import time
import traceback
from contextlib import redirect_stdout
from .domain import Anchor, PageInfo, RuleError, crop_box, pixel_to_mm, identifier
from .storage import digest, fingerprint


def native(request):
    from docuworks_ctypes import XdwApi
    from docuworks_ctypes._raw import types as T, constants as C
    from docuworks_ctypes.encoding import wchar_buffer
    from docuworks_ctypes.errors import check_result
    from PIL import Image
    data = request["data"]
    path = Path(data["path"])
    source_stat = fingerprint(path)
    if digest(path) != data["sha256"]:
        raise RuleError("原本ハッシュが不一致です")
    api = XdwApi.load()
    with api.open_document(path) as doc:
        def info(page):
            value = T.XDW_PAGE_INFO_EX()
            value.nSize = ctypes.sizeof(value)
            check_result(doc.raw.XDW_GetPageInformation(doc.handle, page, ctypes.cast(ctypes.byref(value), ctypes.POINTER(T.XDW_PAGE_INFO))), "XDW_GetPageInformation")
            return {"width_mm": value.nWidth/100, "height_mm": value.nHeight/100, "rotation": value.nDegree}
        if request["kind"] == "inspect":
            result = {"pages": [info(p) for p in range(1, doc.page_count+1)], "docuworks": api.runtime_info.version_text}
        else:
            page = data["page"]
            metadata = info(page)
            target = Path(data["image"])
            target.parent.mkdir(parents=True, exist_ok=True)
            temp = Path(data["temp"])
            temp.mkdir(parents=True, exist_ok=True)
            bmp = temp/"page.bmp"
            if len(str(bmp).encode("utf-16-le"))//2 > 255:
                raise RuleError("DocuWorks描画パスが長すぎます。Portableを短い場所へ移動してください")
            options = T.XDW_IMAGE_OPTION()
            options.nSize = ctypes.sizeof(options)
            options.nDpi, options.nColor = data["dpi"], C.XDW_IMAGE_COLOR
            check_result(doc.raw.XDW_ConvertPageToImageFileW(doc.handle, page, wchar_buffer(str(bmp)), ctypes.byref(options)), "XDW_ConvertPageToImageFileW")
            png = temp/"page.png"
            with Image.open(bmp) as image:
                metadata["pixels"] = list(image.size)
                image.convert("RGB").save(png)
            with Image.open(png) as image:
                image.verify()
            os.replace(png, target)
            bmp.unlink()
            result = metadata | {"docuworks": api.runtime_info.version_text, "image_sha256": digest(target)}
    if digest(path) != data["sha256"] or fingerprint(path) != source_stat:
        raise RuleError("原本が処理中に変わりました")
    return result | {"source_hash": data["sha256"], "source_fingerprint": source_stat}


_engine = None


def ocr(request):
    global _engine
    from PIL import Image
    # Public OCR adapter only; none of the legacy review or template APIs are used.
    from docuworks_integrations.paddle import PaddleOcrEngine
    data = request["data"]
    source = Path(data["source_path"])
    source_stat = fingerprint(source)
    if digest(source) != data["sha256"]:
        raise RuleError("OCRの固定原本ハッシュが一致しません")
    cache = Path(data["cache"])
    cache.mkdir(parents=True, exist_ok=True)
    os.environ["DW_OCR_CACHE"] = str(cache)
    if _engine is None:
        _engine = PaddleOcrEngine(data["models"])
    page = PageInfo(**data["page_info"])
    anchor = Anchor(data["source_id"], data["sha256"], data["page"], tuple(data["rect"]))
    temp = Path(data["temp"])
    temp.mkdir(parents=True, exist_ok=True)
    image_path = temp/"roi.png"
    with Image.open(data["image"]) as image:
        width, height = image.size
        box = crop_box(anchor, page, width, height)
        if box[2] <= box[0] or box[3] <= box[1]:
            raise RuleError("読み取り範囲に画素がありません")
        image.crop(box).convert("RGB").save(image_path)
    start = time.perf_counter()
    regions = _engine.recognize(image_path)
    # Deterministic row grouping uses a fixed seed, then orders left-to-right.
    rows = []
    for i, region in sorted(enumerate(regions), key=lambda pair: (pair[1].bbox.y, pair[1].bbox.x, pair[0])):
        center = region.bbox.y+region.bbox.height/2
        row = next((row for row in rows if abs(center-row[0]) <= min(region.bbox.height, row[1])/2), None)
        if row is None:
            row = [center, region.bbox.height, []]
            rows.append(row)
        row[2].append((region.bbox.x, i, region))
    ordered = [r for row in rows for _, _, r in sorted(row[2], key=lambda item: (item[0], item[1]))]
    result = {"text": " ".join(r.text for r in ordered), "regions": [], "engine": {"name": "PaddleOCR", "version": "3.7.0",
        "model": "PP-OCRv6_medium", "crop_pixels": box, "duration_seconds": time.perf_counter()-start}}
    for r in ordered:
        result["regions"].append({"text": r.text, "confidence": r.confidence,
            "polygon_mm": [pixel_to_mm(p.x, p.y, page, width, height, box[:2]) for p in r.polygon]})
    image_path.unlink(missing_ok=True)
    if digest(source) != data["sha256"] or fingerprint(source) != source_stat:
        raise RuleError("OCR中に原本が変わりました")
    return result | {"source_hash": data["sha256"], "source_fingerprint": source_stat}


class WorkerClient:
    def __init__(self, kind, root, log):
        self.kind, self.root, self.log = kind, Path(root), Path(log)
        self.process = None
        self.lock = threading.Lock()

    def start(self):
        if self.process and self.process.poll() is None:
            return
        self.log.parent.mkdir(parents=True, exist_ok=True)
        self.err = self.log.open("ab")
        env = os.environ.copy()
        temp = self.log.parent/"worker-temp"
        temp.mkdir(exist_ok=True)
        env.update({"TEMP": str(temp), "TMP": str(temp), "PYTHONDONTWRITEBYTECODE": "1", "PYTHONUTF8": "1"})
        # Source development and installed Portable use exactly the same entry point.
        source = str(Path(__file__).parent.parent)
        command = [sys.executable, "-I", "-B", "-X", "utf8", "-c",
            "import sys;sys.path.insert(0,sys.argv[1]);from dw_workbench.workers import serve;serve()", source]
        self.process = subprocess.Popen(command, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=self.err,
            encoding="utf-8", env=env, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))

    def call(self, request):
        with self.lock:
            self.start()
            self.process.stdin.write(json.dumps(request, ensure_ascii=False)+"\n")
            self.process.stdin.flush()
            line = self.process.stdout.readline()
            if not line:
                raise RuleError("ワーカーが終了しました。ログを確認して再試行してください")
            result = json.loads(line)
            if not result["ok"]:
                raise RuleError(result["error"])
            return result["result"]

    def close(self):
        # Cancellation may interrupt a native call. Only previously committed results survive.
        if self.process:
            if self.process.poll() is None:
                self.process.terminate()
                try:
                    self.process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    self.process.kill()
                    self.process.wait(timeout=5)
            for stream in (self.process.stdin, self.process.stdout):
                stream.close()
            self.err.close()
            self.process = None


def serve():
    protocol = sys.stdout
    for line in sys.stdin:
        try:
            request = json.loads(line)
            with redirect_stdout(sys.stderr):
                result = ocr(request) if request["kind"] == "ocr" else native(request)
            output = {"ok": True, "result": result}
        except Exception as exc:
            traceback.print_exc(file=sys.stderr)
            output = {"ok": False, "error": str(exc)}
        protocol.write(json.dumps(output, ensure_ascii=False, allow_nan=False)+"\n")
        protocol.flush()


def capabilities(root):
    result = {"docuworks": "利用不可", "gpu": "利用不可（手入力は利用できます）", "models": False}
    try:
        # Even a version probe may load native libraries and change process state.
        # Keep the SDK outside the Tk process, with a bounded diagnostic lifetime.
        probe = subprocess.run([sys.executable, "-I", "-B", "-X", "utf8", "-c",
            "import json;from docuworks_ctypes import XdwApi;print(json.dumps({'docuworks':XdwApi.load().runtime_info.version_text}))"],
            capture_output=True, text=True, encoding="utf-8", timeout=15,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        if probe.returncode != 0:
            raise RuleError(probe.stderr.strip().splitlines()[-1] if probe.stderr.strip() else "DocuWorksの検出に失敗しました")
        result["docuworks"] = json.loads(probe.stdout)["docuworks"]
    except Exception as exc:
        result["docuworks"] += ": "+str(exc)
    try:
        probe = subprocess.run(["nvidia-smi", "--query-gpu=name", "--format=csv,noheader"], capture_output=True, text=True,
            timeout=5, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        if probe.returncode == 0:
            result["gpu"] = probe.stdout.strip()
    except (OSError, subprocess.TimeoutExpired):
        pass
    result["models"] = all((Path(root)/"models"/n/"inference.yml").is_file() for n in ("PP-OCRv6_medium_det", "PP-OCRv6_medium_rec"))
    if os.environ.get("CUDA_VISIBLE_DEVICES", "").strip().lower() in ("-1", "none", "nodevfiles") or "CUDA_VISIBLE_DEVICES" in os.environ and not os.environ["CUDA_VISIBLE_DEVICES"].strip():
        result["gpu"] = "OCR用GPUは無効（手入力は利用できます）"
    return result
