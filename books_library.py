"""«المكتبة الرقمية المجانية»: the free-book source behind the section.

Every list is built from the public repository EbookFoundation/free-programming-books
(https://github.com/EbookFoundation/free-programming-books, CC BY 4.0). Nothing is invented:
titles, authors, formats and links are read from the repository's own Markdown files, and each
book keeps the link the repository publishes (the author's/publisher's own page or file).

The module only returns data; fetching_news.py writes the Arabic SEO article around it.
"""
import html
import re
import urllib.parse
import urllib.request
from datetime import datetime, timezone

REPO = "EbookFoundation/free-programming-books"
REPO_URL = f"https://github.com/{REPO}"
LICENSE_URL = f"{REPO_URL}/blob/main/LICENSE"
RAW = f"https://raw.githubusercontent.com/{REPO}/main/books/"
UA = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36 NexusPressBot/2.0"
FILES = {
    "ar": ("free-programming-books-ar.md", "العربية"),
    "subjects": ("free-programming-books-subjects.md", "الإنجليزية"),
    "langs": ("free-programming-books-langs.md", "الإنجليزية"),
}
# hosts that are stores / video courses, not a free book
BLOCK_HOSTS = ("youtube.com", "youtu.be", "coursera.org", "udemy.com", "edx.org", "amazon.", "leanpub.com",
               "packtpub.com", "oreilly.com", "manning.com", "pluralsight.com", "skillshare.com", "facebook.com",
               "twitter.com", "x.com", "linkedin.com", "instagram.com", "t.me")

# normalized section names -> the three repository files they come from
TOPICS = [
    {"key": "ai", "label": "الذكاء الاصطناعي وتعلّم الآلة", "short": "الذكاء الاصطناعي",
     "sections": {"ar": ["artificial intelligence"],
                  "subjects": ["artificial intelligence", "machine learning", "prompt engineering", "computer vision",
                               "data science"]},
     "visual": "a neat stack of artificial-intelligence and machine-learning textbooks beside an open laptop showing "
               "abstract neural-network diagrams, a notebook with hand-drawn nodes and arrows, warm desk lamp"},
    {"key": "python", "label": "بايثون", "short": "بايثون",
     "sections": {"ar": ["python"], "langs": ["python", "django", "flask", "fastapi", "pandas", "numpy"]},
     "visual": "a Python programming book open next to a laptop with code on screen, a cup of coffee, sticky notes and "
               "a small rubber snake on a wooden desk"},
    {"key": "web", "label": "تطوير الويب", "short": "تطوير الويب",
     "sections": {"ar": ["html and css", "javascript", "vue js"],
                  "langs": ["html and css", "javascript", "react", "next js", "node js", "typescript", "php"]},
     "visual": "web-development books and a laptop showing a browser layout, colour swatches, wireframe sketches on paper, "
               "a second monitor and a keyboard on a bright desk"},
    {"key": "security", "label": "الأمن السيبراني", "short": "الأمن السيبراني",
     "sections": {"ar": ["security"], "subjects": ["security privacy"], "langs": []},
     "visual": "cybersecurity books on a dark desk, a laptop with a terminal of green text, a padlock and a hardware "
               "security key, cool blue lighting"},
    {"key": "linux", "label": "لينكس وأنظمة التشغيل", "short": "لينكس",
     "sections": {"ar": ["linux", "operating systems"], "subjects": ["operating systems"],
                  "langs": ["linux", "unix", "bash"]},
     "visual": "Linux and operating-systems books beside a laptop with a terminal window, a mechanical keyboard, a small "
               "penguin figurine and a mug on a dark wooden desk"},
    {"key": "git", "label": "Git وإدارة الإصدارات", "short": "Git",
     "sections": {"ar": ["git"], "subjects": ["version control systems"]},
     "visual": "a Git book open next to a laptop showing a branching commit graph, printed diagrams of branches and "
               "merges, a pen and a notebook on a clean desk"},
    {"key": "databases", "label": "قواعد البيانات وSQL", "short": "قواعد البيانات",
     "sections": {"ar": ["db dbms", "sql", "postgresql"], "subjects": ["database"],
                  "langs": ["dbms", "mysql", "postgresql", "sql implementation agnostic", "nosql", "mongodb"]},
     "visual": "database and SQL books stacked beside a laptop showing table schemas and SQL queries, printed entity "
               "diagrams, a ruler and a pencil on a desk"},
    {"key": "algorithms", "label": "الخوارزميات وهياكل البيانات", "short": "الخوارزميات",
     "sections": {"subjects": ["algorithms data structures", "theoretical computer science", "mathematics for computer science"]},
     "visual": "algorithm textbooks open to pages of diagrams, a whiteboard covered with graphs, trees and complexity "
               "notation, a laptop and a cup of tea in a study room"},
    {"key": "cs", "label": "علوم الحاسب والبرمجة", "short": "علوم الحاسب",
     "sections": {"ar": ["introduction to programming in arabic"],
                  "subjects": ["computer science", "programming", "professional development"]},
     "visual": "introductory computer-science books on a library table, a laptop with a simple code editor, a notebook of "
               "flowcharts and a pencil, soft window light"},
    {"key": "arduino", "label": "الأردوينو والإلكترونيات", "short": "الأردوينو",
     "sections": {"ar": ["arduino", "raspberry pi"], "subjects": ["embedded systems"],
                  "langs": ["arduino", "raspberry pi", "iot"]},
     "visual": "electronics books beside an Arduino board, jumper wires, a breadboard with an LED circuit, a small "
               "Raspberry Pi and a soldering iron on a workbench"},
    {"key": "oss", "label": "المصادر المفتوحة", "short": "المصادر المفتوحة",
     "sections": {"ar": ["open source software"], "subjects": ["open source ecosystem", "licensing"]},
     "visual": "open-source books and printed licence papers on a desk, a laptop showing a repository page with branches, "
               "a small open-source mascot plush and a coffee cup"},
    {"key": "kids", "label": "البرمجة للأطفال والمبتدئين", "short": "البرمجة للأطفال",
     "sections": {"ar": ["scratch", "introduction to programming in arabic"],
                  "langs": ["scratch", "app inventor", "basic"]},
     "visual": "colourful beginner programming books beside a laptop with a block-based coding canvas, paper cut-out "
               "shapes, pencils and a small robot toy on a bright desk"},
]

