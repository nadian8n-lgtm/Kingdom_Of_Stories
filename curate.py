"""Keeps the article archive clean:
 1) removes duplicated / near-duplicated articles (same title, near-identical title, or heavily overlapping text),
 2) puts every article in the section it belongs to (LLM classification when a text provider exists, keyword scoring otherwise).
Every article is classified only once (flag cat_ok) so no tokens are wasted on later runs."""
import json
import re

POLITICS = ("حرب", "رئيس", "حكومة", "انتخابات", "قصف", "وزير", "جيش", "سلام", "هدنة", "برلمان", "عقوبات", "اتفاق", "قمة", "أمن", "لجوء",
            "احتجاجات", "مفاوضات", "سفير", "دبلوماسي", "حزب", "تصويت", "نزاع", "غزة", "أوكرانيا", "ترامب", "الأمم المتحدة", "حدود", "عسكري")
HINTS = {
    "ar_sports": ("كرة", "مباراة", "الدوري", "لاعب", "منتخب", "بطولة", "كأس", "هدف", "فريق", "تنس", "ملعب", "رياضة", "أولمبي", "مدرب", "تصفيات",
                  "نهائي", "بطل", "سباق", "سلة", "ميدالية"),
    "ar_economy": ("اقتصاد", "أسعار", "بورصة", "أسهم", "تضخم", "بنك", "ميزانية", "استثمار", "شركة", "نفط", "تجارة", "ضرائب", "عملة", "دولار",
                   "أرباح", "سوق", "صادرات", "واردات", "فائدة", "ديون", "نمو", "أجور", "رسوم", "الأعمال"),
    "ar_tech": ("تكنولوجيا", "ذكاء اصطناعي", "تطبيق", "هاتف", "شريحة", "برمجيات", "سيبراني", "إنترنت", "روبوت", "آبل", "غوغل", "ميتا", "مايكروسوفت",
                "أمازون", "رقمي", "خوارزمية", "بيانات", "حاسوب", "فضاء", "قمر صناعي", "تقنية", "منصة", "قرصنة", "ابتكار", "إنفيديا", "تسلا", "سامسونغ"),
    "ar_arts": ("فيلم", "مسلسل", "مهرجان", "فنان", "موسيقى", "أغنية", "معرض", "رواية", "كتاب", "سينما", "ثقافة", "جائزة", "متحف", "مسرح", "ممثل",
                "مخرج", "ألبوم", "أدب", "شاعر", "فنية", "تراث", "أوسكار", "كان", "وثائقي"),
    "ar_local": ("المغرب", "مغربي", "المغاربة", "المملكة المغربية", "الحكومة", "البرلمان", "المغرب"),
    "ar_cities": ("جريمة", "حادث", "حادثة", "اعتقال", "توقيف", "أمن", "أمني", "درك", "شرطة", "محكمة", "قضية",
                  "تحقيق", "سرقة", "قتل", "اعتداء", "مخدرات", "تهريب", "احتيال", "حريق", "جثة", "نيابة", "سجن",
                  "الرباط", "الدار البيضاء", "مراكش", "طنجة", "فاس", "أكادير", "مكناس", "وجدة", "تطوان", "القنيطرة",
                  "سلا", "آسفي", "الجديدة", "بني ملال", "خريبكة", "الناظور", "الحسيمة", "العيون", "الداخلة", "ورزازات",
                  "الصويرة", "سطات", "برشيد", "المحمدية", "الرشيدية", "شفشاون", "العرائش", "بنجرير", "تيزنيت", "كلميم"),
    "ar_world": POLITICS,
}
TOPICAL = ("ar_sports", "ar_economy", "ar_tech", "ar_arts")


def _ar(t):
    t = re.sub(r"[\u064B-\u065F\u0670\u0640]", "", str(t or "").lower())
    t = re.sub("[أإآٱ]", "ا", t).replace("ى", "ي").replace("ة", "ه")
    return re.sub(r"[^\w\s]", " ", t)


def _words(t):
    return [w for w in _ar(t).split() if len(w) > 2]


