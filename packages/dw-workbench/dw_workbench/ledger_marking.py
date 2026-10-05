"""Deterministic ledger decisions over a frozen Workbench result; no SDK or GUI."""
from collections import Counter, defaultdict
from copy import deepcopy
from dataclasses import asdict
import hashlib
import json
from pathlib import Path
import shutil
from .domain import Anchor, RuleError, Status, identifier, source_from, timestamp
from .ledger import Cell, LedgerBook, exact_value
from .storage import atomic_bytes, digest, relative_path

COLORS = {"red": 0x0000FF, "blue": 0xFF0000, "green": 0x008000, "yellow": 0x00FFFF}


def content_hash(value):
    wire = json.loads(json.dumps(value, ensure_ascii=False, allow_nan=False))
    return hashlib.sha256(json.dumps(wire, ensure_ascii=False, sort_keys=True,
        separators=(",", ":"), allow_nan=False).encode("utf-8")).hexdigest()


def build_preview(dataset, book, config):
    config = deepcopy(config)
    if dataset.get("format_version") != 2:
        raise RuleError("台帳照合にはv0.2.0で新しく確定した結果を選択してください")
    group = next((g for g in dataset["groups"] if
        (g["schema"]["id"], g["schema"]["version"]) == (config["schema_id"], config["schema_version"])), None)
    if group is None:
        raise RuleError("対象の項目定義版が確定結果にありません")
    fields = {f["id"]: f for f in group["schema"]["fields"]}
    if config["key_field"] not in fields or config["draw_field"] not in fields:
        raise RuleError("照合項目と描画項目を指定してください")
    if config.get("color") not in COLORS or config.get("key_kind") not in ("text", "number"):
        raise RuleError("注釈色と照合型が不正です")
    sheet = book.sheet(config["sheet"], config["header_row"])
    if config["key_column"] not in sheet.columns or config["condition_column"] not in sheet.columns:
        raise RuleError("台帳の照合列と条件列を指定してください")
    condition = exact_value(Cell(config["condition_kind"], config["condition_value"]), config["condition_kind"])
    ledger = defaultdict(list)
    notices = []
    for number, cells in sheet.rows:
        key = sheet.cell(number, cells, config["key_column"])
        value = sheet.cell(number, cells, config["condition_column"])
        try:
            token = exact_value(key, config["key_kind"])
        except RuleError as exc:
            notices.append(dict(id="ledger:"+str(number), scope="ledger", status="review", reason=str(exc),
                                ledger_row=number, ledger_key=asdict(key), ledger_condition=asdict(value)))
            continue
        ledger[token].append((number, key, value))
    records = []
    keys = {}
    for record in group["records"]:
        state = record["fields"][config["key_field"]]
        key = Cell("number" if fields[config["key_field"]]["kind"] == "decimal" else "text", state["value"])
        try:
            if state["status"] != Status.ACCEPTED:
                raise RuleError("抽出キーは確認済みではありません")
            keys[record["id"]] = exact_value(key, config["key_kind"])
        except RuleError:
            pass
    counts = Counter(keys.values())
    known = set(keys.values())
    for token, matches in ledger.items():
        if len(matches) > 1 or token not in known:
            for number, key, value in matches:
                notices.append(dict(id="ledger:"+str(number), scope="ledger", status="review",
                    reason="台帳キーが重複しています" if len(matches)>1 else "確定結果に一致するキーがありません",
                    ledger_row=number, ledger_key=asdict(key), ledger_condition=asdict(value)))
    for record in group["records"]:
        state = record["fields"][config["draw_field"]]
        item = dict(id="record:"+record["id"], scope="record", record_id=record["id"],
            source=deepcopy(record["source"]), key_field_id=config["key_field"], draw_field_id=config["draw_field"],
            extracted_key=record["fields"][config["key_field"]]["value"], extracted_value=state["value"], raw=state["raw"],
            anchor=deepcopy(state["anchor"]), profile=deepcopy(record["profile"]), status="review", reason="",
            ledger_rows=[], ledger_key=None, ledger_condition=None)
        try:
            token = keys.get(record["id"])
            if token is None:
                raise RuleError("抽出キーが未確認・空欄、または指定した照合型と異なります")
            if counts[token] > 1:
                raise RuleError("確定結果のキーが重複しています")
            matches = ledger.get(token, [])
            item["ledger_rows"] = [r[0] for r in matches]
            if not matches:
                raise RuleError("台帳に完全一致するキーがありません")
            if len(matches) != 1:
                raise RuleError("台帳キーが重複しています（先頭行は採用しません）")
            _, key, value = matches[0]
            item["ledger_key"], item["ledger_condition"] = asdict(key), asdict(value)
            if exact_value(value, config["condition_kind"]) != condition:
                item.update(status="non_target", reason="台帳値が指定条件と一致しません")
            else:
                if state["status"] != Status.ACCEPTED or not state["anchor"]:
                    raise RuleError("描画項目に確認済みの根拠がありません")
                source = source_from(record["source"])
                anchor = Anchor(**(state["anchor"] | {"rect": tuple(state["anchor"]["rect"])}))
                anchor.validate(source)
                if record["page"] is not None and record["page"] != anchor.page:
                    raise RuleError("記録ページと根拠ページが一致しません")
                if source.pages[anchor.page-1].rotation != 0:
                    raise RuleError("初版では回転ページの注釈出力を行いません")
                item.update(status="target", reason="キー完全一致・条件一致・確認済み根拠あり")
        except RuleError as exc:
            item["reason"] = str(exc)
        records.append(item)
    return dict(schema="dw-workbench-ledger-markup", version=1, dataset_id=dataset["id"],
        dataset_sha256=content_hash(dataset), config=config, ledger_sha256=book.sha256,
        sheet_columns={str(k):v for k,v in sheet.columns.items()}, records=records, notices=notices)


