"""Shared preview rendering for current and legacy OCR producers."""
from pathlib import Path


def create_preview(image_path: Path, regions, run_dir: Path) -> None:
    from PIL import Image, ImageDraw, ImageFont
    with Image.open(image_path) as original:
        image = original.convert("RGB")
    draw = ImageDraw.Draw(image)
    font = ImageFont.load_default(size=max(18, image.width // 100))
    lines = ["# OCR領域一覧", "", "番号付きプレビューと照合し、水平な文字列を1件選択してください。", "",
             "|番号|認識文字列|信頼度|", "|---:|---|---:|"]
    for i, region in enumerate(regions, 1):
        rect = region.bbox
        draw.rectangle((rect.x, rect.y, rect.right, rect.bottom), outline="#e00020", width=3)
        label = str(i)
        pos = (max(0, rect.x), max(0, rect.y - font.size - 4))
        box = draw.textbbox(pos, label, font=font)
        draw.rectangle(box, fill="white")
        draw.text(pos, label, font=font, fill="#0033bb")
        safe = region.text.replace("|", "\\|").replace("\n", "<br>")
        score = "—" if region.confidence is None else f"{region.confidence:.6f}"
        lines.append(f"|{i}|{safe}|{score}|")
    image.save(run_dir / "preview.png")
    (run_dir / "regions.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
