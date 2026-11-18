"""Builds the whole static Arabic story blog «مملكة الأسرار» from articles.json.

Outputs: index.html, hub-stories.html, hub-kids.html, flashes.html,
category-<key>.html (13), articles/<id>.html, about/contact/privacy-policy/editorial-policy/
terms/disclaimer, ai-academy.html, weather.html, search.html, search.json, feed.xml,
sitemap.xml, robots.txt, manifest.webmanifest, sw.js.

«مملكة الأسرار» is a family-safe creative story blog written by نكسوس. There is no news,
no newsroom, no sources for fiction and no comments. Every story is an original creative
work and any resemblance to reality is purely coincidental.
"""
import html
import json
import os
import re
import urllib.parse
from datetime import datetime, timezone
from pathlib import Path

import ai_hub
import legal
try:
    import style_guide
except Exception:          # the site must still build if the module is missing
    style_guide = None

ROOT = Path(__file__).parent
REPO = os.getenv("GITHUB_REPOSITORY", "")  # e.g. user/nexus-blog (set automatically in Actions)
SITE_URL = os.getenv("SITE_URL") or (
    f"https://{REPO.split('/')[0]}.github.io/{REPO.split('/')[1]}" if "/" in REPO else "")
CONTACT_EMAIL = os.getenv("CONTACT_EMAIL") or "nadia.bouizgarne1@gmail.com"
ADSENSE_CLIENT = os.getenv("ADSENSE_CLIENT", "")  # ca-pub-XXXXXXXXXXXXXXXX after approval
# Newsletter: leave empty -> subscribers are e-mailed to CONTACT_EMAIL through FormSubmit.
# Or set NEWSLETTER_BUTTONDOWN=<your buttondown username> to use Buttondown (it can e-mail feed.xml daily).
NEWSLETTER_BUTTONDOWN = os.getenv("NEWSLETTER_BUTTONDOWN", "")
# Google Apps Script web-app URL (Code.gs): contact form + newsletter. Set it as GitHub variable NP_API.
NP_API = os.getenv("NP_API", "").strip()
POLL_NS = "np-" + (re.sub(r"[^a-z0-9]+", "-", REPO.lower()).strip("-") if REPO else "nexus-blog")

# Exactly the 13 sections of the story blog (SPEC §4).
CATEGORIES = {
    "story_realistic": "واقعي وإنساني",
    "story_mystery": "غموض وإثارة",
    "story_scifi": "خيال علمي وتكنولوجيا",
    "story_fantasy": "فانتازيا ومغامرات",
    "story_horror": "رعب نفسي",
    "story_history": "تاريخي وثقافي",
    "story_comedy": "كوميديا وسخرية",
    "kids_3_6": "براعم الصغار (3-6 سنوات)",
    "kids_7_10": "مغامرو المستقبل (7-10 سنوات)",
    "kids_11_14": "يافعون ومراهقون (11-14 سنة)",
    "ar_tech": "تقنية (قراءة رأي)",
    "ar_arts": "فن وثقافة (قراءة رأي)",
    "ar_books": "المكتبة الرقمية المجانية",
}

GROUP_STORIES = [k for k in CATEGORIES if k.startswith("story_")]
GROUP_KIDS = [k for k in CATEGORIES if k.startswith("kids_")]
GROUP_OPINION = ["ar_tech", "ar_arts"]

WORD_HINTS = {k: "2000–5000 كلمة" for k in GROUP_STORIES}
WORD_HINTS.update({k: "800–1500 كلمة" for k in GROUP_KIDS})
WORD_HINTS.update({k: "800–1500 كلمة" for k in GROUP_OPINION})
WORD_HINTS["ar_books"] = "كما كانت"

# Non-clickable form/length chips on every story card (SPEC §6).
TAG_LABELS = {
    "short": "#قصة_قصيرة",
    "flash": "#ومضة_قصصية",
    "serial": "#سلسلة_حلقات",
    "interactive": "#قصة_تفاعلية",
}
FLASH_TAGS = {"flash", "serial", "interactive"}
AGE_BADGES = {
    "kids_3_6": "3-6 سنوات",
    "kids_7_10": "7-10 سنوات",
    "kids_11_14": "11-14 سنة",
}

LITERARY_DISCLAIMER = "هذه القصة عمل إبداعي من تأليف نكسوس، وأي تشابه مع الواقع محض صدفة."
HORROR_NOTICE = ('<aside class="story-warning"><b>تنبيه:</b> قصص الرعب النفسي تعتمد على التوتر '
                 'والغموض فقط، بلا دماء أو تشريح، وهي مخصّصة للكبار الذين يحبّون الإثارة الهادئة.</aside>')

# The top menu has exactly these five items (SPEC §5).
NAV_ITEMS = (
    ("index.html", "الرئيسية", "home"),
    ("hub-stories.html", "عالم القصص", "hub-stories"),
    ("hub-kids.html", "ركن الأطفال", "hub-kids"),
    ("flashes.html", "الومضات والحلقات", "flashes"),
    ("about.html", "عن المدونة", "about"),
)

# Old newspaper pages are removed on every rebuild; ar_tech/ar_arts are now valid opinion
# sections and ar_books is a permanent story-blog page, so none of them is ever removed.
STALE_FILES = (
    "category-ar_local.html", "category-ar_cities.html", "category-ar_world.html",
    "category-ar_economy.html", "category-ar_sports.html",
)

e = html.escape

BOOKS_LEAD = ('<p class="city-lead">مكتبة رقمية مجانية بالكامل: كل مقال يختار لك خمسة كتب حقيقية للتعلّم الذاتي، '
              'بعناوينها وأسماء مؤلفيها وروابط القراءة والتحميل، مأخوذة من مستودع '
              '<a href="https://github.com/EbookFoundation/free-programming-books" rel="nofollow noopener" target="_blank">'
              'Free Programming Books</a> المفتوح. لا اشتراك ولا دفع ولا ملفات مقرصنة.</p>')

# Same mechanism as BOOKS_LEAD, for the two personal-opinion reading sections (SPEC §1/§4).
OPINION_LEAD = ('<p class="city-lead">قراءات نكسوس في التقنية والفن والثقافة آراء شخصية هادئة تهدف إلى الفهم '
                'والتعلّم، لا أخباراً ولا تقارير صحفية. ننسب الوقائع والأرقام إلى مصادرها، '
                'ونعلّم الرأي بـ«رأي شخصي» أو «وجهة نظر».</p>')

