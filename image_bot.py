#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
بوت صور «مملكة الأسرار» — توليد عالي الجودة بلا مفتاح API.

المحرّكات (بالترتيب، وكلها مجانية بلا مفتاح):
  1) FLUX.1-Krea-dev        (Hugging Face Space)
  2) FLUX.1-dev             (Hugging Face Space)
  3) Qwen-Image             (Hugging Face Space)
  4) SD3.5-large            (Hugging Face Space)
  5) FLUX.1-schnell         (Hugging Face Space)
  6) Perchance              (متصفح محلي عبر Playwright — بلا حساب)

المزايا:
  - كل النِسَب: 16:9, 9:16, 1:1, 4:3, 3:4, 3:2, 2:3, 4:5, 5:4, 21:9, 2.39:1
  - دقة تصل إلى 8K (رفع ذكي متعدّد الخطوات + UnsharpMask)
  - محاولات غير محدودة (--retries 0) مع تبديل المحرّكات تلقائياً
  - قصّ نظيف بلا تمطيط + مصغّرات WebP + تركيب في النسختين
  - استئناف ذكي عبر image_bot_state.json

الاستخدام:
  python image_bot.py                          # 34 صورة 16:9 بدقة 4K
  python image_bot.py --engine Perchance       # محرّك واحد محدّد
  python image_bot.py --aspect 1:1 --res 4k    # نسبة ودقة مخصّصتان
  python image_bot.py --aspect all             # كل النِسَب لكل قصة
  python image_bot.py --only <id> --limit 1    # تجربة سريعة
  python image_bot.py --force                  # أعد التوليد
  python image_bot.py --dry-run                # اطبع البرومبتات فقط