LINK_RX = re.compile(r"^\s*[*-]\s+\[(.+?)\]\((https?://[^)\s]+)\)\s*(.*)$")
FMT_RX = re.compile(r"\b(PDF|EPUB|MOBI|ODT|HTML|Online|HTML site)\b", re.I)


def _norm(text):
    text = html.unescape(re.sub(r"<[^>]+>", " ", text or ""))
    return re.sub(r"[^a-z0-9]+", " ", text.lower()).strip()


def _clean(text):
    text = html.unescape(text or "")
    text = re.sub(r"<[^>]+>", "", text)
    text = text.replace("\u200f", "").replace("\u200e", "").replace("\u061c", "")
    text = re.sub(r"\s+", " ", text)
    return text.strip(" \t-–—:;,.")


def _fetch(name):
    url = RAW + name
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=45) as r:
        return r.read().decode("utf-8", "ignore")


def parse(md, lang):
    """Returns {normalized section: [book dicts]} from one repository Markdown file."""
    out, section = {}, ""
    for line in md.splitlines():
        s = line.strip()
        if s.startswith("###"):
            section = _norm(re.sub(r"^#+\s*", "", s))
            continue
        m = LINK_RX.match(line)
        if not m or not section:
            continue
        title, url, tail = _clean(m.group(1)), m.group(2).strip(), _clean(m.group(3))
        if len(title) < 3 or len(title) > 130 or "http" in title.lower():
            continue
        host = urllib.parse.urlparse(url).netloc.lower()
        if not host or any(b in host for b in BLOCK_HOSTS):
            continue
        if "free-programming-books" in url:
            continue
        fmt = {f.upper().replace("ONLINE", "HTML").replace("HTML SITE", "HTML") for f in FMT_RX.findall(tail + " " + url)}
        if not fmt:
            fmt = {"HTML"}
        author = re.sub(r"\([^)]*\)", "", tail)
        author = re.sub(r"\s*[-–—]\s*$", "", author).strip(" -–—")
        if len(author) > 110:
            author = author[:110].rsplit(" ", 1)[0]
        out.setdefault(section, []).append({
            "title": title, "url": url, "author": author,
            "fmt": ", ".join(sorted(fmt)), "lang": lang, "host": host,
        })
    return out


def load_library(log=print):
    """Fetch + parse the three repository files. Returns {file_key: {section: [books]}} (empty on network failure)."""
    lib = {}
    for key, (name, lang) in FILES.items():
        try:
            lib[key] = parse(_fetch(name), lang)
        except Exception as ex:
            log(f"books: cannot read {name}: {str(ex)[:120]}")
            lib[key] = {}
    return lib


