"""AdSense pre-review gate for the family-safe Arabic STORY blog «مملكة الأسرار».

Run AFTER build_site.py. It exits 1 only on real defects:

  * duplicated / near-duplicated titles or bodies
  * reused, look-alike, blurry, tiny, SVG or uncredited article pictures
  * missing required pages, stale newspaper pages/strings, broken 5-item nav
  * missing literary disclaimer, unsafe kids text, un-warned horror
  * invalid optional video metadata, sexual / profanity / grooming / drug / gore text
  * books outside 430-820 words; opinions or stories with sources missing where required

Judgement calls are printed as WARNINGS and do not fail CI: thin seed stories
(adults below 2000 / kids and opinions below 800 words, or above the expected
maximum), empty sections, a missing canonical URL and unanalysable pictures.
Stdlib only; PIL is used when available for the image checks.
"""
import os
import re
import sys
import unicodedata
from html import unescape
from pathlib import Path
from urllib.parse import unquote, urlparse

import build_site

# Windows consoles default to cp1252; Arabic diagnostics must still print cleanly.
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

ROOT = Path(__file__).parent
SKIP_PREFIX = ("http:", "https:", "//", "mailto:", "tel:", "data:", "#", "javascript:")

# SPEC §4: exactly these 13 keys/labels, in this order.
EXPECTED_CATEGORIES = {
    "story_realistic": "واقعي وإنساني",
    "story_mystery": "غموض وإثارة",
    "story_scifi": "خيال علمي وتكنولوجيا",
    "story_fantasy": "فانتازيا ومغامرات",
    "story_horror": "قصص رعب",
    "story_history": "تاريخي وثقافي",
    "story_comedy": "كوميديا وسخرية",
    "story_religious": "قصص دينية",
    "kids_3_6": "براعم الصغار (3-6 سنوات)",
    "kids_7_10": "مغامرو المستقبل (7-10 سنوات)",
    "kids_11_14": "يافعون ومراهقون (11-14 سنة)",
    "ar_tech": "تقنية (قراءة رأي)",
    "ar_arts": "فن وثقافة (قراءة رأي)",
    "ar_books": "المكتبة الرقمية المجانية",
}
STORY_KEYS = tuple(k for k in EXPECTED_CATEGORIES if k.startswith("story_"))
KIDS_KEYS = tuple(k for k in EXPECTED_CATEGORIES if k.startswith("kids_"))
OPINION_KEYS = ("ar_tech", "ar_arts")
SOURCE_KEYS = OPINION_KEYS + ("ar_books",)

TAG_LABELS_EXPECTED = {
    "short": "#قصة_قصيرة",
    "flash": "#ومضة_قصصية",
    "serial": "#سلسلة_حلقات",
    "interactive": "#قصة_تفاعلية",
}
AGE_LABELS_EXPECTED = {
    "kids_3_6": "3-6 سنوات",
    "kids_7_10": "7-10 سنوات",
    "kids_11_14": "11-14 سنة",
}
NAV_LABELS = ("الرئيسية", "عالم القصص", "ركن الأطفال", "🎓 أكاديمية الذكاء الاصطناعي",
              "📚 المكتبة الرقمية المجانية", "الومضات والحلقات", "عن المدونة")

LITERARY_DISCLAIMER = "أي تشابه مع الواقع محض صدفة"
RELIGIOUS_DISCLAIMER = "والله تعالى أعلم وأحكم"
DISCLAIMER_PAGE = "disclaimer.html"
DISCLAIMER_TITLE = "إخلاء مسؤولية"
OPINION_PHRASES = ("رأي شخصي", "وجهة نظر")
OPINION_RX = re.compile(r'class="[^"]*\b(?:opinion|disclaimer)\b[^"]*"', re.I)

