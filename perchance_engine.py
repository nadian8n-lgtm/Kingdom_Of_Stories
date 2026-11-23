#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
محرّك Perchance المجاني — تشغيل متصفح حقيقي بلا حساب ولا مفتاح.

Perchance يولّد صوراً مجاناً وبلا تسجيل، لكن واجهته تعمل عبر iframe و postMessage،
لهذا نستخدم Playwright مع Chrome/Edge المثبّت على الجهاز لاستدعاء دالة التوليد
الرسمية داخل الصفحة مباشرة.

الحدّ الأقصى للدقة الأصلية: 768x512 / 512x768 / 768x768 / 512x512.
image_bot.py يتولّى القصّ والرفع إلى 4K/8K بعد ذلك.
"""
from __future__ import annotations

import base64
import re
import sys
import time
from io import BytesIO

URL = "https://perchance.org/ai-text-to-image-generator"

_JS = r"""
async ([prompt, seed, resolution, timeoutMs]) => {
  const key = Object.keys(window).find(k => /^___textToImagePlugin\d+$/.test(k));
  if (!key) return {error: 'plugin-not-found'};
  try {
    const work = (async () => {
      let out = window[key](prompt, {resolution, seed});
      if (out && typeof out.then === 'function') out = await out;
      return String(out);
    })();
    const timeout = new Promise(res => setTimeout(
      () => res('__PERCHANCE_TIMEOUT__'), timeoutMs || 120000));
    const s = await Promise.race([work, timeout]);
    if (s === '__PERCHANCE_TIMEOUT__') return {error: 'generation-timeout'};
    if (s.startsWith('data:image')) return {data: s};
    return {error: s.slice(0, 300)};
  } catch (e) {
    return {error: String(e)};
  }
}
"""

_DATA_RE = re.compile(r"^data:image/(\w+);base64,(.*)$", re.S)


class PerchanceError(RuntimeError):
    pass


class PerchanceEngine:
    """محرّك صور مجاني يعمل عبر متصفح محلي."""

    def __init__(self, headless: bool = True, timeout: int = 120):
        self.headless = headless
        self.timeout = timeout
        self._pw = None
        self._browser = None
        self._ctx = None
        self._page = None
        self._frame = None

    # ------------------------------------------------------------------
    def _launch(self) -> None:
        try:
            from playwright.sync_api import sync_playwright
        except ImportError as e:  # pragma: no cover
            raise PerchanceError(
                "Playwright غير مثبّت. شغّل: python -m pip install playwright"
            ) from e

        self._pw = sync_playwright().start()
        last = None
        for channel in ("chrome", "msedge"):
            try:
                self._browser = self._pw.chromium.launch(
                    channel=channel,
                    headless=self.headless,
                    args=[
                        "--disable-blink-features=AutomationControlled",
                        "--no-first-run",
                        "--no-default-browser-check",
                    ],
                )
                break
            except Exception as e:  # noqa: BLE001
                last = e
        if not self._browser:
            raise PerchanceError(f"تعذّر تشغيل Chrome/Edge: {last}")

        self._ctx = self._browser.new_context(
            viewport={"width": 1280, "height": 900},
            locale="en-US",
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
            ),
        )
        self._page = self._ctx.new_page()
        self._page.goto(URL, wait_until="domcontentloaded", timeout=90000)

        deadline = time.time() + 90
        while time.time() < deadline:
            for f in self._page.frames:
                if f is self._page.main_frame:
                    continue
                if "ai-text-to-image-generator" in (f.url or ""):
                    try:
                        f.wait_for_function(
                            r"() => Object.keys(window).some(k => /^___textToImagePlugin\d+$/.test(k))",
                            timeout=5000,
                        )
                        # أغلق نافذة الترحيب إن ظهرت كي لا تعطّل التوليد
                        try:
                            f.evaluate(
                                "() => { const b=[...document.querySelectorAll('button')]"
                                ".find(x=>(x.innerText||'').includes('got it')); if(b) b.click(); }"
                            )
                        except Exception:  # noqa: BLE001
                            pass
                        self._frame = f
                        return
                    except Exception:  # noqa: BLE001
                        pass
            self._page.wait_for_timeout(1000)
        raise PerchanceError("لم يجهز مولّد Perchance داخل الصفحة (انتهت المهلة).")

    def _ensure(self) -> None:
        if self._frame is not None:
            try:
                self._frame.evaluate("() => Object.keys(window).some(k => /^___textToImagePlugin\\d+$/.test(k))")
                return
            except Exception:  # noqa: BLE001
                self.close()
        self._launch()

    # ------------------------------------------------------------------
    def generate(self, prompt: str, seed: int | None = None, aspect: str = "16:9"):
        """يولّد صورة ويعيدها كـ PIL.Image. يرفع PerchanceError عند الفشل."""
        from PIL import Image

        self._ensure()
        w, h = _ratio(aspect)
        if w / h > 1.15:
            resolution = "768x512"   # أفقي
        elif w / h < 0.87:
            resolution = "512x768"   # عمودي
        else:
            resolution = "768x768"   # مربّع

        seed = int(seed if seed is not None else time.time() * 1000) % 2147483647
        try:
            res = self._frame.evaluate(_JS, [prompt, seed, resolution, self.timeout * 1000])
        except Exception as e:  # noqa: BLE001
            self.close()
            raise PerchanceError(f"Perchance evaluate: {e}") from e

        if not isinstance(res, dict) or "data" not in res:
            raise PerchanceError(f"Perchance: {res}")
        data = res["data"]
        if data.startswith("(text-to-image-plugin"):
            raise PerchanceError(f"Perchance: {data}")

        m = _DATA_RE.match(data)
        if not m:
            raise PerchanceError(f"Perchance: unexpected payload {data[:80]!r}")
        blob = base64.b64decode(m.group(2))
        im = Image.open(BytesIO(blob))
        im.load()
        return im.convert("RGB")

    # ------------------------------------------------------------------
    def close(self) -> None:
        for obj in (self._ctx, self._browser):
            try:
                if obj:
                    obj.close()
            except Exception:  # noqa: BLE001
                pass
        try:
            if self._pw:
                self._pw.stop()
        except Exception:  # noqa: BLE001
            pass
        self._pw = self._browser = self._ctx = self._page = self._frame = None

    def __enter__(self):
        self._ensure()
        return self

    def __exit__(self, *exc):
        self.close()


def _ratio(aspect: str) -> tuple[float, float]:
    try:
        a, b = aspect.split(":")
        return float(a), float(b)
    except Exception:  # noqa: BLE001
        return 16.0, 9.0


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    p = sys.argv[1] if len(sys.argv) > 1 else "a serene desert dawn, cinematic amber light, no text"
    with PerchanceEngine(headless=True) as eng:
        img = eng.generate(p, seed=1234, aspect="16:9")
    out = "perchance_test.jpg"
    img.save(out, quality=95)
    print("SAVED", out, img.size)