POLL_BANK = [
    ("ما الجزء الذي تقرأه أولاً في مملكة الأسرار؟", ["قراءات دولية", "اقتصاد", "تقنية", "رياضة", "فن وثقافة"]),
    ("أيّ الكتب المجانية تود أن تجدها في المكتبة؟", ["كتب التقنية", "كتب الأدب", "كتب التعلّم الذاتي", "كتب الأعمال"]),
    ("كيف تفضّل أن تُكتب القراءات الدولية؟", ["رأي شخصي واضح", "سياق مختصر", "مقارنة بين المصادر", "سرد هادئ"]),
    ("ما رأيك في استخدام الذكاء الاصطناعي في كتابة المقالات؟", ["أؤيده مع مراجعة بشرية", "أؤيده بالكامل", "أعارضه", "لا رأي لي"]),
    ("كم مرة تزور المدونة؟", ["كل يوم", "بضع مرات في الأسبوع", "مرة في الأسبوع", "أول مرة"]),
    ("ما الوقت الذي تفضّله للقراءة؟", ["الصباح الباكر", "خلال النهار", "المساء", "قبل النوم"]),
    ("أي أسلوب تفضّل في مقالات المدونة؟", ["الفكرة المختصرة", "المقال المعمّق", "الرأي مع المصادر", "الصور والرسوم"]),
    ("ما الرياضة التي تتابعها أكثر؟", ["كرة القدم", "كرة السلة", "التنس", "رياضات أخرى"]),
    ("هل تهتم بقراءة تحليلات اقتصادية مبسّطة؟", ["نعم دائمًا", "أحيانًا", "نادرًا", "لا أهتم"]),
    ("ما المحتوى الذي تودّ أن نزيد منه في المدونة؟", ["قراءات دولية", "مقالات تقنية", "فن وثقافة", "كتب مجانية"]),
    ("كيف تقيّم مملكة الأسرار؟", ["ممتازة", "جيدة", "مقبولة", "تحتاج إلى تحسين"]),
    ("أي موضوع يشغلك أكثر الآن؟", ["الذكاء الاصطناعي", "الاقتصاد", "المناخ", "الثقافة"]),
    ("هل تفضّل القراءة بالوضع الليلي؟", ["نعم دائمًا", "أحيانًا", "لا، أفضّل الوضع العادي"]),
    ("أين تقرأ المقالات غالبًا؟", ["على الهاتف", "على الحاسوب", "على الجهاز اللوحي", "حسب الظرف"]),
]


SW_JS = """/* مملكة الأسرار service worker: instant repeat visits + offline fallback */
const V = 'np-__VERSION__';
const CORE = ['./', 'style.css', 'site.js', 'tools.js', 'logo.webp'];
self.addEventListener('install', e => {
  self.skipWaiting();
  e.waitUntil(caches.open(V).then(c => Promise.allSettled(CORE.map(u => c.add(u)))));
});
self.addEventListener('activate', e => {
  e.waitUntil(caches.keys().then(ks => Promise.all(ks.filter(k => k !== V).map(k => caches.delete(k)))).then(() => self.clients.claim()));
});
self.addEventListener('fetch', e => {
  const r = e.request;
  if (r.method !== 'GET') return;
  const u = new URL(r.url);
  if (u.origin !== location.origin) return;
  if (r.mode === 'navigate') {            // pages: network first, cache when offline
    e.respondWith(fetch(r).then(res => { const cp = res.clone(); caches.open(V).then(c => c.put(r, cp)); return res; })
      .catch(() => caches.match(r).then(m => m || caches.match('./'))));
    return;
  }
  e.respondWith(caches.match(r).then(m => {   // assets & images: cache first, refresh in background
    const net = fetch(r).then(res => { if (res.ok) { const cp = res.clone(); caches.open(V).then(c => c.put(r, cp)); } return res; }).catch(() => m);
    return m || net;
  }));
});
"""


def ad(pos, extra=""):
    """Ad unit. Renders NOTHING until ADSENSE_CLIENT and a slot id are set (so the site stays clean before approval)."""
    slot = os.getenv(f"ADSENSE_SLOT_{pos.upper()}") or os.getenv("ADSENSE_SLOT", "")
    if not (ADSENSE_CLIENT and slot):
        return ""
    return (f'<div class="ad-wrap notranslate {extra}"><ins class="adsbygoogle" style="display:block" data-ad-client="{e(ADSENSE_CLIENT)}" '
            f'data-ad-slot="{e(slot)}" data-ad-format="auto" data-full-width-responsive="true"></ins>'
            '<script>(adsbygoogle=window.adsbygoogle||[]).push({});</script></div>')


def load():
    p = ROOT / "articles.json"
    data = json.loads(p.read_text(encoding="utf-8")) if p.exists() else {}
    arts = data.get("articles", {})
    return {k: sorted(arts.get(k, []), key=lambda a: a["date"], reverse=True) for k in CATEGORIES}


def today_utc():
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def load_poll():
    """Today's poll: poll.json if it is today's, else a rotating question from the built-in bank (so it always changes daily)."""
    t = today_utc()
    p = ROOT / "poll.json"
    try:
        d = json.loads(p.read_text(encoding="utf-8")) if p.exists() else {}
        if d.get("id") == t and d.get("question") and 2 <= len(d.get("options", [])) <= 5:
            return {"id": t, "q": d["question"], "o": d["options"]}
    except Exception:
        pass
    q, o = POLL_BANK[datetime.now(timezone.utc).toordinal() % len(POLL_BANK)]
    return {"id": t, "q": q, "o": o}


# ----------------------------------------------------------------------------- images
def cdn(a, w, h=0):
    """Cloudinary delivery url (auto format/quality, resized) when the article image was uploaded, else ''."""
    u = a.get("cdn", "")
    if "/upload/" not in u:
        return ""
    t = f"f_auto,q_auto,w_{w},c_limit" if not h else f"f_auto,q_auto,w_{w},h_{h},c_fill"
    return u.replace("/upload/", f"/upload/{t}/", 1)


def _ver(rel):
    """Modification time of the picture, used as a cache-buster in the URL."""
    try:
        return str(int((ROOT / urllib.parse.unquote(rel)).stat().st_mtime))
    except Exception:
        return ""


def img_src(a, pre, w):
    """(src, onerror-fallback) : CDN first, local file as safety net.
    The URL carries ?v=<file time>, so a regenerated picture can never be hidden by the browser or the service worker."""
    rel = thumb(a["image"]) if w <= 600 else a["image"]
    v = _ver(a["image"])
    local = pre + rel + (f"?v={v}" if v else "")
    c = cdn(a, w)
    if c:
        c = c + ((f"&v={v}" if "?" in c else f"?v={v}") if v else "")
        return c, f' onerror="this.onerror=null;this.src=\'{e(local)}\'"'
    return local, ""


