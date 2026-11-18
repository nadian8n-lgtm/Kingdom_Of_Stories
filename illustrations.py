"""Original blog illustrations for مملكة الأسرار.

Why this file exists
--------------------
AdSense rejects pages whose pictures are blurry, duplicated, watermarked, or taken from
other websites.  When no image provider answers, the old code wrote an SVG containing a
giant emoji.  On Windows a flag emoji is rendered as a blue two-letter box,
which is exactly the defect that was reported.

This module draws a completely original, text-free, high-resolution illustration for a
story.  Everything is vector-like geometry rendered with Pillow at 2x and downsampled, so
the result is sharp at every size.  There are no photos, no faces, no flags, no logos, no
watermarks and no copyright issues.  The drawing is seeded by the article id, and the
scene is chosen from the headline/summary, so two articles never get the same picture.

Usage
-----
    python illustrations.py                 # redraw every article image in articles.json
    python illustrations.py --only <id>     # one article
    from illustrations import save
    save(article_id, category, title, Path("images/x.webp"))
"""
from __future__ import annotations

import argparse
import json
import math
import os
import random
import re
import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter

W, H = 1000, 563          # 16:9, the size used by the site
S = 2                     # supersampling factor (draw at 2000x1126, then downscale)

# top, bottom, accent, accent2, ink
PALETTES = {
    "ar_world":  ((4, 28, 50), (6, 70, 99), (0, 180, 216), (144, 224, 239), (3, 20, 38)),
    "ar_economy":((5, 46, 43), (6, 78, 59), (251, 191, 36), (52, 211, 153), (3, 30, 27)),
    "ar_tech":   ((20, 11, 46), (42, 26, 94), (167, 139, 250), (34, 211, 238), (11, 6, 28)),
    "ar_sports": ((5, 46, 22), (20, 83, 45), (163, 230, 53), (248, 250, 252), (3, 28, 14)),
    "ar_arts":   ((42, 10, 46), (74, 29, 79), (244, 114, 182), (251, 191, 36), (28, 6, 32)),
    "ar_books":  ((43, 26, 14), (74, 44, 23), (245, 230, 200), (45, 212, 191), (29, 17, 9)),
}
DEFAULT_PALETTE = PALETTES["ar_world"]

# Words that pick a more precise scene inside a section.
K = {
    "weather": ("طقس", "عاصفة", "مطر", "أمطار", "ثلوج", "حرارة", "رياح", "موجة", "برد", "جفاف", "فيضان"),
    "market": ("أسهم", "بورصة", "سوق", "أسواق", "تضخم", "فائدة", "عملة", "دولار", "استثمار", "تمويل", "اقتصاد", "عقار", "بنك"),
    "cyber": ("سيبراني", "اختراق", "قرصنة", "بيانات", "خصوصية", "أمن رقمي", "فيروس", "احتيال"),
    "ai": ("ذكاء اصطناعي", "خوارزمية", "روبوت", "نموذج", "تعلم آلي", "ChatGPT", "إنفيديا"),
    "device": ("هاتف", "آبل", "آيفون", "شاشة", "كاميرا", "شريحة", "حاسوب", "تطبيق"),
    "cinema": ("فيلم", "سينما", "مسلسل", "مخرج", "ممثل", "وثائقي", "دراما", "أوسكار"),
    "music": ("موسيقى", "أغنية", "ألبوم", "مغني", "فرقة", "حفل", "مهرجان"),
    "book": ("كتاب", "رواية", "أدب", "شاعر", "مكتبة", "قراءة", "مخطوط"),
    "football": ("كرة", "مباراة", "دوري", "كأس", "منتخب", "لاعب", "هدف", "ملعب", "فريق", "مدرب", "بطولة", "نهائي"),
    "tennis": ("تنس", "نوسكوفا", "ويمبلدون", "رافائيل", "دجوكوفيتش"),
    "boxing": ("ملاكمة", "وزن", "حلبة", "بوستي", "هاتشينسون"),
    "war": ("حرب", "قصف", "هجوم", "جيش", "عسكري", "أوكرانيا", "غزة", "صواريخ", "قتال"),
    "election": ("انتخابات", "تصويت", "رئيس", "برلمان", "حكومة", "حزب", "مرشح"),
    "diplomacy": ("قمة", "دبلوماسي", "سفير", "اتفاق", "معاهدة", "أمم متحدة", "تحالف", "مفاوضات"),
    "transport": ("قطار", "طيران", "مطار", "طريق", "بنية", "نقل", "مركبات", "دراجات"),
    "energy": ("طاقة", "نفط", "غاز", "كهرباء", "شمسية", "رياح", "هيدروجين", "مناخ", "COP"),
    "health": ("صحة", "مستشفى", "مرض", "دواء", "وباء", "طبي", "مرضى"),
}


def _has(text: str, key: str) -> bool:
    return any(w in text for w in K[key])


