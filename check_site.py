"""Quality gate for the family-safe Arabic STORY blog «مملكة الأسرار».

Run AFTER build_site.py. It exits 1 when the built site has broken internal links,
missing core/generated pages, a stale newspaper page/string, an invalid nav menu,
missing literary disclaimer, unsafe kids/horror/video data, or tag chips that do
not match the articles.json contract. Stdlib only; build_site.py supplies the
authoritative categories, tag keys and age badges.
"""
import os
import re
import sys
from html import escape as html_escape, unescape
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

# SPEC §4: exactly these 14 keys/labels, in this order.
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

# SPEC §6 / §12: non-clickable form/length chips and age badges.
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
NAV_LABELS = ("الرئيسية", "عالم القصص", "ركن الأطفال", "قراءات نكسوس",
              "📚 المكتبة الرقمية", "🛒 عروض أمازون", "🎓 الأكاديمية والخدمات")

# SPEC §10/§12: the fixed literary disclaimer must survive on every article page.
LITERARY_DISCLAIMER = "أي تشابه مع الواقع محض صدفة"
RELIGIOUS_DISCLAIMER = "والله تعالى أعلم وأحكم"
DISCLAIMER_PAGE = "disclaimer.html"
DISCLAIMER_TITLE = "إخلاء مسؤولية"
OPINION_PHRASES = ("رأي شخصي", "وجهة نظر")
OPINION_RX = re.compile(r'class="[^"]*\b(?:opinion|disclaimer)\b[^"]*"', re.I)

# Retired newspaper identity, comments, breaking bar and the deleted Moroccan corner.
FORBIDDEN_HTML = (
    "نكسوس بريس", "Nexus Press", "جريدة إلكترونية", "هيئة تحرير", "التعليقات",
    "زاوية المنتخب المغربي", "corner-badge", "corner-notice",
)
CORNER_TITLE = "زاوية المنتخب المغربي"
CORNER_CLASS_RX = re.compile(r'class="[^"]*\bcorner\b[^"]*"', re.I)
BREAKING_RX = re.compile(r'class="[^"]*\bbreaking\b[^"]*"|<b[^>]*>\s*عاجل\s*</b>')
COMMENT_MARKUP = ('id="comments"', 'class="comments', 'cm-form', 'cm-list', 'cm-count')

# Old news pages only. category-ar_tech.html and category-ar_arts.html are VALID
# opinion sections now and must NOT be flagged.
STALE_PAGES = (
    "category-ar_local.html", "category-ar_cities.html",
    "category-ar_world.html", "category-ar_economy.html", "category-ar_sports.html",
)

# Small Arabic marker list for the kids sections (word-boundary aware, so e.g.
# «دموع» or «دمشق» do not trigger a false alarm).
KIDS_FORBIDDEN_RX = re.compile(
    r"(?<![\u0621-\u064A])(?:ال)?(?:رعب|دم|قتل|سلاح)(?![\u0621-\u064A])")

NAV_RX = re.compile(r'<ul\b[^>]*\bclass="[^"]*\bnav-menu\b[^"]*"[^>]*>(.*?)</ul>', re.I | re.S)
HUB_RX = re.compile(r'class="[^"]*\bhub\b[^"]*"')
HERO_RX = re.compile(r'<img\s+class="hero"[^>]*src="\.\./([^"?]+)')
BODY_RX = re.compile(r"<body[\s>]")

CORE_FILES = (
    "style.css", "site.js", "tools.js", "sw.js", "logo.webp", "manifest.webmanifest",
    "feed.xml", "search.json", "sitemap.xml", "robots.txt",
    "index.html", "hub-stories.html", "hub-kids.html", "media.html", "flashes.html",
    "about.html", "contact.html", "privacy-policy.html", "editorial-policy.html",
    "terms.html", "404.html", "weather.html", "search.html", "ai-academy.html",
    "chat.js", DISCLAIMER_PAGE,
)

problems = []


def add(message):
    problems.append(message)


def read_text(path):
    try:
        return path.read_text(encoding="utf-8", errors="ignore")
    except OSError as ex:
        add(f"cannot read {path.relative_to(ROOT)}: {ex}")
        return ""