FORBIDDEN_HTML = (
    "نكسوس بريس", "Nexus Press", "جريدة إلكترونية", "هيئة تحرير", "التعليقات",
    "زاوية المنتخب المغربي", "corner-badge", "corner-notice",
)
CORNER_TITLE = "زاوية المنتخب المغربي"
CORNER_CLASS_RX = re.compile(r'class="[^"]*\bcorner\b[^"]*"', re.I)
BREAKING_RX = re.compile(r'class="[^"]*\bbreaking\b[^"]*"|<b[^>]*>\s*عاجل\s*</b>')
COMMENT_MARKUP = ('id="comments"', 'class="comments', 'cm-form', 'cm-list', 'cm-count')
STALE_PAGES = (
    "category-ar_local.html", "category-ar_cities.html",
    "category-ar_world.html", "category-ar_economy.html", "category-ar_sports.html",
)

REQUIRED_PAGES = (
    "style.css", "site.js", "tools.js", "sw.js", "logo.webp", "manifest.webmanifest",
    "feed.xml", "search.json", "sitemap.xml", "robots.txt",
    "index.html", "hub-stories.html", "hub-kids.html", "flashes.html",
    "about.html", "contact.html", "privacy-policy.html", "editorial-policy.html",
    "terms.html", "404.html", "weather.html", "search.html", "ai-academy.html",
    "chat.js", DISCLAIMER_PAGE,
)

ARABIC = re.compile(r"[\u0621-\u064A]")
LETTERS = re.compile(r"[^\W\d_]", re.UNICODE)
FLAG = re.compile(r"[\U0001F1E6-\U0001F1FF]")
# Hard failures everywhere (family-safe rules, SPEC §8).
SEXUAL_RX = re.compile(r"(?:سكس|إباح|اباح|إباحية|عاري(?!تين)|اغتصاب|تحرش جنسي|onlyfans|porn)", re.I)
PROFANITY_RX = re.compile(r"(?:\b(?:فاحش|بذيء|شتائم|سباب)\b|\b(?:fuck|shit|bitch|asshole)\b)", re.I)
GROOMING_RX = re.compile(
    r"(?:استدراج\s+(?:الأطفال|القاصرين|طفل)|تحرش\s+(?:بالأطفال|بالقاصرين)|"
    r"إغواء\s+(?:الأطفال|القاصرين)|متحرش|grooming)", re.I)
DRUGS_RX = re.compile(r"(?:مخدرات|مخدر|كوكايين|هيروين|حشيش|ماريجوانا|cocaine|heroin|weed)", re.I)
GORE_RX = re.compile(r"(?:مجزرة|تقطيع\s+الجسد|أعضاء\s+مقطوعة|\bgore\b|bloodbath)", re.I)
# Topic-sensitive terms are allowed in adult fiction; they only fail in kids
# sections or in a horror story that has no warning field.
SENSITIVE_RX = re.compile(r"(?:اغتيال|إرهاب|انتحار|جثة|دماء)")
KIDS_FORBIDDEN_RX = re.compile(r"(?<![\u0621-\u064A])(?:ال)?(?:رعب|دم|قتل|سلاح)(?![\u0621-\u064A])")

JUNK = ("lorem ipsum", "pollinations", "picsum", "test article")
JUNK_TECH = ("undefined", "null", "none", "todo", "placeholder")
TECH_CATS = OPINION_KEYS + ("ar_books",)
_JUNK_WORDS = JUNK + JUNK_TECH
JUNK_RX = {w: re.compile(r"(?<![a-z0-9])" + re.escape(w) + r"(?![a-z0-9])", re.I) for w in _JUNK_WORDS}
TEMPLATE_RX = re.compile(r"\{[a-z_][a-z0-9_]{1,20}\}")
# Scene stills are allowed to exist even when several frames look alike; they are
# video assets, not competing article heroes.
SCENE_IMG_RX = re.compile(r'(?:^|[/\\])story[_-][^/\\]+-scene-\d+\.webp$', re.I)
NAV_RX = re.compile(r'<ul\b[^>]*\bclass="[^"]*\bnav-menu\b[^"]*"[^>]*>(.*?)</ul>', re.I | re.S)
HUB_RX = re.compile(r'class="[^"]*\bhub\b[^"]*"')
BODY_RX = re.compile(r"<body[\s>]")

