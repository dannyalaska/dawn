"""
DAWN demo recorder — narrated + captioned MP4.

Generates ElevenLabs voice-over (voice: Eric — smooth tenor, perfect for
agentic use cases), records the live DAWN dashboard with Playwright, burns
in captions, then stitches everything into a single MP4 via ffmpeg.

Usage:
    # Make sure the DAWN stack is running:
    #   Backend:  cd app && uvicorn app.api.server:app --port 8000 --reload
    #   Frontend: cd web && npm run dev   (serves on :3000)

    pip install playwright elevenlabs pillow requests
    playwright install chromium
    python record_demo.py

Output: docs/demo_recording.mp4
"""

from __future__ import annotations

import io
import os
import subprocess
import sys
import tempfile
import time
import urllib.request
from pathlib import Path

from dotenv import dotenv_values

# ---------------------------------------------------------------------------
# Credentials — search the same .env locations as gridbot
# ---------------------------------------------------------------------------
_ENV_CANDIDATES = [
    Path.home() / "Desktop" / "Shared with RD backup" / "SleepHypnoAI" / ".env",
    Path(__file__).parent.parent / "Shared with RD backup" / "SleepHypnoAI" / ".env",
    Path(__file__).parent / ".env",
]
_ENV_FILE = next((p for p in _ENV_CANDIDATES if p.exists()), _ENV_CANDIDATES[-1])
_dotenv = dotenv_values(_ENV_FILE) if _ENV_FILE.exists() else {}

ELEVENLABS_API_KEY = _dotenv.get("ELEVENLABS_API_KEY") or os.getenv("ELEVENLABS_API_KEY", "")
# Eric — "smooth tenor pitch perfect for agentic use cases" (different from gridbot's voice)
ELEVENLABS_VOICE_ID = "cjVigY5qzO86Huf0OWal"
ELEVENLABS_MODEL = _dotenv.get("ELEVENLABS_MODEL_ID") or os.getenv(
    "ELEVENLABS_MODEL_ID", "eleven_multilingual_v2"
)

# ---------------------------------------------------------------------------
# Recording config
# ---------------------------------------------------------------------------
FRONTEND_URL = "http://localhost:3000"
BACKEND_URL = "http://localhost:8000/health"
RECORD_SECONDS = 65
FPS = 2
OUTPUT_MP4 = Path(__file__).parent / "docs" / "demo_recording.mp4"
VIEWPORT = {"width": 1440, "height": 900}