"""
from __future__ import annotations

import argparse
import io
import json
import math
import sys
import time
import urllib.request
from pathlib import Path

from PIL import Image, ImageFilter, ImageOps, ImageStat

sys.stdout.reconfigure(encoding="utf-8")

BASE = Path(__file__).resolve().parent
ROOT = BASE.parent
TARGET_ROOTS = [BASE, ROOT / "Nexus_Press-main"]
STATE_PATH = BASE / "image_bot_state.json"
CACHE = BASE / "_image_bot_cache"
EXTRA_DIR = "images/aspects"

SITE_W, SITE_H = 1200, 675
TW, TH = 480, 270
UA = {"User-Agent": "Mozilla/5.0 (KingdomOfStories image bot)"}

ASPECTS: dict[str, tuple[int, int]] = {
    "16:9": (16, 9),
    "9:16": (9, 16),
    "1:1": (1, 1),
    "4:3": (4, 3),
    "3:4": (3, 4),
    "3:2": (3, 2),
    "2:3": (2, 3),
    "4:5": (4, 5),
    "5:4": (5, 4),
    "21:9": (21, 9),
    "2.39:1": (239, 100),
}

RES_SIDES = {
    "native": 0,
    "hd": 1280,
    "fhd": 1920,
    "qhd": 2560,
    "4k": 3840,
    "8k": 7680,
}

# ----------------------------------------------------------------------------
# هوية الأسلوب
# ----------------------------------------------------------------------------
STYLE_RELIGIOUS = (
    "Reverent cinematic editorial illustration, museum-quality digital painting, "
    "exactly this palette: deep warm amber, burnt sienna, umber and dark walnut shadows, "
    "lifted by soft volumetric golden side light and a gentle dawn glow. Rich canvas texture, "
    "atmospheric dust motes, dramatic chiaroscuro, shallow depth of field, high detail. "
    "Full-bleed composition that fills the entire frame edge to edge, no black bars, "
    "no letterboxing, no borders, no frame. "
    "Scene: {scene}. One or more anonymous robed onlookers seen strictly from behind, "
    "no facial features, no profile, no identity; never depict the face or image of any prophet. "
    "The prophet is suggested only through reverent symbols and light, never a portrait. "
    "Serene, dignified, family-friendly, "
    "no violence, no gore, no text, no letters, no numbers, no watermark, no logo, no signature."
)
STYLE_ADULT = (
    "High-end cinematic editorial illustration, museum-quality digital painting, "
    "exactly this palette: deep warm amber, burnt sienna, umber and dark walnut shadows, "
    "lifted by soft volumetric golden side light and a gentle glow. Rich canvas texture, "
    "atmospheric dust motes, dramatic chiaroscuro, shallow depth of field, high detail. "
    "Full-bleed composition that fills the entire frame edge to edge, no black bars, "
    "no letterboxing, no borders, no frame. "
    "Scene: {scene}. Warm nostalgic dignified mood, family-friendly, "
    "no violence, no gore, no text, no letters, no numbers, no watermark, no logo, no signature."
)
STYLE_KIDS = (
    "Pixar-style 3D animated film still, adorable expressive characters with big friendly eyes, "
    "soft plush textures, warm cheerful colours, playful gentle mood, cinematic soft lighting, "
    "shallow depth of field, ultra detailed. "
    "Full-bleed composition that fills the entire frame edge to edge, no black bars, "
    "no letterboxing, no borders, no frame. "
    "Scene: {scene}. Family-friendly and joyful, no text, no letters, no numbers, no watermark, no logo."
)

# مشهد لكل قصة (وصف إنجليزي دقيق يعكس العنوان والمحتوى)
SCENES: dict[str, str] = {
    # ---- دينية: رمز بصري مميّز لكل نبي/قصة ----
    # محمد صلى الله عليه وسلم — غار حراء، الثوب، الحجر، والكعبة بعيدة
    "story_religious-202611180017-e1f7a9": "the rocky cave of Hira at dawn, a folded silk cloth resting on a rough mountain stone, the distant silhouette of the Kaaba in the amber haze, an overwhelming serene light",
    # آدم عليه السلام — جنة وطين وملائكة
    "story_religious-202611180018-f2a8b0": "a serene primordial garden with soft green foliage, a gentle stream and rich clay earth, warm light filtering through leaves, an atmosphere of names being taught",
    # إدريس عليه السلام — جبل وسماء وصحيفة
    "story_religious-202611180019-a3b9c1": "a high mountain peak above a sea of clouds with a luminous ascending beam and an open scroll of fine script seen from afar, vast clear dawn sky",
    # نوح عليه السلام — الفلك والطوفان والتنور
    "story_religious-202611180020-b4c0d2": "a great wooden ark floating on calm floodwaters at dawn, a stone oven nearby with faint steam, distant green hills and a clearing rain-washed sky",
    # هود عليه السلام — عاد والريح والسحابة
    "story_religious-202611180021-c5d1e3": "a vast dune desert under sweeping wind clouds, the weathered stone pillars of a lost city on the horizon, dust lifting in the last warm light, a quiet warning",
    # صالح عليه السلام — الناقة والبئر
    "story_religious-202611180022-d6e2f4": "a majestic pale she-camel standing beside a deep stone well with rope and bucket, tall date palms, a simple cup of water glinting in warm morning light",
    # إبراهيم وإسماعيل عليهما السلام — القواعد والبيت
    "story_religious-202611180014-b2c4d6": "the rising stone foundations of a rectangular ancient house in a wide desert plain, a single great stone being lifted, distant palm grove, golden dawn",
    # إبراهيم عليه السلام — ضيوف الخليل
    "story_religious-202611180023-e7f3a5": "a simple desert tent at dusk with three shadowed guest silhouettes at the entrance, a welcoming cup and a glowing lamp inside, desert stars above",
    # يوسف عليه السلام — القميص
    "story_religious-202611180024-f8a4b6": "a beautifully woven linen shirt held up near a deep stone well, a distant caravan crossing amber dunes, tall palms and a long shadow of separation",
    # يوسف عليه السلام — الحلم وخزائن الأرض
    "story_religious-202611180013-a1b3c5": "an ancient granary and palace of golden stone with sacks of grain and a balanced scale, a luminous dreamlike glow in the sky above the dunes",
    # موسى عليه السلام — العجل والرحمة
    "story_religious-202611180025-a9b5c7": "a mountain slope with stone tablets resting on a rock and a small golden calf shadow far below in a distant camp, warm light of mercy breaking through",
    # شعيب عليه السلام — سوق مدين والميزان
    "story_religious-202611180026-b0c6d8": "an ancient market at dawn with wooden stalls and hanging cloth, a balanced brass scale on a table, a gentle wind lifting dust, soft golden haze",
    # موسى عليه السلام — النار والشجرة
    "story_religious-202611180027-c1d7e9": "a solitary glowing burning bush on a rocky mountainside at night, bright flame with no smoke, deep blue starry sky and a hushed reverent space",
    # موسى عليه السلام — غيبة الجبل
    "story_religious-202611180028-d2e8f0": "a high rugged mountain wrapped in cloud with soft divine light at its summit, a small cave opening nearby, silver-blue shadows and expectant stillness",
    # داود عليه السلام — الميزان والحكم
    "story_religious-202611180029-e3f9a1": "a serene judgement hall with a balanced golden scale and an open book on a low wooden table, two shadowed disputants seated, soft window light",
    # سليمان عليه السلام — الريح والصرح وبلقيس
    "story_religious-202611180030-f4a0b2": "a grand courtyard where a strong Wind sweeps silk banners and palm fronds, a distant ornate glass throne under a clearing sky, warm golden light returning",
    # إلياس عليه السلام — الطريق والسراج
    "story_religious-202611180031-a5b1c3": "a quiet olive grove at dusk with a winding stone road and a small oil lamp glowing, distant hills and a peaceful lingering light",
    # اليسع عليه السلام — الرداء والعين
    "story_religious-202611180032-b6c2d4": "a folded simple cloak beside a clear bubbling spring in a rocky valley, a narrow stone path leading to distant palms, soft morning light through reeds",
    # يونس عليه السلام — الحوت والظلمات
    "story_religious-202611180033-c7d3e5": "dark layered storm waves at sea with a great whale silhouette just beneath the surface, a slender beam of light breaking through heavy clouds",
    # زكريا عليه السلام — البشرى في المحراب
    "story_religious-202611180034-d8e4f6": "a serene stone prayer niche glowing with a gentle annunciation light, an open manuscript on a low lectern, reverence and warmth",
    # يحيى عليه السلام — المحراب والتسبيح
    "story_religious-202611180035-e9f5a7": "a small carved wooden mihrab lit by a lamp with a gentle childlike glow of light, an open scroll nearby, midnight-blue and gold tones",
    # مريم عليها السلام — جذع النخلة والرطب
    "story_religious-202611180036-f0a6b8": "a tall date palm bending with ripe clusters of dates falling onto soft earth, a small spring at its base, warm golden harvest light",
    # الصحابة — صفوف المسجد
    "story_religious-202611180015-c3d5e7": "a humble mosque courtyard at dawn with rows of anonymous robed figures seen from behind in quiet prayer, soft golden light through arches, a sense of unity",
    # الخلفاء الراشدون — المصحف والراية
    "story_religious-202611180016-d4e6f8": "an open Quran on a low lectern and a simple banner in a calm mosque, soft golden light through arched windows, dignified and serene",
    # ---- كبار ----
    "story_realistic-202611180001-a1b2c3": "an old cassette recorder on a wooden table in a warm sunlit Arabic home, dust motes floating in golden light, a nostalgic quiet room",
    "story_mystery-202611180002-d4e5f6": "a small yellowed map and an old cinema key on a dusty shelf, a narrow beam of light in a forgotten neighbourhood hall",
    "story_scifi-202611180003-c4d5e6": "a slim weather sensor on a desert ridge with a glowing data ribbon in the sky above a green valley, hopeful dawn light",
    "story_fantasy-202611180004-9b7c2a": "a small wooden boat on a moonlit sea with a glowing lullaby-like ribbon of light over the water before dawn",
    "story_horror-202611180005-e1f2a3": "a closed apartment door with a faint song-like ripple on the wallpaper, soft unsettling shadow and warm lamplight, psychological tension only, no blood",
    "story_history-202611180006-b4c7d9": "an Andalusian copying workshop with reed pens, inkpot and fine handwritten pages, warm window light and carved arches",
    "story_comedy-202611180007-f3a8b2": "a cozy neighbourhood cafe without phones and a small woven basket holding sleeping devices, warm humorous afternoon light",
    # ---- أطفال ----
    "kids_3_6-202611180008-a7b8c9": "a cozy child's bedroom at bedtime with a cute long-eared rabbit lifting a paw, a rounded rabbit shadow on the wall, a warm blue lamp and a smiling mother rabbit",
    "kids_7_10-202611180009-b8c9d0": "a bright third-grade classroom with colourful pencil boxes, a white cup, a tiny curious hamster and two laughing children around a shelf",
    "kids_11_14-202611180010-c9d0e1": "a school lab corner where two teenagers build a cheerful robot from recycled carton, bottle cap, wire and comb on a square table",
}

# ----------------------------------------------------------------------------
# محرّكات Hugging Face المجانية (بلا مفتاح)
# ----------------------------------------------------------------------------
NEGATIVE = (
    "text, letters, words, watermark, logo, signature, caption, blurry, low quality, "
    "black bars, letterbox, borders, frame, empty margins, "
    "distorted anatomy, extra limbs, deformed hands, gore, blood, violence, nsfw"
)

HF_ENGINES = [
    {
        "name": "FLUX.1-Krea-dev",
        "url": "https://black-forest-labs-flux-1-krea-dev.hf.space",
        "api": "infer",
        "builder": lambda p, seed, w, h, aspect: [p, seed, True, w, h, 3.5, 28],
    },
    {
        "name": "FLUX.1-dev",
        "url": "https://black-forest-labs-flux-1-dev.hf.space",
        "api": "infer",
        "builder": lambda p, seed, w, h, aspect: [p, seed, True, w, h, 3.5, 28],
    },
    {
        "name": "Qwen-Image",
        "url": "https://qwen-qwen-image.hf.space",
        "api": "infer",
        "builder": lambda p, seed, w, h, aspect: [p, seed, True, _qwen_aspect(aspect), 4.0, 30, True],
    },
    {
        "name": "SD3.5-large",
        "url": "https://stabilityai-stable-diffusion-3-5-large.hf.space",
        "api": "infer",
        "builder": lambda p, seed, w, h, aspect: [p, NEGATIVE, seed, True, w, h, 4.5, 28],
    },
    {
        "name": "FLUX.1-schnell",
        "url": "https://black-forest-labs-flux-1-schnell.hf.space",
        "api": "infer",
        "builder": lambda p, seed, w, h, aspect: [p, seed, True, w, h, 4],
    },
]

_QWEN_OK = {"16:9", "9:16", "1:1", "4:3", "3:4", "3:2", "2:3"}


class EngineUnavailable(RuntimeError):
    """المحرّك غير متاح الآن (حصة/تسجيل دخول/خدمة متوقّفة) — لا نكرّر عليه."""


def _qwen_aspect(aspect: str) -> str:
    return aspect if aspect in _QWEN_OK else "16:9"


def _ratio(aspect: str) -> tuple[int, int]:
    return ASPECTS.get(aspect, (16, 9))


def native_size(aspect: str, max_side: int = 1344) -> tuple[int, int]:
    """أكبر مقاس أصلي معقول لمحرّكات الانتشار (مضاعفات 8)."""
    rw, rh = _ratio(aspect)
    if rw >= rh:
        w = max_side
        h = round(max_side * rh / rw)
    else:
        h = max_side
        w = round(max_side * rw / rh)
    w = max(512, int(round(w / 8) * 8))
    h = max(512, int(round(h / 8) * 8))
    return w, h


def target_size(aspect: str, res: str) -> tuple[int, int]:
    side = RES_SIDES.get(res.lower(), 3840)
    if side == 0:
        return native_size(aspect)
    rw, rh = _ratio(aspect)
    if rw >= rh:
        w = side
        h = round(side * rh / rw)
    else:
        h = side
        w = round(side * rw / rh)
    w = int(round(w / 2) * 2)
    h = int(round(h / 2) * 2)
    return w, h


def aspect_slug(aspect: str) -> str:
    return aspect.replace(":", "x").replace(".", "_")


# ----------------------------------------------------------------------------
# شبكة/SSE
# ----------------------------------------------------------------------------
def _post_json(url: str, obj: dict, timeout: int = 240) -> str:
    req = urllib.request.Request(
        url, data=json.dumps(obj).encode("utf-8"),
        headers={"Content-Type": "application/json", **UA}, method="POST",
    )
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read().decode("utf-8", "replace")


def _sse_call(base: str, api: str, data: list, timeout: int = 420) -> str:
    body = _post_json(f"{base}/gradio_api/call/{api}", {"data": data}, timeout=120)
    j = json.loads(body)
    eid = j.get("event_id")
    if not eid:
        raise RuntimeError(f"no event_id: {body[:180]}")
    req = urllib.request.Request(f"{base}/gradio_api/call/{api}/{eid}", headers=UA)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read().decode("utf-8", "replace")


def _last_sse_data(raw: str):
    last = None
    for line in raw.splitlines():
        line = line.strip()
        if line.startswith("data:"):
            v = line[5:].strip()
            if v and v != "null":
                last = v
    if not last:
        raise RuntimeError("empty SSE")
    return json.loads(last)


def _find_image_url(node):
    if isinstance(node, dict):
        for k in ("url", "path"):
            v = node.get(k)
            if isinstance(v, str) and (v.startswith("http") or v.startswith("/")):
                return v
        for v in node.values():
            u = _find_image_url(v)
            if u:
                return u
    elif isinstance(node, list):
        for v in node:
            u = _find_image_url(v)
            if u:
                return u
    elif isinstance(node, str) and node.startswith("http"):
        return node
    return None


def _looks_flat(im: Image.Image) -> bool:
    g = im.convert("L").resize((40, 40))
    return float(ImageStat.Stat(g).var[0] or 0.0) < 55.0


def _line_mean(gray: Image.Image, side: str, idx: int) -> tuple[float, float]:
    w, h = gray.size
    if side == "top":
        box = (0, idx, w, idx + 1)
    elif side == "bottom":
        box = (0, h - 1 - idx, w, h - idx)
    elif side == "left":
        box = (idx, 0, idx + 1, h)
    else:
        box = (w - 1 - idx, 0, w - idx, h)
    st = ImageStat.Stat(gray.crop(box))
    return float(st.mean[0]), float(st.var[0])


def _edge_band(gray: Image.Image, side: str, dark: int = 30, flat: int = 22,
               max_frac: float = 0.30) -> int:
    """يقيس سُمك شريط داكن/مصمت ملتصق بحافة الصورة (بالبكسل) بدقة كاملة."""
    w, h = gray.size
    limit = int((h if side in ("top", "bottom") else w) * max_frac)
    if limit < 4:
        return 0

    # مسح خشن سريع لتقدير موضع نهاية الشريط
    coarse = 0
    step = 4
    for i in range(0, limit, step):
        mean, var = _line_mean(gray, side, i + step // 2)
        if mean <= dark and var <= flat * 6:
            coarse = i + step
        else:
            break

    if coarse == 0:
        mean, var = _line_mean(gray, side, 0)
        if not (mean <= dark and var <= flat * 6):
            return 0

    # تنقية على الدقة الكاملة (بما فيها هامش أمان صغير)
    idx = max(0, coarse - step)
    end = min(limit, coarse + max(6, int(coarse * 0.15)))
    band = idx
    while idx < end:
        mean, var = _line_mean(gray, side, idx)
        if mean <= dark and var <= flat * 6:
            band = idx + 1
            idx += 1
        else:
            break
    return band


def _trim_bars(im: Image.Image) -> Image.Image:
    """
    يكتشف ويقصّ الأشرطة السوداء المدمجة (letterbox/pillarbox) حتى تعمّر الصورة الكادر.
    لا يمسّ الصورة إذا لم يجد أشرطة واضحة.
    """
    w, h = im.size
    gray = im.convert("L")
    top = _edge_band(gray, "top")
    bottom = _edge_band(gray, "bottom")
    left = _edge_band(gray, "left")
    right = _edge_band(gray, "right")

    if max(top, bottom, left, right) < max(3, int(min(w, h) * 0.012)):
        return im

    box = (left, top, w - right, h - bottom)
    nw, nh = box[2] - box[0], box[3] - box[1]
    if nw < w * 0.55 or nh < h * 0.55:
        return im
    if nw * nh < w * h * 0.60:
        return im
    return im.crop(box)


def _classify_error(msg: str) -> bool:
    low = msg.lower()
    for needle in ("zerogpu quota", "you have exceeded", "quota", "authenticate",
                   "sign in", "unauthorized", "forbidden", "404", "503"):
        if needle in low:
            return True
    return False


# ----------------------------------------------------------------------------
# توليد
# ----------------------------------------------------------------------------
def _hf_generate(eng: dict, prompt: str, seed: int, aspect: str) -> Image.Image:
    w, h = native_size(aspect)
    data = eng["builder"](prompt, seed, w, h, aspect)
    raw = _sse_call(eng["url"], eng["api"], data)
    if "event: error" in raw:
        raise RuntimeError("space returned event:error (quota/offline)")
    arr = _last_sse_data(raw)
    url = _find_image_url(arr)
    if not url:
        raise RuntimeError(f"no image url in {json.dumps(arr)[:160]}")
    if url.startswith("/"):
        url = eng["url"] + url
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=240) as r:
        blob = r.read()
    im = Image.open(io.BytesIO(blob))
    im.load()
    im = im.convert("RGB")
    if im.size[0] < 256 or im.size[1] < 256:
        raise RuntimeError(f"too small {im.size}")
    if _looks_flat(im):
        raise RuntimeError("image looks blank/flat")
    return im


_PERCHANCE = None


_PERCHANCE_HEADLESS = True


def _perchance_generate(prompt: str, seed: int, aspect: str) -> Image.Image:
    global _PERCHANCE
    from perchance_engine import PerchanceEngine  # local import

    if _PERCHANCE is None:
        _PERCHANCE = PerchanceEngine(headless=_PERCHANCE_HEADLESS)
    im = _PERCHANCE.generate(prompt, seed=seed, aspect=aspect)
    if im.size[0] < 256 or im.size[1] < 256:
        raise RuntimeError(f"too small {im.size}")
    if _looks_flat(im):
        raise RuntimeError("image looks blank/flat")
    return im


def close_perchance() -> None:
    global _PERCHANCE
    if _PERCHANCE is not None:
        try:
            _PERCHANCE.close()
        finally:
            _PERCHANCE = None


def generate_one(prompt: str, seed: int, aspect: str, engines: list[str],
                 retries: int = 0) -> tuple[Image.Image, str]:
    """
    يولّد صورة واحدة. retries=0 يعني محاولات غير محدودة.
    يعيد (الصورة، اسم المحرّك).
    """
    dead: set[str] = set()
    attempt = 0
    while True:
        attempt += 1
        for name in engines:
            if name in dead:
                continue
            try:
                if name == "Perchance":
                    im = _perchance_generate(prompt, seed + attempt, aspect)
                else:
                    eng = next(e for e in HF_ENGINES if e["name"] == name)
                    im = _hf_generate(eng, prompt, seed + attempt, aspect)
                print(f"      ✓ {name} {im.size[0]}x{im.size[1]}", flush=True)
                return im, name
            except Exception as e:  # noqa: BLE001
                msg = f"{name}: {type(e).__name__}: {str(e)[:170]}"
                print("      ✗", msg, flush=True)
                if _classify_error(msg) and name != "Perchance":
                    dead.add(name)
        if all(n in dead for n in engines):
            raise EngineUnavailable("كل المحرّكات غير متاحة الآن.")
        if retries and attempt >= retries:
            raise RuntimeError(f"فشلت {attempt} محاولة/محاولات.")
        wait = min(90, 3 * (2 ** min(attempt, 5)))
        print(f"      … إعادة المحاولة بعد {wait}s (المحاولة {attempt + 1})", flush=True)
        time.sleep(wait)


# ----------------------------------------------------------------------------
# المعالجة والتركيب
# ----------------------------------------------------------------------------
def _smart_upscale(im: Image.Image, size: tuple[int, int]) -> Image.Image:
    """قصّ إلى النسبة + رفع تدريجي بجودة عالية + ترشيح تفاصيل."""
    fitted = ImageOps.fit(im, size, method=Image.LANCZOS, centering=(0.5, 0.42))
    tw, th = size
    if fitted.size != size:  # pragma: no cover
        fitted = fitted.resize(size, Image.LANCZOS)
    # sharpen only when we actually enlarged
    if im.size[0] < tw * 0.9:
        fitted = fitted.filter(ImageFilter.UnsharpMask(radius=1.4, percent=95, threshold=3))
    return fitted


def build_prompt(article: dict, category: str) -> str:
    scene = SCENES.get(article["id"], article.get("image_alt", article.get("title", "")))
    if category.startswith("kids_"):
        style = STYLE_KIDS
    elif category == "story_religious":
        style = STYLE_RELIGIOUS
    else:
        style = STYLE_ADULT
    return style.format(scene=scene)


def save_image(im: Image.Image, article_id: str, aspect: str, res: str,
               install_site: bool, out_dir: Path | None = None) -> dict:
    out = {"aspect": aspect, "res": res, "written": []}

    if out_dir is not None:
        out_dir.mkdir(parents=True, exist_ok=True)
        p = out_dir / f"{article_id}-{aspect_slug(aspect)}-{res}.jpg"
        im.save(p, "JPEG", quality=95, subsampling=0)
        out["big"] = str(p)
        out["master"] = str(p)
        out["written"].append(str(p))
        return out

    CACHE.mkdir(exist_ok=True)
    slug = aspect_slug(aspect)
    master = CACHE / f"{article_id}@{slug}@{res}.jpg"
    im.save(master, "JPEG", quality=94, subsampling=0)
    out["master"] = str(master)

    if install_site and aspect == "16:9":
        site = im.resize((SITE_W, SITE_H), Image.LANCZOS)
        rel_big = Path("images") / f"{article_id}-scene-1.webp"
        rel_small = Path("images") / "t" / f"{article_id}-scene-1.webp"
        for root in TARGET_ROOTS:
            big = root / rel_big
            small = root / rel_small
            big.parent.mkdir(parents=True, exist_ok=True)
            small.parent.mkdir(parents=True, exist_ok=True)
            site.save(big, "WEBP", quality=90, method=6)
            site.resize((TW, TH), Image.LANCZOS).save(small, "WEBP", quality=84, method=6)
            out["written"] += [str(big), str(small)]
        out["big"] = str(rel_big)
    else:
        rel = Path(EXTRA_DIR) / f"{article_id}-{slug}.webp"
        p = BASE / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        im.save(p, "WEBP", quality=90, method=6)
        out["written"].append(str(p))
        out["big"] = str(rel)
    return out


def image_ok(article_id: str) -> bool:
    for root in TARGET_ROOTS:
        p = root / "images" / f"{article_id}-scene-1.webp"
        if not p.exists() or p.stat().st_size < 6000:
            return False
    return True


def load_state() -> dict:
    if STATE_PATH.exists():
        try:
            return json.loads(STATE_PATH.read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001
            return {}
    return {}


def save_state(state: dict) -> None:
    STATE_PATH.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")


# ----------------------------------------------------------------------------
# CLI
# ----------------------------------------------------------------------------
def main() -> int:
    ap = argparse.ArgumentParser(description="Kingdom Of Secrets image bot — free, keyless, 4K+.")
    ap.add_argument("--only", default="", help="article ids مفصولة بفواصل")
    ap.add_argument("--limit", type=int, default=0, help="توقّف بعد N صورة")
    ap.add_argument("--force", action="store_true", help="أعد التوليد حتى لو موجودة")
    ap.add_argument("--dry-run", action="store_true", help="اطبع البرومبتات فقط")
    ap.add_argument("--aspect", default="16:9", help="16:9 | 9:16 | 1:1 | 4:3 | 3:4 | 3:2 | 2:3 | 21:9 | all")
    ap.add_argument("--res", default="4k", help="native | hd | fhd | qhd | 4k | 8k")
    ap.add_argument("--retries", type=int, default=0, help="0 = محاولات غير محدودة")
    ap.add_argument("--engine", default="auto",
                    help="auto | Perchance | FLUX.1-Krea-dev | FLUX.1-dev | Qwen-Image | SD3.5-large | FLUX.1-schnell")
    ap.add_argument("--headful", action="store_true", help="أظهر نافذة المتصفح (Perchance)")
    ap.add_argument("--out-dir", default="", help="مجلد معاينة: احفظ هناك فقط بلا تركيب في الموقع")
    args = ap.parse_args()

    global _PERCHANCE_HEADLESS
    _PERCHANCE_HEADLESS = not args.headful
    out_dir = Path(args.out_dir) if args.out_dir else None

    aspects = list(ASPECTS) if args.aspect.lower() == "all" else [args.aspect]
    for a in aspects:
        if a not in ASPECTS:
            print(f"نسبة غير معروفة: {a}\nالمتاح: {', '.join(ASPECTS)}")
            return 2

    if args.engine.lower() == "auto":
        engines = [e["name"] for e in HF_ENGINES] + ["Perchance"]
    else:
        if args.engine != "Perchance" and args.engine not in {e["name"] for e in HF_ENGINES}:
            print("محرّك غير معروف. المتاح:", ", ".join([e["name"] for e in HF_ENGINES] + ["Perchance"]))
            return 2
        engines = [args.engine]

    data = json.loads((BASE / "articles.json").read_text(encoding="utf-8"))
    only = {x.strip() for x in args.only.split(",") if x.strip()}

    jobs: list[tuple[str, dict]] = []
    for cat, arts in data["articles"].items():
        if not cat.startswith(("story_", "kids_")):
            continue
        for a in arts:
            if only and a["id"] not in only:
                continue
            jobs.append((cat, a))

    state = load_state()
    done = failed = skipped = 0
    t0 = time.time()

    try:
        for i, (cat, a) in enumerate(jobs, 1):
            aid = a["id"]
            prompt = build_prompt(a, cat)
            for aspect in aspects:
                key = f"{aid}|{aspect}|{args.res}"
                tw, th = target_size(aspect, args.res)
                if args.dry_run:
                    print(f"\n[{i}/{len(jobs)}] {aid} ({cat}) {aspect} -> {tw}x{th}\n  {prompt}")
                    continue
                if (not args.force and not out_dir and aspect == "16:9" and image_ok(aid)
                        and state.get(key, {}).get("status") == "ok"):
                    print(f"[{i}/{len(jobs)}] skip: {aid} {aspect}", flush=True)
                    skipped += 1
                    continue

                print(f"\n[{i}/{len(jobs)}] {aid} ({cat}) {aspect} -> {tw}x{th}", flush=True)
                try:
                    seed = 1000 + i * 7919 + sum(ord(c) for c in aspect)
                    im, used = generate_one(prompt, seed, aspect, engines, retries=args.retries)
                    im = _trim_bars(im)
                    im = _smart_upscale(im, (tw, th))
                    info = save_image(im, aid, aspect, args.res,
                                      install_site=(aspect == "16:9" and out_dir is None),
                                      out_dir=out_dir)
                    if out_dir is None:
                        state[key] = {
                            "status": "ok", "engine": used, "aspect": aspect, "res": args.res,
                            "size": [tw, th], "image": info["big"], "ts": int(time.time()),
                        }
                        save_state(state)
                    done += 1
                    print(f"      saved -> {info['big']}", flush=True)
                except Exception as e:  # noqa: BLE001
                    print(f"      FAILED: {e}", flush=True)
                    state[key] = {"status": "error", "error": str(e)[:300], "ts": int(time.time())}
                    save_state(state)
                    failed += 1
                if args.limit and done >= args.limit:
                    print(f"\nreached --limit {args.limit}", flush=True)
                    raise SystemExit(0)
    except KeyboardInterrupt:
        print("\nتوقّف يدوي — الحالة محفوظة.", flush=True)
    finally:
        close_perchance()

    mins = (time.time() - t0) / 60
    print(f"\nDONE ok={done} failed={failed} skipped={skipped} in {mins:.1f} min")
    return 0 if failed == 0 else 2


if __name__ == "__main__":
    raise SystemExit(main())
