"""Video factory for Kingdom Of Secrets fiction stories (SPEC.md §7, §13, §14).

Standalone and defensive: it never imports fetch_news.py (no circular import).
Only stdlib is imported at module load; edge-tts, imageio-ffmpeg, internetarchive
and Pillow are imported lazily and are allowed to be missing.

Public API (exactly as per SPEC §14):
    available() -> bool
    is_configured() -> bool
    build_for_story(article: dict, cat: str, img_bytes: bytes|None) -> dict|None

Every failure is caught inside this module and reported with a
``video_factory: ...`` line, so a broken video never fails the publishing run.
"""

import asyncio
import base64
import json
import math
import os
import re
import shutil
import struct
import subprocess
import tempfile
import threading
import time
import urllib.error
import urllib.request
import zlib
from pathlib import Path

ROOT = Path(__file__).resolve().parent

# --------------------------------------------------------------------------- configuration
# Cloudflare / IA secrets are read at call time (see _cf_creds / _ia_creds).
CF_MODEL = (os.getenv("CF_IMAGE_MODEL") or "").strip() or "@cf/black-forest-labs/flux-1-schnell"
try:
    CF_STEPS = max(1, min(int(os.getenv("CF_IMAGE_STEPS") or "6"), 20))
except (TypeError, ValueError):
    CF_STEPS = 6

IA_COLLECTION = (os.getenv("IA_COLLECTION") or "opensource_media").strip()
IA_PREFIX = (os.getenv("IA_IDENTIFIER_PREFIX") or "nexus-stories").strip()

try:
    MAX_SCENES = max(1, min(int(os.getenv("VIDEO_MAX_SCENES") or "40"), 200))
except (TypeError, ValueError):
    MAX_SCENES = 40
try:
    MAX_MINUTES = max(1, min(int(os.getenv("VIDEO_MAX_MINUTES") or "20"), 120))
except (TypeError, ValueError):
    MAX_MINUTES = 20
try:
    FPS = max(8, min(int(os.getenv("VIDEO_FPS") or "24"), 60))
except (TypeError, ValueError):
    FPS = 24

CAP_SEC = float(MAX_MINUTES * 60)
BUILD_BUDGET_SEC = CAP_SEC          # module-level wall-clock budget for one build
XFADE_SEC = 0.6                     # crossfade allowance per scene boundary
WORDS_PER_MIN = 150.0               # Arabic narration estimate
DEFAULT_VOICE = "ar-SA-ZariyahNeural"
STYLE_PREFIX = ("high quality 3D animated cinematic film still, Pixar-like charming characters, "
                "soft volumetric light, warm colours")
NEGATIVE = "no text, no logos, no real faces, no violence, no gore"
KIDS_EXTRA = "gentle, bright, friendly, bedtime-safe"
SIZE = "1280x720"

# Rotating, safe, copyright-free scene ideas (style only, never film/character names).
SCENE_IDEAS = [
    "a curious traveller discovering a glowing doorway in a cosy old library",
    "friends sharing warm tea beside a rain-streaked window",
    "a little workshop full of brass lamps and impossible inventions",
    "a paper boat sailing down a moonlit river of stars",
    "a kite rising above soft green hills at golden hour",
    "a lantern-lit bridge and a slow boat at dusk",
    "a quiet rooftop garden under a violet dawn sky",
    "a wooden market stall selling paper flowers and sweet bread",
    "a small lighthouse beaming over a gentle turquoise sea",
    "a family kitchen where neighbours share stories and bread",
    "a tiny train chugging through a forest of painted paper trees",
    "children watching fireflies in a meadow at blue hour",
    "an old telescope pointed at a sky full of soft coloured clouds",
    "a friendly cat asleep on a stack of stories in a sunbeam",
    "a cobblestone lane lined with tiny warm-lit houses",
]

KIDS_IDEAS = [
    "a small teddy bear and a child waving at a bright rainbow",
    "friendly farm animals dancing in a sunny meadow",
    "a toy rocket leaving a trail of glitter above soft clouds",
    "a smiling moon reading a bedtime story to little stars",
    "a baby dragon made of soft paper breathing tiny bubbles",
    "a fluffy cloud family floating over a green hill",
    "a little boat bobbing on a calm bathtub sea with paper sails",
    "a kind robot watering flowers in a sunny garden",
]