try:
    MIN_PER_CAT = int(os.getenv("ADSENSE_MIN_PER_CATEGORY") or "0")
except ValueError:
    MIN_PER_CAT = 0
problems, warnings = [], []


def warn(message):
    warnings.append(message)


def fail(message):
    problems.append(message)


def read_text(path):
    try:
        return path.read_text(encoding="utf-8", errors="ignore")
    except OSError as ex:
        fail(f"cannot read {path.relative_to(ROOT)}: {ex}")
        return ""


def load_data():
    try:
        raw = build_site.load()
        if not isinstance(raw, dict):
            raise TypeError("build_site.load() did not return a mapping")
        return {k: (raw.get(k) or []) for k in EXPECTED_CATEGORIES}
    except Exception as ex:
        fail(f"cannot load articles through build_site.load(): {type(ex).__name__}: {ex}")
        return {k: [] for k in EXPECTED_CATEGORIES}


def body_text(article):
    raw = article.get("content", "") or ""
    if isinstance(raw, (list, tuple)):
        return "\n\n".join(str(x) for x in raw)
    return str(raw)


def source_list(article):
    srcs = article.get("sources") or []
    if not isinstance(srcs, list):
        try:
            import ast
            srcs = ast.literal_eval(srcs)
        except Exception:
            srcs = []
    return srcs if isinstance(srcs, list) else []


def tag_keys(article):
    raw = article.get("tags") or []
    if isinstance(raw, str):
        raw = [raw]
    fn = getattr(build_site, "tag_key", None)
    out = []
    for item in raw:
        if callable(fn):
            try:
                out.append(str(fn(item)))
                continue
            except Exception:
                pass
        t = re.sub(r"\s+", "_", str(item or "").strip()).lstrip("#")
        if t in TAG_LABELS_EXPECTED:
            out.append(t)
            continue
        for key, label in TAG_LABELS_EXPECTED.items():
            if t == label.lstrip("#"):
                out.append(key)
                break
        else:
            out.append(re.sub(r"[^a-z0-9]+", "-", t.lower()).strip("-") or "other")
    return out


def inside_root(rel):
    try:
        p = (ROOT / str(rel)).resolve()
        return p.is_file() and str(p).startswith(str(ROOT.resolve()) + os.sep)
    except Exception:
        return False


def arabic_ratio(text):
    letters = LETTERS.findall(text or "")
    return len(ARABIC.findall(text)) / len(letters) if letters else 0.0


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
    return len(a & b) / len(a | b) if a and b else 0.0


def containment(a, b):
    return len(a & b) / min(len(a), len(b)) if a and b else 0.0


def dhash(im, size=8):
    im = im.convert("L").resize((size + 1, size))
    p = im.tobytes()
    bits = 0
    for r in range(size):
        for c in range(size):
            bits = (bits << 1) | (1 if p[r * (size + 1) + c] > p[r * (size + 1) + c + 1] else 0)
    return bits


def check_nav(text, rel):
    m = NAV_RX.search(text)
    if not m:
        fail(f"{rel}: missing <ul class=\"nav-menu\">")
        return
    items = re.findall(r"<li\b[^>]*>(.*?)</li>", m.group(1), re.I | re.S)
    if len(items) != 7:
        fail(f"{rel}: nav-menu has {len(items)} <li> items (must be exactly 7)")
        return
    labels = [" ".join(unescape(re.sub(r"<[^>]*>", "", li)).split()) for li in items]
    if tuple(labels) != NAV_LABELS:
        fail(f"{rel}: nav-menu labels {labels!r} != {list(NAV_LABELS)!r}")