def _grad(w: int, h: int, top, bottom) -> Image.Image:
    img = Image.new("RGB", (w, h))
    d = ImageDraw.Draw(img)
    for y in range(h):
        t = y / max(1, h - 1)
        d.line([(0, y), (w, y)], fill=tuple(int(top[i] * (1 - t) + bottom[i] * t) for i in range(3)))
    return img


def _glow(size, center, radius, color, alpha=90, blur=None):
    layer = Image.new("RGBA", size, (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)
    cx, cy = center
    d.ellipse([cx - radius, cy - radius, cx + radius, cy + radius], fill=tuple(color) + (alpha,))
    return layer.filter(ImageFilter.GaussianBlur(blur if blur is not None else max(4, radius / 3)))


def _add(base: Image.Image, layer: Image.Image) -> Image.Image:
    return Image.alpha_composite(base.convert("RGBA"), layer)


def _rgba(size):
    return Image.new("RGBA", size, (0, 0, 0, 0))


def _poly(d, pts, fill=None, outline=None, width=1):
    d.polygon([(int(x), int(y)) for x, y in pts], fill=fill)
    if outline:
        d.line([(int(x), int(y)) for x, y in pts] + [(int(pts[0][0]), int(pts[0][1]))],
               fill=outline, width=width, joint="curve")


def _window_grid(d, x, y, w, h, cols, rows, color, lit=0.45, rng=None):
    rng = rng or random
    gw, gh = w / cols, h / rows
    for i in range(cols):
        for j in range(rows):
            if rng.random() < lit:
                pad = max(1, int(min(gw, gh) * 0.18))
                d.rectangle([x + i * gw + pad, y + j * gh + pad,
                             x + (i + 1) * gw - pad, y + (j + 1) * gh - pad], fill=color)


def _stars(d, rng, n, w, h, color=(255, 255, 255)):
    for _ in range(n):
        x, y = rng.uniform(0, w), rng.uniform(0, h * 0.6)
        r = rng.choice([1, 1, 1, 2, 2, 3])
        a = rng.randint(30, 130)
        d.ellipse([x - r, y - r, x + r, y + r], fill=color + (a,))


def _mountains(d, w, h, horizon, color, color2, rng, peaks=5):
    pts = [(0, h)]
    step = w / peaks
    for i in range(peaks + 1):
        x = i * step
        y = horizon - rng.uniform(0.02, 0.12) * h
        pts.append((x - step * 0.5, horizon))
        pts.append((x, y))
    pts += [(w, horizon), (w, h)]
    _poly(d, pts, fill=color)
    # a lighter ridge behind
    pts2 = [(0, h)]
    for i in range(peaks + 1):
        x = i * step + step * 0.35
        y = horizon - rng.uniform(0.01, 0.07) * h
        pts2.append((x - step * 0.4, horizon))
        pts2.append((x, y))
    pts2 += [(w, horizon), (w, h)]
    _poly(d, pts2, fill=color2)


def _skyline(d, w, h, base_y, color, window, rng, count=14, max_h=0.34):
    x = -20
    while x < w + 20:
        bw = rng.uniform(0.045, 0.095) * w
        bh = rng.uniform(0.10, max_h) * h
        _poly(d, [(x, base_y), (x, base_y - bh), (x + bw, base_y - bh), (x + bw, base_y)], fill=color)
        if rng.random() < 0.8:
            _window_grid(d, x + bw * 0.12, base_y - bh + bh * 0.12, bw * 0.76, bh * 0.72,
                         max(2, int(bw / 26)), max(2, int(bh / 28)), window, rng=rng)
        x += bw + rng.uniform(2, 10)


def _sun(d, w, h, rng, color, accent):
    cx, cy = rng.uniform(0.62, 0.86) * w, rng.uniform(0.14, 0.30) * h
    r = rng.uniform(0.05, 0.09) * w
    d.ellipse([cx - r, cy - r, cx + r, cy + r], fill=color + (230,))
    d.ellipse([cx - r * 0.62, cy - r * 0.62, cx + r * 0.62, cy + r * 0.62], fill=accent + (255,))


def _rain(d, w, h, rng, color, n=90):
    for _ in range(n):
        x, y = rng.uniform(0, w), rng.uniform(0, h)
        ln = rng.uniform(10, 34)
        d.line([(x, y), (x - ln * 0.22, y + ln)], fill=tuple(color) + (rng.randint(35, 90),), width=rng.choice([1, 1, 2]))


def _clouds(d, w, h, rng, color):
    for _ in range(rng.randint(4, 7)):
        cx, cy = rng.uniform(0, w), rng.uniform(0.08, 0.36) * h
        for i in range(rng.randint(3, 6)):
            r = rng.uniform(0.035, 0.085) * w
            d.ellipse([cx + i * r * 0.7 - r, cy - r * 0.7, cx + i * r * 0.7 + r, cy + r * 0.7],
                      fill=color + (rng.randint(40, 85),))


# --------------------------------------------------------------------------- scenes
def _scene_sports(img, d, rng, title, pal):
    w, h = img.size
    accent, accent2 = pal[2], pal[3]
    tennis = _has(title, "tennis")
    boxing = _has(title, "boxing")
    if boxing:
        # arena: crowd, spotlights, ring canvas, ropes and two gloves
        for _ in range(260):
            cx, cy = rng.uniform(0, w), rng.uniform(0, h * 0.50)
            r = rng.choice([1, 1, 2, 2, 3])
            d.ellipse([cx - r, cy - r, cx + r, cy + r], fill=accent2 + (rng.randint(25, 80),))
        for sx in (0.22, 0.50, 0.78):
            _poly(d, [(w * sx, 0), (w * (sx + 0.05), 0), (w * (sx + 0.16), h * 0.70), (w * (sx - 0.10), h * 0.70)],
                  fill=(255, 246, 220, 16))
        d.rectangle([0, h * 0.58, w, h], fill=(18, 12, 10, 255))
        _poly(d, [(w * 0.08, h * 0.58), (w * 0.92, h * 0.58), (w * 1.02, h), (-w * 0.02, h)], fill=(46, 32, 26, 255))
        for i in range(7):
            y = h * (0.60 + i * 0.055)
            d.line([(w * 0.02, y), (w * 0.98, y)], fill=(90, 66, 52, 70), width=1)
        for i, off in enumerate((0.10, 0.20, 0.30)):
            y = h * (0.58 + off * 0.55)
            d.line([(w * 0.06, y), (w * 0.94, y)], fill=accent + (210,), width=7 - i)
            d.line([(w * 0.06, y - 2), (w * 0.94, y - 2)], fill=(255, 255, 255, 90), width=1)
        for px in (0.08, 0.92):
            d.rectangle([w * px - 8, h * 0.56, w * px + 8, h * 0.86], fill=(70, 48, 36, 255))
        # two boxing gloves facing each other (objects, no people)
        for gx, flip in ((0.40, 1), (0.62, -1)):
            gw, gh = w * 0.11, h * 0.13
            x, y = w * gx, h * 0.70
            d.ellipse([x - gw / 2, y - gh / 2, x + gw / 2, y + gh / 2], fill=accent + (240,))
            d.ellipse([x - gw * 0.22, y - gh * 0.55, x + gw * 0.28, y - gh * 0.05], fill=accent + (240,))
            wx1, wx2 = x + flip * gw * 0.30, x + flip * gw * 0.62
            d.rectangle([min(wx1, wx2), y - gh * 0.18, max(wx1, wx2), y + gh * 0.18], fill=accent + (240,))
            d.arc([x - gw / 2, y - gh / 2, x + gw / 2, y + gh / 2], start=0 if flip > 0 else 180,
                  end=180 if flip > 0 else 360, fill=(255, 255, 255, 120), width=3)
        d.ellipse([w * 0.44, h * 0.86, w * 0.56, h * 0.92], fill=(0, 0, 0, 70))
        return
    if tennis:
        d.polygon([(w * 0.12, h * 0.42), (w * 0.88, h * 0.42), (w, h), (0, h)], fill=(13, 72, 94, 255))
        d.polygon([(w * 0.16, h * 0.44), (w * 0.84, h * 0.44), (w * 0.96, h * 0.98), (w * 0.04, h * 0.98)],
                  outline=(230, 245, 250, 230), width=4)
        d.line([(w * 0.5, h * 0.44), (w * 0.5, h * 0.98)], fill=(230, 245, 250, 230), width=4)
        d.line([(w * 0.15, h * 0.68), (w * 0.85, h * 0.68)], fill=(230, 245, 250, 230), width=3)
        d.ellipse([w * 0.47, h * 0.20, w * 0.53, h * 0.275], fill=accent2 + (255,))
        return
    # stadium
    horizon = h * 0.50
    d.ellipse([-w * 0.10, horizon - h * 0.06, w * 1.10, h * 1.15], fill=(10, 24, 20, 255))
    d.ellipse([w * 0.06, horizon + h * 0.02, w * 0.94, h * 1.05], fill=(16, 58, 34, 255))
    # stands + crowd dots
    for side in (0, 1):
        x0 = -w * 0.02 if side == 0 else w * 0.80
        for r in range(7):
            for c in range(9):
                cx = x0 + c * w * 0.026
                cy = horizon + r * h * 0.022
                d.ellipse([cx, cy, cx + 3, cy + 3], fill=accent2 + (rng.randint(30, 80),))
    # pitch
    _poly(d, [(w * 0.18, horizon), (w * 0.82, horizon), (w * 1.02, h), (-w * 0.02, h)], fill=(22, 101, 52, 255))
    # mowing stripes
    for i in range(7):
        x0 = w * 0.18 + (w * 0.64) * i / 7
        _poly(d, [(x0, horizon), (x0 + w * 0.09, horizon), (x0 + (w * 0.09) * 1.55, h), (x0 - w * 0.03, h)],
              fill=(28, 118, 60, 90) if i % 2 else (12, 80, 42, 60))
    d.line([(w * 0.18, horizon), (w * 0.82, horizon)], fill=(240, 250, 245, 220), width=4)
    d.line([(w * 0.5, horizon), (w * 0.5, h)], fill=(240, 250, 245, 220), width=3)
    d.ellipse([w * 0.42, horizon + h * 0.10, w * 0.58, horizon + h * 0.36], outline=(240, 250, 245, 220), width=3)
    # goals
    d.rectangle([w * 0.34, horizon - h * 0.055, w * 0.42, horizon], outline=(240, 250, 245, 220), width=3)
    d.rectangle([w * 0.58, horizon - h * 0.055, w * 0.66, horizon], outline=(240, 250, 245, 220), width=3)
    # floodlights
    for fx in (0.08, 0.92):
        d.line([(w * fx, h * 0.06), (w * fx, horizon + h * 0.02)], fill=(210, 225, 220, 210), width=5)
        d.rectangle([w * fx - w * 0.035, h * 0.035, w * fx + w * 0.035, h * 0.075], fill=(240, 250, 245, 240))
        cone = [(w * fx - w * 0.03, h * 0.07), (w * fx + w * 0.03, h * 0.07),
                (w * (0.5 + (fx - 0.5) * 0.55), horizon + h * 0.10)]
        _poly(d, [cone[0], cone[1], cone[2], (cone[2][0] - w * 0.08, cone[2][1])], fill=accent2 + (18,))
    # ball
    bx, by, br = w * 0.52, h * 0.78, h * 0.055
    d.ellipse([bx - br, by - br, bx + br, by + br], fill=(248, 250, 252, 255))
    for a in range(0, 360, 72):
        rad = math.radians(a)
        px, py = bx + math.cos(rad) * br * 0.42, by + math.sin(rad) * br * 0.42
        d.ellipse([px - br * 0.16, py - br * 0.16, px + br * 0.16, py + br * 0.16], fill=(20, 30, 40, 255))


def _scene_world(img, d, rng, title, pal):
    w, h = img.size
    accent, accent2 = pal[2], pal[3]
    cx, cy = w * 0.5, h * 0.48
    r = h * 0.34
    # rings
    for i, rr in enumerate((r * 1.10, r * 0.72, r * 0.40)):
        d.ellipse([cx - rr, cy - rr * 0.34, cx + rr, cy + rr * 0.34], outline=tuple(accent2) + (80 - i * 18,), width=2)
    d.line([(cx - r * 1.15, cy), (cx + r * 1.15, cy)], fill=accent2 + (50,), width=2)
    # globe
    d.ellipse([cx - r, cy - r, cx + r, cy + r], fill=(6, 52, 78, 255), outline=accent + (230,), width=3)
    # continents: seeded blobs, clipped visually inside the circle
    for _ in range(7):
        bx, by = cx + rng.uniform(-0.58, 0.58) * r, cy + rng.uniform(-0.58, 0.58) * r
        pts = []
        n = rng.randint(7, 11)
        for i in range(n):
            a = 2 * math.pi * i / n
            rad = r * rng.uniform(0.08, 0.20)
            pts.append((bx + math.cos(a) * rad * rng.uniform(0.8, 1.4), by + math.sin(a) * rad * rng.uniform(0.7, 1.2)))
        _poly(d, pts, fill=(34, 150, 120, 190))
    # meridians
    for k in (0.35, 0.65):
        d.ellipse([cx - r * k, cy - r, cx + r * k, cy + r], outline=accent2 + (70,), width=2)
    for k in (0.35, 0.65):
        d.ellipse([cx - r, cy - r * k, cx + r, cy + r * k], outline=accent2 + (60,), width=2)
    # connection arcs and nodes
    for _ in range(6):
        x1, y1 = cx + rng.uniform(-0.9, 0.9) * r, cy + rng.uniform(-0.9, 0.9) * r
        x2, y2 = cx + rng.uniform(-0.9, 0.9) * r, cy + rng.uniform(-0.9, 0.9) * r
        mx, my = (x1 + x2) / 2 + rng.uniform(-0.2, 0.2) * r, (y1 + y2) / 2 - rng.uniform(0.1, 0.4) * r
        pts = []
        for t in [i / 18 for i in range(19)]:
            px = (1 - t) ** 2 * x1 + 2 * (1 - t) * t * mx + t ** 2 * x2
            py = (1 - t) ** 2 * y1 + 2 * (1 - t) * t * my + t ** 2 * y2
            pts.append((px, py))
        d.line(pts, fill=accent + (110,), width=2)
        for x, y in ((x1, y1), (x2, y2)):
            d.ellipse([x - 4, y - 4, x + 4, y + 4], fill=accent2 + (230,))
    if _has(title, "war"):
        d.arc([cx - r, cy - r, cx + r, cy + r], start=20, end=150, fill=(255, 120, 90, 170), width=5)


def _scene_economy(img, d, rng, title, pal):
    w, h = img.size
    accent, accent2 = pal[2], pal[3]
    # grid
    for i in range(1, 6):
        y = h * (0.18 + i * 0.12)
        d.line([(w * 0.06, y), (w * 0.94, y)], fill=(255, 255, 255, 20), width=1)
    for i in range(1, 7):
        x = w * (0.06 + i * 0.13)
        d.line([(x, h * 0.16), (x, h * 0.84)], fill=(255, 255, 255, 14), width=1)
    # bars
    n = 8
    bw = w * 0.075
    for i in range(n):
        bh = h * rng.uniform(0.10, 0.52) * (0.55 + i / n)
        x = w * 0.10 + i * w * 0.105
        y = h * 0.84 - bh
        d.rectangle([x, y, x + bw, h * 0.84], fill=accent + (rng.randint(120, 210),))
        d.rectangle([x, y, x + bw, y + bh * 0.10], fill=accent2 + (230,))
    # trend line
    pts = [(w * 0.08, h * 0.78)]
    for i in range(1, 9):
        pts.append((w * (0.08 + i * 0.105), h * (0.78 - i * 0.045 - rng.uniform(-0.03, 0.03))))
    d.line(pts, fill=(255, 255, 255, 230), width=4, joint="curve")
    for x, y in pts:
        d.ellipse([x - 5, y - 5, x + 5, y + 5], fill=accent2 + (255,))
    # coins
    for i in range(4):
        cx, cy = w * (0.78 + i * 0.035), h * (0.74 - i * 0.055)
        d.ellipse([cx - 26, cy - 10, cx + 26, cy + 10], fill=accent + (230,), outline=(255, 255, 255, 120), width=2)
    # skyline silhouette
    _skyline(d, w, h, h * 0.87, (4, 24, 22, 255), accent + (60,), rng, count=12, max_h=0.09)
    if _has(title, "energy"):
        # wind turbines / sun
        for tx in (0.18, 0.28, 0.38):
            d.line([(w * tx, h * 0.60), (w * tx, h * 0.34)], fill=(220, 235, 230, 200), width=4)
            for a in (0, 120, 240):
                rad = math.radians(a)
                d.line([(w * tx, h * 0.34), (w * tx + math.cos(rad) * w * 0.045, h * 0.34 + math.sin(rad) * w * 0.045)],
                       fill=(220, 235, 230, 200), width=3)


def _scene_tech(img, d, rng, title, pal):
    w, h = img.size
    accent, accent2 = pal[2], pal[3]
    # dot matrix
    for i in range(16):
        for j in range(9):
            if rng.random() < 0.35:
                x, y = w * (0.06 + i * 0.058), h * (0.10 + j * 0.095)
                d.rectangle([x, y, x + 3, y + 3], fill=accent2 + (rng.randint(30, 100),))
    if _has(title, "cyber"):
        # shield + lock
        cx, cy = w * 0.5, h * 0.50
        pts = [(cx, cy - h * 0.28), (cx + w * 0.14, cy - h * 0.18), (cx + w * 0.12, cy + h * 0.10),
               (cx, cy + h * 0.26), (cx - w * 0.12, cy + h * 0.10), (cx - w * 0.14, cy - h * 0.18)]
        _poly(d, pts, fill=(20, 40, 70, 230), outline=accent + (240,), width=5)
        d.rectangle([cx - w * 0.035, cy - h * 0.02, cx + w * 0.035, cy + h * 0.11], fill=accent2 + (240,))
        d.arc([cx - w * 0.035, cy - h * 0.11, cx + w * 0.035, cy + h * 0.02], start=180, end=360,
              fill=accent2 + (240,), width=6)
        return
    if _has(title, "device"):
        # phone
        pw, ph = w * 0.20, h * 0.52
        x, y = w * 0.40, h * 0.22
        d.rounded_rectangle([x, y, x + pw, y + ph], radius=22, fill=(8, 10, 24, 255), outline=accent + (240,), width=4)
        d.rounded_rectangle([x + 8, y + 14, x + pw - 8, y + ph - 14], radius=14, fill=(18, 24, 48, 255))
        for i in range(3):
            d.ellipse([x + 22 + i * 26, y + ph - 24, x + 34 + i * 26, y + ph - 12], fill=accent2 + (200,))
        for i in range(3):
            d.rounded_rectangle([x + 22, y + 40 + i * 38, x + pw - 22, y + 66 + i * 38], radius=8, fill=accent + (70,))
        return
    # chip + circuits
    cx, cy = w * 0.5, h * 0.48
    cw, ch = w * 0.22, h * 0.30
    d.rounded_rectangle([cx - cw / 2, cy - ch / 2, cx + cw / 2, cy + ch / 2], radius=18,
                        fill=(18, 20, 48, 255), outline=accent + (240,), width=5)
    d.rounded_rectangle([cx - cw * 0.30, cy - ch * 0.30, cx + cw * 0.30, cy + ch * 0.30], radius=8,
                        fill=(30, 34, 72, 255), outline=accent2 + (200,), width=3)
    # pins
    for i in range(6):
        off = (i - 2.5) * (ch * 0.13)
        d.line([(cx - cw / 2, cy + off), (cx - cw / 2 - w * 0.045, cy + off)], fill=accent2 + (200,), width=3)
        d.line([(cx + cw / 2, cy + off), (cx + cw / 2 + w * 0.045, cy + off)], fill=accent2 + (200,), width=3)
    for i in range(4):
        off = (i - 1.5) * (cw * 0.18)
        d.line([(cx + off, cy - ch / 2), (cx + off, cy - ch / 2 - h * 0.06)], fill=accent2 + (200,), width=3)
        d.line([(cx + off, cy + ch / 2), (cx + off, cy + ch / 2 + h * 0.06)], fill=accent2 + (200,), width=3)
    # traces
    for i in range(10):
        side = rng.choice(["l", "r", "t", "b"])
        if side in ("l", "r"):
            y = rng.uniform(0.17, 0.83) * h
            x0 = 0 if side == "l" else w
            x1 = cx - cw / 2 if side == "l" else cx + cw / 2
            xm = rng.uniform(x1, x0)
            d.line([(x0, y), (xm, y), (xm, cy + rng.uniform(-ch / 2, ch / 2))], fill=accent2 + (70,), width=2)
        else:
            x = rng.uniform(0.12, 0.88) * w
            y0 = 0 if side == "t" else h
            y1 = cy - ch / 2 if side == "t" else cy + ch / 2
            ym = rng.uniform(y1, y0)
            d.line([(x, y0), (x, ym), (cx + rng.uniform(-cw / 2, cw / 2), ym)], fill=accent2 + (70,), width=2)
    # neural nodes
    for _ in range(18):
        x, y = rng.uniform(0.06, 0.94) * w, rng.uniform(0.10, 0.90) * h
        d.ellipse([x - 4, y - 4, x + 4, y + 4], fill=accent + (180,))


def _scene_arts(img, d, rng, title, pal):
    w, h = img.size
    accent, accent2 = pal[2], pal[3]
    # curtains
    for side in (0, 1):
        x0 = 0 if side == 0 else w
        x1 = w * 0.22 if side == 0 else w * 0.78
        pts = [(x0, 0), (x1, 0)]
        for i in range(6):
            px = x1 + (x0 - x1) * i / 5
            pts.append((px + (w * 0.02 if side == 0 else -w * 0.02) * (i % 2), h))
        pts.append((x0, h))
        _poly(d, pts, fill=(52, 14, 58, 220))
    # spotlights
    for sx in (0.30, 0.70):
        _poly(d, [(w * sx, 0), (w * (sx + 0.06), 0), (w * (sx + 0.22), h), (w * (sx - 0.10), h)],
              fill=accent2 + (18,))
    if _has(title, "music"):
        bars = 28
        for i in range(bars):
            bh = (0.10 + abs(math.sin(i * 0.7 + rng.random())) * 0.45) * h
            x = w * (0.14 + i * 0.026)
            d.rounded_rectangle([x, h * 0.55 - bh / 2, x + w * 0.012, h * 0.55 + bh / 2],
                                radius=4, fill=accent + (rng.randint(120, 230),))
        # notes
        for nx, ny in ((0.30, 0.30), (0.68, 0.34)):
            d.ellipse([w * nx - 10, h * ny - 7, w * nx + 10, h * ny + 7], fill=accent2 + (240,))
            d.line([(w * nx + 9, h * ny), (w * nx + 9, h * ny - h * 0.16)], fill=accent2 + (240,), width=4)
        return
    if _has(title, "book"):
        # open book
        cx, cy = w * 0.5, h * 0.60
        bw, bh = w * 0.38, h * 0.26
        _poly(d, [(cx, cy - bh * 0.35), (cx - bw / 2, cy - bh * 0.55), (cx - bw / 2, cy + bh * 0.35), (cx, cy + bh * 0.55)],
              fill=(245, 232, 205, 245))
        _poly(d, [(cx, cy - bh * 0.35), (cx + bw / 2, cy - bh * 0.55), (cx + bw / 2, cy + bh * 0.35), (cx, cy + bh * 0.55)],
              fill=(255, 244, 224, 245))
        d.line([(cx, cy - bh * 0.35), (cx, cy + bh * 0.55)], fill=(120, 90, 60, 220), width=4)
        for i in range(5):
            y = cy - bh * 0.24 + i * bh * 0.12
            d.line([(cx - bw * 0.40, y), (cx - bw * 0.08, y - bh * 0.03)], fill=(150, 120, 90, 160), width=2)
            d.line([(cx + bw * 0.08, y - bh * 0.03), (cx + bw * 0.40, y)], fill=(150, 120, 90, 160), width=2)
        return
    # cinema / default: film reel + strip
    cx, cy, r = w * 0.48, h * 0.48, h * 0.20
    d.ellipse([cx - r, cy - r, cx + r, cy + r], fill=(28, 8, 32, 255), outline=accent + (240,), width=5)
    for i in range(6):
        a = 2 * math.pi * i / 6
        hx, hy = cx + math.cos(a) * r * 0.52, cy + math.sin(a) * r * 0.52
        d.ellipse([hx - r * 0.13, hy - r * 0.13, hx + r * 0.13, hy + r * 0.13], fill=accent2 + (240,))
    d.ellipse([cx - r * 0.12, cy - r * 0.12, cx + r * 0.12, cy + r * 0.12], fill=accent + (240,))
    # film strip
    sx, sy = w * 0.70, h * 0.20
    for i in range(4):
        y = sy + i * h * 0.11
        d.rounded_rectangle([sx, y, sx + w * 0.20, y + h * 0.08], radius=4, fill=(18, 8, 22, 235),
                            outline=accent + (120,), width=2)
        for j in range(4):
            d.rectangle([sx + 4 + j * w * 0.05, y + 5, sx + 10 + j * w * 0.05, y + 10], fill=(240, 230, 220, 180))


def _scene_books(img, d, rng, title, pal):
    w, h = img.size
    accent, accent2 = pal[2], pal[3]
    # shelf
    d.rectangle([0, h * 0.78, w, h * 0.83], fill=(36, 20, 10, 255))
    # stacked books
    x = w * 0.16
    y = h * 0.74
    colors = [accent2, accent, (200, 120, 80), (120, 180, 160), (230, 200, 150)]
    for i in range(6):
        bw, bh = w * rng.uniform(0.10, 0.20), h * rng.uniform(0.055, 0.09)
        d.rounded_rectangle([x, y - bh, x + bw, y], radius=4, fill=colors[i % len(colors)] + (245,))
        d.line([(x + bw * 0.12, y - bh * 0.82), (x + bw * 0.88, y - bh * 0.82)], fill=(40, 25, 15, 120), width=3)
        x += bw * 0.55
        y -= bh * 0.92
    # open book right
    cx, cy = w * 0.66, h * 0.62
    bw, bh = w * 0.28, h * 0.20
    _poly(d, [(cx, cy - bh * 0.30), (cx - bw / 2, cy - bh * 0.48), (cx - bw / 2, cy + bh * 0.30), (cx, cy + bh * 0.48)],
          fill=(255, 246, 226, 250))
    _poly(d, [(cx, cy - bh * 0.30), (cx + bw / 2, cy - bh * 0.48), (cx + bw / 2, cy + bh * 0.30), (cx, cy + bh * 0.48)],
          fill=(245, 232, 205, 250))
    d.line([(cx, cy - bh * 0.30), (cx, cy + bh * 0.48)], fill=(120, 90, 60, 220), width=4)
    # lamp glow
    lx, ly = w * 0.86, h * 0.24
    d.line([(lx, h * 0.78), (lx, ly + h * 0.06)], fill=(200, 180, 140, 220), width=6)
    _poly(d, [(lx - w * 0.06, ly + h * 0.06), (lx + w * 0.06, ly + h * 0.06), (lx + w * 0.035, ly - h * 0.02),
              (lx - w * 0.035, ly - h * 0.02)], fill=accent + (240,))
    # floating pages
    for i in range(8):
        px, py = rng.uniform(0.08, 0.92) * w, rng.uniform(0.12, 0.55) * h
        pw, ph = rng.uniform(0.02, 0.05) * w, rng.uniform(0.02, 0.04) * h
        d.rectangle([px, py, px + pw, py + ph], fill=(255, 246, 226, rng.randint(80, 160)))


SCENES = {
    "ar_world": _scene_world,
    "ar_economy": _scene_economy,
    "ar_tech": _scene_tech,
    "ar_sports": _scene_sports,
    "ar_arts": _scene_arts,
    "ar_books": _scene_books,
}


def _speckle(d, rng, w, h, n, color=(255, 255, 255)):
    """Fine print-like texture so large flat areas never look empty or low-detail."""
    for _ in range(n):
        x, y = rng.uniform(0, w), rng.uniform(0, h)
        r = rng.choice([0.7, 1, 1, 1.5, 2])
        a = rng.randint(10, 52)
        if rng.random() < 0.55:
            d.ellipse([x - r, y - r, x + r, y + r], fill=tuple(color) + (a,))
        else:
            ln = rng.uniform(3, 11)
            d.line([(x, y), (x + ln * 0.35, y - ln)], fill=tuple(color) + (a,), width=1)


def draw(art_id: str, cat: str, title: str = "") -> Image.Image:
    """Return a deterministic 1000x563 RGB illustration for this article.

    The scene is painted on an oversized canvas, then mirrored, cropped and zoomed
    differently for every article.  That makes two sports (or two tech) pictures
    structurally different instead of two copies of one template, which is what an
    AdSense reviewer looks for when deciding that a site reuses the same image.
    """
    pal = PALETTES.get(cat, DEFAULT_PALETTE)
    rng = random.Random(str(art_id) + "|" + str(cat))
    zoom = rng.uniform(1.30, 1.70)
    bw, bh = int(W * S * zoom), int(H * S * zoom)
    img = _grad(bw, bh, pal[0], pal[1])
    overlay = _rgba((bw, bh))

    # soft colour fields (keep each picture clearly different)
    overlay = _add(overlay, _glow((bw, bh), (rng.uniform(0.1, 0.9) * bw, rng.uniform(0.0, 0.5) * bh),
                                  rng.uniform(0.20, 0.42) * bw, pal[2], rng.randint(22, 46), blur=bw * 0.10))
    overlay = _add(overlay, _glow((bw, bh), (rng.uniform(0.0, 1.0) * bw, rng.uniform(0.5, 1.0) * bh),
                                  rng.uniform(0.18, 0.38) * bw, pal[3], rng.randint(16, 38), blur=bw * 0.09))

    # draw everything on the composited overlay (the previous code drew on a discarded layer)
    d = ImageDraw.Draw(overlay)

    # light beams / grid
    for i in range(rng.randint(2, 4)):
        x = rng.uniform(-0.3, 0.9) * bw
        _poly(d, [(x, 0), (x + bw * 0.10, 0), (x + bw * 0.32, bh), (x + bw * 0.18, bh)],
              fill=(255, 255, 255, rng.randint(6, 14)))

    if cat in ("ar_world", "ar_tech", "ar_arts"):
        _stars(d, rng, rng.randint(30, 70), bw, bh)

    _speckle(d, rng, bw, bh, rng.randint(900, 1600), (255, 255, 255))

    # draw the scene at 2x
    SCENES.get(cat, _scene_world)(img, d, rng, title or "", pal)
    img = _add(img, overlay)

    if rng.random() < 0.5:                      # mirror: changes the whole composition
        img = img.transpose(Image.Transpose.FLIP_LEFT_RIGHT)

    # random close crop from the oversized scene (keeps the centre subject, moves the edges)
    w, h = W * S, H * S
    ox = rng.randint(0, max(0, bw - w))
    oy = rng.randint(0, max(0, bh - h))
    img = img.crop((ox, oy, ox + w, oy + h))

    # subtle diagonal lines for an editorial-print feel
    lines = _rgba((w, h))
    ld = ImageDraw.Draw(lines)
    for i in range(-14, 42):
        x = i * w * 0.035
        ld.line([(x, 0), (x + w * 0.10, h)], fill=(255, 255, 255, 7), width=1)
    for y in range(0, h, 4):
        ld.line([(0, y), (w, y)], fill=(255, 255, 255, 4), width=1)
    _speckle(ld, rng, w, h, 700, (255, 255, 255))
    img = _add(img, lines)

    # vignette
    vig = _rgba((w, h))
    vd = ImageDraw.Draw(vig)
    vd.rectangle([0, 0, w, h], fill=(0, 0, 0, 120))
    vd.ellipse([w * 0.06, -h * 0.10, w * 0.94, h * 1.10], fill=(0, 0, 0, 0))
    img = _add(img, vig.filter(ImageFilter.GaussianBlur(w * 0.05)))

    # fine grain (Pillow-native, no numpy)
    noise = Image.effect_noise((w, h), 34).convert("L").point(lambda p: p // 5)
    grain = Image.merge("RGBA", (noise, noise, noise, Image.new("L", (w, h), 42)))
    img = _add(img, grain)

    return img.convert("RGB").resize((W, H), Image.LANCZOS)


def save(art_id: str, cat: str, title: str, out_path: Path) -> Path:
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    img = draw(art_id, cat, title)
    if out_path.suffix.lower() == ".webp":
        img.save(out_path, "WEBP", quality=92, method=6)
    else:
        img.save(out_path, "PNG", optimize=True)
    return out_path


def main(argv=None):
    ap = argparse.ArgumentParser(description="Regenerate original illustrations for مملكة الأسرار")
    ap.add_argument("--only", help="article id")
    ap.add_argument("--json", default="articles.json")
    args = ap.parse_args(argv)
    root = Path(__file__).resolve().parent
    data = json.loads((root / args.json).read_text(encoding="utf-8"))
    arts = data.get("articles", {})
    made = 0
    for cat, items in arts.items():
        for a in items:
            if args.only and a.get("id") != args.only:
                continue
            old = root / a.get("image", "")
            stem = old.stem if old.suffix.lower() in (".webp", ".svg") else a["id"]
            out = old if old.suffix.lower() == ".webp" else root / "images" / f"{stem}.webp"
            save(a["id"], cat, a.get("title", ""), out)
            a["image"] = out.relative_to(root).as_posix()
            a["image_credit"] = {"source": "مملكة الأسرار", "author": "نكسوس",
                                 "license": "original blog illustration", "kind": "illustration"}
            a["image_kind"] = "illustration"
            made += 1
            print("illustration:", a["image"])
    if not args.only:
        (root / args.json).write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"done: {made} illustration(s)")


if __name__ == "__main__":
    main()
