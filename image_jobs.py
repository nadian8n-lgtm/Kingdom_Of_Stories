"""On-demand image helper for «مملكة الأسرار»: bridges the repository with an AI assistant session (chat agent).

Why this exists
---------------
The GitHub Actions cron can only call image providers that expose an HTTP API with a key
(Gemini / Cloudflare Flux / Together / OpenAI - all already wired into fetch_news.py). A chat
assistant cannot be called from cron, but it CAN produce much better pictures on demand inside a
session. This script is the bridge:

    1) python3 image_jobs.py export [--limit N] [--cat KEY] [--all]
       -> writes image_jobs.json: every article that still carries a drawn placeholder, newest
          first, each with a ready-to-use English brief built from the article's own image_prompt.
    2) The assistant generates one picture per job (16:9, editorial, text-free) and saves it as
       generated/<article_id>.png
    3) python3 image_jobs.py apply-dir generated      (or: apply <article_id> <file>)
       -> converts each picture to the exact WebP path the article already references (1280px wide,
          q88, 16:9 centre-crop), marks the article image_kind="ai" so no regeneration pass ever
          overwrites it again, drops the stale thumbnail and rewrites articles.json canonically.
    4) python3 image_jobs.py verify
       -> runs the SAME image gates as adsense_audit.py, so you know before pushing whether the
          AdSense gate will accept every new picture (size, dimensions, sharpness, look-alikes).
    5) python3 image_jobs.py zip
       -> nexus_images_update.zip (articles.json + the new images/ files + this script + a note)
          ready to upload to the repository root on GitHub.

Commands: status | export | apply <id> <file> | apply-dir <dir> | verify [--all] | zip
Flags:    --limit N  --cat KEY  --all  --force
"""
import json
import random
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).parent
ARTICLES = ROOT / "articles.json"
JOBS = ROOT / "image_jobs.json"
GENERATED = ROOT / "generated"

CATEGORIES = ("ar_world", "ar_economy", "ar_tech", "ar_sports", "ar_arts", "ar_books")
PICTURE_SUFFIXES = (".png", ".jpg", ".jpeg", ".webp")

# The AdSense gate in adsense_audit.py rejects a picture that fails any of these. They are duplicated here so
# `verify` reports exactly what the gate will report - keep the two files in sync.
MIN_BYTES = 8 * 1024
MIN_WIDTH, MIN_HEIGHT = 640, 320
MIN_SHARPNESS = 80.0
MAX_DHASH_DISTANCE = 6
TARGET_WIDTH = 1280
TARGET_QUALITY = 88

# Same visual language as fetch_news.build_prompt, duplicated so this file stays standalone
# (fetch_news imports heavy modules the image bridge does not need).
IMG_STYLE = {
    "ar_world": "thoughtful editorial illustration, wide conceptual composition",
    "ar_economy": "clean editorial illustration, markets, charts or abstract finance motifs",
    "ar_tech": "modern technology illustration, clean futuristic atmosphere",
    "ar_sports": "dynamic sports illustration, stadium energy and motion",
    "ar_arts": "cultural illustration, rich colour and atmosphere",
    "ar_books": "illustrated still-life of books and a laptop on a desk, warm library light, no people",
}
ANGLES = ["wide establishing shot", "low-angle shot", "aerial drone view", "intimate close-up of a telling object",
          "shot from behind a silhouette", "symmetrical centered composition", "telephoto compressed perspective",
          "shallow depth of field detail shot", "over-the-shoulder framing", "high-angle view from a balcony"]
PALETTES = ["muted teal and amber", "cool blue-grey with one warm accent", "desaturated earth tones",
            "deep shadows with sodium-orange highlights", "soft pastel dawn colours", "high-contrast black and sandy beige"]
LIGHTS = ["soft early-morning light", "dramatic overcast sky", "warm golden hour", "cool blue hour",
          "crisp midday sunlight", "moody night with practical lights", "diffused window light", "stormy contrasty light"]
