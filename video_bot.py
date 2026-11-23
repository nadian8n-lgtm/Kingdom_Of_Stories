#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
بوت فيديو «مملكة الأسرار» — مجاني وبلا مفتاح، بطول غير محدود.

الأوضاع:
  1) still : صورة ثابتة تماماً بلا زوم ولا حركة (الافتراضي: --motion static).
  2) ai    : مقاطع Wan2.1-fast من Hugging Face (بلا مفتاح) ثم لصقها بـ ffmpeg.
  3) auto  : يجرّب ai ثم يرجع إلى still تلقائياً.
  وللحركة السينمائية الاختيارية: --motion in|out|pan|sine (Ken Burns).

كل النِسَب مدعومة، والطول غير محدود:
  --duration 0   يعني لصق متواصل بلا نهاية (أوقفه بـ Ctrl+C)

أمثلة:
  python video_bot.py --only <id> --duration 30
  python video_bot.py --only <id> --mode still --aspect 9:16 --res 4k
  python video_bot.py --all --duration 60 --aspect 16:9
"""
from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import sys
import time
import urllib.request
import uuid
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")

from image_bot import ASPECTS, BASE, CACHE, SCENES, aspect_slug, build_prompt, target_size

VIDEO_DIR = BASE / "videos"
UA = {"User-Agent": "Mozilla/5.0 (KingdomOfStories video bot)"}

try:
    import imageio_ffmpeg

    FFMPEG = imageio_ffmpeg.get_ffmpeg_exe()
except Exception:  # noqa: BLE001
    FFMPEG = shutil.which("ffmpeg") or ""


def ffmpeg(args: list[str], timeout: int = 3600) -> None:
    if not FFMPEG:
        raise RuntimeError("ffmpeg غير متوفّر. شغّل: python -m pip install imageio-ffmpeg")
    cmd = [FFMPEG, "-hide_banner", "-loglevel", "error", "-y", *args]
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    if r.returncode != 0:
        raise RuntimeError(f"ffmpeg: {r.stderr.strip()[:400]}")


# ----------------------------------------------------------------------------
# إيجاد أفضل صورة مصدر
# ----------------------------------------------------------------------------
def find_still(article_id: str, aspect: str = "16:9") -> Path | None:
    slug = aspect_slug(aspect)
    candidates = sorted(
        CACHE.glob(f"{article_id}@{slug}@*.jpg"),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )
    if candidates:
        return candidates[0]
    candidates = sorted(
        CACHE.glob(f"{article_id}@16x9@*.jpg"),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )
    if candidates:
        return candidates[0]
    p = BASE / "images" / f"{article_id}-scene-1.webp"
    return p if p.exists() else None


# ----------------------------------------------------------------------------
# وضع still: صورة ثابتة (افتراضي) أو حركة سينمائية اختيارية + تكرار بلا نهاية
# ----------------------------------------------------------------------------
def make_cycle(still: Path, out: Path, size: tuple[int, int], seconds: float,
               fps: int = 30, motion: str = "static", crf: int = 18,
               preset: str = "veryfast", tune: str | None = None) -> Path:
    w, h = size
    frames = max(2, int(seconds * fps))

    if motion == "static":
        # صورة ثابتة تماماً: قصّ full-bleed يملأ الإطار بلا أي زوم أو تحريك.
        vf = (
            f"scale={w}:{h}:force_original_aspect_ratio=increase:flags=lanczos,"
            f"crop={w}:{h},fps={fps},format=yuv420p"
        )
    else:
        up_w = int(w * 1.3) // 2 * 2
        up_h = int(h * 1.3) // 2 * 2
        if motion == "in":
            z = f"1.02+0.10*on/{frames}"
            x = "iw/2-(iw/zoom/2)"
            y = "ih/2-(ih/zoom/2)"
        elif motion == "out":
            z = f"1.12-0.10*on/{frames}"
            x = "iw/2-(iw/zoom/2)"
            y = "ih/2-(ih/zoom/2)"
        elif motion == "pan":
            z = "1.10"
            x = f"(iw-iw/zoom)*(on/{frames})"
            y = "ih/2-(ih/zoom/2)"
        else:  # sine
            z = f"1.07+0.05*(0.5-0.5*cos(2*PI*on/{frames}))"
            x = f"iw/2-(iw/zoom/2)+{max(2, w // 90)}*sin(2*PI*on/{frames})"
            y = "ih/2-(ih/zoom/2)"
        vf = (
            f"scale={up_w}:{up_h}:flags=lanczos,"
            f"zoompan=z='{z}':x='{x}':y='{y}':d=1:s={w}x{h}:fps={fps},"
            "format=yuv420p"
        )
    cmd = [
        "-loop", "1", "-i", str(still), "-t", f"{seconds:.3f}",
        "-vf", vf,
        "-c:v", "libx264", "-preset", preset, "-crf", str(crf),
        "-pix_fmt", "yuv420p",
    ]
    if tune:
        cmd += ["-tune", tune]
    cmd += ["-movflags", "+faststart", str(out)]
    ffmpeg(cmd)
    return out


def loop_cycle(cycle: Path, out: Path, duration: float) -> Path:
    args = ["-stream_loop", "-1", "-i", str(cycle)]
    if duration and duration > 0:
        args += ["-t", f"{duration:.3f}", "-c", "copy", "-movflags", "+faststart", str(out)]
    else:
        args += ["-c", "copy", "-movflags", "frag_keyframe+empty_moov", str(out)]
    ffmpeg(args, timeout=0 if not duration else 3600)
    return out


def build_still_video(still: Path, out: Path, size: tuple[int, int], duration: float,
                      fps: int = 30, web: bool = False, motion: str = "static") -> Path:
    VIDEO_DIR.mkdir(parents=True, exist_ok=True)
    tmp = VIDEO_DIR / f"_cycle_{uuid.uuid4().hex[:8]}.mp4"
    make_cycle(still, tmp, size, seconds=12, fps=fps, motion=motion,
               crf=30 if web else 18,
               preset="veryfast",
               tune="stillimage" if web else None)
    try:
        loop_cycle(tmp, out, duration)
    finally:
        tmp.unlink(missing_ok=True)
    return out


# ----------------------------------------------------------------------------
# وضع ai: Wan2.1-fast (Hugging Face Space، بلا مفتاح)
# ----------------------------------------------------------------------------
WAN = "https://multimodalart-wan2-1-fast.hf.space"


def _post(url: str, data: bytes, headers: dict, timeout: int = 120) -> bytes:
    req = urllib.request.Request(url, data=data, headers=headers, method="POST")
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read()


def _upload(path: Path) -> str:
    boundary = "----kos" + uuid.uuid4().hex
    body = b""
    body += f"--{boundary}\r\n".encode()
    body += f'Content-Disposition: form-data; name="files"; filename="{path.name}"\r\n'.encode()
    body += b"Content-Type: image/png\r\n\r\n"
    body += path.read_bytes() + b"\r\n"
    body += f"--{boundary}--\r\n".encode()
    raw = _post(
        f"{WAN}/gradio_api/upload?upload_id={uuid.uuid4().hex}",
        body,
        {"Content-Type": f"multipart/form-data; boundary={boundary}", **UA},
    )
    arr = json.loads(raw.decode("utf-8", "replace"))
    return arr[0] if isinstance(arr, list) else arr


def _sse(base: str, api: str, data: list, timeout: int = 1800) -> str:
    raw = _post(
        f"{base}/gradio_api/call/{api}",
        json.dumps({"data": data}).encode(),
        {"Content-Type": "application/json", **UA},
    )
    eid = json.loads(raw.decode())["event_id"]
    req = urllib.request.Request(f"{base}/gradio_api/call/{api}/{eid}", headers=UA)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read().decode("utf-8", "replace")


def _find_media_url(node) -> str | None:
    if isinstance(node, dict):
        for k in ("url", "path"):
            v = node.get(k)
            if isinstance(v, str) and (v.startswith("http") or v.startswith("/")):
                if any(x in v.lower() for x in (".mp4", ".webm", ".gif", "/file=")):
                    return v
        for v in node.values():
            u = _find_media_url(v)
            if u:
                return u
    elif isinstance(node, list):
        for v in node:
            u = _find_media_url(v)
            if u:
                return u
    elif isinstance(node, str) and node.startswith("http"):
        return node
    return None


def wan_clip(still: Path, prompt: str, out: Path, aspect: str, seconds: float = 5.0,
             seed: int = 42) -> Path:
    remote = _upload(still)
    rw, rh = ASPECTS.get(aspect, (16, 9))
    h = 720
    w = int(round(h * rw / rh / 16) * 16)
    data = [
        {"path": remote, "meta": {"_type": "gradio.FileData"}},
        prompt, h, w,
        "blurry, low quality, text, watermark, violence, gore",
        float(seconds), 5.0, 30, seed, True,
    ]
    raw = _sse(WAN, "generate_video", data)
    if "event: error" in raw:
        raise RuntimeError("Wan2.1 أعاد خطأ (حصة/توقّف).")
    last = None
    for line in raw.splitlines():
        if line.strip().startswith("data:"):
            v = line[5:].strip()
            if v and v != "null":
                last = v
    if not last:
        raise RuntimeError("Wan2.1: استجابة فارغة.")
    url = _find_media_url(json.loads(last))
    if not url:
        raise RuntimeError("Wan2.1: لم أجد رابط الفيديو.")
    if url.startswith("/"):
        url = WAN + url
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=600) as r:
        out.write_bytes(r.read())
    return out


def concat_clips(clips: list[Path], out: Path) -> Path:
    lst = out.with_suffix(".txt")
    lst.write_text("".join(f"file '{c.as_posix()}'\n" for c in clips), encoding="utf-8")
    try:
        ffmpeg(["-f", "concat", "-safe", "0", "-i", str(lst), "-c", "copy", str(out)])
    finally:
        lst.unlink(missing_ok=True)
    return out


def build_ai_video(still: Path, prompt: str, out: Path, aspect: str, duration: float,
                   fps: int = 25, max_clips: int = 2) -> Path:
    """يولّد مقاطع Wan2.1 قصيرة ثم يعيد تكرارها (stream copy) لبلوغ الطول المطلوب."""
    VIDEO_DIR.mkdir(parents=True, exist_ok=True)
    clips: list[Path] = []
    for i in range(1, max(1, max_clips) + 1):
        clip = VIDEO_DIR / f"_ai_{uuid.uuid4().hex[:8]}_{i}.mp4"
        print(f"      Wan2.1 clip {i}/{max_clips} …", flush=True)
        try:
            wan_clip(still, prompt, clip, aspect, seconds=5.0, seed=42 + i)
        except Exception as e:  # noqa: BLE001
            print("      ✗", str(e)[:180], flush=True)
            break
        clips.append(clip)
    if not clips:
        raise RuntimeError("تعذّر توليد أي مقطع AI.")
    merged = VIDEO_DIR / f"_aimerge_{uuid.uuid4().hex[:8]}.mp4"
    concat_clips(clips, merged)
    for c in clips:
        c.unlink(missing_ok=True)
    if duration and duration > 0:
        ffmpeg(["-stream_loop", "-1", "-i", str(merged), "-t", f"{duration:.3f}",
                "-c", "copy", "-movflags", "+faststart", str(out)])
        merged.unlink(missing_ok=True)
    else:
        shutil.move(str(merged), str(out))
    return out


def mux_audio(video: Path, audio: Path | None, out: Path, fade_tail: float = 1.2,
              bitrate: str = "192k", mono: bool = False) -> Path:
    """يضمّ التعليق الصوتي إلى الفيديو بجودة عالية (بلا إعادة ترميز للصورة)."""
    if not audio or not Path(audio).exists():
        shutil.move(str(video), str(out))
        return out
    cmd = [
        "-i", str(video), "-i", str(audio),
        "-map", "0:v:0", "-map", "1:a:0",
        "-c:v", "copy", "-c:a", "aac", "-b:a", bitrate, "-ar", "48000",
        "-af", f"apad=pad_dur={fade_tail:.2f}",
        "-shortest", "-movflags", "+faststart", str(out),
    ]
    if mono:
        cmd += ["-ac", "1"]
    ffmpeg(cmd)
    Path(video).unlink(missing_ok=True)
    return out


def media_duration(path: Path) -> float:
    try:
        r = subprocess.run([FFMPEG, "-hide_banner", "-i", str(path)],
                           capture_output=True, text=True)
        m = re.search(r"Duration:\s*(\d+):(\d+):(\d+(?:\.\d+)?)", r.stderr)
        if m:
            h, mi, se = m.groups()
            return int(h) * 3600 + int(mi) * 60 + float(se)
    except Exception:  # noqa: BLE001
        pass
    return 0.0


def split_audio(audio: Path, out_dir: Path, base: str, part_seconds: float) -> list[tuple[Path, float]]:
    """يقسّم التعليق الصوتي إلى أجزاء صغيرة مناسبة لرفع GitHub (أقل من 25MB)."""
    total = media_duration(audio)
    out: list[tuple[Path, float]] = []
    t = 0.0
    n = 0
    while total > 0 and t < total - 0.3:
        n += 1
        dur = min(part_seconds, total - t)
        p = out_dir / f"{base}-part{n}.m4a"
        ffmpeg(["-ss", f"{t:.3f}", "-t", f"{dur + 0.8:.3f}", "-i", str(audio),
                "-c:a", "aac", "-b:a", "64k", "-ac", "1", "-ar", "44100", str(p)])
        out.append((p, dur))
        t += dur
    return out


# ----------------------------------------------------------------------------
def main() -> int:
    ap = argparse.ArgumentParser(description="Kingdom Of Secrets video bot — free, narrated, unlimited length.")
    ap.add_argument("--only", default="")
    ap.add_argument("--all", action="store_true", help="كل القصص")
    ap.add_argument("--aspect", default="16:9")
    ap.add_argument("--res", default="4k", help="hd | fhd | qhd | 4k")
    ap.add_argument("--duration", type=float, default=0,
                    help="ثوانٍ؛ 0 = يتبع طول التعليق الصوتي")
    ap.add_argument("--fps", type=int, default=25)
    ap.add_argument("--mode", default="auto", choices=["auto", "ai", "still"])
    ap.add_argument("--motion", default="static",
                    choices=["static", "in", "out", "pan", "sine"],
                    help="حركة الصورة؛ static = صورة ثابتة بلا زوم (الافتراضي)")
    ap.add_argument("--ai-clips", type=int, default=2, help="عدد مقاطع Wan2.1 قبل التكرار")
    ap.add_argument("--out-dir", default="")
    ap.add_argument("--narration", action=argparse.BooleanOptionalAction, default=True,
                    help="تعليق صوتي يقرأ القصة (افتراضي: مفعّل)")
    ap.add_argument("--voice", default="", help="تجاوز الصوت، مثل ar-SA-HamedNeural")
    ap.add_argument("--voice-rate", default="", help="سرعة القراءة، مثل -10%%")
    ap.add_argument("--music", type=float, default=-1.0,
                    help="جهارة الخلفية السينمائية (0 = بلا خلفية)")
    ap.add_argument("--subs", action="store_true", help="ولّد ملف ترجمة SRT مع الفيديو")
    ap.add_argument("--force-voice", action="store_true", help="أعد توليد التعليق الصوتي")
    ap.add_argument("--web", action="store_true",
                    help="نسخة خفيفة للموقع: 720p/12fps/AAC 192k متوافقة مع رفع GitHub")
    ap.add_argument("--part-minutes", type=float, default=0,
                    help="قسّم الفيديو إلى أجزاء (دقائق؛ 0 = جزء واحد؛ مع --web الافتراضي 9)")
    ap.add_argument("--install", action="store_true",
                    help="أضف الفيديو إلى articles.json ليظهر داخل صفحة القصة")
    args = ap.parse_args()

    if args.aspect not in ASPECTS:
        print("نسبة غير معروفة:", args.aspect)
        return 2

    bitrate = "192k"
    mono = False
    if args.web:
        size = (1280, 720) if ASPECTS[args.aspect][0] >= ASPECTS[args.aspect][1] else (720, 1280)
        args.fps = min(args.fps, 12)
        bitrate = "192k"
        mono = True
        if not args.part_minutes:
            args.part_minutes = 9.0
    else:
        size = target_size(args.aspect, args.res if args.res != "8k" else "4k")

    data = json.loads((BASE / "articles.json").read_text(encoding="utf-8"))
    out_dir = Path(args.out_dir) if args.out_dir else VIDEO_DIR
    out_dir.mkdir(parents=True, exist_ok=True)

    only = {x.strip() for x in args.only.split(",") if x.strip()}
    jobs = []
    for cat, arts in data["articles"].items():
        if not cat.startswith(("story_", "kids_")):
            continue
        for a in arts:
            if args.all or not only or a["id"] in only:
                jobs.append((cat, a))
    if not args.all:
        jobs = [j for j in jobs if not only or j[1]["id"] in only]

    ok = fail = 0
    for i, (cat, a) in enumerate(jobs, 1):
        aid = a["id"]
        still = find_still(aid, args.aspect)
        if not still:
            print(f"[{i}/{len(jobs)}] {aid}: لا توجد صورة — شغّل image_bot.py أولاً.", flush=True)
            fail += 1
            continue
        prompt = build_prompt(a, cat)
        out = out_dir / f"{aid}-{aspect_slug(args.aspect)}-{args.res}.mp4"
        print(f"\n[{i}/{len(jobs)}] {aid} {args.aspect} -> {size[0]}x{size[1]} ({args.mode})", flush=True)

        audio: Path | None = None
        narr_len = 0.0
        if args.narration:
            try:
                from narration_engine import audio_duration, narrate_article

                audio = out_dir / f"{aid}-narration.m4a"
                srt = out_dir / f"{aid}-narration.srt" if args.subs else None
                if audio.exists() and audio.stat().st_size > 20000 and not args.force_voice:
                    narr_len = audio_duration(audio)
                    print(f"      = تعليق صوتي موجود ({narr_len / 60:.1f} د)", flush=True)
                else:
                    music = None if args.music < 0 else max(0.0, args.music)
                    narrate_article(a, cat, out_dir, srt=args.subs,
                                    voice=args.voice or None,
                                    rate=args.voice_rate or None,
                                    music=music)
                    narr_len = audio_duration(audio)
            except Exception as e:  # noqa: BLE001
                print("      ⚠ تعذّر التعليق الصوتي:", str(e)[:180], flush=True)
                audio = None
                narr_len = 0.0
            # A silent 30-second placeholder must NEVER be installed as a
            # "narrated" story. Fail loudly so the resume driver retries it.
            if args.narration and (not audio or narr_len <= 0):
                print("      ⛔ فشل التعليق الصوتي؛ لا يُنشأ فيديو صامت. ستُعاد المحاولة.",
                      flush=True)
                fail += 1
                continue

        if narr_len > 0:
            duration = max(narr_len + 1.4, args.duration)
        else:
            duration = args.duration if args.duration > 0 else 30.0

        slug = aspect_slug(args.aspect)
        segments: list[tuple[Path | None, float]] = []
        if audio and args.part_minutes > 0 and duration > args.part_minutes * 60:
            segments = split_audio(audio, out_dir,
                                   f"{aid}-{slug}-narration", args.part_minutes * 60)
            print(f"      سيُقسَّم إلى {len(segments)} أجزاء", flush=True)
        if not segments:
            segments = [(audio, duration)]

        built: list[Path] = []
        try:
            for part_no, (seg_audio, seg_duration) in enumerate(segments, 1):
                suffix = "" if len(segments) == 1 else f"-part{part_no}"
                out = out_dir / f"{aid}-{slug}-{'web' if args.web else args.res}{suffix}.mp4"
                temp_video = out_dir / f"_v_{uuid.uuid4().hex[:8]}.mp4"
                print(f"      جزء {part_no}/{len(segments)} — {seg_duration / 60:.1f} د", flush=True)

                try:
                    if args.motion == "static" or args.mode == "still":
                        build_still_video(still, temp_video, size, seg_duration,
                                          args.fps, web=args.web, motion=args.motion)
                    elif args.mode in ("auto", "ai"):
                        try:
                            build_ai_video(still, prompt, temp_video, args.aspect, seg_duration,
                                           args.fps, args.ai_clips)
                        except Exception as e:  # noqa: BLE001
                            if args.mode == "ai":
                                raise
                            print("      رجوع إلى الصورة الثابتة:", str(e)[:120], flush=True)
                            build_still_video(still, temp_video, size, seg_duration,
                                              args.fps, web=args.web, motion=args.motion)
                    else:
                        build_still_video(still, temp_video, size, seg_duration,
                                          args.fps, web=args.web, motion=args.motion)

                    mux_audio(temp_video, seg_audio, out, bitrate=bitrate, mono=mono)
                except Exception:
                    temp_video.unlink(missing_ok=True)
                    raise

                mb = out.stat().st_size / 1048576
                built.append(out)
                print(f"      saved -> {out.name}  ({mb:.1f} MB)", flush=True)

            ok += 1
            if args.install and out_dir == VIDEO_DIR:
                v: dict = {
                    "poster": a.get("image") or "",
                    "seconds": int(round(duration)),
                    "narration": "edge-tts",
                }
                if len(built) == 1:
                    v["url"] = built[0].relative_to(BASE).as_posix()
                else:
                    v["parts"] = [
                        {"url": p.relative_to(BASE).as_posix(),
                         "seconds": int(round(segments[j][1]))}
                        for j, p in enumerate(built)
                    ]
                a["video"] = v
                if audio and Path(audio).exists():
                    a["audio"] = {
                        "url": Path(audio).relative_to(BASE).as_posix(),
                        "title": "استمع إلى القصة بصوت نكسوس",
                    }
                (BASE / "articles.json").write_text(
                    json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
                print("      + أُضيف إلى articles.json", flush=True)
        except Exception as e:  # noqa: BLE001
            fail += 1
            print("      FAILED:", str(e)[:220], flush=True)

    print(f"\nDONE ok={ok} failed={fail}")
    return 0 if fail == 0 else 2


if __name__ == "__main__":
    raise SystemExit(main())