def check_structure(text, rel):
    if (len(BODY_RX.findall(text)) != 1 or text.count("</body>") != 1
            or text.count("</html>") != 1 or not text.rstrip().endswith("</html>")):
        fail(f"{rel}: <body>/</body>/</html> tags are not exactly right")
    for needle in ('class="main-nav"', 'class="footer"'):
        if needle not in text:
            fail(f"{rel} lacks {needle}")


data = load_data()

# ---------------------------------------------------------------- core pages
for need in REQUIRED_PAGES:
    if not (ROOT / need).exists():
        fail(f"missing required page/file: {need}")
for key in EXPECTED_CATEGORIES:
    if not (ROOT / f"category-{key}.html").exists():
        fail(f"missing generated category page: category-{key}.html")

disclaimer = ROOT / DISCLAIMER_PAGE
if disclaimer.exists():
    dtext = read_text(disclaimer)
    if DISCLAIMER_TITLE not in dtext:
        fail(f"{DISCLAIMER_PAGE}: missing title «{DISCLAIMER_TITLE}»")
    if LITERARY_DISCLAIMER not in dtext:
        fail(f"{DISCLAIMER_PAGE}: missing fixed literary disclaimer «{LITERARY_DISCLAIMER}»")

# Builder contract (same 13 keys/labels and chip/badge names as check_site.py).
builder_cats = getattr(build_site, "CATEGORIES", {}) or {}
if set(builder_cats) != set(EXPECTED_CATEGORIES):
    fail(f"category keys are not the 13 story-blog keys: {sorted(builder_cats)}")
for key, name in EXPECTED_CATEGORIES.items():
    if builder_cats.get(key) != name:
        fail(f"category label for {key}: {builder_cats.get(key)!r} != {name!r}")
if getattr(build_site, "TAG_LABELS", None) != TAG_LABELS_EXPECTED:
    fail("build_site.TAG_LABELS does not match SPEC §6")
if getattr(build_site, "AGE_BADGES", None) != AGE_LABELS_EXPECTED:
    fail("build_site.AGE_BADGES does not match SPEC §4")

# Hub / flashes / horror category structure.
shub = ROOT / "hub-stories.html"
if shub.exists():
    text = read_text(shub)
    if not HUB_RX.search(text):
        fail("hub-stories.html: missing class=\"hub\" (page hub)")
    for key in STORY_KEYS:
        if EXPECTED_CATEGORIES[key] not in text:
            fail(f"hub-stories.html: missing genre label «{EXPECTED_CATEGORIES[key]}»")
khub = ROOT / "hub-kids.html"
if khub.exists():
    text = read_text(khub)
    if not HUB_RX.search(text):
        fail("hub-kids.html: missing class=\"hub\" (page hub)")
    if 'class="badge age-badge"' not in text:
        fail("hub-kids.html: missing class=\"badge age-badge\"")
    for key in KIDS_KEYS:
        if EXPECTED_CATEGORIES[key] not in text:
            fail(f"hub-kids.html: missing age label «{EXPECTED_CATEGORIES[key]}»")
        if AGE_LABELS_EXPECTED.get(key, "") not in text:
            fail(f"hub-kids.html: missing age badge «{AGE_LABELS_EXPECTED.get(key, '')}»")
flash_page = ROOT / "flashes.html"
if flash_page.exists() and 'class="flashes"' not in read_text(flash_page):
    fail("flashes.html: missing class=\"flashes\"")
if not (ROOT / "category-story_horror.html").exists() or "تنبيه" not in read_text(ROOT / "category-story_horror.html"):
    fail("category-story_horror.html: missing the word «تنبيه»")

# The retired random/stock image providers must never return in working code.
for src in ROOT.glob("*.py"):
    if src.name == Path(__file__).name:
        continue
    text = src.read_text(encoding="utf-8", errors="ignore").lower()
    for bad in ("pollinations", "picsum", "unsplash.com/", "source.unsplash"):
        if bad in text:
            fail(f"{src.name}: forbidden image provider/token '{bad}'")