def thumb(rel):
    """Small 480px WebP for cards (much lighter than the 1000px hero). Falls back to the original."""
    p = ROOT / rel
    if not p.exists() or p.suffix == ".svg":
        return rel
    t = ROOT / "images" / "t" / (p.stem + ".webp")
    if not t.exists():
        try:
            from PIL import Image
            t.parent.mkdir(exist_ok=True)
            im = Image.open(p).convert("RGB")
            im.thumbnail((480, 480))
            im.save(t, "WEBP", quality=70, method=6)
        except Exception:
            return rel
    return f"images/t/{t.name}"


def clean_thumbs(data):
    keep = {Path(a["image"]).stem for k in CATEGORIES for a in data[k]}
    for t in (ROOT / "images" / "t").glob("*.webp"):
        if t.stem not in keep:
            t.unlink()


def ensure_images(data):
    """Self-healing build step: a story must never point at a missing or SVG picture.
    If the file is absent (e.g. it was never generated or never pushed), we draw a real original
    WebP illustration on the spot and write the repaired path + credit back to articles.json."""
    changed, repaired = False, 0
    for k, items in data.items():
        for a in items:
            rel = a.get("image", "")
            p = ROOT / rel if rel else None
            broken = (not rel) or (p is None) or (not p.is_file()) or p.suffix.lower() == ".svg"
            if not broken:
                try:
                    broken = p.stat().st_size < 8192
                except OSError:
                    broken = True
            if not broken:
                continue
            stem = f"{a.get('id', 'article')}-ill"
            out = ROOT / "images" / f"{stem}.webp"
            try:
                import illustrations
                illustrations.save(stem, k, a.get("title", ""), out)
            except Exception as ex:
                # Safety net: if illustrations.py is missing, draw a sharp geometric
                # Pillow illustration directly so the build never leaves a broken image.
                try:
                    from PIL import Image, ImageDraw
                    import random
                    out.parent.mkdir(exist_ok=True)
                    r = random.Random(stem)
                    palettes = {
                        "story_realistic": ((30, 64, 175), (30, 58, 138), (191, 219, 254)),
                        "story_mystery": ((30, 41, 59), (15, 23, 42), (148, 163, 184)),
                        "story_scifi": ((109, 40, 217), (76, 29, 149), (221, 214, 254)),
                        "story_fantasy": ((5, 122, 85), (4, 95, 70), (167, 243, 208)),
                        "story_horror": ((51, 15, 51), (30, 10, 35), (216, 180, 254)),
                        "story_history": ((146, 64, 14), (120, 53, 15), (253, 230, 138)),
                        "story_comedy": ((190, 24, 93), (131, 24, 67), (251, 207, 232)),
                        "kids_3_6": ((2, 132, 199), (3, 105, 161), (224, 242, 254)),
                        "kids_7_10": ((22, 163, 74), (21, 128, 61), (220, 252, 231)),
                        "kids_11_14": ((124, 58, 237), (91, 33, 182), (237, 233, 254)),
                        "ar_tech": ((14, 116, 144), (8, 84, 110), (165, 243, 252)),
                        "ar_arts": ((190, 24, 93), (131, 24, 67), (251, 207, 232)),
                        "ar_books": ((30, 64, 175), (30, 58, 138), (191, 219, 254)),
                    }
                    c1, c2, c3 = palettes.get(k, ((15, 23, 42), (30, 58, 138), (148, 163, 184)))
                    im = Image.new("RGB", (1280, 720), c1)
                    dr = ImageDraw.Draw(im)
                    for y in range(720):
                        t = y / 719
                        col = tuple(int(c1[i] * (1 - t) + c2[i] * t) for i in range(3))
                        dr.line([(0, y), (1280, y)], fill=col)
                    for _ in range(36):
                        x0, y0 = r.randint(20, 1100), r.randint(20, 560)
                        w, h = r.randint(80, 340), r.randint(80, 300)
                        col = c3 if r.random() > 0.35 else (255, 255, 255)
                        if r.random() > 0.5:
                            dr.ellipse([x0, y0, x0 + w, y0 + w], outline=col, width=r.randint(4, 10))
                        else:
                            dr.rectangle([x0, y0, x0 + w, y0 + h], outline=col, width=r.randint(4, 9))
                    for _ in range(28):
                        x1, y1 = r.randint(0, 1280), r.randint(0, 720)
                        x2, y2 = x1 + r.randint(-380, 380), y1 + r.randint(-280, 280)
                        dr.line([(x1, y1), (x2, y2)], fill=c3 if r.random() > 0.3 else (255, 255, 255), width=r.randint(3, 7))
                    for _ in range(24):
                        cx, cy, rad = r.randint(40, 1240), r.randint(40, 680), r.randint(12, 48)
                        dr.ellipse([cx - rad, cy - rad, cx + rad, cy + rad], fill=c3 if r.random() > 0.4 else c1, outline=(255, 255, 255), width=2)
                    im.save(out, "WEBP", quality=90, method=6)
                except Exception as ex2:
                    print(f"cannot draw a replacement picture for {a.get('id')}: {str(ex)[:120]} / {str(ex2)[:80]}")
                    continue
            a["image"] = f"images/{out.name}"
            a["image_credit"] = {"source": "مملكة الأسرار", "author": "نكسوس",
                                 "license": "original blog illustration", "kind": "illustration"}
            a["image_kind"] = "illustration"
            a.pop("cdn", None)
            changed, repaired = True, repaired + 1
    if changed:
        (ROOT / "articles.json").write_text(
            json.dumps({"categories": CATEGORIES, "articles": {k: data[k] for k in CATEGORIES}},
                       ensure_ascii=False, indent=1), encoding="utf-8")
        print(f"repaired {repaired} missing/placeholder image reference(s)")


# ----------------------------------------------------------------------------- layout pieces
def head(title, desc, pre, canonical="", image="", extra=""):
    ads = (f'<script async src="https://pagead2.googlesyndication.com/pagead/js/adsbygoogle.js?client={e(ADSENSE_CLIENT)}" crossorigin="anonymous"></script>'
           if ADSENSE_CLIENT else "")
    og = f'<meta property="og:image" content="{e(image)}"><meta name="twitter:image" content="{e(image)}">' if image else ""
    can = f'<link rel="canonical" href="{e(canonical)}">' if canonical else ""
    return f"""<!DOCTYPE html>
<html lang="ar" dir="rtl">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{e(title)}</title>
<meta name="description" content="{e(desc)}">
<meta property="og:title" content="{e(title)}"><meta property="og:description" content="{e(desc)}"><meta property="og:type" content="website"><meta property="og:site_name" content="مملكة الأسرار Kingdom Of Secrets"><meta name="twitter:card" content="summary_large_image">{og}{can}
<script>try{{var t=localStorage.getItem('np-theme');if(t)document.documentElement.setAttribute('data-theme',t)}}catch(e){{}}</script>
<link rel="preconnect" href="https://fonts.googleapis.com"><link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link rel="preload" as="style" href="https://fonts.googleapis.com/css2?family=Cairo:wght@400;700;900&display=swap" onload="this.onload=null;this.rel='stylesheet'">
<noscript><link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Cairo:wght@400;700;900&display=swap"></noscript>
<meta name="theme-color" content="#0b3c7a">
<link rel="manifest" href="{pre}manifest.webmanifest"><link rel="icon" type="image/png" href="{pre}icon-192.png"><link rel="apple-touch-icon" href="{pre}icon-192.png">
<link rel="alternate" type="application/rss+xml" title="مملكة الأسرار Kingdom Of Secrets" href="{pre}feed.xml">
<link rel="stylesheet" href="{pre}style.css">
{extra}{ads}
</head>"""