def resolved_items(session):
    result = deepcopy(session["preview"]["records"] + session["preview"]["notices"])
    exclusions = session.get("exclusions", {})
    valid = {item["id"] for item in result}
    if not set(exclusions).issubset(valid):
        raise RuleError("除外対象がプレビューにありません")
    for item in result:
        if item["id"] in exclusions:
            reason = exclusions[item["id"]]
            if not isinstance(reason, str) or not reason.strip():
                raise RuleError("明示除外には理由が必要です")
            item.update(status="excluded", exclusion_reason=reason)
    return result


def summary(session):
    items = resolved_items(session)
    return {scope: dict(Counter(item["status"] for item in items if item["scope"] == scope))
            for scope in ("record", "ledger")}


def save_session(root, dataset, book, config):
    preview = build_preview(dataset, book, config)
    plan_id = identifier()
    folder = relative_path(root, "exports/ledger-markups/"+plan_id)
    folder.mkdir(parents=True, exist_ok=False)
    try:
        atomic_bytes(folder/"ledger.xlsx", book.payload)
        session = dict(id=plan_id, created=timestamp(), ledger_original_path=str(book.path),
                       preview=preview, exclusions={}, outputs=[])
        project = Path(root).resolve()
        if book.path.is_relative_to(project):
            session["ledger_reference"] = dict(scope="project", path=book.path.relative_to(project).as_posix())
        elif project.parent.name == "projects" and book.path.is_relative_to(project.parent.parent):
            session["ledger_reference"] = dict(scope="portable", path=book.path.relative_to(project.parent.parent).as_posix())
        save_decisions(folder, session)
        return folder, session
    except BaseException:
        shutil.rmtree(folder)
        raise


def save_decisions(folder, session):
    resolved_items(session)
    atomic_bytes(Path(folder)/"session.json", json.dumps(session, ensure_ascii=False,
        sort_keys=True, allow_nan=False, indent=2).encode("utf-8"))


def load_session(folder, dataset):
    folder = Path(folder)
    session = json.loads((folder/"session.json").read_text(encoding="utf-8"))
    if folder.name != session["id"]:
        raise RuleError("照合保存先のIDが一致しません")
    verify_session(folder, session, dataset)
    return session


def original_ledger_path(folder, session):
    """Resolve a saved local reference after relocation; legacy/external paths stay exact."""
    reference = session.get("ledger_reference")
    if reference is None:
        return Path(session["ledger_original_path"])
    if not isinstance(reference, dict) or set(reference) != {"scope", "path"}:
        raise RuleError("台帳参照の保存形式が不正です")
    folder = Path(folder).resolve()
    if folder.parent.name != "ledger-markups" or folder.parent.parent.name != "exports":
        raise RuleError("台帳参照の保存先構成が不正です")
    project = folder.parents[2]
    if reference["scope"] == "project":
        return relative_path(project, reference["path"])
    if reference["scope"] == "portable" and project.parent.name == "projects":
        return relative_path(project.parent.parent, reference["path"])
    raise RuleError("台帳参照の保存範囲が不正です")


def verify_session(folder, session, dataset):
    frozen = session["preview"]
    if content_hash(dataset) != frozen["dataset_sha256"]:
        raise RuleError("確定結果がプレビュー後に変わりました。再照合してください")
    snapshot = LedgerBook(Path(folder)/"ledger.xlsx")
    rebuilt = build_preview(dataset, snapshot, frozen["config"])
    # JSON turns integer column keys into strings; compare canonical wire values.
    if content_hash(rebuilt) != content_hash(frozen):
        raise RuleError("台帳スナップショットまたはマーク指示が変わりました。再照合してください")
    original = original_ledger_path(folder, session)
    if not original.is_file() or digest(original) != frozen["ledger_sha256"]:
        raise RuleError("元台帳が変更・移動されています。現在の台帳から再照合してください")
    resolved_items(session)


def drawing_spec(root, session):
    items = resolved_items(session)
    if any(item["status"] == "review" for item in items):
        raise RuleError("要確認を解消するか、理由を付けて明示除外してください")
    targets = [item for item in items if item["status"] == "target"]
    if not targets:
        raise RuleError("描画対象がありません")
    sources = {}
    for item in targets:
        source = item["source"]
        path = relative_path(root, source["path"])
        if not path.is_file() or digest(path) != source["sha256"]:
            raise RuleError("固定原本が変更・欠損しています: "+source["name"])
        record = sources.setdefault(source["id"], dict(source=source, path=str(path), marks={}))
        anchor = item["anchor"]
        key = (anchor["page"], *anchor["rect"])
        mark = record["marks"].setdefault(key, dict(page=anchor["page"], rect=anchor["rect"], references=[]))
        mark["references"].append(dict(record_id=item["record_id"], field_id=item["draw_field_id"],
                                       dataset_id=session["preview"]["dataset_id"]))
    return [dict(source=v["source"], path=v["path"], marks=list(v["marks"].values())) for v in sources.values()]