def _grams(text, n=4):
    w = _words(text)
    return {tuple(w[i:i + n]) for i in range(max(0, len(w) - n + 1))}


def _is_book_list(a):
    return "كتب مجانية لتعلم" in (a.get("title") or "") or a.get("kind") == "books"


def duplicates(a, b):
    ta, tb = set(_words(a["title"])), set(_words(b["title"]))
    if ta and tb and (ta == tb or len(ta & tb) / len(ta | tb) >= 0.75):
        return True
    if _is_book_list(a) and _is_book_list(b):
        return False      # two different book lists share the layout, not the story: only an identical title is a duplicate
    ga, gb = _grams(a.get("content", "")), _grams(b.get("content", ""))
    return bool(ga and gb and len(ga & gb) / min(len(ga), len(gb)) >= 0.40)


def dedupe(arts):
    """Keeps the newest copy of every story. Returns the list of removed articles (the caller deletes their images)."""
    flat = sorted(((k, a) for k, v in arts.items() for a in v), key=lambda t: t[1]["date"], reverse=True)
    kept, removed = [], []
    for k, a in flat:
        if any(duplicates(a, b) for _, b in kept):
            removed.append(a)
        else:
            kept.append((k, a))
    keep_ids = {a["id"] for _, a in kept}
    for k in arts:
        arts[k] = [a for a in arts[k] if a["id"] in keep_ids]
    return removed


def is_duplicate_of_any(new, arts):
    return any(duplicates(new, b) for v in arts.values() for b in v)


def _stem(w):
    return re.sub(r"^(وال|بال|لل|ال|و)", "", w) if len(w) > 4 else w


def _score(text, words):
    toks = [_stem(t) for t in _ar(text).split()]
    joined = " ".join(toks)
    n = 0
    for w in words:
        k = _ar(w).strip()
        if " " in k:
            parts = k.split()
            n += joined.count(_stem(parts[0]) + " " + _stem(parts[1]))
        else:
            ks = _stem(k)
            n += sum(1 for t in toks if t == ks or (len(ks) >= 4 and t.startswith(ks)))
    return n


CITY_NAMES = ("الرباط", "الدار البيضاء", "مراكش", "طنجة", "فاس", "أكادير", "مكناس", "وجدة", "تطوان", "القنيطرة",
              "سلا", "آسفي", "بني ملال", "خريبكة", "الناظور", "الحسيمة", "العيون", "الداخلة", "ورزازات",
              "الصويرة", "سطات", "برشيد", "المحمدية", "الرشيدية", "شفشاون", "العرائش", "بنجرير", "تيزنيت", "كلميم",
              "تازة", "أزرو", "إفران", "جرسيف", "تاوريرت", "سيدي قاسم", "سيدي سليمان", "خنيفرة", "أزيلال", "تنغير",
              "ميدلت", "فكيك", "جرادة", "بوعرفة", "السمارة", "طانطان", "بوجدور", "الدشيرة")
CRIME_HINTS = ("جريمة", "جناية", "جنحة", "قتل", "اغتيال", "اعتداء", "اعتقال", "توقيف", "موقوف", "متهم", "ضحية",
               "تحقيق قضائي", "درك", "شرطة", "أمني", "سرقة", "سطو", "تهريب", "مخدرات", "اختطاف", "اغتصاب",
               "تحرش", "جثة", "سجن", "شكاية", "حريق", "احتيال", "قضية", "محكمة", "نيابة", "حكم قضائي")
MOROCCO_WORDS = ("المغرب", "المغربي", "المغاربة", "المملكة المغربية", "المملكة")
STRONG_ECONOMY = ("أسهم", "بورصة", "أسواق المال", "تضخم", "فائدة", "دولار", "اقتصاد", "استثمار", "عملة",
                  "بنك", "ديون", "نفط", "ميزانية", "ضرائب")