KIDS_CATS = ("kids_3_6", "kids_7_10", "kids_11_14", "kids", "children", "child")
_BAD_VISUAL = ("blood", "gore", "violence", "kill", "weapon", "gun", "knife", "death",
               "nude", "naked", "horror", "scary", "frightening", "logo", "watermark",
               "celebrity", "real person")


def _log(msg):
    print(f"video_factory: {msg}", flush=True)


def _str(value):
    if value is None:
        return ""
    if isinstance(value, (list, tuple)):
        return "\n".join(_str(v) for v in value)
    return str(value).strip()


def _cf_creds():
    """Read Cloudflare credentials at call time (env may change after import)."""
    return ((os.getenv("CF_ACCOUNT_ID") or os.getenv("CLOUDFLARE_ACCOUNT_ID") or "").strip(),
            (os.getenv("CF_API_TOKEN") or os.getenv("CLOUDFLARE_API_TOKEN") or "").strip())


def _ia_creds():
    return ((os.getenv("IA_ACCESS_KEY") or "").strip(),
            (os.getenv("IA_SECRET_KEY") or "").strip())


def is_configured() -> bool:
    """True when the required secrets exist, even if a package is missing."""
    cf_account, cf_token = _cf_creds()
    access, secret = _ia_creds()
    return bool(cf_account and cf_token and access and secret)


def available() -> bool:
    """True only when all required packages AND all credentials are present."""
    if not is_configured():
        return False
    for mod in ("edge_tts", "imageio_ffmpeg", "internetarchive"):
        try:
            __import__(mod)
        except Exception:
            return False
    return True


# --------------------------------------------------------------------------- scene planning
def _is_kids(cat):
    c = _str(cat).lower()
    return any(k in c for k in KIDS_CATS)


def _content_text(article):
    parts = []
    for para in _str(article.get("content")).splitlines():
        p = para.strip()
        if not p:
            continue
        if p.startswith("## "):
            p = p[3:].strip()
        if p:
            parts.append(p)
    return "\n".join(parts)


def _safe_idea(text, kids, index):
    """Keep prompts English, family-safe and free of logos / real faces / text."""
    raw = _str(text)
    bad = not raw or bool(re.search(r"[\u0600-\u06ff]", raw)) or any(
        word in raw.lower() for word in _BAD_VISUAL)
    if bad:
        pool = KIDS_IDEAS if kids else SCENE_IDEAS
        raw = pool[index % len(pool)]
    parts = [STYLE_PREFIX, raw]
    if kids:
        parts.append(KIDS_EXTRA)
    parts.append(NEGATIVE)
    return ", ".join(parts)


def _plan_scenes(article, cat):
    """Return a list of {"narration", "visual"} capped by MAX_SCENES."""
    kids = _is_kids(cat)
    raw_scenes = article.get("scenes")
    scenes = []
    if isinstance(raw_scenes, list):
        for item in raw_scenes:
            if isinstance(item, dict):
                narration = _str(item.get("narration"))
                visual = _str(item.get("visual"))
            else:
                narration, visual = "", _str(item)
            if narration or visual:
                scenes.append({"narration": narration, "visual": visual})

    if not any(s["narration"] for s in scenes):
        # No usable narrated scenes: derive them from the story body.
        text = _content_text(article)
        words = text.split()
        if not words:
            return []
        lo, hi = (80, 120) if kids else (120, 180)
        target = (lo + hi) // 2
        # Widen the chunks when needed so the whole story fits in MAX_SCENES.
        target = max(target, int(math.ceil(len(words) / float(MAX_SCENES))))
        title = _str(article.get("title")) or "a gentle story"
        label = _str(cat) or "fiction"
        ideas = KIDS_IDEAS if kids else SCENE_IDEAS
        scenes = []
        for i in range(0, len(words), target):
            chunk = words[i:i + target]
            scenes.append({
                "narration": " ".join(chunk),
                "visual": (f"scene inspired by {title[:120]}, {label} category: "
                           f"{ideas[len(scenes) % len(ideas)]}"),
            })

    scenes = [s for s in scenes if s["narration"]][:MAX_SCENES]
    if not scenes:
        return []
    # Always force the English style envelope + negative constraints, even on supplied visuals.
    for i, scene in enumerate(scenes):
        scene["visual"] = _safe_idea(scene["visual"], kids, i)
    return _trim_to_budget(scenes)