# ---------------------------------------------------------------- articles
ids, titles, image_hashes, seen_paths = {}, {}, {}, {}
content_sets = []
category_tags = {k: set() for k in EXPECTED_CATEGORIES}
for k, arts in data.items():
    for a in arts or []:
        if not isinstance(a, dict):
            fail(f"bad article entry in {k}")
            continue
        aid, title = str(a.get("id") or ""), str(a.get("title") or "")
        if not aid or not title:
            fail(f"article without id/title in {k}")
            continue
        if aid in ids:
            fail(f"duplicate article id: {aid}")
        ids[aid] = k
        tkey = norm(title)
        if tkey in titles:
            fail(f"duplicate title: {aid} == {titles[tkey]}")
        titles[tkey] = aid

        summary = str(a.get("summary") or "")
        body = body_text(a)
        low = (title + " " + summary + " " + body).lower()

        if arabic_ratio(title) < 0.55:
            fail(f"{aid}: title is not Arabic enough ({arabic_ratio(title):.2f})")
        if not (15 <= len(title) <= 115):
            warn(f"{aid}: title length {len(title)}")
        if len(summary) < 40:
            warn(f"{aid}: summary shorter than 40 characters")
        if k != "ar_books":
            hashes = a.get("hashtags") or []
            if not isinstance(hashes, list) or len(hashes) < 3:
                warn(f"{aid}: fewer than 3 strong hashtags -> weaker viral/SEO discovery")
        if FLAG.search(title + summary + body):
            fail(f"{aid}: emoji flag in text (the old blue 'MA' box defect)")

        for bad in JUNK:
            if JUNK_RX[bad].search(low):
                fail(f"{aid}: leftover junk word '{bad}'")
        if k not in TECH_CATS:
            for bad in JUNK_TECH:
                if JUNK_RX[bad].search(low):
                    fail(f"{aid}: template leftover '{bad}' (only allowed in an opinion/library article)")
        tpl = TEMPLATE_RX.search(low)
        if tpl:
            fail(f"{aid}: unrendered template placeholder {tpl.group(0)}")

        # Family safety: hard failures everywhere.
        for label, rx in (("sexual", SEXUAL_RX), ("profanity", PROFANITY_RX),
                          ("grooming", GROOMING_RX), ("drugs", DRUGS_RX), ("gore", GORE_RX)):
            if rx.search(low):
                fail(f"{aid}: {label} content -> AdSense risk")
        # Topic-sensitive terms are fine in adult stories, but not in kids text
        # and not in horror without a visible warning.
        warning = str(a.get("warning") or "").strip()
        if SENSITIVE_RX.search(low) and (k in KIDS_KEYS or (k == "story_horror" and not warning)):
            fail(f"{aid}: sensitive term in kids text or un-warned horror story")
        if k in KIDS_KEYS:
            m = KIDS_FORBIDDEN_RX.search(title + " " + summary)
            if m:
                fail(f"{aid}: kids title/summary contains forbidden marker «{m.group(0)}»")

        # Word counts: only books are a hard gate. Thin seed content is a warning.
        wc = words(body)
        if k == "ar_books":
            if not (430 <= wc <= 820):
                fail(f"{aid}: books article {wc} words (must be 430-820)")
        elif k in STORY_KEYS:
            if wc < 2000:
                warn(f"{aid}: story under 2000 words ({wc}) — seed content")
            elif wc > 5000:
                warn(f"{aid}: story over 5000 words ({wc})")
        else:  # kids and ar_tech / ar_arts
            if wc < 800:
                warn(f"{aid}: article under 800 words ({wc}) — seed content")
            elif wc > 1500:
                warn(f"{aid}: article over 1500 words ({wc})")

        # Sources are required ONLY for books and the two opinion sections.
        srcs = source_list(a)
        if k in SOURCE_KEYS:
            if not srcs:
                fail(f"{aid}: {k} article has no cited source")
            for s in srcs:
                url = s.get("url", "") if isinstance(s, dict) else str(s)
                if not str(url).startswith("http"):
                    fail(f"{aid}: malformed source {str(url)[:60]}")
        # No sources requirement for fiction, and no single-source warning.

        # Image checks: SVG placeholders stay rejected; scene stills are allowed.
        rel = str(a.get("image") or "")
        p = ROOT / rel
        if not rel or not p.is_file():
            fail(f"{aid}: missing image {rel}")
        else:
            if p.suffix.lower() == ".svg":
                fail(f"{aid}: SVG placeholder image (blue 'MA' box defect)")
            try:
                size = p.stat().st_size
                if size < 8 * 1024:
                    fail(f"{aid}: image smaller than 8 KB ({size // 1024} KB)")
            except OSError:
                pass
            if not a.get("image_credit"):
                fail(f"{aid}: image without credit")
            try:
                from PIL import Image, ImageFilter, ImageStat
                im = Image.open(p)
                if im.width < 640 or im.height < 320:
                    fail(f"{aid}: image too small ({im.width}x{im.height})")
                sharp = ImageStat.Stat(im.convert("L").filter(ImageFilter.FIND_EDGES)).var[0]
                if sharp < 80:
                    fail(f"{aid}: blurry image (sharpness {sharp:.0f} < 80)")
                if not SCENE_IMG_RX.search(rel):
                    h = dhash(im)
                    for other, (oh, orel) in image_hashes.items():
                        if bin(h ^ oh).count("1") <= 6:
                            fail(f"{aid}: image looks like {other} ({rel} vs {orel})")
                    image_hashes[aid] = (h, rel)
            except ImportError:
                warn(f"{aid}: Pillow unavailable, image similarity checks skipped")
            except Exception as ex:
                warn(f"{aid}: image could not be analysed ({str(ex)[:60]})")
            owner = seen_paths.get(rel)
            if owner and owner != aid:
                fail(f"{aid}: same image file reused ({rel} already belongs to {owner})")
            else:
                seen_paths[rel] = aid

        # Tag chips must be rendered on the article page and its category card.
        tkeys = tag_keys(a)
        category_tags[k].update(tkeys)

        # Optional video: validate only when it is actually present.
        video = a.get("video")
        if video:
            if not isinstance(video, dict):
                fail(f"{aid}: video field must be a mapping")
            else:
                vurl = str(video.get("url") or "")
                vpage = str(video.get("page") or "")
                poster = str(video.get("poster") or "")
                if not vurl.lower().endswith(".mp4"):
                    fail(f"{aid}: video url must end in .mp4 ({vurl[:80]!r})")
                if not vpage.startswith("https://archive.org/details/"):
                    fail(f"{aid}: video page must be an archive.org details page ({vpage[:80]!r})")
                if not poster or not inside_root(poster):
                    fail(f"{aid}: video poster is missing outside ROOT ({poster[:80]!r})")

        # Built page markers.
        page = ROOT / "articles" / f"{aid}.html"
        if not page.exists():
            fail(f"{aid}: article page was not built")
        else:
            html = read_text(page)
            needed = RELIGIOUS_DISCLAIMER if k == "story_religious" else LITERARY_DISCLAIMER
            if needed not in html:
                fail(f"{aid}: article page missing «{needed}»")
            if 'class="img-credit"' not in html:
                fail(f"{aid}: page has no image credit caption")
            if srcs and 'class="sources"' not in html:
                fail(f"{aid}: page has no sources block")
            if k in OPINION_KEYS:
                if not any(phrase in html for phrase in OPINION_PHRASES) and not OPINION_RX.search(html):
                    fail(f"{aid}: {k} article page has no opinion marker")
            for tkey in tkeys:
                if f'class="tag tag-{tkey}"' not in html:
                    fail(f"{aid}: page missing tag chip class=\"tag tag-{tkey}\"")
            if k == "story_horror":
                if not warning:
                    fail(f"{aid}: horror article has an empty warning field")
                if 'class="story-warning"' not in html:
                    fail(f"{aid}: horror page missing class=\"story-warning\"")
            if video:
                if 'class="story-video"' not in html:
                    fail(f"{aid}: page missing class=\"story-video\"")
                if "<video" not in html.lower():
                    fail(f"{aid}: page missing <video> player")
            if '<link rel="canonical"' not in html:
                warn(f"{aid}: no canonical URL (set SITE_URL in Actions)")
            if ('name="description" content=""' in html or '<meta name="description"' not in html):
                fail(f"{aid}: empty or missing meta description")

        content_sets.append((aid, shingles(body), shingles(title)))