def _key(book):
    return book["url"].split("#")[0].rstrip("/").lower()


def pick_books(topic, lib, used=(), number=5):
    """The 5 real repository entries for one topic: Arabic first (max 3), then English; no repeated link,
    no more than 2 books from the same website. Returns [] when the topic cannot fill the list."""
    used = {u.split("#")[0].rstrip("/").lower() for u in used}
    pool, seen = [], set()
    for file_key, sections in topic["sections"].items():
        for sec in sections:
            for book in lib.get(file_key, {}).get(_norm(sec), []):
                k = _key(book)
                if k in used or k in seen:
                    continue
                seen.add(k)
                score = 0
                if book["lang"] == "العربية":
                    score += 100
                if "PDF" in book["fmt"]:
                    score += 10
                elif "EPUB" in book["fmt"]:
                    score += 6
                year = re.search(r"\b(20[0-2]\d)\b", book["title"])
                if year:
                    score += max(0, int(year.group(1)) - 2015)
                pool.append((score, book))
    pool.sort(key=lambda t: -t[0])
    out, per_host, arabic = [], {}, 0
    for _, book in pool:
        if len(out) >= number:
            break
        if book["lang"] == "العربية" and arabic >= 3:
            continue
        if per_host.get(book["host"], 0) >= 2:
            continue
        per_host[book["host"]] = per_host.get(book["host"], 0) + 1
        arabic += book["lang"] == "العربية"
        out.append(book)
    return out


def make_payload(articles, lib=None, log=print):
    """Everything the article writer needs: topic, fixed SEO title, the 5 book entries and the source note."""
    lib = lib or load_library(log)
    used = set()
    for a in articles:
        for b in a.get("books", []) or []:
            if b.get("url"):
                used.add(b["url"])
        used.update(re.findall(r"\]\((https?://[^)\s]+)\)", a.get("content", "")))
    order = sorted(TOPICS, key=lambda t: (sum(1 for a in articles
                                                if (a.get("book_topic") or next((x["key"] for x in TOPICS if x["short"] in a.get("title", "")), None)) == t["key"]),
                                           TOPICS.index(t)))
    for topic in order + TOPICS:                      # second pass: allow a topic that simply has new books left
        books = pick_books(topic, lib, used)
        if len(books) == 5:
            year = datetime.now(timezone.utc).year
            return {
                "topic": topic["key"],
                "label": topic["label"],
                "short": topic["short"],
                "books": books,
                "title": f"أفضل 5 كتب مجانية لتعلم {topic['short']} في {year}",
                "summary": f"قائمة مختارة من خمسة كتب مجانية لتعلم {topic['label']}، بروابط القراءة والتحميل "
                           f"من مستودع Free Programming Books المفتوح.",
                "visual_prompt": topic["visual"],
                "repo_url": REPO_URL,
                "license_url": LICENSE_URL,
            }
    log("books: no topic has 5 fresh entries left right now")
    return None


def list_block(books):
    """The Markdown block that build_site renders as <ul class="book-list">: real titles, authors, formats and links."""
    lines = ["## الكتب الخمسة المجانية", ""]
    for b in books:
        author = f" — {b['author']}" if b["author"] else ""
        fmt = f" ({b['fmt']})" if b["fmt"] else ""
        lang_note = "(بالعربية)" if b["lang"] == "العربية" else "(بالإنجليزية)"
        lines.append(f"- [{b['title']}]({b['url']}){author}{fmt} {lang_note}")
    return "\n".join(lines)


def credit_block(payload):
    """Attribution required by the repository licence + a plain note on the books' own rights."""
    return ("## عن الحقوق والمصادر\n\n"
            f"اختيرت هذه الكتب من مستودع [Free Programming Books]({payload['repo_url']}) المفتوح، وهو أكبر تجميع "
            f"عالمي للكتب البرمجية المجانية القانونية (أكثر من 360 ألف نجمة على GitHub)، ويُوزَّع تحت رخصة المشاع "
            f"الإبداعي [CC BY 4.0]({payload['license_url']}). عناوين الكتب وأسماء مؤلفيها وروابطها مأخوذة كما هي "
            "من المستودع دون تغيير. حقوق كل كتاب تبقى لمؤلفه أو ناشره ووفق الرخصة التي نشره بها، والروابط تحيل إلى "
            "المصدر الأصلي الذي ينشره المستودع؛ وإذا تعذّر فتح رابط فابحث عن الكتاب بالعنوان في المستودع.")
