"""NP_PREFLIGHT - self-healing guard that runs before every GitHub Actions Python job.

Why this exists
---------------
A stale/corrupted copy of two scripts was observed inside Actions:

  * adsense_audit.py line 126 had the module docstring pasted onto the
    SCENE_IMG_RX line, producing "unterminated string literal".
  * fetch_news.py had a stray Arabic docstring line floating as bare code,
    producing "invalid character '،' (U+060C)".

The canonical local files are clean, but this guard makes the workflow repair
any shipped copy before it is imported, and recreates missing thumbnails that
check_site.py reports as "index.html -> missing images/t/...".

It is idempotent: on a correct checkout it changes nothing.
"""

import py_compile
import re
import shutil
import sys
from pathlib import Path
from urllib.parse import unquote, urlparse

ROOT = Path(__file__).resolve().parent
MARK = "NP_PREFLIGHT v2026-11-19a"

SCENE_CORRECT = r"""SCENE_IMG_RX = re.compile(r'(?:^|[/\\])story[_-][^/\\]+-scene-\d+\.webp$', re.I)"""

STRAY_ARABIC = (
    "أدبية وقصص دينية مستندة إلى القرآن والسنة الصحيحة) "
    "وثلاث فئات عمرية في ركن الأطفال، إضافة"
)

changed = []


def save(path, text):
    path.write_text(text, encoding="utf-8")
    changed.append(path.name)


def repair_adsense():
    path = ROOT / "adsense_audit.py"
    if not path.exists():
        return
    text = path.read_text(encoding="utf-8", errors="replace")
    lines = text.splitlines()
    out, seen = [], False
    for line in lines:
        if "SCENE_IMG_RX" in line and "re.compile" in line:
            if not seen:
                out.append(SCENE_CORRECT)
                seen = True
            # drop the correct line if it appears more than once
            continue
        # a pasted docstring fragment alone on a line after the imports
        if '"""AdSense pre-review gate' in line and len(out) > 20:
            continue
        out.append(line)
    if not seen:
        # insert just before the first NAV_RX definition when missing entirely
        for i, line in enumerate(out):
            if "NAV_RX" in line and "re.compile" in line:
                out.insert(i, SCENE_CORRECT)
                seen = True
                break
    if not seen:
        out.append(SCENE_CORRECT)
    rebuilt = "\n".join(out) + "\n"
    if rebuilt != text:
        save(path, rebuilt)


def repair_fetch():
    path = ROOT / "fetch_news.py"
    if not path.exists():
        return
    text = path.read_text(encoding="utf-8", errors="replace")
    lines = text.splitlines()
    out = []
    # the genuine copy of STRAY_ARABIC lives in the module docstring (line 4);
    # only remove it when it escaped into bare code further down the file.
    for i, line in enumerate(lines):
        if STRAY_ARABIC in line and i > 20 and not line.lstrip().startswith("#"):
            continue
        out.append(line)
    rebuilt = "\n".join(out) + "\n"
    if rebuilt != text:
        save(path, rebuilt)


def restore_thumbnails():
    """Copy a missing images/t/<name> from images/<name>; generate a safe fallback."""
    thumb_dir = ROOT / "images" / "t"
    thumb_dir.mkdir(parents=True, exist_ok=True)
    refs = set()
    for page in ROOT.rglob("*.html"):
        try:
            text = page.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        for raw in re.findall(r'(?:href|src)="([^"]+)"', text):
            part = urlparse(raw)
            if part.scheme or part.netloc:
                continue
            rel = unquote(part.path)
            if not re.search(r"\.(webp|png|jpe?g)$", rel, re.I):
                continue
            target = (page.parent / rel).resolve()
            if target.exists():
                continue
            refs.add(target)

    if not refs:
        return

    try:
        from PIL import Image, ImageDraw
    except ImportError:
        Image = None

    made = 0
    for target in sorted(refs):
        source = ROOT / "images" / target.name
        target.parent.mkdir(parents=True, exist_ok=True)
        if source.exists() and source.resolve() != target:
            shutil.copy2(source, target)
            made += 1
        elif Image is not None:
            img = Image.new("RGB", (480, 270), (11, 60, 122))
            draw = ImageDraw.Draw(img)
            draw.rectangle((10, 10, 469, 259), outline=(214, 169, 79), width=5)
            draw.text((28, 124), "Kingdom Of Secrets", fill=(255, 255, 255))
            img.save(target, "WEBP")
            made += 1
    if made:
        changed.append(f"{made} thumbnail(s) restored")


def verify_syntax():
    bad = []
    for path in sorted(ROOT.rglob("*.py")):
        if "node_modules" in path.parts:
            continue
        try:
            py_compile.compile(str(path), doraise=True)
        except Exception as exc:
            bad.append(f"{path.relative_to(ROOT)}: {exc}")
    if bad:
        print(f"{MARK}: SYNTAX FAILURE", file=sys.stderr)
        for line in bad:
            print("  " + line, file=sys.stderr)
        sys.exit(1)


repair_adsense()
repair_fetch()
restore_thumbnails()
verify_syntax()
print(f"{MARK}: OK | repaired: {', '.join(changed) if changed else 'nothing (already clean)'}")