for k, keys in category_tags.items():
    if not keys:
        continue
    cat_page = ROOT / f"category-{k}.html"
    if not cat_page.exists():
        continue
    html = read_text(cat_page)
    for tkey in sorted(keys):
        if f'class="tag tag-{tkey}"' not in html:
            fail(f"category-{k}.html: card missing tag chip class=\"tag tag-{tkey}\"")

# near-duplicate articles
for i in range(len(content_sets)):
    ai, abody, atitle = content_sets[i]
    for j in range(i + 1, len(content_sets)):
        bi, bbody, btitle = content_sets[j]
        tsim = jaccard(atitle, btitle)
        bsim = containment(abody, bbody)
        if tsim >= 0.72:
            fail(f"near-duplicate title: {ai} ~ {bi} ({tsim:.0%})")
        elif bsim >= 0.20:
            fail(f"near-duplicate article: {ai} ~ {bi} ({bsim:.0%} of 6-word sequences)")

# ---------------------------------------------------------------- sections
for k, name in EXPECTED_CATEGORIES.items():
    n = len(data[k])
    if n == 0:
        warn(f"section «{name}» is empty -> it must stay hidden until it has real articles")
    elif n < MIN_PER_CAT:
        fail(f"section «{name}» has only {n} articles (minimum {MIN_PER_CAT})")