def HAS_DEALS():
    """The Amazon deals pages are linked only when deals/index.html exists (created by amazon_products.js)."""
    return (ROOT / "deals" / "index.html").exists()


def live_categories(data):
    """All 13 sections always get a page (even when empty), so the reader sees the full structure."""
    return list(CATEGORIES)


def header(pre, data, active):
    nav = "".join(f'<li><a href="{pre}{u}"{" class=active" if active == key else ""}>{e(n)}</a></li>'
                  for u, n, key in NAV_ITEMS)
    return f"""<body data-pre="{pre}" data-api="{e(NP_API)}">
<div class="progress" id="progress"></div>
<div class="top-bar notranslate"><div class="container flex">
<span class="today"><span class="live">●</span> <span id="today">مدونة قصصية إبداعية آمنة للعائلات</span> <span class="last-up" id="last-up"></span></span>
<div class="top-tools"><button class="icon-btn" id="theme-btn" type="button" aria-label="الوضع الليلي" title="الوضع الليلي">🌓</button>
<div class="lang-box" translate="no"><span>🌐</span>
<button class="lang-btn" data-l="ar">العربية</button>|<button class="lang-btn" data-l="fr">Français</button>|<button class="lang-btn" data-l="en">English</button></div></div>
</div></div>
<header class="main-header"><div class="container flex">
<a href="{pre}index.html" class="notranslate logo"><img src="{pre}logo.webp" width="165" height="90" alt="مملكة الأسرار Kingdom Of Secrets"></a>
<div class="header-tag">قصص إبداعية يكتبها نكسوس</div>
<form class="hsearch" action="{pre}search.html" role="search"><input name="q" type="search" placeholder="ابحث في قصص المدونة…" aria-label="بحث"><button type="submit" aria-label="بحث">🔍</button></form></div></header>
<nav class="main-nav"><div class="container"><ul class="nav-menu">{nav}</ul></div></nav>"""


def footer(pre, data):
    """Exactly the three groups of SPEC §10, plus the fixed literary disclaimer."""
    about_links = (f'<li><a href="{pre}about.html">عن المدونة</a></li>'
                   f'<li><a href="{pre}disclaimer.html">إخلاء المسؤولية الأدبي</a></li>')
    contact_links = (f'<li><a href="{pre}contact.html">اتصل بي / اقترح فكرة</a></li>'
                     f'<li><a href="mailto:{e(CONTACT_EMAIL)}">{e(CONTACT_EMAIL)}</a></li>')
    policy_links = (f'<li><a href="{pre}privacy-policy.html">سياسة الخصوصية</a></li>'
                    f'<li><a href="{pre}editorial-policy.html">سياسة المحتوى وحقوق النشر</a></li>'
                    f'<li><a href="{pre}terms.html">شروط الاستخدام</a></li>')
    return f"""<footer class="footer"><div class="container footer-grid">
<div><h4>من نحن وإخلاء المسؤولية</h4><ul>{about_links}</ul></div>
<div><h4>تواصل معي / اقترح فكرة</h4><ul>{contact_links}</ul></div>
<div><h4>سياسة الخصوصية وحقوق النشر</h4><ul>{policy_links}</ul></div>
</div><div class="footer-bottom"><p class="literary-note">{e(LITERARY_DISCLAIMER)}</p>
© {datetime.now().year} مملكة الأسرار Kingdom Of Secrets. جميع الحقوق محفوظة.</div></footer>
<button class="to-top" id="to-top" type="button" aria-label="أعلى الصفحة">↑</button>
<div id="google_translate_element" style="display:none"></div>
<script src="{pre}site.js" defer></script>
</body></html>"""


def tag_key(raw):
    """Canonical, CSS-safe key for a tag (accepts both keys and the Arabic labels)."""
    t = re.sub(r"\s+", "_", str(raw or "").strip()).lstrip("#")
    if t in TAG_LABELS:
        return t
    for key, label in TAG_LABELS.items():
        if t == label.lstrip("#"):
            return key
    return re.sub(r"[^a-z0-9]+", "-", t.lower()).strip("-") or "other"


def tag_chips(a):
    """Plain (non-clickable) spans: <span class="tag tag-<key>">التسمية</span>."""
    out = []
    for raw in a.get("tags") or []:
        key = tag_key(raw)
        label = TAG_LABELS.get(key) or str(raw)
        if not label.startswith("#"):
            label = "#" + label
        out.append(f'<span class="tag tag-{e(key)}">{e(label)}</span>')
    return "".join(out)


def hashtag_chips(a):
    """Strong discovery hashtags from articles.json (non-clickable, escaped)."""
    out = []
    for raw in a.get("hashtags") or []:
        h = str(raw).strip()
        if not h:
            continue
        if not h.startswith("#"):
            h = "#" + h
        out.append(f'<span class="hashtag">{e(h)}</span>')
    return "".join(out)


def age_badge(cat):
    label = AGE_BADGES.get(cat)
    return f'<span class="badge age-badge">{e(label)}</span>' if label else ""


def video_player(a, pre):
    """Optional film from SPEC §7/§12. Returns '' when the story has no usable video dict."""
    v = a.get("video")
    if not isinstance(v, dict) or not v.get("url"):
        return ""
    poster = str(v.get("poster") or "").strip()
    if poster and not poster.startswith(("http://", "https://")):
        poster = pre + poster.lstrip("/")
    url = str(v.get("url") or "").strip()
    page = str(v.get("page") or "").strip()
    detail = ["🎬 فيلم القصة"]
    try:
        seconds = int(v.get("seconds") or 0)
        if seconds > 0:
            detail.append(f"مدته {seconds // 60} دقيقة")
    except (TypeError, ValueError):
        pass
    try:
        scenes = int(v.get("scenes") or 0)
        if scenes > 0:
            detail.append(f"{scenes} مشهد")
    except (TypeError, ValueError):
        pass
    link = (f' <a href="{e(page)}" rel="nofollow noopener" target="_blank">شاهد على Internet Archive</a>'
            if page else "")
    return (f'<div class="story-video"><video controls playsinline preload="metadata" poster="{e(poster)}">'
            f'<source src="{e(url)}" type="video/mp4">'
            'متصفحك لا يدعم تشغيل الفيديو (your browser does not support video).'
            f'</video><p class="video-meta">{" — ".join(e(x) for x in detail)}.{link}</p></div>')