def _trim_to_budget(scenes):
    """Drop trailing scenes while the estimated narration is longer than the cap."""
    kept = list(scenes)
    while kept and _base_seconds(kept) > CAP_SEC:
        kept.pop()
    return kept


def _base_seconds(scenes):
    return sum(max(1.5, len(s["narration"].split()) * 60.0 / WORDS_PER_MIN) for s in scenes)


def _durations(scenes, audio_sec):
    """Per-scene seconds: word-driven, gently scaled to the real TTS length."""
    base = [max(1.5, len(s["narration"].split()) * 60.0 / WORDS_PER_MIN) for s in scenes]
    total = sum(base)
    target = min(audio_sec if audio_sec > 0 else total, CAP_SEC)
    scale = (target / total) if total > 0 else 1.0
    return [max(1.5, b * scale + XFADE_SEC) for b in base], min(target, CAP_SEC)


# --------------------------------------------------------------------------- image helpers
def _load(path):
    with open(path, "rb") as fh:
        return fh.read()


def _solid_png(rgb=(38, 52, 80), width=320, height=180):
    """Tiny valid PNG fallback using only stdlib (no Pillow required)."""
    def chunk(tag, data):
        return (struct.pack(">I", len(data)) + tag + data
                + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF))

    row = b"\x00" + bytes(rgb) * width
    raw = zlib.compress(row * height, 6)
    return (b"\x89PNG\r\n\x1a\n"
            + chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0))
            + chunk(b"IDAT", raw) + chunk(b"IEND", b""))


def _to_webp(data, fallback_index=0):
    """Convert arbitrary image bytes to WebP with Pillow; degrade safely."""
    try:
        from PIL import Image
        import io
        image = Image.open(io.BytesIO(data)).convert("RGB")
        buf = io.BytesIO()
        image.save(buf, "WEBP", quality=82)
        return buf.getvalue()
    except Exception:
        if data[:8] == b"\x89PNG\r\n\x1a\n" or data[:4] == b"RIFF":
            return data
        colours = [(38, 52, 80), (64, 84, 110), (96, 74, 62), (48, 78, 72)]
        try:
            from PIL import Image
            import io
            buf = io.BytesIO()
            Image.new("RGB", (320, 180), colours[fallback_index % len(colours)]).save(buf, "WEBP")
            return buf.getvalue()
        except Exception:
            return _solid_png(colours[fallback_index % len(colours)])


def _solid_bytes(index):
    colours = [(38, 52, 80), (64, 84, 110), (96, 74, 62), (48, 78, 72)]
    try:
        from PIL import Image
        import io
        buf = io.BytesIO()
        Image.new("RGB", (320, 180), colours[index % len(colours)]).save(buf, "WEBP", quality=80)
        return buf.getvalue()
    except Exception:
        return _solid_png(colours[index % len(colours)])


def _flux_image(prompt):
    """POST one prompt to Cloudflare Workers AI and return decoded image bytes."""
    cf_account, cf_token = _cf_creds()
    if not cf_account or not cf_token:
        raise RuntimeError("Cloudflare credentials missing")
    url = (f"https://api.cloudflare.com/client/v4/accounts/{cf_account}"
           f"/ai/run/{CF_MODEL}")
    payload = json.dumps({"prompt": prompt[:2000], "steps": CF_STEPS}).encode("utf-8")
    headers = {"Authorization": f"Bearer {cf_token}", "Content-Type": "application/json"}
    last = ""
    for attempt in range(2):
        try:
            req = urllib.request.Request(url, data=payload, headers=headers, method="POST")
            with urllib.request.urlopen(req, timeout=120) as resp:
                raw = resp.read()
            result = json.loads(raw.decode("utf-8", "replace"))
            if not result.get("success"):
                raise RuntimeError(str(result.get("errors") or "Cloudflare reported failure")[:200])
            encoded = _str((result.get("result") or {}).get("image"))
            if "," in encoded and encoded.strip().startswith("data:"):
                encoded = encoded.split(",", 1)[1]
            if not encoded:
                raise RuntimeError("empty image in Cloudflare response")
            decoded = base64.b64decode(encoded, validate=False)
            if len(decoded) < 1024:
                raise RuntimeError("suspiciously small image")
            return decoded
        except Exception as exc:
            last = str(exc)[:200]
            if attempt == 0:
                time.sleep(2)
    raise RuntimeError(last or "Cloudflare image generation failed")