NEGATIVES = ("MANDATORY NEGATIVES: no text, no letters, no numbers, no logos, no watermark, no signature, no brand names, "
             "no trademarks, no identifiable real people or celebrities, no posed portrait, no fashion model, no glamour "
             "or beauty shot, no graphic violence, no blood, no dead bodies, no sexual content, no religious desecration.")


# --------------------------------------------------------------------------- articles.json
def load():
    if not ARTICLES.exists():
        print(f"ERROR: {ARTICLES} not found. Run this script from the repository root.")
        sys.exit(1)
    try:
        data = json.loads(ARTICLES.read_text(encoding="utf-8"))
    except json.JSONDecodeError as ex:
        print(f"ERROR: {ARTICLES.name} is not valid JSON: {ex}")
        sys.exit(1)
    arts = data.get("articles")
    if not isinstance(arts, dict):
        print(f"ERROR: {ARTICLES.name} has no \"articles\" object - is this the right file?")
        sys.exit(1)
    return data, arts


def save(data):
    """Rewrite articles.json in the canonical shape build_site.load() expects, losing nothing else."""
    arts = data.get("articles") or {}
    out = dict(data)                                   # keep any extra top-level key the pipeline may add later
    out["categories"] = data.get("categories") or {}
    out["articles"] = {k: arts[k] for k in CATEGORIES if k in arts}
    for k in arts:                                     # never silently drop an unknown section
        out["articles"].setdefault(k, arts[k])
    ARTICLES.write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")


def all_articles(arts):
    rows = [(cat, a) for cat, lst in arts.items() if isinstance(lst, list) for a in lst if isinstance(a, dict) and a.get("id")]
    rows.sort(key=lambda r: r[1].get("date", ""), reverse=True)
    return rows


def needs_image(a):
    kind = a.get("image_kind") or (a.get("image_credit") or {}).get("kind")
    img = a.get("image") or ""
    return kind != "ai" or not img or img.endswith(".svg")


def build_brief(cat, art_id, scene):
    r = random.Random(f"{art_id}-0")                   # stable: the same article always gets the same brief
    lens = r.choice(["24mm wide lens", "35mm documentary lens", "50mm natural perspective", "85mm short telephoto"])
    return ("Editorial news photograph for the front page of an international newspaper, photorealistic, shot on a "
            "full-frame camera with a " + lens + ", " + r.choice(ANGLES) + ", " + r.choice(LIGHTS) + ", "
            + r.choice(PALETTES) + " colour grade, natural skin texture, sharp focus on the subject, subtle film grain, "
            "high dynamic range, 16:9 landscape composition. " + IMG_STYLE.get(cat, "") + ". Scene: " + scene + ". " + NEGATIVES)


# --------------------------------------------------------------------------- image quality gates
def dhash(im, size=8):
    """Identical implementation to adsense_audit.dhash so `verify` predicts the gate exactly."""
    im = im.convert("L").resize((size + 1, size))
    p = im.tobytes()
    bits = 0
    for r in range(size):
        for c in range(size):
            bits = (bits << 1) | (1 if p[r * (size + 1) + c] > p[r * (size + 1) + c + 1] else 0)
    return bits


def sharpness(im):
    from PIL import ImageFilter, ImageStat
    return ImageStat.Stat(im.convert("L").filter(ImageFilter.FIND_EDGES)).var[0]


def gate_one(rel, im=None):
    """Return the list of reasons the AdSense gate would reject this picture (empty = it passes)."""
    bad = []
    p = ROOT / rel
    if not rel or not p.is_file():
        return [f"missing file {rel or '(no path)'}"]
    if p.suffix.lower() == ".svg":
        bad.append("SVG placeholder (the blue 'MA' box defect)")
    size = p.stat().st_size
    if size < MIN_BYTES:
        bad.append(f"only {size // 1024} KB (the gate needs {MIN_BYTES // 1024} KB)")
    try:
        from PIL import Image
        im = im or Image.open(p)
        if im.width < MIN_WIDTH or im.height < MIN_HEIGHT:
            bad.append(f"too small ({im.width}x{im.height}, minimum {MIN_WIDTH}x{MIN_HEIGHT})")
        sh = sharpness(im)
        if sh < MIN_SHARPNESS:
            bad.append(f"blurry (sharpness {sh:.0f} < {MIN_SHARPNESS:.0f})")
    except Exception as ex:
        bad.append(f"unreadable picture ({str(ex)[:70]})")
    return bad


