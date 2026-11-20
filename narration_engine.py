#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
محرّك التعليق الصوتي «مملكة الأسرار» — مجاني 100% وبلا مفتاح.

يعتمد على أصوات Microsoft Edge العصبية (edge-tts) وهي:
  - مجانية تماماً بلا حساب ولا مفتاح ولا بطاقة.
  - عربية فصيحة طبيعية (23 صوتاً عربياً).
  - تون سينمائي مضبوط: سرعة + طبقة صوت + وقفات + ماسترنغ.

الوظائف:
  - narration_for(article, category) : يحوّل المقال إلى نص سردي نظيف.
  - build_narration(...)             : ينتج m4a جاهزاً للفيديو + ملف SRT اختياري.
  - تون لكل نوع: دينية وقورة، رعب هامسة، أطفال دافئة، كوميديا خفيفة…

الاستخدام المباشر:
  python narration_engine.py --only story_religious-202611180017-e1f7a9 --voice ar-SA-HamedNeural
"""
from __future__ import annotations

import argparse
import asyncio
import html
import json
import re
import shutil
import subprocess
import sys
import time
import uuid
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")

BASE = Path(__file__).resolve().parent
VOICE_DIR = BASE / "_narration_cache"
VOICE_DIR.mkdir(exist_ok=True)

try:
    import imageio_ffmpeg

    FFMPEG = imageio_ffmpeg.get_ffmpeg_exe()
except Exception:  # noqa: BLE001
    FFMPEG = shutil.which("ffmpeg") or ""

# ----------------------------------------------------------------------------
# تون الصوت لكل نوع (Voice + Prosody)
# ----------------------------------------------------------------------------
PROFILES: dict[str, dict] = {
    "story_religious": dict(voice="ar-SA-HamedNeural", rate="+0%", pitch="+0Hz", gap=0.55, music=0.0),
    "story_history":   dict(voice="ar-SA-HamedNeural", rate="+0%", pitch="+0Hz", gap=0.5,  music=0.0),
    "story_realistic": dict(voice="ar-SA-HamedNeural", rate="+0%", pitch="+0Hz", gap=0.4,  music=0.0),
    "story_fantasy":   dict(voice="ar-SA-HamedNeural", rate="+0%", pitch="+0Hz", gap=0.45, music=0.0),
    "story_mystery":   dict(voice="ar-EG-ShakirNeural", rate="+0%", pitch="+0Hz", gap=0.6,  music=0.0),
    "story_horror":    dict(voice="ar-EG-ShakirNeural", rate="+0%", pitch="+0Hz", gap=0.75, music=0.0),
    "story_scifi":     dict(voice="ar-MA-JamalNeural", rate="+0%",  pitch="+0Hz", gap=0.4,  music=0.0),
    "story_comedy":    dict(voice="ar-MA-JamalNeural", rate="+0%",  pitch="+0Hz", gap=0.3,  music=0.0),
    "kids_3_6":        dict(voice="ar-SA-ZariyahNeural", rate="+0%", pitch="+0Hz", gap=0.5,  music=0.0),
    "kids_7_10":       dict(voice="ar-SA-ZariyahNeural", rate="+0%", pitch="+0Hz", gap=0.4,  music=0.0),
    "kids_11_14":      dict(voice="ar-SA-ZariyahNeural", rate="+0%", pitch="+0Hz", gap=0.35, music=0.0),
}
DEFAULT_PROFILE = dict(voice="ar-SA-HamedNeural", rate="+0%", pitch="+0Hz", gap=0.45, music=0.0)

# أسطر لا تُقرأ (إخلاءات، ملاحظات تحريرية، وسوم)
_SKIP_STARTS = ("إخلاء", "تنبيه", "ملاحظة", "المصدر", "اقرأ أيضاً", "اقرأ أيضا", "شارك", "تابع")
_TAG_RE = re.compile(r"<[^>]+>")
_MD_RE = re.compile(r"[*_`#>\[\]|]+")
_SPACE_RE = re.compile(r"[ \t\u00a0]+")
_DIACRITICS = "\u064b-\u0652\u0670"

# أسماء الأنبياء والرسل (يُضاف لكل اسم «عليه السلام»، وللنبي محمد صلى الله عليه وسلم الدعاء كاملاً)
_MUHAMMAD_RE = re.compile(
    r"(?<![\u0621-\u064a])(?:[وبلكف])?"
    r"(?:رسول\s+الله\s+محمد|النبي\s+محمد|سيدنا\s+محمد|محمد)"
    rf"[{_DIACRITICS}]?",
    re.UNICODE,
)
_PROPHETS_RE = re.compile(
    r"(?<![\u0621-\u064a])(?:[وبلكف])?"
    r"(?:آدم|إدريس|نوح|هود|إبراهيم|لوط|إسماعيل|إسحاق|يعقوب|يوسف|أيوب|شعيب|"
    r"موسى|هارون|داود|سليمان|إلياس|اليسع|يونس|زكريا|يحيى|عيسى)"
    rf"[{_DIACRITICS}]?",
    re.UNICODE,
)
# «صالح» يُذكر أيضاً كفعل (فصالح أهلها)، لذلك نضيفه فقط مع قرينة صريحة.
_SALEH_RE = re.compile(
    r"(?<![\u0621-\u064a])(?:[وبلكف])?(?:النبي\s+|نبي\s+الله\s+|سيدنا\s+)?صالح"
    rf"[{_DIACRITICS}]?(?=\s*(?:عليه|[،.؛؟:«»)]|$))",
    re.UNICODE,
)
_DUA_MUHAMMAD = "صلى الله عليه وسلم"
_DUA_PROPHET = "عليه السلام"

# أسماء السور التي تُطابق أسماء الأنبياء (يوسف: 4، هود: 46، نوح: 1...).
# clean_text يُزيل الأقواس فيبقى «يوسف: 4»، فكان يُ-added إليه «عليه السلام»
# ويُشكَّك كأنه ذكر للنبيّ، فيخرج السرد بـ«يُوسُف عَلَيْهِ السَّلَامُ: 4».
# هذا كلامٌ ليس في القرآن، وهو سبب «خطأ التشكيل أثناء السرد».
_CITATION_TAIL_RE = re.compile(r"^\s*[:\-]\s*\d")


def _is_citation(remaining: str) -> bool:
    """هل الاسم الذي تبعَه «: رقم» هو اسم سورةٍ في مرجع آية؟"""
    return bool(_CITATION_TAIL_RE.match(remaining[:12]))


def _has_dua(tail: str) -> bool:
    """ينظر فقط لما يلي الاسم مباشرة لتفادي تكرار الدعاء الموجود أصلاً."""
    t = re.sub(rf"[{_DIACRITICS}\s،.؛:!؟«»()]", "", tail[:20])
    return t.startswith(("صلى", "عليه", "ﷺ"))


def _spoken_dua(text: str) -> str:
    """
    يحوّل رمز ﷺ إلى عبارة منطوقة كاملة: edge-tts لا ينطق الرمز إطلاقاً،
    وهذا هو السبب الرئيسي في «عدم قراءة كل النص المكتوب».
    """
    def glyph(m: re.Match) -> str:
        prefix = text[max(0, m.start() - 30):m.start()]
        last = None
        for pm in _PROPHETS_RE.finditer(prefix):
            last = pm
        dua = _DUA_PROPHET if last and len(prefix) - last.end() <= 4 else _DUA_MUHAMMAD
        nxt = text[m.end():m.end() + 1]
        return f" {dua}" + ("" if nxt and nxt[0] in "،.؛:!؟«»)]" else " ")

    text = re.sub("ﷺ", glyph, text)
    for _ in range(4):
        before = text
        text = re.sub(rf"(?:{_DUA_MUHAMMAD}\s+){{2,}}", _DUA_MUHAMMAD + " ", text)
        text = re.sub(rf"(?:{_DUA_PROPHET}\s+){{2,}}", _DUA_PROPHET + " ", text)
        text = re.sub(rf"{_DUA_MUHAMMAD}\s+{_DUA_PROPHET}(?=\s|$)", _DUA_MUHAMMAD + " ", text)
        if text == before:
            break
    return re.sub(r"[ \t]{2,}", " ", text)


def apply_honorifics(text: str) -> str:
    """ﷺ لمحمد صلى الله عليه وسلم، و«عليه السلام» لباقي الأنبياء والرسل — بلا تكرار."""
    text = _spoken_dua(text)

    def muhammad(m: re.Match) -> str:
        tail = text[m.end():m.end() + 45]
        if _is_citation(tail) or _has_dua(tail):
            return m.group(0)
        return m.group(0) + " " + _DUA_MUHAMMAD

    text = _MUHAMMAD_RE.sub(muhammad, text)

    def prophet(m: re.Match) -> str:
        tail = text[m.end():m.end() + 45]
        if _is_citation(tail) or _has_dua(tail):
            return m.group(0)
        return m.group(0) + " " + _DUA_PROPHET

    text = _PROPHETS_RE.sub(prophet, text)
    return _SALEH_RE.sub(prophet, text)


# ----------------------------------------------------------------------------
# تشكيل انتقائي: يُضاف قبل التركيب الصوتي فقط، ولا يغيّر حروف النص الأصلي.
# الهدف تثبيت مخارج الحروف وتحسين النطق لدى محرّك edge-tts.
# ----------------------------------------------------------------------------
_VOCAL_PHRASES = [
    ("صلى الله عليه وسلم", "صَلَّى اللَّهُ عَلَيْهِ وَسَلَّمَ"),
    ("عليه السلام", "عَلَيْهِ السَّلَامُ"),
    ("عليهما السلام", "عَلَيْهِمَا السَّلَامُ"),
    ("رضي الله عنهم", "رَضِيَ اللَّهُ عَنْهُمْ"),
    ("رضي الله عنها", "رَضِيَ اللَّهُ عَنْهَا"),
    ("سبحانه وتعالى", "سُبْحَانَهُ وَتَعَالَى"),
    ("والله أعلم", "وَاللَّهُ أَعْلَمُ"),
]
# تشكيل داخلي فقط (بلا حركة إعراب أخيرة) كي لا نفرض رفعاً أو نصباً خاطئاً؛
# edge-tts يكمل حركة آخر الكلمة من السياق، فتثبت المخارج دون كسر الإعراب.
_VOCAL_WORDS = {
    "محمد": "مُحَمَّد", "آدم": "آدَم", "إدريس": "إِدْرِيس", "نوح": "نُوح",
    "هود": "هُود", "صالح": "صَالِح", "شعيب": "شُعَيْب", "إبراهيم": "إِبْرَاهِيم",
    "إسماعيل": "إِسْمَاعِيل", "إسحاق": "إِسْحَاق", "يعقوب": "يَعْقُوب",
    "يوسف": "يُوسُف", "موسى": "مُوسَى", "هارون": "هَارُون", "داود": "دَاوُد",
    "سليمان": "سُلَيْمَان", "إلياس": "إِلْيَاس", "اليسع": "الْيَسَع",
    "يونس": "يُونُس", "زكريا": "زَكَرِيَّا", "يحيى": "يَحْيَى", "عيسى": "عِيسَى",
    "مريم": "مَرْيَم",
}
_VOCAL_WORDS = sorted(_VOCAL_WORDS.items(), key=lambda kv: -len(kv[0]))
_DIAC_RE = re.compile(r"[\u064b-\u0652\u0670]")


def vocalize(text: str) -> str:
    """يُشكّل العبارات المحورية تشكيلاً محافظاً يخدم النطق لا يعنيه.

    يُطبَّق على نص edge-tts فقط قبل التركيب؛ النص الأصلي في articles.json
    وملف SRT يحتفظان بحروفه، والهدف تثبيت مخارج الحروف لا تغيير المعنى.
    """
    for a, b in _VOCAL_PHRASES:
        text = text.replace(a, b)
    for word, form in _VOCAL_WORDS:
        pattern = rf"(?<![\u0621-\u064a]){re.escape(word)}(?![\u0621-\u064a])"
        def repl(m: re.Match) -> str:
            # لا تُشكَّك أسماء السور في مراجع الآيات (يوسف: 4، هود: 46...)
            if _is_citation(text[m.end():m.end() + 12]):
                return m.group(0)
            return m.group(0) if _DIAC_RE.search(m.group(0)) else form
        text = re.sub(pattern, repl, text)
    return text


def coverage_report(article: dict) -> dict:
    """يتأكد أن كل كلمة من النص الأصلي وصلت إلى نص التعليق (بعد إضافة الألقاب)."""
    import unicodedata

    def norm(s: str) -> list[str]:
        s = re.sub(rf"[{_DIACRITICS}]", "", s.lower())
        s = unicodedata.normalize("NFKC", s)
        return re.findall(r"[\u0621-\u064a0-9]+", s)

    source = clean_text(article.get("content")) + " " + clean_text(article.get("title"))
    target = apply_honorifics(narration_text(article))
    src, dst = norm(source), norm(target)
    from collections import Counter
    missing = Counter(src) - Counter(dst)
    return {
        "source_words": len(src),
        "narration_words": len(dst),
        "missing": sum(missing.values()),
        "examples": list(missing.keys())[:12],
        "glyph_replaced": str(article.get("content", "")).count("ﷺ"),
    }


# ----------------------------------------------------------------------------
def clean_text(value) -> str:
    """يحوّل أي قيمة (نص/قائمة/HTML) إلى نص عربي نظيف صالح للقراءة."""
    if isinstance(value, (list, tuple)):
        parts = [clean_text(v) for v in value]
        return "\n\n".join(p for p in parts if p)
    s = html.unescape(str(value or ""))
    s = _TAG_RE.sub(" ", s)
    s = _MD_RE.sub(" ", s)
    s = s.replace("\u200f", "").replace("\u200e", "")
    s = _SPACE_RE.sub(" ", s)
    lines = []
    for raw in s.splitlines():
        line = raw.strip(" -–—·•\t")
        if not line:
            continue
        if line.startswith(_SKIP_STARTS):
            continue
        lines.append(line)
    return "\n".join(lines).strip()


def narration_text(article: dict, brand: bool = True) -> str:
    """نص السرد: افتتاحية الهوية، العنوان، الملخّص، فقرات القصة، ثم خاتمة."""
    chunks: list[str] = []
    title = clean_text(article.get("title"))
    if brand:
        chunks.append("من مملكة الأسرار، نقدّم لكم.")
    if title:
        chunks.append(title + ".")
    summary = clean_text(article.get("summary"))
    if summary and len(summary) < 700:
        chunks.append(summary)
    body = clean_text(article.get("content"))
    if body:
        chunks.append(body)
    if brand:
        chunks.append("إلى اللقاء في حكاية أخرى، من مملكة الأسرار.")
    return "\n\n".join(chunks)


# ----------------------------------------------------------------------------
def _split_chunks(text: str, limit: int = 240) -> list[str]:
    """يقسّم عند الفقرات أولاً، ثم عند الوقفات، ليأخذ كل حدث نبرتَه المستقلة."""
    out: list[str] = []
    for para in re.split(r"\n\s*\n+", text.strip()):
        para = para.strip()
        if not para:
            continue
        parts = [p.strip() for p in re.split(r"(?<=[،,.!؟…:؛])\s+|\n+", para) if p.strip()]
        buf = ""
        for p in parts:
            if len(buf) + len(p) + 1 <= limit:
                buf = f"{buf} {p}".strip()
            else:
                if buf:
                    out.append(buf)
                    buf = ""
                while len(p) > limit:
                    cut = p.rfind("،", 0, limit)
                    if cut < limit // 2:
                        cut = p.rfind(" ", 0, limit)
                    if cut < limit // 3:
                        cut = limit
                    out.append(p[:cut].strip())
                    p = p[cut:].strip()
                buf = p
        if buf:
            out.append(buf)
    return out


# ----------------------------------------------------------------------------
# تدرّج الأداء: كل مقطع يأخذ نبرة تناسب حدثه (هدوء / تصاعد / ذروة / فرح / سؤال)
# ----------------------------------------------------------------------------
_TENSION = (
    "صرخ", "نادى", "نودي", "انشقّ", "انشقت", "زلزلة", "زلّت", "عاصفة", "ريح", "ظلام",
    "خشي", "خاف", "فزع", "رعب", "دهش", "تعجّب", "تحدّى", "أنذر", "حذّر", "وعيد",
    "نار", "جبل", "بطش", "شدّة", "شدة", "غضب", "قسوة", "محنة", "بلاء", "امتحان",
    "التنّور", "فار", "غرق", "هلاك", "سحر", "حوت", "ظلمات",
    "طوفان", "موجات", "صيحة", "عذاب", "زلزال", "فزع", "اشتدّ", "جاثمين",
)
_JOY = (
    "بشارة", "فرح", "فرحت", "سرور", "ابتسم", "رضي", "رسول", "نجاة", "نجا", "أمان",
    "رحمة", "رطب", "مطر", "خصب", "رزق", "عود", "لقاء", "سلام", "أمن",
)


def _num(value: str, default: int = 0) -> int:
    m = re.search(r"([+-]?\d+)", str(value))
    return int(m.group(1)) if m else default


def _pct(v: int) -> str:
    return f"{v:+d}%"


def _hz(v: int) -> str:
    return f"{v:+d}Hz"


def _energy(chunk: str) -> float:
    """درجة حدّة المقطع من 0 إلى 1، تُبنى على الكلمات وعلامات الترقيم."""
    score = 0.12
    for w in _TENSION:
        if w in chunk:
            score += 0.16
    for w in _JOY:
        if w in chunk:
            score += 0.10
    if "؟" in chunk or "!" in chunk:
        score += 0.16
    if "«" in chunk:
        score += 0.08
    if len(chunk) > 200:
        score += 0.05
    return min(1.0, score)


_HOOK_RE = re.compile(r"^(توقّف|تخيّل|ما الذي|قبل أن تقرأ|كم من|في لحظة|لو سألت|تخيّلوا|تأمّل)")


def _chunk_prosody(chunk: str, base: dict, category: str) -> dict:
    """يعيد نسخة من إعدادات الصوت مضبوطة على حدّة هذا المقطع بالذات."""
    p = dict(base)
    e = _energy(chunk)
    base_rate, base_pitch = _num(base["rate"]), _num(base["pitch"])
    gap = float(base.get("gap") or 0.45)

    # الافتتاحية الخطّافة: إبطاءٌ محسوب، نبرةٌ أخفض، جهارةٌ أوضح، ووقفةٌ قبل الحدث
    if _HOOK_RE.search(chunk.strip()):
        p.update(rate=_pct(base_rate - 2), pitch=_hz(base_pitch - 1),
                 volume="+4%", pause=gap * 1.35)
        return p

    if "؟" in chunk and e < 0.55:
        p.update(rate=_pct(base_rate - 2), pitch=_hz(base_pitch + 1),
                 volume="+1%", pause=gap * 1.15)
    elif any(w in chunk for w in _JOY) and e < 0.62:
        p.update(rate=_pct(base_rate + 1), pitch=_hz(base_pitch + 1),
                 volume="+3%", pause=gap * 0.9)
    elif e >= 0.62:
        # الذروة: نُبطئ قليلاً ونُخفض النبرة ونمنحها وقفةً درامية
        p.update(rate=_pct(base_rate - 4), pitch=_hz(base_pitch - 2),
                 volume="+6%", pause=gap * 1.7)
    elif e >= 0.35:
        p.update(rate=_pct(base_rate - 1), pitch=_hz(base_pitch),
                 volume="+2%", pause=gap * 1.25)
    else:
        p.update(rate=_pct(base_rate), pitch=_hz(base_pitch),
                 volume="+0%", pause=gap * 0.85)

    if category in ("story_horror", "story_mystery") and e >= 0.62:
        p["rate"] = _pct(_num(p["rate"]) - 2)
        p["pitch"] = _hz(_num(p["pitch"]) - 1)

    # الوقفة عند الفاصلة قصيرة جداً: تنفّسٌ بين الكلمات بلا إيقاع مقطّع
    if chunk.rstrip().endswith("،"):
        p["pause"] = gap * 0.45
        p["rate"] = _pct(base_rate)
    return p


def _run(args: list[str], timeout: int = 0) -> None:
    if not FFMPEG:
        raise RuntimeError("ffmpeg غير متوفّر (pip install imageio-ffmpeg).")
    r = subprocess.run([FFMPEG, "-hide_banner", "-loglevel", "error", "-y", *args],
                       capture_output=True, text=True, timeout=(timeout or None))
    if r.returncode != 0:
        raise RuntimeError(f"ffmpeg: {r.stderr.strip()[:400]}")


def audio_duration(path: Path) -> float:
    """مدة الملف الصوتي بالثواني."""
    try:
        r = subprocess.run([FFMPEG, "-hide_banner", "-i", str(path)],
                           capture_output=True, text=True)
        m = re.search(r"Duration:\s*(\d+):(\d+):(\d+(?:\.\d+)?)", r.stderr)
        if m:
            h, mi, se = m.groups()
            return int(h) * 3600 + int(mi) * 60 + float(se)
    except Exception:  # noqa: BLE001
        pass
    try:
        from mutagen.mp4 import MP4

        return float(MP4(str(path)).info.length)
    except Exception:  # noqa: BLE001
        return 0.0


# ----------------------------------------------------------------------------
async def _synth_chunk(text: str, profile: dict, out_mp3: Path) -> list[tuple[float, float, str]]:
    """يولّد مقطعاً واحداً ويعيد حدود الكلمات (بداية، نهاية، كلمة)."""
    import edge_tts

    comm = edge_tts.Communicate(
        text,
        profile["voice"],
        rate=profile["rate"],
        pitch=profile["pitch"],
        volume=profile.get("volume", "+0%"),
        boundary="WordBoundary",
        receive_timeout=120,
    )
    words: list[tuple[float, float, str]] = []
    with open(out_mp3, "wb") as fh:
        async for chunk in comm.stream():
            if chunk["type"] == "audio":
                fh.write(chunk["data"])
            elif chunk["type"] == "WordBoundary":
                start = chunk["offset"] / 1e7
                dur = chunk["duration"] / 1e7
                words.append((start, start + dur, chunk["text"]))
    if out_mp3.stat().st_size < 800:
        raise RuntimeError("edge-tts: مقطع فارغ (شبكة/صوت غير متاح).")
    return words


def _srt_time(t: float) -> str:
    ms = int(round(t * 1000))
    h, ms = divmod(ms, 3600000)
    m, ms = divmod(ms, 60000)
    s, ms = divmod(ms, 1000)
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


def _write_srt(words: list[tuple[float, float, str]], path: Path,
               max_chars: int = 46, max_sec: float = 4.6) -> None:
    """يجمع الكلمات في أسطر ترجمة مريحة للقراءة (لا كلمة لكل سطر)."""
    lines: list[str] = []
    idx = 0
    buf: list[tuple[float, float, str]] = []

    def flush() -> None:
        nonlocal idx, buf
        if not buf:
            return
        text = _DIAC_RE.sub("", " ".join(w for _, _, w in buf)).strip()
        start, end = buf[0][0], buf[-1][1]
        if text:
            idx += 1
            lines.extend([str(idx), f"{_srt_time(start)} --> {_srt_time(end)}", text, ""])
        buf = []

    for start, end, word in words:
        if buf and (len(" ".join(w for _, _, w in buf)) + len(word) + 1 > max_chars
                    or end - buf[0][0] > max_sec):
            flush()
        buf.append((start, end, word))
        if word.endswith((".", "؟", "!", "…", ":", "؛")):
            flush()
    flush()
    path.write_text("\n".join(lines), encoding="utf-8")


# ----------------------------------------------------------------------------
async def _synth_many(chunks: list[str], profiles: list[dict], work: Path, retries: int = 3,
                      workers: int = 4, verbose: bool = True
                      ) -> list[tuple[int, Path, list[tuple[float, float, str]]]]:
    """يولّد كل المقاطع بالتوازي (أسرع 4×) مع الحفاظ على الترتيب."""
    sem = asyncio.Semaphore(max(1, workers))

    async def one(i: int, text: str):
        async with sem:
            mp3 = work / f"part_{i:04d}.mp3"
            last: Exception | None = None
            for attempt in range(1, retries + 1):
                try:
                    words = await _synth_chunk(text, profiles[i - 1], mp3)
                    return i, mp3, words
                except Exception as e:  # noqa: BLE001
                    last = e
                    await asyncio.sleep(1.2 * attempt)
            raise RuntimeError(f"تعذّر توليد المقطع {i}: {last}")

    tasks = [asyncio.create_task(one(i, c)) for i, c in enumerate(chunks, 1)]
    out: list[tuple[int, Path, list[tuple[float, float, str]]]] = []
    for fut in asyncio.as_completed(tasks):
        out.append(await fut)
        if verbose and len(out) % 10 == 0:
            print(f"      صوت: {len(out)}/{len(chunks)}", flush=True)
    out.sort(key=lambda r: r[0])
    return out


def build_narration(text: str, out_m4a: Path, *, category: str = "story_religious",
                    voice: str | None = None, rate: str | None = None,
                    pitch: str | None = None, gap: float | None = None,
                    music: float | None = None, srt_out: Path | None = None,
                    retries: int = 3, workers: int = 4, verbose: bool = True) -> Path:
    """
    ينتج تعليقاً صوتياً احترافياً (m4a/AAC) من نص عربي.
    يعيد مسار الملف الصوتي.
    """
    prof = dict(PROFILES.get(category, DEFAULT_PROFILE))
    if voice:
        prof["voice"] = voice
    if rate:
        prof["rate"] = rate
    if pitch:
        prof["pitch"] = pitch
    if gap is not None:
        prof["gap"] = float(gap)
    if music is not None:
        prof["music"] = float(music)

    out_m4a = Path(out_m4a)
    out_m4a.parent.mkdir(parents=True, exist_ok=True)
    text = vocalize(apply_honorifics(text))
    chunks = _split_chunks(text)
    if not chunks:
        raise RuntimeError("لا يوجد نص للقراءة.")

    work = VOICE_DIR / f"work_{uuid.uuid4().hex[:10]}"
    work.mkdir(parents=True, exist_ok=True)
    try:
        pieces: list[Path] = []
        words_all: list[tuple[float, float, str]] = []
        cursor = 0.0

        # نبرة كل مقطع تتبع حدثه، ووقفته تتبع شدّته
        profiles = [_chunk_prosody(c, prof, category) for c in chunks]

        # صمت بين المقاطع (بنفس ترميز edge-tts: 24kHz mono 48kbps) — ملف لكل طول
        silences: dict[str, Path] = {}

        def silence_for(seconds: float) -> Path:
            key = f"{max(0.0, seconds):.2f}"
            if key not in silences:
                fp = work / f"gap_{key.replace('.', '_')}.mp3"
                _run(["-f", "lavfi", "-i", "anullsrc=r=24000:cl=mono",
                      "-t", key, "-c:a", "libmp3lame",
                      "-b:a", "48k", "-ar", "24000", "-ac", "1", str(fp)])
                silences[key] = fp
            return silences[key]

        parts = asyncio.run(_synth_many(chunks, profiles, work, retries=retries,
                                        workers=workers, verbose=verbose))
        for n, (_, mp3, ws) in enumerate(parts, 1):
            dur = audio_duration(mp3)
            for s, e, w in ws:
                words_all.append((cursor + s, cursor + e, w))
            pieces.append(mp3)
            cursor += dur
            if n < len(chunks):
                pause = float(profiles[n - 1].get("pause", prof["gap"]))
                pieces.append(silence_for(pause))
                cursor += pause
        if verbose:
            print(f"      صوت: {len(chunks)} مقطعاً ({cursor / 60:.1f} دقيقة)", flush=True)

        # دمج المقاطع
        lst = work / "parts.txt"
        lst.write_text("".join(f"file '{p.as_posix()}'\n" for p in pieces), encoding="utf-8")
        joined = work / "joined.wav"
        _run(["-f", "concat", "-safe", "0", "-i", str(lst),
              "-c:a", "pcm_s16le", "-ar", "24000", "-ac", "1", str(joined)])
        total = audio_duration(joined)
        if total <= 0:
            raise RuntimeError("الصوت الناتج فارغ.")

        # ماسترنغ احترافي: تنظيف ترددات + تسوية جهارة + قصّ الصمت + تلاشي
        fade_out = max(0.3, min(2.5, total * 0.01))
        chain = (
            # تنقية الصوت: قصّ الغثّ، ثم خفض الرنين الأنفي (الغنّة)
            # عند 300Hz و1100Hz مع رفع طفيف لمنطقة الوضوح 2.8k-4.5k.
            "highpass=f=90,lowpass=f=13000,"
            "equalizer=f=300:t=q:w=1.0:g=-3.5,"
            "equalizer=f=1100:t=q:w=1.2:g=-2.0,"
            "equalizer=f=2800:t=q:w=1.0:g=2.0,"
            "equalizer=f=4500:t=q:w=1.2:g=1.5,"
            "deesser=i=0.30:m=0.5,"
            "acompressor=threshold=-22dB:ratio=2.5:attack=8:release=160,"
            "loudnorm=I=-16:TP=-1.5:LRA=11,"
            f"afade=t=in:st=0:d=0.35,afade=t=out:st={max(0.0, total - fade_out):.2f}:d={fade_out:.2f},"
            "aresample=48000"
        )
        mastered = work / "narration.m4a"
        _run(["-i", str(joined), "-af", chain, "-c:a", "aac", "-b:a", "192k",
              "-ar", "48000", "-ac", "1", str(mastered)])

        # خلفية سينمائية هادئة (اختيارية) بجهارة منخفضة جداً
        vol = float(prof.get("music") or 0)
        if vol > 0:
            pad = work / "pad.m4a"
            _run([
                "-f", "lavfi", "-i",
                f"sine=frequency=146.83:sample_rate=48000:duration={total:.2f}",
                "-f", "lavfi", "-i",
                f"sine=frequency=220:sample_rate=48000:duration={total:.2f}",
                "-f", "lavfi", "-i",
                f"sine=frequency=293.66:sample_rate=48000:duration={total:.2f}",
                "-filter_complex",
                "[0:a]volume=0.5[a0];[1:a]volume=0.33[a1];[2:a]volume=0.22[a2];"
                "[a0][a1][a2]amix=inputs=3:normalize=0,"
                "tremolo=f=0.12:d=0.30,highpass=f=120,lowpass=f=1200,volume=0.35[pad]",
                "-map", "[pad]", "-c:a", "aac", "-b:a", "128k", str(pad),
            ])
            mixed = work / "mixed.m4a"
            _run([
                "-i", str(mastered), "-i", str(pad),
                "-filter_complex",
                f"[1:a]volume={vol:.3f}[m];[0:a][m]amix=inputs=2:duration=first:normalize=0[out]",
                "-map", "[out]", "-c:a", "aac", "-b:a", "192k", str(mixed),
            ])
            shutil.copyfile(mixed, out_m4a)
        else:
            shutil.copyfile(mastered, out_m4a)

        if srt_out is not None:
            _write_srt(words_all, Path(srt_out))

        if verbose:
            print(f"      ✓ تعليق صوتي: {audio_duration(out_m4a) / 60:.1f} دقيقة", flush=True)
        return out_m4a
    finally:
        shutil.rmtree(work, ignore_errors=True)


# ----------------------------------------------------------------------------
def narrate_article(article: dict, category: str, out_dir: Path,
                    *, srt: bool = False, voice: str | None = None,
                    rate: str | None = None, music: float | None = None,
                    workers: int = 4, verbose: bool = True) -> tuple[Path, Path | None]:
    """يبني تعليقاً لمقال ويعيد (الملف الصوتي، ملف الترجمة أو None)."""
    aid = article["id"]
    out_dir = Path(out_dir)
    audio = out_dir / f"{aid}-narration.m4a"
    sub = out_dir / f"{aid}-narration.srt" if srt else None
    text = narration_text(article)
    if len(text) < 40:
        raise RuntimeError(f"{aid}: نص القصة قصير جداً للقراءة.")
    return build_narration(text, audio, category=category, voice=voice, rate=rate,
                           music=music, srt_out=sub, workers=workers,
                           verbose=verbose), sub


# ----------------------------------------------------------------------------
def main() -> int:
    ap = argparse.ArgumentParser(description="Kingdom Of Secrets narration engine (edge-tts).")
    ap.add_argument("--only", default="", help="معرّفات مقالات مفصولة بفواصل")
    ap.add_argument("--all", action="store_true")
    ap.add_argument("--voice", default="", help="اسم صوت عربي، مثل ar-SA-HamedNeural")
    ap.add_argument("--rate", default="", help="مثل -10%%")
    ap.add_argument("--music", type=float, default=None, help="جهارة الخلفية 0 لإيقافها")
    ap.add_argument("--srt", action="store_true")
    ap.add_argument("--workers", type=int, default=4, help="عدد المقاطع المتوازية")
    ap.add_argument("--out-dir", default="")
    args = ap.parse_args()

    data = json.loads((BASE / "articles.json").read_text(encoding="utf-8"))
    only = {x.strip() for x in args.only.split(",") if x.strip()}
    out_dir = Path(args.out_dir) if args.out_dir else BASE / "audio"
    ok = fail = 0
    for cat, arts in data["articles"].items():
        if not cat.startswith(("story_", "kids_")):
            continue
        for a in arts:
            if args.all or not only or a["id"] in only:
                print(f"\n{a['id']} ({cat})", flush=True)
                try:
                    path, sub = narrate_article(a, cat, out_dir, srt=args.srt,
                                                voice=args.voice or None,
                                                rate=args.rate or None,
                                                music=args.music,
                                                workers=args.workers)
                    print("  ->", path, flush=True)
                    ok += 1
                except Exception as e:  # noqa: BLE001
                    print("  FAILED:", str(e)[:240], flush=True)
                    fail += 1
    print(f"\nDONE ok={ok} failed={fail}")
    return 0 if fail == 0 else 2


if __name__ == "__main__":
    raise SystemExit(main())