# --------------------------------------------------------------------------- narration
def _tts_save(text, voice, path):
    import edge_tts

    async def _go():
        comm = edge_tts.Communicate(text, voice)
        await comm.save(path)

    try:
        asyncio.run(_go())
        return
    except RuntimeError as exc:
        if "running event loop" not in str(exc):
            raise
    # Called from inside an existing event loop: run the coroutine on its own thread.
    box = {}

    def worker():
        try:
            asyncio.run(_go())
            box["ok"] = True
        except Exception as exc:
            box["err"] = exc

    thread = threading.Thread(target=worker, daemon=True)
    thread.start()
    thread.join()
    if "err" in box:
        raise box["err"]
    if not box.get("ok"):
        raise RuntimeError("edge-tts did not finish")


def _audio_duration(ffmpeg, audio_path):
    """Get the real MP3 length from ffmpeg's progress output (0.0 when unknown)."""
    try:
        proc = subprocess.run([ffmpeg, "-hide_banner", "-i", audio_path, "-f", "null", "-"],
                              capture_output=True, text=True, timeout=120)
        hits = re.findall(r"time=(\d+):(\d+):(\d+(?:\.\d+)?)", proc.stderr or "")
        if hits:
            h, m, s = hits[-1]
            return int(h) * 3600 + int(m) * 60 + float(s)
    except Exception:
        pass
    return 0.0


# --------------------------------------------------------------------------- ffmpeg rendering
def _run_ffmpeg(cmd, out_path, timeout):
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    except subprocess.TimeoutExpired:
        return False, "ffmpeg timeout"
    except Exception as exc:
        return False, str(exc)[:300]
    if proc.returncode != 0:
        return False, (proc.stderr or "").strip()[-500:] or f"exit {proc.returncode}"
    try:
        if not os.path.isfile(out_path) or os.path.getsize(out_path) < 1024:
            return False, "ffmpeg produced no output"
    except Exception as exc:
        return False, str(exc)[:200]
    return True, ""