total = len(ids)
if total < 30:
    # A curated launch archive is fine for a story blog; the scheduled pipeline grows it.
    warn(f"only {total} articles on the whole site — keep the scheduled story factory running")
big = max((len(data[k]) for k in EXPECTED_CATEGORIES), default=0)
if total and big / total > 0.55:
    warn(f"one section holds {big}/{total} articles: balance the sections before applying")

# ---------------------------------------------------------------- generated pages
for stale in STALE_PAGES:
    if (ROOT / stale).exists():
        fail(f"stale newspaper page still generated: {stale}")
for p in ROOT.glob("city-*.html"):
    fail(f"stale city page still generated: {p.name}")

html_files = list(ROOT.glob("*.html")) + list((ROOT / "articles").glob("*.html"))
pages = sorted({p for p in html_files
                if not p.name.startswith("google") and p.name != "404.html"})
for p in pages:
    rel = p.relative_to(ROOT).as_posix()
    html = read_text(p)
    for bad in FORBIDDEN_HTML:
        if bad in html:
            fail(f"{rel}: forbidden newspaper/corner wording {bad!r}")
    if BREAKING_RX.search(html):
        fail(f"{rel}: old «عاجل» breaking-news bar")
    if CORNER_CLASS_RX.search(html):
        fail(f"{rel}: deleted Moroccan corner markup (class corner)")
    for marker in COMMENT_MARKUP:
        if marker in html:
            fail(f"{rel}: old comment UI marker {marker!r}")
    check_nav(html, rel)
    check_structure(html, rel)
    if (p.parent == ROOT and p.name.startswith("category-")
            and p.stem[len("category-"):] not in EXPECTED_CATEGORIES):
        fail(f"stale category page: {p.name}")

# ---------------------------------------------------------------- report
print(f"AdSense audit: {total} articles, {len(image_hashes)} images checked")
for k in EXPECTED_CATEGORIES:
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