STRONG_MARKET = ("أسهم", "بورصة", "أسواق المال", "تضخم", "فائدة", "دولار", "عملة", "نفط", "بنك", "ديون", "عائدات")
STRONG_TECH = ("روبوت", "روبوتات", "ذكاء اصطناعي", "تكنولوجيا", "تقنية", "سيبراني", "قرصنة", "هاتف", "شريحة",
               "برمجيات", "خوارزمية", "إنترنت", "بيانات", "دراجات", "كهربائية", "شحن", "إنفيديا", "غوغل",
               "آبل", "مايكروسوفت", "ميتا", "أمازون", "تسلا", "سامسونغ", "أوبن إيه آي")
STRONG_ARTS = ("فيلم", "وثائقي", "مسلسل", "مهرجان", "موسيقى", "ألبوم", "معرض", "مسرح", "رواية", "سينما", "أوسكار")
STRONG_POLITICS = ("انتخابات", "استفتاء", "رئيس", "حكومة", "برلمان", "وزير", "حرب", "قصف", "جيش", "معاهدة",
                   "قمة", "عقوبات", "سفير", "دبلوماسي", "ائتلاف", "انقلاب")


def heuristic(a, current):
    """Conservative fallback (used only when no language model is available).

    Hard guards, so the mistakes that blocked AdSense can never come back:
      * sport is never filed as world/Morocco news and world politics is never filed as sport;
      * «أخبار المغرب» needs Morocco to be the actual subject (a foreign event is not Moroccan news);
      * «أخبار المدن» needs both a named Moroccan city and a crime/security/court vocabulary.
    """
    title, body = a["title"], a.get("summary", "") + " " + a.get("content", "")[:700]
    score = {c: 3 * _score(title, w) + _score(body, w) for c, w in HINTS.items()}
    sports, world = score["ar_sports"], score["ar_world"]
    crime = 2 * _score(title, CRIME_HINTS) + _score(body, CRIME_HINTS)
    city = 3 * _score(title, CITY_NAMES) + _score(body, CITY_NAMES)
    morocco_centered = (_score(title, MOROCCO_WORDS) >= 1 or _score(title, CITY_NAMES) >= 1
                        or _score(body, MOROCCO_WORDS) >= 2)
    best = max(TOPICAL, key=lambda c: score[c])

    # 1) a real sports story always belongs to sport, whatever section it came from
    if sports >= 5 and sports >= world and sports >= crime:
        return "ar_sports"
    # 2) a named city + a crime/court vocabulary is city news (and nothing else)
    if crime >= 4 and city >= 2 and sports < 6:
        return "ar_cities"
    # 3) Morocco news when Morocco is really the subject (national affairs include Moroccan tech/economy)
    if morocco_centered and score["ar_local"] >= 3 and crime < 4 and sports < 5:
        return "ar_local"
    # 4) a market headline stays economy even when an election or AI is in the same sentence
    if _score(title, STRONG_MARKET) >= 1 and score["ar_economy"] >= 4:
        return "ar_economy"
    # 5) a film/documentary/music headline stays arts even when the film is about a war
    if _score(title, STRONG_ARTS) >= 1 and score["ar_arts"] >= 3:
        return "ar_arts"
    # 6) a technology headline stays tech even when the place is a conflict zone
    if _score(title, STRONG_TECH) >= 1 and score["ar_tech"] >= 2 and score["ar_tech"] >= score["ar_world"] - 2:
        return "ar_tech"
    # 7) elections / war / diplomacy are world news
    if _score(title, STRONG_POLITICS) >= 1 and world >= 4 and not morocco_centered:
        return "ar_world"
    # 7b) a technology story already filed in tech keeps its section when the headline is clearly tech
    if current == "ar_tech" and _score(title, STRONG_TECH) >= 1 and not _score(title, STRONG_POLITICS):
        return "ar_tech"
    # 8) clear topical winners: economy / tech / arts
    if best in ("ar_economy", "ar_tech", "ar_arts") and score[best] >= 5 and score[best] >= world + 1:
        return best
    # 9) international politics/society must not stay in sport or Morocco news
    if world >= 4 and not morocco_centered and world >= sports + 1:
        return "ar_world"
    # 10) keep a correct section rather than flipping it on weak evidence
    if current == "ar_sports" and sports >= 3:
        return "ar_sports"
    if current in TOPICAL and score[current] >= 3 and world < score[current] + 3:
        return current
    if current == "ar_local" and not morocco_centered and world >= 2:
        return "ar_world"
    return current