def _render_video(ffmpeg, image_paths, durations, audio_path, out_path, deadline=0.0):
    """Three attempts: xfade+Ken Burns, concat+Ken Burns, then static concat."""
    base = (f"scale=1280:720:force_original_aspect_ratio=increase,crop=1280:720,"
            f"setsar=1,fps={FPS}")
    zoom = (f"zoompan=z='1.03+0.03*sin(on/180)':x='iw/2-(iw/zoom/2)':"
            f"y='ih/2-(ih/zoom/2)':d=1:s={SIZE}:fps={FPS}")
    tail = ["-c:v", "libx264", "-preset", "veryfast", "-crf", "26", "-r", str(FPS),
            "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "128k",
            "-movflags", "+faststart", "-shortest", "-t", f"{CAP_SEC:.1f}", str(out_path)]

    def time_left():
        if not deadline:
            return int(CAP_SEC)
        return int(max(0.0, deadline - time.monotonic()))

    if deadline and time_left() <= 0:
        return False, "time budget exhausted before rendering"

    # 1) Separate inputs + crossfades + subtle Ken Burns zoom.
    if len(image_paths) > 1:
        graph, inputs = [], []
        for i, (path, duration) in enumerate(zip(image_paths, durations)):
            inputs += ["-loop", "1", "-framerate", str(FPS), "-t", f"{duration:.3f}", "-i", str(path)]
            graph.append(f"[{i}:v]{base},trim=duration={duration:.3f},"
                         f"setpts=PTS-STARTPTS[v{i}]")
        last, acc = "v0", 0.0
        for i in range(1, len(image_paths)):
            acc += durations[i - 1]
            offset = max(0.0, acc - i * XFADE_SEC)
            name = f"x{i}"
            graph.append(f"[{last}][v{i}]xfade=transition=fade:duration={XFADE_SEC}:"
                         f"offset={offset:.3f}[{name}]")
            last = name
        graph.append(f"[{last}]{zoom},format=yuv420p[v]")
        cmd = ([ffmpeg, "-y", "-hide_banner", "-loglevel", "error"] + inputs
               + ["-i", audio_path, "-filter_complex", ";".join(graph),
                  "-map", "[v]", "-map", f"{len(image_paths)}:a"] + tail)
        ok, err = _run_ffmpeg(cmd, out_path, max(60, min(int(CAP_SEC), 3600, time_left())))
        if ok:
            return True, "xfade+zoompan"
        _log(f"xfade attempt failed, retrying with concat: {err[:300]}")

    # 2) Concat demuxer + Ken Burns zoom (still very simple, one output stream).
    with tempfile.NamedTemporaryFile("w", suffix=".txt", delete=False, encoding="utf-8") as fh:
        list_path = Path(fh.name)
        for path, duration in zip(image_paths, durations):
            q = str(path).replace("\\", "/").replace("'", "'\\''")
            fh.write(f"file '{q}'\nduration {duration:.3f}\n")
        q = str(image_paths[-1]).replace("\\", "/").replace("'", "'\\''")
        fh.write(f"file '{q}'\n")
    try:
        prefix = [ffmpeg, "-y", "-hide_banner", "-loglevel", "error",
                  "-f", "concat", "-safe", "0", "-i", str(list_path), "-i", audio_path]
        simple = f"setpts=N/({FPS}*TB)"
        for filt, label in ((f"{base},{simple},{zoom},format=yuv420p", "concat+zoompan"),
                            (f"{base},{simple},format=yuv420p", "static concat")):
            if deadline and time_left() <= 0:
                return False, "time budget exhausted during rendering"
            cmd = prefix + ["-filter_complex", f"[0:v]{filt}[v]", "-map", "[v]", "-map", "1:a"] + tail
            ok, err = _run_ffmpeg(cmd, out_path, max(60, min(int(CAP_SEC), 3600, time_left())))
            if ok:
                return True, label
            _log(f"{label} attempt failed: {err[:300]}")
            if label == "concat+zoompan":
                _log("retrying once with a minimal static filter")
    finally:
        try:
            list_path.unlink()
        except Exception:
            pass
    return False, "all ffmpeg attempts failed"


# --------------------------------------------------------------------------- upload
def _identifier(article):
    prefix = IA_PREFIX or "nexus-stories"
    ident = f"{prefix}-{_str(article.get('id')) or 'story'}".lower()
    ident = re.sub(r"[^a-z0-9-]+", "-", ident)
    ident = re.sub(r"-{2,}", "-", ident).strip("-")[:80].rstrip("-")
    return ident or "nexus-stories"


def _upload(identifier, video_path, poster_path, article):
    import internetarchive

    access, secret = _ia_creds()
    session = internetarchive.get_session(config={"access_key": access, "secret_key": secret})
    filename = f"{identifier}.mp4"
    metadata = {
        "mediatype": "movies",
        "title": _str(article.get("title")) or identifier,
        "description": _str(article.get("summary")),
        "creator": "مملكة الأسرار",
        "language": "ar",
    }
    if IA_COLLECTION:
        metadata["collection"] = IA_COLLECTION
    result = session.upload(identifier, str(video_path), key=filename, metadata=metadata)
    if result is False:
        raise RuntimeError("Internet Archive rejected the upload")
    if poster_path and os.path.isfile(poster_path):
        try:
            session.upload(identifier, str(poster_path), key=os.path.basename(poster_path))
        except Exception as exc:
            _log(f"poster upload skipped: {str(exc)[:200]}")
    return filename


