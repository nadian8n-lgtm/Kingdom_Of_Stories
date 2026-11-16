"""AdSense pre-review gate for Nexus Press.

Run AFTER build_site.py. It fails (exit 1) when the site shows one of the
defects that get an AdSense application rejected:

  * duplicated / near-duplicated articles or titles
  * the same or a look-alike picture on two articles, blurry pictures,
    missing picture credit, SVG placeholders (the old blue "MA" box)
  * an article without a cited source, or a Moroccan source in a
    non-Moroccan section
  * a foreign story filed under «أخبار المغرب» أو «أخبار المدن»
  * Latin-only / empty / too-short articles, books outside 430-820 words
  * emoji flags, lorem ipsum, undefined/None leftovers, forbidden image hosts
  * missing legal pages, missing sources block, missing image credit caption
  * a thin section (fewer than ADSENSE_MIN_PER_CATEGORY articles)

Anything that is a judgement call (a single-source article, a sensitive
headline) is printed as a WARNING and does not fail the build.
"""
import os
import re
import sys
import unicodedata
from pathlib import Path

import build_site

ROOT = Path(__file__).parent
problems, warnings = [], []
data = build_site.load()
allart = [(k, a) for k in build_site.CATEGORIES for a in data[k]]
MIN_PER_CAT = int(os.getenv("ADSENSE_MIN_PER_CATEGORY") or "0")

ARABIC = re.compile(r"[\u0621-\u064A]")
LETTERS = re.compile(r"[^\W\d_]", re.UNICODE)
FLAG = re.compile(r"[\U0001F1E6-\U0001F1FF]")
SEXUAL_RX = re.compile(r"(?:سكس|إباح|اباح|إباحية|عاري(?!تين)|اغتصاب|تحرش جنسي|onlyfans|porn)")
RISKY = ("مجزرة", "إرهاب", "اغتيال", "انتحار", "طفل", "قاصر", "جثة", "دماء")
# Unambiguous leftovers: they can never be a legitimate part of an article.
JUNK = ("lorem ipsum", "pollinations", "picsum", "test article")
# Real words in a programming article (a JavaScript book list talks about "undefined" and "placeholder" all the time),
# so they only fail outside the tech/library sections - there they are almost certainly a template leftover.
JUNK_TECH = ("undefined", "null", "none", "todo", "placeholder")
TECH_CATS = ("ar_tech", "ar_books")
_JUNK_WORDS = JUNK + JUNK_TECH
JUNK_RX = {w: re.compile(r"(?<![a-z0-9])" + re.escape(w) + r"(?![a-z0-9])") for w in _JUNK_WORDS}
# An unrendered f-string/format placeholder, e.g. {lo} or {image_prompt}: always a defect.
TEMPLATE_RX = re.compile(r"\{[a-z_][a-z0-9_]{1,20}\}")
REQUIRED_PAGES = ("index.html", "about.html", "contact.html", "privacy-policy.html",
                  "editorial-policy.html", "terms.html", "404.html", "feed.xml", "sitemap.xml",
                  "robots.txt", "style.css", "site.js", "tools.js", "sw.js", "logo.webp",
                  "manifest.webmanifest", "search.json")


def arabic_ratio(text):
    letters = LETTERS.findall(text or "")
    if not letters:
        return 0.0
    return len(ARABIC.findall(text)) / len(letters)


def words(text):
    return len(re.findall(r"\S+", text or ""))


def norm(text):
    text = unicodedata.normalize("NFKC", text or "")
    text = re.sub(r"[^\w\u0621-\u064A]+", " ", text)
    return " ".join(text.lower().split())


def shingles(text, n=6):
    toks = norm(text).split()
    return {" ".join(toks[i:i + n]) for i in range(max(0, len(toks) - n + 1))}


def jaccard(a, b):
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


def containment(a, b):
    if not a or not b:
        return 0.0
    return len(a & b) / min(len(a), len(b))


def dhash(im, size=8):
    im = im.convert("L").resize((size + 1, size))
    p = im.tobytes()
    bits = 0
    for r in range(size):
        for c in range(size):
            bits = (bits << 1) | (1 if p[r * (size + 1) + c] > p[r * (size + 1) + c + 1] else 0)
    return bits


# ---------------------------------------------------------------- core pages
for need in REQUIRED_PAGES:
    if not (ROOT / need).exists():
        problems.append(f"missing required page/file: {need}")