def load_data():
    """Never crash on legacy/malformed data: report the failure and keep checking."""
    try:
        raw = build_site.load()
        if not isinstance(raw, dict):
            raise TypeError("build_site.load() did not return a mapping")
        return {k: (raw.get(k) or []) for k in EXPECTED_CATEGORIES}
    except Exception as ex:
        add(f"cannot load articles through build_site.load(): {type(ex).__name__}: {ex}")
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


def hashtag_list(article):
    raw = article.get("hashtags") or []
    if isinstance(raw, str):
        raw = re.split(r"[\s,،]+", raw)
    out = []
    for h in raw:
        h = str(h or "").strip()
        if h:
            out.append(h if h.startswith("#") else "#" + h)
    return out


def inside_root(rel):
    """A poster path must be a real local file inside the repository."""
    try:
        p = (ROOT / str(rel)).resolve()
        return p.is_file() and str(p).startswith(str(ROOT.resolve()) + os.sep)
    except Exception:
        return False


def check_nav(text, rel):
    m = NAV_RX.search(text)
    if not m:
        add(f"{rel}: missing <ul class=\"nav-menu\">")
        return
    items = re.findall(r"<li\b[^>]*>(.*?)</li>", m.group(1), re.I | re.S)
    if len(items) != 7:
        add(f"{rel}: nav-menu has {len(items)} <li> items (must be exactly 7)")
        return
    # Drop the nested sub-menu panels; only the 7 root labels are compared.
    labels = []
    for li in items:
        root = re.sub(r'<div\b[^>]*\bsub-menu\b.*?</div>', '', li, flags=re.I | re.S)
        labels.append(" ".join(unescape(re.sub(r"<[^>]*>", "", root)).split()))
    if tuple(labels) != NAV_LABELS:
        add(f"{rel}: nav-menu labels {labels!r} != {list(NAV_LABELS)!r}")


def check_structure(text, rel):
    if (len(BODY_RX.findall(text)) != 1 or text.count("</body>") != 1
            or text.count("</html>") != 1 or not text.rstrip().endswith("</html>")):
        add(f"{rel}: <body>/</body>/</html> tags are not exactly right")
    for needle in ('class="main-nav"', 'class="footer"'):
        if needle not in text:
            add(f"{rel} lacks {needle}")


data = load_data()

# ---- 1. authoritative builder contract --------------------------------------
builder_cats = getattr(build_site, "CATEGORIES", {}) or {}
if set(builder_cats) != set(EXPECTED_CATEGORIES):
    add(f"category keys are not the 14 story-blog keys: {sorted(builder_cats)}")
for key, name in EXPECTED_CATEGORIES.items():
    if builder_cats.get(key) != name:
        add(f"category label for {key}: {builder_cats.get(key)!r} != {name!r}")
if getattr(build_site, "TAG_LABELS", None) != TAG_LABELS_EXPECTED:
    add("build_site.TAG_LABELS does not match SPEC §6 (short/flash/serial/interactive)")
if getattr(build_site, "AGE_BADGES", None) != AGE_LABELS_EXPECTED:
    add("build_site.AGE_BADGES does not match SPEC §4 (three kids age labels)")

# ---- 2. required pages -------------------------------------------------------
for need in CORE_FILES:
    if not (ROOT / need).exists():
        add(f"missing core file: {need}")
for key in EXPECTED_CATEGORIES:
    if not (ROOT / f"category-{key}.html").exists():
        add(f"missing generated category page: category-{key}.html")

# ---- 3. disclaimer page (literary, not an opinion disclaimer) ---------------
disclaimer = ROOT / DISCLAIMER_PAGE
if disclaimer.exists():
    dtext = read_text(disclaimer)
    if DISCLAIMER_TITLE not in dtext:
        add(f"{DISCLAIMER_PAGE}: missing title «{DISCLAIMER_TITLE}»")
    if LITERARY_DISCLAIMER not in dtext:
        add(f"{DISCLAIMER_PAGE}: missing fixed literary disclaimer «{LITERARY_DISCLAIMER}»")

# ---- 4. hub / flash / horror category pages ---------------------------------
stories_hub = ROOT / "hub-stories.html"
if stories_hub.exists():
    text = read_text(stories_hub)
    if not HUB_RX.search(text):
        add("hub-stories.html: missing class=\"hub\" (page hub)")
    for key in STORY_KEYS:
        if EXPECTED_CATEGORIES[key] not in text:
            add(f"hub-stories.html: missing genre label «{EXPECTED_CATEGORIES[key]}»")