# --------------------------------------------------------------------------- commands
def cmd_status():
    data, arts = load()
    rows = all_articles(arts)
    todo = [(c, a) for c, a in rows if needs_image(a)]
    print(f"articles: {len(rows)} | real AI images: {len(rows) - len(todo)} | placeholders to replace: {len(todo)}")
    for c, a in todo[:10]:
        print(f"  - {a['id']} [{c}] {(a.get('title') or '')[:60]}")
    if len(todo) > 10:
        print(f"  ... and {len(todo) - 10} more")
    return len(todo)


def cmd_export(limit=None, only_todo=True, cat=None):
    data, arts = load()
    rows = all_articles(arts)
    if only_todo:
        rows = [(c, a) for c, a in rows if needs_image(a)]
    if cat:
        rows = [(c, a) for c, a in rows if c == cat or a["id"].startswith(cat)]
        if not rows:
            print(f"no article to export for '{cat}' (sections: {', '.join(CATEGORIES)})")
            return
    if limit:
        rows = rows[:limit]
    jobs = []
    for c, a in rows:
        scene = (a.get("image_prompt") or a.get("image_prompt_editor") or a.get("title") or "").strip()
        jobs.append({
            "id": a["id"],
            "cat": c,
            "title": a.get("title", ""),
            "summary": (a.get("summary") or "")[:200],
            "date": a.get("date", ""),
            "target": a.get("image") or f"images/{a['id']}.webp",
            "save_as": f"generated/{a['id']}.png",
            "prompt": build_brief(c, a["id"], scene),
        })
    GENERATED.mkdir(exist_ok=True)
    JOBS.write_text(json.dumps(jobs, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"wrote {JOBS.name}: {len(jobs)} job(s), newest first")
    for j in jobs[:5]:
        print(f"  - {j['id']} -> {j['target']}")
    if len(jobs) > 5:
        print(f"  ... and {len(jobs) - 5} more")
    print(f"\nnext: save each picture as generated/<id>.png, then run: python3 {Path(__file__).name} apply-dir generated")


def _apply_one(index, art_id, src, force=False):
    src = Path(src)
    if not src.is_file():
        print(f"  ! {art_id}: source file not found ({src})")
        return False
    cat, a = index[art_id]
    if not force and a.get("image_kind") == "ai":
        print(f"  = {art_id}: already has an AI picture - skipped (use --force to replace it)")
        return False
    try:
        from PIL import Image
    except ImportError:
        print("Pillow is required: pip install pillow")
        sys.exit(1)
    try:
        img = Image.open(src).convert("RGB")
    except Exception as ex:
        print(f"  ! {art_id}: cannot read {src.name} ({str(ex)[:70]})")
        return False
    if img.width < MIN_WIDTH or img.height < MIN_HEIGHT:
        print(f"  ! {art_id}: {src.name} is only {img.width}x{img.height} - generate at least {MIN_WIDTH}x{MIN_HEIGHT}")
        return False

    # centre-crop to 16:9 (the site hero ratio) then downscale to the pipeline standard
    w, h = img.size
    ratio = 16 / 9
    if abs(w / h - ratio) > 0.02:
        if w / h > ratio:
            nw = int(h * ratio)
            img = img.crop(((w - nw) // 2, 0, (w - nw) // 2 + nw, h))
        else:
            nh = int(w / ratio)
            img = img.crop((0, (h - nh) // 2, w, (h - nh) // 2 + nh))
    img.thumbnail((TARGET_WIDTH, TARGET_WIDTH))

    rel = a.get("image") or f"images/{a['id']}.webp"
    if not rel.endswith(".webp"):
        rel = f"images/{a['id']}.webp"
    out = ROOT / rel
    out.parent.mkdir(parents=True, exist_ok=True)
    old_paths = {a.get("image"), f"images/{a['id']}.svg"}
    img.save(out, "WEBP", quality=TARGET_QUALITY, method=6)
    for stale in old_paths:                            # remove the placeholder it replaces
        if stale and stale != rel:
            (ROOT / stale).unlink(missing_ok=True)
    (ROOT / "images" / "t" / (Path(rel).stem + ".webp")).unlink(missing_ok=True)   # stale thumbnail

    a["image"] = rel
    a["image_kind"] = "ai"
    a["image_credit"] = {"source": "AI", "author": "نكسوس",
                         "license": "image generated for مملكة الأسرار", "kind": "ai"}
    if not a.get("image_alt"):
        a["image_alt"] = a.get("title", "")
    a["regen"] = True
    a.pop("cdn", None)                                 # the Cloudinary copy points at the old picture

    bad = gate_one(rel, img)
    if bad:
        print(f"  ~ {art_id} -> {rel} ({img.width}x{img.height}) BUT the AdSense gate will reject it: {'; '.join(bad)}")
    else:
        print(f"  + {art_id} -> {rel} ({img.width}x{img.height}) gate OK")
    return True


def _index(arts):
    return {a["id"]: (c, a) for c, a in all_articles(arts)}


def cmd_apply(art_id, src, force=False):
    data, arts = load()
    index = _index(arts)
    if art_id not in index:
        print(f"unknown article id: {art_id}")
        print(f"run `python3 {Path(__file__).name} status` to list the ids")
        sys.exit(1)
    if _apply_one(index, art_id, src, force):
        save(data)
        print("articles.json updated")


def cmd_apply_dir(d, force=False):
    d = Path(d)
    if not d.is_dir():
        print(f"ERROR: '{d}' is not a directory. Generate the pictures first, or pass the right folder:")
        print(f"  python3 {Path(__file__).name} apply-dir generated")
        sys.exit(1)
    files = sorted(f for f in d.iterdir() if f.is_file() and f.suffix.lower() in PICTURE_SUFFIXES)
    if not files:
        print(f"no picture found in '{d}' (expected .png/.jpg/.jpeg/.webp named <article_id>.png)")
        return
    data, arts = load()
    index = _index(arts)
    applied, unknown = 0, []
    for f in files:
        if f.stem in index:
            applied += 1 if _apply_one(index, f.stem, f, force) else 0
        else:
            unknown.append(f.name)
    if applied:
        save(data)
    print(f"\napplied {applied} picture(s) out of {len(files)} file(s)"
          + ("; articles.json updated" if applied else "; articles.json untouched"))
    for name in unknown:
        print(f"  ? skipped {name}: no article with that id")
    if applied:
        print(f"next: python3 {Path(__file__).name} verify   then   python3 {Path(__file__).name} zip")


def cmd_verify(only_ai=True):
    """Predict adsense_audit.py: every picture is checked against the very same gates.

    By default only the hand-made AI pictures are reported (those are the ones you just produced and the
    ones the gate will judge first); pass --all to audit every picture on the site.
    """
    data, arts = load()
    rows = all_articles(arts)
    hashes, failures, paths = {}, [], {}
    checked = 0
    for cat, a in rows:
        rel = a.get("image") or ""
        kind = a.get("image_kind") or (a.get("image_credit") or {}).get("kind") or "-"
        bad = gate_one(rel)
        p = ROOT / rel
        if p.is_file() and p.suffix.lower() != ".svg":
            checked += 1
            try:
                from PIL import Image
                h = dhash(Image.open(p))
                alike = [o for o, (oh, _) in hashes.items() if bin(h ^ oh).count("1") <= MAX_DHASH_DISTANCE]
                if alike:
                    shown = ", ".join(alike[:2]) + (f" +{len(alike) - 2} more" if len(alike) > 2 else "")
                    bad.append(f"looks like the picture of {shown}")
                hashes[a["id"]] = (h, rel)
            except Exception as ex:
                bad.append(f"could not be analysed ({str(ex)[:60]})")
        if not a.get("image_credit"):
            bad.append("no image credit")
        owner = paths.get(rel)
        if owner and owner != a["id"]:
            bad.append(f"the same file is used by {owner}")
        elif rel:
            paths[rel] = a["id"]
        if bad and (not only_ai or kind == "ai"):
            failures.append((a["id"], kind, bad[:3]))
    ai = sum(1 for _, a in rows if a.get("image_kind") == "ai")
    scope = "the hand-made AI pictures" if only_ai else "every picture"
    print(f"verify: {len(rows)} articles | {ai} AI picture(s) | {checked} analysed | reporting {scope}")
    if only_ai:
        print(f"        (run with --all to audit the {len(rows) - ai} drawn placeholder(s) too)")
    if not failures:
        print(f"OK: {scope} pass the AdSense image gates (file, size, dimensions, sharpness, uniqueness, credit).")
        return 0
    print(f"\nWOULD FAIL THE ADSENSE GATE ({len(failures)}):")
    for aid, kind, bad in failures[:25]:
        print(f"  - {aid} [{kind}]: {'; '.join(bad)}")
    if len(failures) > 25:
        print(f"  ... and {len(failures) - 25} more")
    return 1


def cmd_zip():
    import zipfile
    data, arts = load()
    touched = [a["image"] for _, a in all_articles(arts)
               if a.get("image_kind") == "ai" and a.get("image") and (ROOT / a["image"]).is_file()]
    if not touched:
        print("nothing to pack yet: no article is marked image_kind=\"ai\". Run apply-dir first.")
        return
    stamp = datetime.now(timezone.utc).strftime("%y%m%d%H%M")
    zpath = ROOT / f"nexus_images_update-{stamp}.zip"
    note = ("Upload every entry of this archive to the ROOT of the repository (Add file > Upload files),\n"
            "keeping the images/ folder, then commit. The next run of build_site.py rebuilds the pages with\n"
            "these pictures. Do not upload the archive itself.\n")
    with zipfile.ZipFile(zpath, "w", zipfile.ZIP_DEFLATED) as z:
        z.write(ARTICLES, "articles.json")
        z.write(Path(__file__), Path(__file__).name)
        z.writestr("UPLOAD_ME_FIRST.txt", note)
        for rel in touched:
            z.write(ROOT / rel, rel)
    print(f"wrote {zpath.name}: articles.json + {Path(__file__).name} + {len(touched)} picture(s)")
    print("upload its CONTENTS to the repository root (merge/replace), then commit.")


def _flag(args, name):
    return name in args


def _opt(args, name):
    if name in args and args.index(name) + 1 < len(args):
        return args[args.index(name) + 1]
    return None


def main():
    args = sys.argv[1:]
    if not args:
        print(__doc__)
        return
    cmd, force = args[0], _flag(args, "--force")
    if cmd == "status":
        cmd_status()
    elif cmd == "export":
        limit = _opt(args, "--limit")
        cmd_export(int(limit) if limit else None, not _flag(args, "--all"), _opt(args, "--cat"))
    elif cmd == "apply":
        if len(args) < 3:
            print("usage: image_jobs.py apply <article_id> <picture_file> [--force]")
            sys.exit(1)
        cmd_apply(args[1], args[2], force)
    elif cmd == "apply-dir":
        cmd_apply_dir(_opt(args, "--dir") or (args[1] if len(args) > 1 and not args[1].startswith("--") else "generated"), force)
    elif cmd == "verify":
        sys.exit(cmd_verify(only_ai=not _flag(args, "--all")))
    elif cmd == "zip":
        cmd_zip()
    else:
        print(f"unknown command: {cmd}")
        print(__doc__)
        sys.exit(1)


if __name__ == "__main__":
    main()