def card(a, pre, cat, eager=False, extra=""):
    src, fb = img_src(a, pre, 480)
    cls = "card" + (" " + extra.strip() if extra else "")
    chips = tag_chips(a)
    chips_html = f'<div class="tags">{chips}</div>' if chips else ""
    hashes = hashtag_chips(a)
    hashes_html = f'<div class="hashtags">{hashes}</div>' if hashes else ""
    return (f'<a class="{cls}" href="{pre}articles/{a["id"]}.html"><img loading="{"eager" if eager else "lazy"}" decoding="async" width="480" height="270" '
            f'src="{e(src)}"{fb} alt="{e(a.get("image_alt", a["title"]))}">'
            f'<div class="info"><span class="badge">{e(CATEGORIES[cat])}</span>{age_badge(cat)}<h3>{e(a["title"])}</h3>'
            f'{chips_html}{hashes_html}<p>{e(a["date"][:10])}</p></div></a>')


def newsletter(kind="box"):
    if NEWSLETTER_BUTTONDOWN:
        prov, target = "buttondown", NEWSLETTER_BUTTONDOWN
    else:
        prov, target = "formsubmit", CONTACT_EMAIL
    form = (f'<form class="nl-form" data-provider="{prov}" data-target="{e(target)}" novalidate>'
            '<input type="email" name="email" placeholder="بريدك الإلكتروني" required autocomplete="email" aria-label="البريد الإلكتروني">'
            '<input type="text" name="_honey" tabindex="-1" autocomplete="off" style="display:none">'
            '<button class="btn" type="submit">اشترك الآن</button></form><p class="form-msg nl-msg" role="status"></p>')
    txt = "اشترك في نشرة مملكة الأسرار لتصلك القصص الجديدة أولاً"
    if kind == "band":
        return f'<section class="nl-band"><div><h3>📬 النشرة البريدية</h3><p>{txt}.</p></div>{form}</section>'
    return f'<div class="widget nl-box"><h4>📬 النشرة البريدية</h4><p>{txt}.</p>{form}</div>'


def wx_mini():
    return ('<div class="widget wx-mini notranslate" aria-live="polite"><h4>🌦️ الطقس ومواقيت الصلاة</h4>'
            '<div class="wx-mini-out"><p class="muted">اكتب اسم مدينتك لتظهر لك حالة الطقس ومواقيت الصلاة.</p></div>'
            '<div class="wx-box"><input class="wx-mini-q" type="search" placeholder="اكتب اسم المدينة…" autocomplete="off" aria-label="المدينة">'
            '<button class="wx-geo" type="button" title="استخدم موقعي" aria-label="موقعي">📍</button><ul class="wx-sug"></ul></div></div>')


def poll_widget(poll):
    payload = e(json.dumps(poll, ensure_ascii=False), quote=True)
    return (f'<div class="widget poll" data-poll="{payload}" data-ns="{e(POLL_NS)}"><h4>📊 استطلاع اليوم</h4>'
            f'<div class="poll-body"><p class="poll-q">{e(poll["q"])}</p></div></div>')


def services_widget(pre):
    """AI academy, weather, the free library and (when present) Amazon deals stay out of the top menu."""
    items = [("ai-academy.html", "🎓 أكاديمية الذكاء الاصطناعي"),
             ("weather.html", "🌦️ الطقس ومواقيت الصلاة"),
             ("category-ar_books.html", "📚 المكتبة الرقمية المجانية")]
    if HAS_DEALS():
        items.append(("deals/index.html", "🛒 عروض أمازون"))
    links = "".join(f'<li><a href="{pre}{u}">{e(n)}</a></li>' for u, n in items)
    return f'<div class="widget services-box"><h4>🔎 استكشف مملكة الأسرار</h4><ul>{links}</ul></div>'


def sidebar(pre, data, poll):
    latest = sorted((a for k in CATEGORIES for a in data[k]), key=lambda a: a["date"], reverse=True)[:8]
    lis = "".join(f'<li><span class="rank">{i}</span><a href="{pre}articles/{a["id"]}.html">{e(a["title"])}</a></li>' for i, a in enumerate(latest, 1))
    return (f'<aside>{ad("side1")}{wx_mini()}{poll_widget(poll)}{newsletter()}{services_widget(pre)}'
            f'<div class="widget saved-box" id="saved-box"><h4>🔖 محفوظاتي</h4>'
            '<ul class="saved-list"><li class="muted">اضغط «حفظ» على أي قصة لتظهر هنا وتقرأها لاحقًا.</li></ul></div>'
            f'<div class="widget"><h4>📝 أحدث ما كُتب</h4><ul>{lis or "<li>قريباً</li>"}</ul></div>'
            f'{ad("side2", "sticky")}</aside>')


LINK_RX = re.compile(r"\[([^\]]{1,200})\]\((https?://[^)\s]+)\)")


def inline_md(text):
    """Escapes everything, then turns ONLY safe http(s) Markdown links into real links.
    Used by the book lists (the links come from the repository) and by the stories themselves."""
    out, last = [], 0
    for m in LINK_RX.finditer(text):
        out.append(e(text[last:m.start()]))
        label, url = m.group(1), m.group(2)
        out.append(f'<a href="{e(url)}" rel="nofollow noopener" target="_blank">{e(label)}</a>')
        last = m.end()
    out.append(e(text[last:]))
    return "".join(out)


def render_body(content, clean=True):
    if style_guide and clean:
        content = "\n\n".join(style_guide.clean_body(content, as_list=True))
    out, n = [], 0
    for block in re.split(r"\n\s*\n", content.strip()):
        block = block.strip()
        if block.startswith("## "):
            out.append(f"<h2>{inline_md(block[3:].strip())}</h2>")
            continue
        lines = [l.strip() for l in block.splitlines() if l.strip()]
        if lines and all(l.startswith("- ") for l in lines):
            lis = "".join(f"<li>{inline_md(l[2:].strip())}</li>" for l in lines)
            out.append(f'<ul class="book-list">{lis}</ul>')
            continue
        if block:
            out.append(f"<p>{inline_md(block)}</p>")
            n += 1
            if n in (3, 7, 11):
                out.append(ad("inline"))
    return "\n\n".join(out)


def share_bar():
    return ('<div class="share notranslate"><span>شارك المقال:</span>'
            '<button type="button" data-net="whatsapp" class="s-wa">واتساب</button>'
            '<button type="button" data-net="facebook" class="s-fb">فيسبوك</button>'
            '<button type="button" data-net="x" class="s-x">X</button>'
            '<button type="button" data-net="telegram" class="s-tg">تيليغرام</button>'
            '<button type="button" data-net="copy" class="s-cp">نسخ الرابط</button></div>')