def classify_llm(items, llm, categories):
    names = "\n".join(f"- {k}: {v}" for k, v in categories.items())
    system = ("أنت رئيس تحرير. صنّف كل مقال في قسم واحد فقط من الأقسام التالية:\n" + names +
              "\nالقواعد الصارمة:\n"
              "- ar_local: كل خبر موضوعه الأساسي المغرب أو المغاربة أو مؤسسات الدولة المغربية (سياسة داخلية واجتماع وشأن وطني). "
              "الخبر الذي لا يتحدث عن المغرب ليس خبراً مغربياً.\n"
              "- ar_cities: حوادث وجرائم وقضايا وقضاء وأمن ووقائع في مدينة مغربية محددة، بلا أسماء أشخاص.\n"
              "- ar_world: كل ما يقع خارج المغرب: السياسة الدولية والعربية والحروب والانتخابات الأجنبية والعلاقات بين الدول والمنظمات الدولية. "
              "أي خبر رياضي أو فني أو اقتصادي أو تقني لا يوضع هنا.\n"
              "- ar_sports: كل ما يتعلق بالرياضة فقط، محلية أو دولية: مباريات ونتائج وتحليلات وانتقالات وبطولات ومنتخبات. "
              "أخبار المنتخب المغربي والأندية المغربية واللاعبين المغاربة تبقى رياضة حتى لو كانت محلية. "
              "الخبر السياسي أو الحربي أو القضائي لا يوضع أبداً في الرياضة.\n"
              "- ar_economy: الاقتصاد والمال والأسواق والشركات. ar_tech: التكنولوجيا والعلوم الرقمية. "
              "ar_arts: الفن والثقافة والسينما والأدب والموسيقى.\n"
              "- الرياضة لا تدخل أبداً في ar_world أو ar_local، والأخبار الدولية السياسية لا تدخل أبداً في ar_sports. "
              "عند الشك بين قسمين اختر القسم الذي يطابق الموضوع الأساسي للخبر لا مصدره.\n"
              'أعد JSON فقط بالشكل {"id": "رمز_القسم", ...} لكل المقالات.')
    user = "\n".join(f"[{a['id']}] {a['title']} — {a.get('summary', '')[:220]}" for a in items)
    raw = llm(system, user)
    a, b = raw.find("{"), raw.rfind("}")
    data = json.loads(raw[a:b + 1])
    return {k: v for k, v in data.items() if v in categories}


def run(arts, categories, llm=None, limit=30, log=print):
    """Returns (removed_articles, moved_count). Mutates `arts` in place."""
    removed = dedupe(arts)
    # «المكتبة الرقمية المجانية» is written deterministically from the book repository: never classify into or out of it.
    for a in arts.get("ar_books", []):
        a["cat_ok"] = True
    cats = {k: v for k, v in categories.items() if k != "ar_books"}
    todo = [(k, a) for k, v in arts.items() for a in v if not a.get("cat_ok") and k != "ar_books"][:limit]
    verdict = {}
    if llm and todo:
        for i in range(0, len(todo), 10):
            chunk = [a for _, a in todo[i:i + 10]]
            try:
                verdict.update(classify_llm(chunk, llm, cats))
            except Exception as ex:
                log("classification by the model failed, using keyword scoring:", str(ex)[:120])
                break
    moves = []
    for k, a in todo:
        new = verdict.get(a["id"]) or heuristic(a, k)
        a["cat_ok"] = True
        if new != k:
            moves.append((k, new, a))
    for old, new, a in moves:
        arts[old] = [x for x in arts[old] if x["id"] != a["id"]]
        arts[new].append(a)
        log(f"moved to the right section: {a['id']}  {old} -> {new}  | {a['title'][:60]}")
    for k in arts:
        arts[k].sort(key=lambda x: x["date"], reverse=True)
    return removed, len(moves)