kids_hub = ROOT / "hub-kids.html"
if kids_hub.exists():
    text = read_text(kids_hub)
    if not HUB_RX.search(text):
        add("hub-kids.html: missing class=\"hub\" (page hub)")
    if 'class="badge age-badge"' not in text:
        add("hub-kids.html: missing class=\"badge age-badge\"")
    for key in KIDS_KEYS:
        if EXPECTED_CATEGORIES[key] not in text:
            add(f"hub-kids.html: missing age label «{EXPECTED_CATEGORIES[key]}»")
        badge = AGE_LABELS_EXPECTED.get(key, "")
        if badge and badge not in text:
            add(f"hub-kids.html: missing age badge «{badge}»")

flashes = ROOT / "flashes.html"
if flashes.exists() and 'class="flashes"' not in read_text(flashes):
    add("flashes.html: missing class=\"flashes\"")

horror_cat = ROOT / "category-story_horror.html"
if not horror_cat.exists() or "تنبيه" not in read_text(horror_cat):
    add("category-story_horror.html: missing the word «تنبيه»")

# ---- 5. every generated page: nav, structure, forbidden leftovers, links -----
html_files = list(ROOT.glob("*.html")) + list((ROOT / "articles").glob("*.html"))
pages = sorted({p for p in html_files
                if not p.name.startswith("google") and p.name != "404.html"})
page_texts = {}
images = {}
for page in pages:
    rel = page.relative_to(ROOT).as_posix()
    text = read_text(page)
    page_texts[page] = text

    for bad in FORBIDDEN_HTML:
        if bad in text:
            add(f"{rel}: forbidden newspaper/corner wording {bad!r}")
    if BREAKING_RX.search(text):
        add(f"{rel}: old «عاجل» breaking-news bar")
    if CORNER_CLASS_RX.search(text):
        add(f"{rel}: deleted Moroccan corner markup (class corner)")
    for marker in COMMENT_MARKUP:
        if marker in text:
            add(f"{rel}: old comment UI marker {marker!r}")

    check_nav(text, rel)
    check_structure(text, rel)

    if (page.parent == ROOT and page.name.startswith("category-")
            and page.stem[len("category-"):] not in EXPECTED_CATEGORIES):
        add(f"stale category page: {page.name}")

    for val in re.findall(r'(?:href|src)="([^"]+)"', text):
        if not val or val.startswith(SKIP_PREFIX):
            continue
        target = (page.parent / unquote(urlparse(val).path)).resolve()
        if not target.exists():
            add(f"{rel} -> missing {val}")

    if page.parent.name == "articles":
        m = HERO_RX.search(text)
        if m:
            images.setdefault(unquote(m.group(1)), []).append(page.name)

for img, owners in images.items():
    if len(owners) > 1:
        add(f"same image used by several articles: {img} -> {owners}")