# The retired random/stock image providers must never come back in the code.
for src in ROOT.glob("*.py"):
    if src.name == Path(__file__).name:
        continue
    text = src.read_text(encoding="utf-8", errors="ignore").lower()
    for bad in ("pollinations", "picsum", "unsplash.com/", "source.unsplash"):
        if bad in text:
            problems.append(f"{src.name}: forbidden image provider/token '{bad}'")

# ---------------------------------------------------------------- articles
ids, titles, image_hashes, seen_paths = {}, {}, {}, {}
content_sets = []
for k, a in allart:
    aid, title = a.get("id", ""), a.get("title", "")
    if not aid or not title:
        problems.append(f"article without id/title in {k}")
        continue
    if aid in ids:
        problems.append(f"duplicate article id: {aid}")
    ids[aid] = k
    tkey = norm(title)
    if tkey in titles:
        problems.append(f"duplicate title: {aid} == {titles[tkey]}")
    titles[tkey] = aid

    if arabic_ratio(title) < 0.55:
        problems.append(f"{aid}: title is not Arabic enough ({arabic_ratio(title):.2f})")
    if not (15 <= len(title) <= 115):
        warnings.append(f"{aid}: title length {len(title)}")
    if len(a.get("summary", "")) < 40:
        warnings.append(f"{aid}: summary shorter than 40 characters")
    if FLAG.search(title + a.get("summary", "") + a.get("content", "")):
        problems.append(f"{aid}: emoji flag in text (the old blue 'MA' box defect)")

    body = a.get("content", "")
    low = (title + " " + body).lower()
    for bad in JUNK:
        if JUNK_RX[bad].search(low):
            problems.append(f"{aid}: leftover junk word '{bad}'")
    if k not in TECH_CATS:
        for bad in JUNK_TECH:
            if JUNK_RX[bad].search(low):
                problems.append(f"{aid}: template leftover '{bad}' (only allowed inside a programming article)")
    tpl = TEMPLATE_RX.search(low)
    if tpl:
        problems.append(f"{aid}: unrendered template placeholder {tpl.group(0)}")
    if SEXUAL_RX.search(low):
        problems.append(f"{aid}: sexual/inappropriate term -> AdSense risk")
    if any(w in low for w in RISKY) and not a.get("sources"):
        problems.append(f"{aid}: sensitive headline without sources")

    wc = words(body)
    if k == "ar_books":
        if not (430 <= wc <= 820):
            problems.append(f"{aid}: books article {wc} words (must be 430-820)")
    else:
        if wc < 430:
            problems.append(f"{aid}: article too thin ({wc} words)")
        elif wc < 780:
            warnings.append(f"{aid}: article under 800 words ({wc})")
        elif wc > 1600:
            warnings.append(f"{aid}: article over 1500 words ({wc})")

    srcs = a.get("sources") or []
    if not isinstance(srcs, list):
        try:
            import ast
            srcs = ast.literal_eval(srcs)
        except Exception:
            srcs = []
    if k != "ar_books" and not srcs:
        problems.append(f"{aid}: no cited source")
    for s in srcs:
        url = s.get("url", "") if isinstance(s, dict) else str(s)
        if not url.startswith("http"):
            problems.append(f"{aid}: malformed source {url[:60]}")
            continue
        if build_site.is_moroccan(url, (s.get("publisher", "") if isinstance(s, dict) else "")) and k not in build_site.MOROCCAN_OK_CATS:
            problems.append(f"{aid}: Moroccan source in section {k} (it will be removed at build time)")
    if k != "ar_books" and len(srcs) < 2:
        warnings.append(f"{aid}: single-source article")

    # section rules
    if k in ("ar_local", "ar_cities"):
        if not srcs:
            problems.append(f"{aid}: Moroccan section without a Moroccan source")
        elif not any(build_site.is_moroccan(s.get("url", ""), s.get("publisher", "")) for s in srcs if isinstance(s, dict)):
            problems.append(f"{aid}: no Moroccan source although it is filed in {k}")
    if k == "ar_local":
        foreign = [s for s in srcs if isinstance(s, dict) and not build_site.is_moroccan(s.get("url", ""), s.get("publisher", ""))]
        if foreign:
            problems.append(f"{aid}: foreign source inside «أخبار المغرب» -> {foreign[0].get('url', '')[:70]}")
    if k == "ar_cities" and not a.get("city"):
        problems.append(f"{aid}: city article without a city")

    # image
    rel = a.get("image", "")
    p = ROOT / rel
    if not rel or not p.is_file():
        problems.append(f"{aid}: missing image {rel}")
    else:
        if p.suffix.lower() == ".svg":
            problems.append(f"{aid}: SVG placeholder image (blue 'MA' box defect)")
        elif p.stat().st_size < 8 * 1024:
            problems.append(f"{aid}: image smaller than 8 KB ({p.stat().st_size // 1024} KB)")
        credit = a.get("image_credit")
        if not credit:
            problems.append(f"{aid}: image without credit")
        try:
            from PIL import Image, ImageFilter, ImageStat
            im = Image.open(p)
            if im.width < 640 or im.height < 320:
                problems.append(f"{aid}: image too small ({im.width}x{im.height})")
            sharp = ImageStat.Stat(im.convert("L").filter(ImageFilter.FIND_EDGES)).var[0]
            if sharp < 80:
                problems.append(f"{aid}: blurry image (sharpness {sharp:.0f} < 80)")
            h = dhash(im)
            for other, (oh, orel) in image_hashes.items():
                if bin(h ^ oh).count("1") <= 6:
                    problems.append(f"{aid}: image looks like {other} ({rel} vs {orel})")
            image_hashes[aid] = (h, rel)
        except Exception as ex:
            warnings.append(f"{aid}: image could not be analysed ({str(ex)[:60]})")
        owner = seen_paths.get(rel)
        if owner and owner != aid:
            problems.append(f"{aid}: same image file reused ({rel} already belongs to {owner})")
        else:
            seen_paths[rel] = aid

    # built page markers
    page = ROOT / "articles" / f"{aid}.html"
    if not page.exists():
        problems.append(f"{aid}: article page was not built")
    else:
        html = page.read_text(encoding="utf-8")
        if 'class="img-credit"' not in html:
            problems.append(f"{aid}: page has no image credit caption")
        if srcs and 'class="sources"' not in html:
            problems.append(f"{aid}: page has no sources block")
        if '<link rel="canonical"' not in html:
            warnings.append(f"{aid}: no canonical URL (set SITE_URL in Actions)")
        if 'name="description" content=""' in html:
            problems.append(f"{aid}: empty meta description")

    content_sets.append((aid, shingles(body), shingles(title)))

