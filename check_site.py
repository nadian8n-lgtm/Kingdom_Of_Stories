"""Quality gate: exits with code 1 if the built site has broken internal links, missing images, missing core files,
a Moroccan source link, or two articles sharing the same image file."""
import re
import sys
from pathlib import Path
from urllib.parse import unquote, urlparse

import build_site

ROOT = Path(__file__).parent
SKIP_PREFIX = ("http:", "https:", "//", "mailto:", "tel:", "data:", "#", "javascript:")
problems = []

for need in ("style.css", "site.js", "tools.js", "sw.js", "logo.webp", "manifest.webmanifest", "feed.xml", "search.json",
             "index.html", "about.html", "contact.html", "privacy-policy.html", "editorial-policy.html", "terms.html",
             "404.html", "weather.html", "search.html", "ai-academy.html", "chat.js"):
    if not (ROOT / need).exists():
        problems.append(f"missing core file: {need}")

pages = [p for p in list(ROOT.glob("*.html")) + list((ROOT / "articles").glob("*.html"))
         if not p.name.startswith("google") and p.name != "404.html"]
# Map each article id to its current category in articles.json (since curate.run can move articles across sections without renaming id)
id_to_cat = {}
try:
    for _cat, _items in build_site.load().items():
        for _a in _items:
            if _a.get("id"):
                id_to_cat[_a["id"]] = _cat
except Exception:
    pass
images = {}
for page in pages:
    text = page.read_text(encoding="utf-8")
    src_section = text.split('class="sources"', 1)[1].split('</div>', 1)[0] if 'class="sources"' in text else ""
    for val in re.findall(r'href="(https?://[^"]+)"', src_section):
        if page.parent.name == "articles":
            cat = id_to_cat.get(page.stem) or page.name.split("-")[0]
            if build_site.is_moroccan(val) and cat not in build_site.MOROCCAN_OK_CATS:
                problems.append(f"{page.name}: Moroccan source link {val}")
    for val in re.findall(r'(?:href|src)="([^"]+)"', text):
        if val.startswith(SKIP_PREFIX):
            continue
        target = (page.parent / unquote(urlparse(val).path)).resolve()
        if not target.exists():
            problems.append(f"{page.relative_to(ROOT)} -> missing {val}")
    # every page must open <body> once and close </body></html> exactly once, at the very end
    if len(re.findall(r"<body[\s>]", text)) != 1 or text.count("</body>") != 1 or text.count("</html>") != 1 or not text.rstrip().endswith("</html>"):
        problems.append(f"{page.relative_to(ROOT)}: <body>/</body>/</html> tags are not exactly right")
    for needle in ('class="main-nav"', 'class="footer"'):
        if needle not in text:
            problems.append(f"{page.relative_to(ROOT)} lacks {needle}")
    if page.parent.name == "articles":
        m = re.search(r'<img class="hero"[^>]*src="\.\./([^"?]+)', text)
        if m:
            images.setdefault(m.group(1), []).append(page.name)

for img, owners in images.items():
    if len(owners) > 1:
        problems.append(f"same image used by several articles: {img} -> {owners}")

if problems:
    print("SITE CHECK FAILED:")
    print("\n".join(sorted(set(problems))[:50]))
    sys.exit(1)
print(f"site check OK: {len(pages)} pages, all internal links and images exist")