# ---------------------------------------------------------------------------
# Narration script: (start_second, caption_text, spoken_text)
# ---------------------------------------------------------------------------
NARRATION = [
    (
        0,
        "Dawn — AI-powered data intelligence for ops teams",
        "This is Dawn. An AI-powered data intelligence platform built for operations teams "
        "who need answers fast — without engineers in the loop.",
    ),
    (
        9,
        "One click loads demo data + runs full agent analysis",
        "Hit Run Demo and Dawn ingests your dataset, profiles every column, and kicks off "
        "a seven-agent analysis pipeline — automatically. No configuration required.",
    ),
    (
        20,
        "Data quality checks run on every ingest",
        "Every feed gets automatic data quality checks. Green means your data is clean. "
        "Red means Dawn already found something worth investigating before you even asked.",
    ),
    (
        30,
        "Seven agents — planner, executor, memory, QA, and more",
        "Dawn's agent swarm generates an action plan, executes analytical tasks, spots "
        "anomalies, checks for drift, and writes a structured report — all without a single query.",
    ),
    (
        41,
        "Runs on any LLM — local or cloud",
        "Dawn runs on whatever LLM you choose. Fully local with Ollama or LM Studio for "
        "air-gapped deployments, or cloud-powered with OpenAI or Claude. One toggle.",
    ),
    (
        51,
        "Ask in plain English — Dawn writes and runs the SQL",
        "Teams can ask questions in plain English. Dawn translates them to SQL, runs them "
        "read-only against your connected databases, and returns live results. Securely.",
    ),
    (
        60,
        "Dawn — from raw data to insight in seconds",
        "Dawn. From raw data to boardroom-ready insight in seconds. "
        "Private, fast, and built for the ops teams who can't wait.",
    ),
]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def load_font(size: int):
    """Load system font with graceful fallback."""
    try:
        from PIL import ImageFont

        for candidate in [
            "/System/Library/Fonts/Helvetica.ttc",
            "/System/Library/Fonts/SF-Pro-Display-Semibold.otf",
            "/System/Library/Fonts/SFNSDisplay.ttf",
            "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        ]:
            if Path(candidate).exists():
                return ImageFont.truetype(candidate, size)
        return ImageFont.load_default()
    except Exception:
        from PIL import ImageFont

        return ImageFont.load_default()


def caption_for_time(t: float) -> str:
    """Return the caption active at time t."""
    active = ""
    for start, caption, _ in NARRATION:
        if t >= start:
            active = caption
    return active


def burn_caption(frame_bytes: bytes, caption: str) -> bytes:
    """Overlay a frosted caption bar at the bottom of the frame."""
    from PIL import Image, ImageDraw

    img = Image.open(io.BytesIO(frame_bytes)).convert("RGB")
    if not caption:
        out = io.BytesIO()
        img.save(out, format="PNG")
        return out.getvalue()

    draw = ImageDraw.Draw(img)
    w, h = img.size
    font_size = max(22, w // 50)
    font = load_font(font_size)

    bbox = draw.textbbox((0, 0), caption, font=font)
    text_w = bbox[2] - bbox[0]
    text_h = bbox[3] - bbox[1]
    bar_h = text_h + 32
    bar_y = h - bar_h - 16

    # Frosted dark overlay
    overlay = Image.new("RGBA", img.size, (0, 0, 0, 0))
    odraw = ImageDraw.Draw(overlay)
    odraw.rectangle([(0, bar_y - 10), (w, h)], fill=(8, 10, 20, 200))

    # Cyan accent line at top of bar
    odraw.rectangle([(0, bar_y - 10), (w, bar_y - 7)], fill=(6, 182, 212, 255))  # cyan-500

    img = Image.alpha_composite(img.convert("RGBA"), overlay).convert("RGB")
    draw = ImageDraw.Draw(img)

    x = (w - text_w) // 2
    y = bar_y + 6
    # Drop shadow
    draw.text((x + 2, y + 2), caption, font=font, fill=(0, 0, 0, 160))
    # White text
    draw.text((x, y), caption, font=font, fill=(255, 255, 255))

    out = io.BytesIO()
    img.save(out, format="PNG")
    return out.getvalue()


def add_dawn_watermark(frame_bytes: bytes) -> bytes:
    """Add a subtle DAWN watermark to the top-right corner."""
    from PIL import Image, ImageDraw

    img = Image.open(io.BytesIO(frame_bytes)).convert("RGB")
    draw = ImageDraw.Draw(img)
    w, _h = img.size
    font_size = max(16, w // 72)
    font = load_font(font_size)
    label = "DAWN"
    bbox = draw.textbbox((0, 0), label, font=font)
    tw = bbox[2] - bbox[0]
    draw.text((w - tw - 18, 14), label, font=font, fill=(6, 182, 212, 200))
    out = io.BytesIO()
    img.save(out, format="PNG")
    return out.getvalue()


# ---------------------------------------------------------------------------
# Voice-over generation
# ---------------------------------------------------------------------------


def generate_vo(tmp_dir: Path) -> list[tuple[float, Path]]:
    """Generate MP3 for each narration segment via ElevenLabs REST API."""
    import requests as req

    if not ELEVENLABS_API_KEY:
        print("[vo] ELEVENLABS_API_KEY not set — skipping voice-over")
        return []

    url = f"https://api.elevenlabs.io/v1/text-to-speech/{ELEVENLABS_VOICE_ID}"
    headers = {
        "xi-api-key": ELEVENLABS_API_KEY,
        "Content-Type": "application/json",
        "Accept": "audio/mpeg",
    }

    clips: list[tuple[float, Path]] = []
    for i, (start_sec, _caption, spoken) in enumerate(NARRATION):
        preview = spoken[:60] + ("…" if len(spoken) > 60 else "")
        print(f'  [vo] Segment {i+1}/{len(NARRATION)}: "{preview}"')
        payload = {
            "text": spoken,
            "model_id": ELEVENLABS_MODEL,
            "voice_settings": {
                "stability": 0.42,  # slightly looser for a more natural, energetic delivery
                "similarity_boost": 0.78,
                "style": 0.35,  # adds expressiveness
                "use_speaker_boost": True,
            },
        }
        try:
            resp = req.post(url, json=payload, headers=headers, timeout=45)
            resp.raise_for_status()
            out_path = tmp_dir / f"vo_{i:02d}.mp3"
            out_path.write_bytes(resp.content)
            print(f"           → {len(resp.content) // 1024} KB  saved to {out_path.name}")
            clips.append((float(start_sec), out_path))
        except Exception as exc:
            print(f"  [vo] FAILED segment {i+1}: {exc}")

    return clips


# ---------------------------------------------------------------------------
# Health checks
# ---------------------------------------------------------------------------


def wait_for_url(url: str, label: str, timeout: int = 30) -> bool:
    """Return True once url responds 200, False if timeout expires."""
    print(f"[check] Waiting for {label} at {url} …", end=" ", flush=True)
    for _ in range(timeout):
        try:
            urllib.request.urlopen(url, timeout=2)
            print("✓")
            return True
        except Exception:
            time.sleep(1)
    print("✗ timed out")
    return False


# ---------------------------------------------------------------------------
# Screen recording
# ---------------------------------------------------------------------------


def dismiss_login_modal(page) -> None:
    """Click 'Skip for now' if the login modal is visible."""
    try:
        skip = page.locator("button:has-text('Skip for now')")
        if skip.is_visible(timeout=2000):
            skip.click()
            print("  [setup] Dismissed login modal")
    except Exception:
        pass


def scroll_to_section(page, selector: str) -> None:
    """Scroll element into view if it exists."""
    try:
        el = page.locator(selector).first
        if el.count():
            el.scroll_into_view_if_needed(timeout=2000)
    except Exception:
        pass


def record_frames(page, total_seconds: float, fps: int) -> list[bytes]:
    """Capture frames with captions and watermark burned in."""
    total_frames = int(total_seconds * fps)
    interval = 1.0 / fps
    frames: list[bytes] = []

    # Scene actions keyed by approximate start second
    scene_actions: dict[int, str] = {
        s: action
        for s, action in [
            (0, "top"),
            (9, "run-demo-button"),
            (20, "feed-gallery"),
            (30, "agent-panel"),
            (41, "model-provider"),
            (51, "nl-sql"),
            (60, "top"),
        ]
    }
    last_action = ""

    print(f"[recorder] Capturing {total_frames} frames @ {fps}fps over {total_seconds:.0f}s …")
    for i in range(total_frames):
        t = i * interval

        # Trigger scroll/focus actions at scene boundaries
        current_action = ""
        for start_s, action in sorted(scene_actions.items()):
            if t >= start_s:
                current_action = action
        if current_action != last_action:
            _apply_scene_action(page, current_action)
            last_action = current_action

        raw = page.screenshot(full_page=False)
        caption = caption_for_time(t)
        captioned = burn_caption(raw, caption)
        watermarked = add_dawn_watermark(captioned)
        frames.append(watermarked)

        print(f"  frame {i+1:03d}/{total_frames}  t={t:5.1f}s  '{caption[:45]}'", end="\r")
        time.sleep(interval)

    print()
    return frames


def _apply_scene_action(page, action: str) -> None:
    """Scroll/focus the relevant part of the UI for each scene."""
    try:
        if action == "top":
            page.evaluate("window.scrollTo({top: 0, behavior: 'smooth'})")
        elif action == "run-demo-button":
            # Scroll sidebar into view — the Run Demo button lives there
            el = page.locator("[data-demo-target='dawn-sidebar']").first
            if el.count():
                el.scroll_into_view_if_needed(timeout=1500)
            page.evaluate("window.scrollTo({top: 0, behavior: 'smooth'})")
        elif action == "feed-gallery":
            # Scroll to the feed gallery section
            el = page.locator("text=Feeds").first
            if el.count():
                el.scroll_into_view_if_needed(timeout=1500)
        elif action == "agent-panel":
            el = page.locator("[data-tile-expanded='agent'], [data-demo-target='agent']").first
            if el.count():
                el.scroll_into_view_if_needed(timeout=1500)
        elif action == "model-provider":
            el = page.locator("text=Model Provider").first
            if el.count():
                el.scroll_into_view_if_needed(timeout=1500)
            page.evaluate("window.scrollTo({top: 0, behavior: 'smooth'})")
        elif action == "nl-sql":
            el = page.locator("text=Query, text=SQL, text=Ask").first
            if el.count():
                el.scroll_into_view_if_needed(timeout=1500)
    except Exception:
        pass  # non-fatal — frame will still be captured


# ---------------------------------------------------------------------------
# Video encoding
# ---------------------------------------------------------------------------


def frames_to_silent_mp4(frames: list[bytes], fps: int, out_path: Path) -> Path:
    """Write frames as PNG sequence, encode to silent MP4 via ffmpeg."""
    with tempfile.TemporaryDirectory() as td:
        td_path = Path(td)
        print(f"[encoder] Writing {len(frames)} PNG frames …")
        for idx, frame in enumerate(frames):
            (td_path / f"frame_{idx:05d}.png").write_bytes(frame)

        silent_mp4 = out_path.with_suffix(".silent.mp4")
        result = subprocess.run(
            [
                "ffmpeg",
                "-y",
                "-framerate",
                str(fps),
                "-i",
                str(td_path / "frame_%05d.png"),
                "-vf",
                "scale=1440:-2",  # ensure even dimensions
                "-c:v",
                "libx264",
                "-pix_fmt",
                "yuv420p",
                "-crf",
                "18",  # high quality
                "-preset",
                "slow",
                str(silent_mp4),
            ],
            capture_output=True,
        )
        if result.returncode != 0:
            print("[encoder] ffmpeg stderr:", result.stderr.decode()[-800:])
            result.check_returncode()

    return silent_mp4


def mix_audio(silent_mp4: Path, vo_clips: list[tuple[float, Path]], out_path: Path) -> None:
    """Mix voice-over clips at their start offsets and mux with video."""
    if not vo_clips:
        print("[encoder] No voice-over — keeping silent video.")
        silent_mp4.rename(out_path)
        return

    inputs: list[str] = ["-i", str(silent_mp4)]
    filter_parts: list[str] = []

    for idx, (start_sec, clip_path) in enumerate(vo_clips):
        inputs += ["-i", str(clip_path)]
        delay_ms = int(start_sec * 1000)
        filter_parts.append(f"[{idx + 1}:a]adelay={delay_ms}|{delay_ms}[a{idx}]")

    mix_inputs = "".join(f"[a{i}]" for i in range(len(vo_clips)))
    filter_parts.append(f"{mix_inputs}amix=inputs={len(vo_clips)}:normalize=0[aout]")

    result = subprocess.run(
        [
            "ffmpeg",
            "-y",
            *inputs,
            "-filter_complex",
            ";".join(filter_parts),
            "-map",
            "0:v",
            "-map",
            "[aout]",
            "-c:v",
            "copy",
            "-c:a",
            "aac",
            "-b:a",
            "192k",
            "-shortest",
            str(out_path),
        ],
        capture_output=True,
    )
    if result.returncode != 0:
        print("[encoder] audio mix ffmpeg stderr:", result.stderr.decode()[-800:])
        result.check_returncode()

    silent_mp4.unlink(missing_ok=True)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main() -> None:
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print("Missing dependency: pip install playwright && playwright install chromium")
        sys.exit(1)

    out_path = OUTPUT_MP4
    out_path.parent.mkdir(parents=True, exist_ok=True)

    print("=" * 60)
    print("  DAWN Demo Recorder")
    print(f"  Voice: Eric (ElevenLabs)  |  {RECORD_SECONDS}s @ {FPS}fps")
    print(f"  Output: {out_path}")
    print("=" * 60)

    # Check stack is up
    backend_up = wait_for_url(BACKEND_URL, "Backend API", timeout=10)
    frontend_up = wait_for_url(FRONTEND_URL, "Frontend", timeout=15)

    if not frontend_up:
        print("\n⚠  Frontend not reachable at http://localhost:3000")
        print("   Start it with:  cd web && npm run dev")
        print("   Then re-run this script.\n")
        sys.exit(1)

    if not backend_up:
        print("\n⚠  Backend not reachable — some panels will show empty state.")
        print("   Start it with:  uvicorn app.api.server:app --port 8000\n")

    with tempfile.TemporaryDirectory() as td:
        tmp_dir = Path(td)

        # 1. Generate voice-over first (takes ~20s, non-blocking for the browser)
        print("\n[vo] Generating voice-over with Eric (ElevenLabs) …")
        vo_clips = generate_vo(tmp_dir)
        print(f"[vo] {len(vo_clips)}/{len(NARRATION)} segments generated.\n")

        # 2. Record the live app with Playwright
        with sync_playwright() as p:
            print("[recorder] Launching browser …")
            browser = p.chromium.launch(
                headless=True,
                args=[
                    "--disable-web-security",
                    "--force-device-scale-factor=1",
                ],
            )
            ctx = browser.new_context(
                viewport=VIEWPORT,
                device_scale_factor=1,
                color_scheme="dark",
            )
            page = ctx.new_page()

            print(f"[recorder] Opening {FRONTEND_URL} …")
            page.goto(FRONTEND_URL, wait_until="networkidle", timeout=30000)
            time.sleep(2)

            # Dismiss login modal if present
            dismiss_login_modal(page)
            time.sleep(1)

            # Record frames
            frames = record_frames(page, RECORD_SECONDS, FPS)
            browser.close()

        # 3. Encode
        print("\n[encoder] Encoding video …")
        silent_mp4 = frames_to_silent_mp4(frames, FPS, out_path)

        # 4. Mix audio
        print("[encoder] Mixing voice-over …")
        mix_audio(silent_mp4, vo_clips, out_path)

    size_mb = out_path.stat().st_size / 1_000_000
    print(f"\n{'=' * 60}")
    print(f"  ✓  Done!  {out_path}")
    print(f"     Size:  {size_mb:.1f} MB")
    print(f"     Duration: ~{RECORD_SECONDS}s")
    print(f"{'=' * 60}\n")


if __name__ == "__main__":
    main()