# ---- 6. article-level contract ----------------------------------------------
category_tags = {k: set() for k in EXPECTED_CATEGORIES}
for key, arts in data.items():
    for a in arts or []:
        if not isinstance(a, dict):
            add(f"bad article entry in {key}")
            continue
        aid = str(a.get("id") or "")
        title = str(a.get("title") or "")
        if not aid or not title:
            add(f"article without id/title in {key}")
            continue
        apage = ROOT / "articles" / f"{aid}.html"
        if not apage.exists():
            add(f"{aid}: article page was not built")
            continue
        text = page_texts.get(apage)
        if text is None:
            text = read_text(apage)

        needed = RELIGIOUS_DISCLAIMER if key == "story_religious" else LITERARY_DISCLAIMER
        if needed not in text:
            add(f"{aid}: article page missing «{needed}»")

        # SPEC §6/§12: every tag on an article must be rendered as a plain chip.
        keys = tag_keys(a)
        category_tags[key].update(keys)
        for tkey in keys:
            needle = f'class="tag tag-{tkey}"'
            if needle not in text:
                add(f"{aid}: article page missing tag chip {needle}")

        # SPEC §6/§15: strong discovery hashtags are required on every new story/opinion
        # and must actually be rendered on the built page (the four preserved books are exempt).
        hashes = hashtag_list(a)
        if key != "ar_books":
            if len(hashes) < 3:
                add(f"{aid}: fewer than 3 strong hashtags ({len(hashes)})")
            for h in hashes:
                if f'<span class="hashtag">{html_escape(h)}</span>' not in text:
                    add(f"{aid}: article page missing hashtag chip {h!r}")

        # Opinion readings (not fiction) need a personal-opinion marker + sources.
        if key in OPINION_KEYS:
            if not any(p in text for p in OPINION_PHRASES) and not OPINION_RX.search(text):
                add(f"{aid}: {key} article missing opinion marker «رأي شخصي»/«وجهة نظر»")
            if not source_list(a):
                add(f"{aid}: {key} article has no sources entry")

        # Kids sections: no horror/violence markers in title or summary.
        if key in KIDS_KEYS:
            headline = title + " " + str(a.get("summary") or "")
            m = KIDS_FORBIDDEN_RX.search(headline)
            if m:
                add(f"{aid}: kids title/summary contains forbidden marker «{m.group(0)}»")

        # Psychological horror: a warning is mandatory in data AND on the page.
        if key == "story_horror":
            warning = str(a.get("warning") or "").strip()
            if not warning:
                add(f"{aid}: horror article has an empty warning field")
            if 'class="story-warning"' not in text:
                add(f"{aid}: horror article page missing class=\"story-warning\"")

        # Video is optional; local narrated files and legacy archive.org links are both valid.
        video = a.get("video")
        if video:
            if not isinstance(video, dict):
                add(f"{aid}: video field must be a mapping")
            else:
                parts = video.get("parts")
                if isinstance(parts, list) and parts:
                    urls = [str(x.get("url") if isinstance(x, dict) else x) for x in parts]
                else:
                    urls = [str(video.get("url") or "")]
                page_url = str(video.get("page") or "")
                poster = str(video.get("poster") or "")
                if not urls or any(not u.lower().endswith(".mp4") for u in urls):
                    add(f"{aid}: video urls must end in .mp4")
                if page_url and not page_url.startswith("https://archive.org/details/"):
                    add(f"{aid}: video page must be an archive.org details page ({page_url[:80]!r})")
                if not poster or not inside_root(poster):
                    add(f"{aid}: video poster is missing outside ROOT ({poster[:80]!r})")
                if 'class="story-video"' not in text:
                    add(f'{aid}: article page missing class="story-video"')
                if "<video" not in text.lower():
                    add(f"{aid}: article page missing <video> player")
                for u in urls:
                    if u.startswith(("http://", "https://")):
                        continue
                    if not (ROOT / u.lstrip("/")).is_file():
                        add(f"{aid}: missing local video file ({u})")

        audio = a.get("audio")
        if audio:
            if isinstance(audio, str):
                audio = {"url": audio}
            if not isinstance(audio, dict):
                add(f"{aid}: audio field must be a mapping")
            else:
                u = str(audio.get("url") or "")
                if not u.lower().endswith((".mp3", ".m4a")):
                    add(f"{aid}: audio url must end in .mp3 or .m4a ({u[:80]!r})")
                if not u.startswith(("http://", "https://")) and not (ROOT / u.lstrip("/")).is_file():
                    add(f"{aid}: missing local audio file ({u})")
                if "<audio" not in text.lower():
                    add(f"{aid}: article page missing <audio> player")

# Cards on category pages must carry the same chips (build_site.card()).
for key, keys in category_tags.items():
    if not keys:
        continue
    cat_page = ROOT / f"category-{key}.html"
    if not cat_page.exists():
        continue
    text = page_texts.get(cat_page)
    if text is None:
        text = read_text(cat_page)
    for tkey in sorted(keys):
        if f'class="tag tag-{tkey}"' not in text:
            add(f"category-{key}.html: card missing tag chip class=\"tag tag-{tkey}\"")

# ---- 7. stale pages ---------------------------------------------------------
for stale in STALE_PAGES:
    if (ROOT / stale).exists():
        add(f"stale newspaper page still generated: {stale}")
for p in ROOT.glob("city-*.html"):
    add(f"stale city page still generated: {p.name}")

if problems:
    print("SITE CHECK FAILED:")
    print("\n".join(sorted(set(problems))[:50]))
    sys.exit(1)
print(f"site check OK: {len(pages)} pages, all internal links and images exist")