# near-duplicate articles
for i in range(len(content_sets)):
    ai, abody, atitle = content_sets[i]
    for j in range(i + 1, len(content_sets)):
        bi, bbody, btitle = content_sets[j]
        tsim = jaccard(atitle, btitle)
        bsim = containment(abody, bbody)
        if tsim >= 0.72:
            problems.append(f"near-duplicate title: {ai} ~ {bi} ({tsim:.0%})")
        elif bsim >= 0.20:
            problems.append(f"near-duplicate article: {ai} ~ {bi} ({bsim:.0%} of 6-word sequences)")

# ---------------------------------------------------------------- sections
for k, name in build_site.CATEGORIES.items():
    n = len(data[k])
    if n == 0:
        warnings.append(f"section «{name}» is empty -> it must stay hidden until it has real articles")
    elif n < MIN_PER_CAT:
        problems.append(f"section «{name}» has only {n} articles (minimum {MIN_PER_CAT})")

total = len(allart)
if total < 30:
    problems.append(f"only {total} articles on the whole site: too thin for AdSense")
big = max((len(v) for v in data.values()), default=0)
if total and big / total > 0.55:
    warnings.append(f"one section holds {big}/{total} articles: balance the sections before applying")

# ---------------------------------------------------------------- report
print(f"AdSense audit: {total} articles, {len(image_hashes)} images checked")
for k in build_site.CATEGORIES:
    print(f"  {k:10s} {len(data[k]):3d}")
if warnings:
    print(f"\nWARNINGS ({len(warnings)}):")
    for w in sorted(set(warnings))[:40]:
        print("  -", w)
if problems:
    print(f"\nADSENSE AUDIT FAILED ({len(set(problems))}):")
    for p in sorted(set(problems))[:60]:
        print("  -", p)
    sys.exit(1)
print("\nAdSense audit OK: no duplicates, no broken/misclassified/dangerous content.")