# --------------------------------------------------------------------------- main entry point
def build_for_story(article: dict, cat: str, img_bytes: bytes | None) -> dict | None:
    """Build, narrate, render and upload a story video; never raises."""
    started = time.monotonic()
    try:
        if not available():
            _log("packages or credentials missing; skipping video")
            return None
        if not isinstance(article, dict):
            _log("article is not a dictionary")
            return None

        story_id = _str(article.get("id")) or "story"
        scenes = _plan_scenes(article, cat)
        if not scenes:
            _log("no narrated scenes could be prepared")
            return None

        import imageio_ffmpeg
        ffmpeg = imageio_ffmpeg.get_ffmpeg_exe()
        if not ffmpeg or not os.path.isfile(ffmpeg):
            _log("ffmpeg binary not found")
            return None

        images_dir = ROOT / "images"
        images_dir.mkdir(parents=True, exist_ok=True)
        main_bytes = img_bytes if isinstance(img_bytes, (bytes, bytearray)) and len(img_bytes) > 512 else b""
        image_paths, used = [], set()
        for i, scene in enumerate(scenes):
            if time.monotonic() - started > BUILD_BUDGET_SEC:
                _log("wall-clock budget exhausted during image generation")
                return None
            path = images_dir / f"story-{story_id}-scene-{i:02d}.webp"
            path = path.resolve()
            if path in used:  # defensive: never include the same filename twice
                k = 2
                while path.with_name(f"{path.stem}-{k}{path.suffix}") in used:
                    k += 1
                path = path.with_name(f"{path.stem}-{k}{path.suffix}")
            used.add(path)
            try:
                data = _flux_image(scene["visual"])
                path.write_bytes(data)
            except Exception as exc:
                _log(f"image for scene {i + 1} failed, using fallback: {str(exc)[:200]}")
                try:
                    data = _to_webp(main_bytes, i) if main_bytes else _solid_bytes(i)
                    path.write_bytes(data)
                except Exception as exc2:
                    _log(f"fallback image for scene {i + 1} failed: {str(exc2)[:200]}")
                    return None
            image_paths.append(path)

        video_data = article.get("video")
        voice = (video_data.get("voice") if isinstance(video_data, dict) else "") or ""
        voice = _str(voice) or _str(os.getenv("EDGE_TTS_VOICE")) or DEFAULT_VOICE

        with tempfile.TemporaryDirectory(prefix="nexus-video-") as tmp:
            tmp_dir = Path(tmp)
            text_path = tmp_dir / "narration.txt"
            text_path.write_text("\n\n".join(s["narration"] for s in scenes), encoding="utf-8")
            audio_path = tmp_dir / "narration.mp3"
            try:
                _tts_save(text_path.read_text(encoding="utf-8"), voice, str(audio_path))
                if not audio_path.is_file() or audio_path.stat().st_size < 1024:
                    raise RuntimeError("empty TTS output")
            except Exception as exc:
                _log(f"edge-tts failed: {str(exc)[:300]}")
                return None

            durations, planned = _durations(scenes, _audio_duration(ffmpeg, str(audio_path)))
            out_path = tmp_dir / f"{story_id}.mp4"
            ok, mode = _render_video(ffmpeg, image_paths, durations, str(audio_path), str(out_path),
                                     started + BUILD_BUDGET_SEC)
            if not ok:
                _log(f"video rendering failed: {mode}")
                return None
            _log(f"rendered {mode}: {len(scenes)} scenes, {int(planned)} seconds")

            poster = images_dir / f"{story_id}-poster.webp"
            try:
                if image_paths[0].resolve() != poster.resolve():
                    shutil.copyfile(str(image_paths[0]), str(poster))
            except Exception as exc:
                _log(f"poster copy failed: {str(exc)[:200]}")

            if time.monotonic() - started > BUILD_BUDGET_SEC:
                _log("wall-clock budget exhausted before upload")
                return None
            try:
                identifier = _identifier(article)
                filename = _upload(identifier, out_path, poster if poster.is_file() else None, article)
            except Exception as exc:
                _log(f"Internet Archive upload failed: {str(exc)[:300]}")
                return None

            return {
                "url": f"https://archive.org/download/{identifier}/{filename}",
                "page": f"https://archive.org/details/{identifier}",
                "poster": f"images/{story_id}-poster.webp",
                "seconds": int(planned),
                "scenes": len(scenes),
                "voice": voice,
            }
    except Exception as exc:
        _log(f"unexpected error: {type(exc).__name__}: {str(exc)[:300]}")
        return None


if __name__ == "__main__":
    _log(f"available={available()} is_configured={is_configured()}")