def reading_time(text):
    return max(1, round(len(re.findall(r"\S+", text)) / 190))


def shell(title, desc, pre, canonical, data, active, inner, poll, extra_head="", image=""):
    return (head(title, desc, pre, canonical, image, extra_head) + header(pre, data, active)
            + f'<div class="container">{ad("top")}{inner}{ad("bottom")}</div>' + footer(pre, data))


# ----------------------------------------------------------------------------- build
def write_page(name, title, desc, pre, canonical, data, active, inner, poll, extra_head="", image=""):
    (ROOT / name).write_text(shell(title, desc, pre, canonical, data, active, inner, poll, extra_head, image), encoding="utf-8")


def build():
    data = load()
    ensure_images(data)
    poll = load_poll()
    base = SITE_URL
    (ROOT / "articles").mkdir(exist_ok=True)
    for old in (ROOT / "articles").glob("*.html"):
        old.unlink()
    live = live_categories(data)
    # Stale newspaper pages must disappear from the published blog even after an old upload.
    # category-ar_books.html is a permanent story-blog page and is never deleted.
    for stale in STALE_FILES:
        (ROOT / stale).unlink(missing_ok=True)
    for stale in ROOT.glob("city-*.html"):
        stale.unlink()
    urls = (["index.html", "hub-stories.html", "hub-kids.html", "flashes.html"]
            + [f"category-{k}.html" for k in live]
            + ["weather.html", "search.html", "about.html", "contact.html", "privacy-policy.html",
               "editorial-policy.html", "terms.html", "disclaimer.html", "ai-academy.html"])
    allart = sorted(((k, a) for k in CATEGORIES for a in data[k]), key=lambda t: t[1]["date"], reverse=True)
    clean_thumbs(data)

    # ---- home: «قصة الأسبوع» + the latest stories of every section + preserved widgets
    story_items = [(k, a) for k in live if k in GROUP_STORIES for a in data[k]]
    featured = next(((k, a) for k, a in story_items if a.get("featured") or a.get("manual")), None)
    if featured is None and story_items:
        featured = story_items[0]
    if featured:
        fk, fa = featured
        featured_html = ('<section class="sect featured-wrap"><h2 class="block-title">✍️ قصة الأسبوع</h2>'
                         + card(fa, "", fk, eager=True, extra=" featured") + '</section>')
    else:
        featured_html = ('<section class="sect featured-wrap"><h2 class="block-title">✍️ قصة الأسبوع</h2>'
                         '<div class="empty">تظهر هنا أحدث قصة مختارة حين يبدأ النشر.</div></section>')

    sections, shown = "", 0
    for k in live:
        name = CATEGORIES[k]
        cards_html = "".join(card(a, "", k) for a in data[k][:6])
        extra = OPINION_LEAD if k in GROUP_OPINION else (BOOKS_LEAD if k == "ar_books" else "")
        hint = f'<p class="word-hint">📏 {e(WORD_HINTS[k])}</p>'
        if not data[k]:
            cards_html = ('<div class="empty">جزء «' + e(name) + '» جاهز: يبدأ النشر فيه مع أول قصة، '
                          f'ويمكنك تصفحه من <a class="badge" href="category-{k}.html">هنا ←</a>.</div>')
        more_link = f'<p class="more"><a class="badge" href="category-{k}.html">كل قصص {e(name)} ←</a></p>'
        sections += (f'<section class="sect"><h2 class="block-title">{e(name)}</h2>{hint}{extra}'
                     f'<div class="grid">{cards_html}</div>{more_link}</section>')
        shown += 1
        if shown == 2:
            sections += newsletter("band")
        if shown % 2 == 0:
            sections += ad("middle")
    services = ('<section class="sect services"><h2 class="block-title">🔎 المزيد في مملكة الأسرار</h2>'
                + services_widget("") + '</section>')
    inner = (f'{featured_html}{ad("under_slider")}<div class="layout"><main>{sections}{services}</main>'
             f'{sidebar("", data, poll)}</div>')
    write_page("index.html", "مملكة الأسرار Kingdom Of Secrets | قصص إبداعية",
               "مملكة الأسرار: قصص إبداعية آمنة للعائلات في الواقعية والغموض والخيال والفانتازيا والرعب والتاريخ والكوميديا، وركن للأطفال ومكتبة رقمية مجانية.",
               "", base + "/" if base else "", data, "home", inner, poll)

    # ---- hub: عالم القصص (7 genre cards)
    genre_cards = "".join(
        f'<a class="card hub-card" href="category-{k}.html"><div class="info">'
        f'<span class="badge">{e(WORD_HINTS[k])}</span><h3>{e(CATEGORIES[k])}</h3>'
        f'<p>{len(data[k])} قصة متاحة</p></div></a>' for k in GROUP_STORIES)
    inner = ('<div class="layout"><main><div class="page hub"><h1>عالم القصص</h1>'
             '<p class="lead">سبعة تصنيفات أدبية يكتبها نكسوس لتقرأها وقت ما تشاء. '
             f'{e(LITERARY_DISCLAIMER)}</p><div class="grid">{genre_cards}</div></div></main>'
             f'{sidebar("", data, poll)}</div>')
    write_page("hub-stories.html", "عالم القصص | مملكة الأسرار",
               "التصنيفات الأدبية السبعة في مملكة الأسرار: واقعي وإنساني، غموض، خيال علمي، فانتازيا، رعب نفسي، تاريخي وكوميديا.",
               "", f"{base}/hub-stories.html" if base else "", data, "hub-stories", inner, poll)

    # ---- hub: ركن الأطفال (3 age cards with age badges)
    age_cards = "".join(
        f'<a class="card age-card" href="category-{k}.html"><div class="info">'
        f'{age_badge(k)}<h3>{e(CATEGORIES[k])}</h3>'
        f'<p>{len(data[k])} قصة مناسبة لعمر طفلك</p></div></a>' for k in GROUP_KIDS)
    inner = ('<div class="layout"><main><div class="page hub"><h1>ركن الأطفال</h1>'
             '<p class="lead">قصص بسيطة ورسائل إيجابية، مصنّفة حسب العمر، وبلا رعب أو عنف أو مواضيع ناضجة. '
             f'{e(LITERARY_DISCLAIMER)}</p><div class="grid">{age_cards}</div></div></main>'
             f'{sidebar("", data, poll)}</div>')
    write_page("hub-kids.html", "ركن الأطفال | مملكة الأسرار",
               "ثلاث فئات عمرية في ركن الأطفال: 3-6 سنوات، 7-10 سنوات، 11-14 سنة، بقصص آمنة ولغة بسيطة.",
               "", f"{base}/hub-kids.html" if base else "", data, "hub-kids", inner, poll)

    # ---- flashes: stories tagged flash / serial / interactive
    flash_items = [(k, a) for k in live for a in data[k]
                   if FLASH_TAGS.intersection(tag_key(t) for t in (a.get("tags") or []))]
    flash_cards = "".join(card(a, "", k) for k, a in flash_items)
    if not flash_cards:
        flash_cards = '<div class="empty">لا تومضات أو حلقات منشورة بعد؛ تعود هذه الصفحة حين تظهر أول ومضة قصصية.</div>'
    inner = ('<div class="layout"><main><div class="flashes"><h1>الومضات والحلقات</h1>'
             '<p class="lead">قصص قصيرة جداً، وحلقات متتابعة، وقصص تختار فيها النهاية بنفسك. '
             f'{e(LITERARY_DISCLAIMER)}</p><div class="grid">{flash_cards}</div></div></main>'
             f'{sidebar("", data, poll)}</div>')
    write_page("flashes.html", "الومضات والحلقات | مملكة الأسرار",
               "القصص الومضية والمسلسلة والتفاعلية في مملكة الأسرار، حيث يختار القارئ النهاية.",
               "", f"{base}/flashes.html" if base else "", data, "flashes", inner, poll)

    # ---- category pages (13) + article pages
    for k in live:
        name = CATEGORIES[k]
        cards = "".join(card(a, "", k) for a in data[k]) or '<div class="empty">لا توجد قصص في هذا الجزء بعد.</div>'
        hint = f'<p class="word-hint">📏 عدد الكلمات: {e(WORD_HINTS[k])}</p>'
        extra = OPINION_LEAD if k in GROUP_OPINION else (BOOKS_LEAD if k == "ar_books" else "")
        if k == "ar_books" and not data[k]:
            extra += ('<div class="empty">قوائم الكتب تُبنى آلياً من مستودع Free Programming Books؛ '
                      'تظهر هنا فور اكتمال أول قائمة من خمسة كتب حقيقية.</div>')
        warning = HORROR_NOTICE if k == "story_horror" else ""
        inner = (f'<div class="layout"><main><h1 class="block-title">{e(name)}</h1>{hint}{warning}{extra}'
                 f'<div class="grid">{cards}</div>{ad("middle")}'
                 f'<p class="literary-note">{e(LITERARY_DISCLAIMER)}</p></main>{sidebar("", data, poll)}</div>')
        write_page(f"category-{k}.html", f"{name} | مملكة الأسرار",
                   f"قصص {name} في مملكة الأسرار. {LITERARY_DISCLAIMER}", "",
                   f"{base}/category-{k}.html" if base else "", data, k, inner, poll)

        for a in data[k]:
            chips = tag_chips(a)
            tags_block = f'<div class="tags">{chips}</div>' if chips else ""
            hashes = hashtag_chips(a)
            hashtags_block = f'<div class="hashtags">{hashes}</div>' if hashes else ""
            video_html = video_player(a, "../")
            opinion_note = OPINION_LEAD if k in GROUP_OPINION else ""
            warning_html = (f'<aside class="story-warning"><b>تنبيه:</b> {e(a["warning"])}</aside>'
                            if a.get("warning") else "")
            author_note = f'<aside class="author-note">{e(LITERARY_DISCLAIMER)}</aside>'
            src_html = ""
            if (k == "ar_books" or k in GROUP_OPINION) and a.get("sources"):
                src = "".join(f'<li><a href="{e(s["url"])}" rel="nofollow noopener" target="_blank">{e(s.get("publisher", s["url"]))}</a></li>'
                              for s in a["sources"])
                src_intro = ("مراجع هذه المقالة من المكتبة الرقمية المجانية، مع ذكر المصدر عند أي اقتباس."
                             if k == "ar_books" else
                             "قراءة رأي شخصية ليست عملاً صحفياً: الوقائع والأرقام مسندة إلى مصادرها، والرأي معلَّم بـ«رأي شخصي» أو «وجهة نظر».")
                src_html = (f'<div class="sources"><b>📚 المصادر والمراجع:</b><p class="src-hint">{src_intro}</p><ul>{src}</ul></div>')
            rel_pool = [x for x in data[k] if x["id"] != a["id"]]
            related = "".join(card(r, "../", k) for r in rel_pool[:3])
            url = f"{base}/articles/{a['id']}.html" if base else ""
            img_abs = cdn(a, 1200) or (f"{base}/{a['image']}" if base else a["image"])
            schema_type = "BlogPosting" if (k == "ar_books" or k in GROUP_OPINION) else "CreativeWork"
            ld = json.dumps({"@context": "https://schema.org", "@type": schema_type, "headline": a["title"],
                             "datePublished": a["date"], "image": [img_abs], "genre": name,
                             "publisher": {"@type": "Organization", "name": "مملكة الأسرار"},
                             "author": {"@type": "Person", "name": "نكسوس"}}, ensure_ascii=False)
            credit = a.get("image_credit") or {}
            if credit.get("kind") == "illustration" or credit.get("source") in ("مملكة الأسرار", "نكسوس"):
                credit_html = '<figcaption class="img-credit">رسم توضيحي أصلي — مملكة الأسرار</figcaption>'
            elif credit.get("kind") == "ai" or str(credit.get("source", "")).lower() in ("ai", "gemini", "openai", "cloudflare", "together", "hfspace", "genai"):
                credit_html = '<figcaption class="img-credit">صورة توليدية أُنشئت خصيصاً لـ«مملكة الأسرار»</figcaption>'
            elif credit.get("source") or credit.get("author"):
                credit_html = f'<figcaption class="img-credit">الصورة: {e(credit.get("author") or credit.get("source"))}</figcaption>'
            else:
                credit_html = ""
            rt = reading_time(a["content"])
            # Fiction keeps its author's voice: the news-oriented style cleaner is only used for the
            # four preserved book articles when they are not explicitly marked manual.
            clean = k == "ar_books" and not a.get("manual")
            inner = f"""<div class="layout"><main><article class="article">
<nav class="crumbs" aria-label="مسار التصفح"><a href="../index.html">الرئيسية</a> › <a href="../category-{k}.html">{e(name)}</a></nav>
<span class="badge">{e(name)}</span>{age_badge(k)}<h1>{e(a["title"])}</h1>
<div class="meta">نكسوس · {e(a["date"][:10])} · ⏱ {rt} د للقراءة</div>
{tags_block}
{hashtags_block}
{video_html}
{opinion_note}
{share_bar()}
{warning_html}
{author_note}
{ad("article_top")}
<figure class="hero-fig"><img class="hero" width="1000" height="563" fetchpriority="high" src="{e(img_src(a, "../", 1000)[0])}"{img_src(a, "../", 1000)[1]} alt="{e(a.get("image_alt", a["title"]))}">{credit_html}</figure>
<div class="article-body">

{render_body(a["content"], clean=clean)}

</div>{ad("article_bottom")}{share_bar()}{src_html}{newsletter("band")}</article>
<section class="related"><h2 class="block-title">قصص ذات صلة</h2><div class="grid">{related}</div></section></main>{sidebar("../", data, poll)}</div>"""
            write_page(f"articles/{a['id']}.html", f'{a["title"]} | مملكة الأسرار', a.get("summary", a["title"]),
                       "../", url, data, k, inner, poll,
                       f'<script type="application/ld+json">{ld}</script>', img_abs)
            urls.append(f"articles/{a['id']}.html")

    # ---- AI academy (generated so the hourly quality gate never fails on a missing page)
    write_page("ai-academy.html", ai_hub.TITLE, ai_hub.DESC, "", f"{base}/ai-academy.html" if base else "",
               data, "ai", ai_hub.body("chat.js"), poll)

    # ---- weather & prayer page, search page
    wx = """<div class="page wx-page notranslate"><h1>🌦️ الطقس ومواقيت الصلاة</h1>
<p class="lead">اكتب اسم أي مدينة في العالم لتظهر لك حالة الطقس وتوقعات الأيام القادمة ومواقيت الصلاة بتوقيت المدينة نفسها.</p>
<div id="wx-app"><div class="wx-box"><input id="wx-q" type="search" placeholder="مثال: الرباط، مكة المكرمة، باريس، New York" autocomplete="off" aria-label="المدينة">
<button class="wx-geo" id="wx-geo" type="button" title="استخدم موقعي">📍 موقعي</button><ul class="wx-sug" id="wx-sug"></ul></div>
<div class="wx-chips" id="wx-chips"></div><div id="wx-out" aria-live="polite"></div></div></div>"""
    write_page("weather.html", "الطقس ومواقيت الصلاة حول العالم | مملكة الأسرار",
               "حالة الطقس وتوقعات الأيام ومواقيت الصلاة لأي مدينة في العالم.",
               "", f"{base}/weather.html" if base else "", data, "weather",
               f'<div class="layout"><main>{wx}</main>{sidebar("", data, poll).replace(wx_mini(), "")}</div>', poll)
    sr = ('<div class="page"><h1>🔍 البحث</h1><form class="search-big" action="search.html"><input id="sq" name="q" type="search" '
          'placeholder="ابحث في قصص المدونة…" autofocus aria-label="بحث"><button class="btn" type="submit">بحث</button></form>'
          '<div id="search-app"><div id="search-out" class="grid"></div></div></div>')
    write_page("search.html", "البحث | مملكة الأسرار", "ابحث في قصص مملكة الأسرار.", "",
               f"{base}/search.html" if base else "", data, "",
               f'<div class="layout"><main>{sr}</main>{sidebar("", data, poll)}</div>', poll,
               '<meta name="robots" content="noindex,follow">')
    index = [{"i": a["id"], "t": a["title"], "s": a.get("summary", ""), "c": CATEGORIES[k], "d": a["date"][:10],
              "h": a.get("hashtags") or [], "m": cdn(a, 480) or thumb(a["image"])}
             for k, a in allart]
    (ROOT / "search.json").write_text(json.dumps(index, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")

    # ---- legal pages (including about.html and the literary disclaimer page)
    today = datetime.now().strftime("%Y-%m-%d")
    for fname, (title, body, cls) in legal.pages(CONTACT_EMAIL, today, CATEGORIES, newsletter("band")).items():
        write_page(fname, f"{title} | مملكة الأسرار", f"{title} - مملكة الأسرار", "",
                   f"{base}/{fname}" if base else "", data, "",
                   f'<div class="page {cls}"><h1>{title}</h1>{body}</div>', poll)

    # ---- feed, sitemap, robots, PWA files
    def absu(rel):
        return f"{base}/{rel}" if base else rel
    items = "".join(
        f"<item><title>{e(a['title'])}</title><link>{e(absu('articles/' + a['id'] + '.html'))}</link><guid isPermaLink=\"false\">{e(a['id'])}</guid>"
        f"<pubDate>{datetime.fromisoformat(a['date']).strftime('%a, %d %b %Y %H:%M:%S +0000')}</pubDate><category>{e(CATEGORIES[k])}</category>"
        f"<description>{e(a.get('summary', ''))}</description></item>" for k, a in allart[:30])
    (ROOT / "feed.xml").write_text(
        '<?xml version="1.0" encoding="UTF-8"?><rss version="2.0"><channel><title>مملكة الأسرار Kingdom Of Secrets</title>'
        f'<link>{e(base or "/")}</link><description>قصص إبداعية آمنة للعائلات من تأليف نكسوس</description><language>ar</language>{items}</channel></rss>', encoding="utf-8")
    (ROOT / "manifest.webmanifest").write_text(json.dumps({
        "name": "مملكة الأسرار Kingdom Of Secrets", "short_name": "مملكة الأسرار", "lang": "ar", "dir": "rtl", "start_url": "./", "scope": "./",
        "display": "standalone", "background_color": "#f5f8fb", "theme_color": "#0b3c7a",
        "icons": [{"src": "icon-192.png", "sizes": "192x192", "type": "image/png"}, {"src": "icon-512.png", "sizes": "512x512", "type": "image/png"}]},
        ensure_ascii=False), encoding="utf-8")
    ver = (allart[0][1]["date"] if allart else "0").replace(":", "").replace("-", "")[:12] + str(len(allart))
    (ROOT / "sw.js").write_text(SW_JS.replace("__VERSION__", ver), encoding="utf-8")
    if base:
        (ROOT / "robots.txt").write_text(
            f"User-agent: *\nAllow: /\nDisallow: /admin/\nDisallow: /admin.html\n\nSitemap: {base}/sitemap.xml\n",
            encoding="utf-8")
        sm = "".join(f"<url><loc>{base}/{u}</loc></url>" for u in urls if u != "search.html")
        (ROOT / "sitemap.xml").write_text(f'<?xml version="1.0" encoding="UTF-8"?><urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">{sm}</urlset>', encoding="utf-8")
    else:
        if not (ROOT / "robots.txt").exists():
            (ROOT / "robots.txt").write_text(
                "User-agent: *\nAllow: /\nDisallow: /admin/\nDisallow: /admin.html\n", encoding="utf-8")
        sm = "".join(f"<url><loc>{u}</loc></url>" for u in urls if u != "search.html")
        (ROOT / "sitemap.xml").write_text(f'<?xml version="1.0" encoding="UTF-8"?><urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">{sm}</urlset>', encoding="utf-8")
    print(f"site built: {sum(len(v) for v in data.values())} articles")


if __name__ == "__main__":
    build()
