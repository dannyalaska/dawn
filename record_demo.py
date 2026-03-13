"""
DAWN demo recorder — narrated + captioned MP4.

Seeds demo data via the live backend API, then records the populated DAWN
dashboard using headless Playwright. No zoom effects — just the real UI
scrolling through each feature area with ElevenLabs voice-over.

Demo data: docs/DAWN_Demo_Workbook.xlsx
  • "Ticketing Data"  — 150 rows × 6 cols
  • "Sales Revenue"   — 150 rows × 5 cols

Usage:
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

import requests as _req
from dotenv import dotenv_values

# ---------------------------------------------------------------------------
# Credentials
# ---------------------------------------------------------------------------
_ENV_CANDIDATES = [
    Path.home() / "Desktop" / "Shared with RD backup" / "SleepHypnoAI" / ".env",
    Path(__file__).parent.parent / "Shared with RD backup" / "SleepHypnoAI" / ".env",
    Path(__file__).parent / ".env",
]
_ENV_FILE = next((p for p in _ENV_CANDIDATES if p.exists()), _ENV_CANDIDATES[-1])
_dotenv = dotenv_values(_ENV_FILE) if _ENV_FILE.exists() else {}

ELEVENLABS_API_KEY = _dotenv.get("ELEVENLABS_API_KEY") or os.getenv("ELEVENLABS_API_KEY", "")
ELEVENLABS_VOICE_ID = "0IdiDzv8s1u4MJX5rxvj"
ELEVENLABS_MODEL = _dotenv.get("ELEVENLABS_MODEL_ID") or os.getenv(
    "ELEVENLABS_MODEL_ID", "eleven_multilingual_v2"
)

# ---------------------------------------------------------------------------
# Recording config
# ---------------------------------------------------------------------------
FRONTEND_URL = "http://localhost:3000"
BACKEND_URL = "http://localhost:8000"
FPS = 3
OUTPUT_MP4 = Path(__file__).parent / "docs" / "demo_recording.mp4"
VIEWPORT = {"width": 1440, "height": 900}

# ---------------------------------------------------------------------------
# Narration script: (start_second, caption_text, spoken_text)
# ---------------------------------------------------------------------------
NARRATION = [
    (
        0,
        "Dawn — AI-powered data intelligence for ops teams",
        "This is Dawn. Drop in any spreadsheet and your ops team goes from raw data "
        "to structured insight — without a single line of code or an engineer in the loop.",
    ),
    (
        10,
        "Drop in a spreadsheet — Dawn profiles it instantly",
        "Drag your file in. Dawn previews the schema, detects column types, "
        "and shows you sample rows before anything is committed.",
    ),
    (
        22,
        "One click — data is ingested and context is live",
        "Hit Send to Dawn. The workbook is indexed, every column profiled, "
        "and your dataset is immediately available as a live context for querying and analysis.",
    ),
    (
        34,
        "Automatic metrics and tags — no config needed",
        "Dawn auto-generates key metrics and infers semantic tags — "
        "financial, temporal, geospatial — straight from your column names and values.",
    ),
    (
        44,
        "Seven agents analyse your data automatically",
        "The agent swarm kicks off without prompting. A planner, executor, memory agent, "
        "anomaly detector, drift checker, QA agent, and reporter — all running in parallel.",
    ),
    (
        55,
        "Ask in plain English — Dawn writes and runs the SQL",
        "Ask anything in plain English. Dawn translates it to SQL, "
        "runs it read-only against your data, and returns live results. Securely, in seconds.",
    ),
    (
        65,
        "Dawn — raw data to insight in seconds",
        "Dawn. From raw spreadsheet to boardroom-ready insight in seconds. "
        "Private, fast, and built for the ops teams who can't wait.",
    ),
]


# ---------------------------------------------------------------------------
# PIL caption helpers
# ---------------------------------------------------------------------------


def _pil():
    from PIL import Image, ImageDraw, ImageFont

    return Image, ImageDraw, ImageFont


def load_font(size: int):
    _, _, ImageFont = _pil()
    for candidate in [
        "/System/Library/Fonts/Helvetica.ttc",
        "/System/Library/Fonts/SF-Pro-Display-Semibold.otf",
        "/System/Library/Fonts/SFNSDisplay.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    ]:
        if Path(candidate).exists():
            try:
                return ImageFont.truetype(candidate, size)
            except Exception:
                pass
    return ImageFont.load_default()


def caption_for_time(t: float) -> str:
    active = ""
    for start, caption, _ in NARRATION:
        if t >= start:
            active = caption
    return active


def burn_caption(frame_bytes: bytes, caption: str) -> bytes:
    Image, ImageDraw, _ = _pil()
    img = Image.open(io.BytesIO(frame_bytes)).convert("RGB")
    if not caption:
        out = io.BytesIO()
        img.save(out, format="PNG")
        return out.getvalue()

    draw = ImageDraw.Draw(img)
    w, h = img.size
    font = load_font(max(22, w // 52))
    bbox = draw.textbbox((0, 0), caption, font=font)
    text_w = bbox[2] - bbox[0]
    text_h = bbox[3] - bbox[1]
    bar_y = h - text_h - 52

    overlay = Image.new("RGBA", img.size, (0, 0, 0, 0))
    odraw = ImageDraw.Draw(overlay)
    odraw.rectangle([(0, bar_y - 14), (w, h)], fill=(8, 10, 20, 215))
    odraw.rectangle([(0, bar_y - 14), (w, bar_y - 10)], fill=(6, 182, 212, 255))

    img = Image.alpha_composite(img.convert("RGBA"), overlay).convert("RGB")
    draw = ImageDraw.Draw(img)
    x = (w - text_w) // 2
    y = bar_y + 4
    draw.text((x + 2, y + 2), caption, font=font, fill=(0, 0, 0, 160))
    draw.text((x, y), caption, font=font, fill=(255, 255, 255))

    out = io.BytesIO()
    img.save(out, format="PNG")
    return out.getvalue()


def add_dawn_watermark(frame_bytes: bytes) -> bytes:
    Image, ImageDraw, _ = _pil()
    img = Image.open(io.BytesIO(frame_bytes)).convert("RGB")
    draw = ImageDraw.Draw(img)
    w, _ = img.size
    font = load_font(max(16, w // 72))
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
        print(f'  [vo] Segment {i + 1}/{len(NARRATION)}: "{preview}"')
        payload = {
            "text": spoken,
            "model_id": ELEVENLABS_MODEL,
            "voice_settings": {
                "stability": 0.40,
                "similarity_boost": 0.80,
                "style": 0.30,
                "use_speaker_boost": True,
            },
        }
        try:
            resp = _req.post(url, json=payload, headers=headers, timeout=45)
            resp.raise_for_status()
            out_path = tmp_dir / f"vo_{i:02d}.mp3"
            out_path.write_bytes(resp.content)
            print(f"           → {len(resp.content) // 1024} KB")
            clips.append((float(start_sec), out_path))
        except Exception as exc:
            print(f"  [vo] FAILED segment {i + 1}: {exc}")

    return clips


# ---------------------------------------------------------------------------
# Health checks & pre-staging
# ---------------------------------------------------------------------------


def wait_for_url(url: str, label: str, timeout: int = 30) -> bool:
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


DEMO_WORKBOOK = Path(__file__).parent / "docs" / "DAWN_Demo_Workbook.xlsx"


# ---------------------------------------------------------------------------
# Recorder — plain screenshot accumulator, no zoom
# ---------------------------------------------------------------------------


class Recorder:
    def __init__(self, page, fps: int = FPS):
        self.page = page
        self.fps = fps
        self.interval = 1.0 / fps
        self.frames: list[bytes] = []
        self._t = 0.0

    @property
    def t(self) -> float:
        return self._t

    def snap(self, n: int = 1) -> None:
        raw = self.page.screenshot(full_page=False)
        caption = caption_for_time(self._t)
        frame = add_dawn_watermark(burn_caption(raw, caption))
        for _ in range(n):
            self.frames.append(frame)
            self._t += self.interval
            time.sleep(self.interval)

    def wait_and_snap(self, seconds: float) -> None:
        """Hold current view for `seconds`, capturing at FPS."""
        end = self._t + seconds
        while self._t < end:
            self.snap(1)

    def scroll_to(self, y: int, smooth: bool = True) -> None:
        behavior = "smooth" if smooth else "auto"
        self.page.evaluate(f"window.scrollTo({{top: {y}, behavior: '{behavior}'}})")
        time.sleep(0.4)

    def try_click(self, selector: str, timeout: int = 2000) -> bool:
        try:
            el = self.page.locator(selector).first
            if el.is_visible(timeout=timeout):
                el.scroll_into_view_if_needed(timeout=timeout)
                time.sleep(0.15)
                el.click()
                return True
        except Exception:
            pass
        return False

    def try_scroll_into_view(self, selector: str, timeout: int = 2000) -> bool:
        try:
            el = self.page.locator(selector).first
            if el.count():
                el.scroll_into_view_if_needed(timeout=timeout)
                time.sleep(0.3)
                return True
        except Exception:
            pass
        return False


# ---------------------------------------------------------------------------
# Choreography — straight shots, no zoom
# ---------------------------------------------------------------------------


def _expand_tile(page, tile_id: str) -> bool:
    """Click the expand button on a DAWN tile by its data-demo-target."""
    try:
        tile = page.locator(f"[data-demo-target='{tile_id}']").first
        if not tile.count():
            return False
        tile.scroll_into_view_if_needed(timeout=2000)
        time.sleep(0.2)
        btn = tile.locator("button").first
        if btn.is_visible(timeout=1000):
            btn.click()
            return True
        tile.click()
        return True
    except Exception:
        return False


def _wait_for_text(page, text: str, timeout: int = 15) -> bool:
    """Poll until `text` appears anywhere on the page."""
    for _ in range(timeout):
        try:
            if page.locator(f"text={text}").count() > 0:
                return True
        except Exception:
            pass
        time.sleep(1)
    return False


def record_choreography(page) -> list[bytes]:
    r = Recorder(page, fps=FPS)

    # -----------------------------------------------------------------------
    # SCENE 1 (0–10s) — Dashboard wide shot
    # -----------------------------------------------------------------------
    print("  [scene 1] Dashboard overview …")
    r.scroll_to(0)
    time.sleep(1.0)
    r.wait_and_snap(10)

    # -----------------------------------------------------------------------
    # SCENE 2 (10–22s) — Expand Upload tile, drop in the workbook, click Preview
    # -----------------------------------------------------------------------
    print("  [scene 2] Upload tile — file drop + Preview …")
    _expand_tile(page, "upload")
    time.sleep(1.0)
    r.try_scroll_into_view("[data-demo-target='upload']", timeout=2000)
    r.wait_and_snap(2)  # show the upload zone clearly

    # Set the file on the hidden input — real file ingestion, no shortcuts
    file_input = page.locator("input[type='file']").first
    file_input.set_input_files(str(DEMO_WORKBOOK))
    time.sleep(1.0)
    r.wait_and_snap(2)  # show filename / "Ready to preview" status

    # Click Preview
    r.try_click("button:has-text('Preview')", timeout=3000)
    print("    → clicked Preview")
    time.sleep(0.5)
    r.wait_and_snap(4)  # show preview loading → sample rows appear

    # -----------------------------------------------------------------------
    # SCENE 3 (22–34s) — Click "Send to Dawn", watch ingestion + status
    # -----------------------------------------------------------------------
    print("  [scene 3] Send to Dawn — ingestion …")
    r.try_click("button:has-text('Send to Dawn')", timeout=5000)
    print("    → clicked Send to Dawn")
    time.sleep(0.5)
    r.wait_and_snap(3)  # "Sending…" spinner visible

    # Wait for "✓ Indexed" confirmation (real backend call)
    print("    → waiting for index confirmation …", end=" ", flush=True)
    confirmed = _wait_for_text(page, "Indexed", timeout=20)
    print("✓" if confirmed else "timed out")
    r.wait_and_snap(4)  # show "✓ Indexed" status message

    # -----------------------------------------------------------------------
    # SCENE 4 (34–44s) — Insight tile auto-populated with metrics + tags
    # -----------------------------------------------------------------------
    print("  [scene 4] Insight tile …")
    _expand_tile(page, "insight")
    time.sleep(1.0)
    r.try_scroll_into_view("[data-demo-target='insight']", timeout=2000)
    r.wait_and_snap(10)

    # -----------------------------------------------------------------------
    # SCENE 5 (44–55s) — Agent swarm tile running analysis
    # -----------------------------------------------------------------------
    print("  [scene 5] Agent swarm …")
    r.scroll_to(0)
    _expand_tile(page, "agent")
    time.sleep(1.0)
    r.try_scroll_into_view("[data-demo-target='agent']", timeout=2000)
    # Click Run if available — agent needs an active feed/source
    r.try_click("[data-demo-target='agent'] button:has-text('Run')", timeout=2000)
    time.sleep(0.5)
    r.wait_and_snap(10)

    # -----------------------------------------------------------------------
    # SCENE 6 (55–65s) — Context Chat — NL to SQL
    # -----------------------------------------------------------------------
    print("  [scene 6] Context Chat / NL-to-SQL …")
    r.scroll_to(0)
    _expand_tile(page, "contextChat")
    time.sleep(1.0)
    r.try_scroll_into_view("[data-demo-target='contextChat']", timeout=2000)
    r.wait_and_snap(3)

    # Type a sample question to show the NL-to-SQL flow
    question = "What are the top 5 ticket categories by volume?"
    try:
        ta = page.locator("[data-demo-target='contextChat'] textarea").first
        if not ta.count():
            ta = page.locator("textarea").first
        if ta.is_visible(timeout=2000):
            ta.click()
            ta.type(question, delay=40)
            r.wait_and_snap(2)  # show question typed in
            # Submit
            page.keyboard.press("Enter")
            time.sleep(0.5)
            r.wait_and_snap(4)  # show response / SQL loading
    except Exception as exc:
        print(f"    → chat input error: {exc}")
        r.wait_and_snap(7)

    # -----------------------------------------------------------------------
    # SCENE 7 (65–73s) — Outro wide shot
    # -----------------------------------------------------------------------
    print("  [scene 7] Outro …")
    r.scroll_to(0, smooth=True)
    time.sleep(0.5)
    r.wait_and_snap(8)

    print(f"  [done] {len(r.frames)} frames ({r.t:.1f}s @ {FPS}fps)")
    return r.frames


# ---------------------------------------------------------------------------
# Video encoding
# ---------------------------------------------------------------------------


def frames_to_silent_mp4(frames: list[bytes], fps: int, out_path: Path) -> Path:
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
                "scale=1440:-2",
                "-c:v",
                "libx264",
                "-pix_fmt",
                "yuv420p",
                "-crf",
                "18",
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

    print("=" * 64)
    print("  DAWN Demo Recorder — real upload workflow")
    print("  File: DAWN_Demo_Workbook.xlsx")
    print("  Flow: upload → preview → ingest → insights → agents → NL-SQL")
    print(f"  Output: {out_path}")
    print("=" * 64)

    backend_up = wait_for_url(f"{BACKEND_URL}/health", "Backend API", timeout=10)
    frontend_up = wait_for_url(FRONTEND_URL, "Frontend", timeout=15)

    if not frontend_up:
        print("\n⚠  Frontend not reachable at http://localhost:3000")
        print("   Start with:  cd web && npm run dev\n")
        sys.exit(1)

    if not backend_up:
        print("\n⚠  Backend not reachable — ingestion will fail.\n")

    if not DEMO_WORKBOOK.exists():
        print(f"\n⚠  Demo workbook not found: {DEMO_WORKBOOK}\n")
        sys.exit(1)

    print(
        f"[setup] Demo workbook: {DEMO_WORKBOOK.name} ({DEMO_WORKBOOK.stat().st_size // 1024} KB)"
    )

    with tempfile.TemporaryDirectory() as td:
        tmp_dir = Path(td)

        print("\n[vo] Generating voice-over …")
        vo_clips = generate_vo(tmp_dir)
        print(f"[vo] {len(vo_clips)}/{len(NARRATION)} segments ready.\n")

        with sync_playwright() as p:
            print("[recorder] Launching headless Chromium …")
            browser = p.chromium.launch(
                headless=True,
                args=["--force-device-scale-factor=1", "--no-sandbox"],
            )
            ctx = browser.new_context(
                viewport=VIEWPORT,
                device_scale_factor=1,
                color_scheme="dark",
            )
            page = ctx.new_page()

            print(f"[recorder] Opening {FRONTEND_URL} …")
            page.goto(FRONTEND_URL, wait_until="networkidle", timeout=30000)
            # Dismiss login modal via localStorage
            page.evaluate("() => { localStorage.setItem('dawn.auth.dismissed', '1'); }")
            page.reload(wait_until="networkidle", timeout=20000)
            time.sleep(2)

            # Close modal if still visible
            for sel in ["button:has-text('Skip for now')", "button[aria-label='Close']"]:
                try:
                    el = page.locator(sel).first
                    if el.is_visible(timeout=800):
                        el.click()
                        time.sleep(0.5)
                        break
                except Exception:
                    pass

            # Debug: capture state before recording
            dbg_pre = out_path.parent / "debug_before_record.png"
            page.screenshot(path=str(dbg_pre), full_page=False)
            print(f"[recorder] Pre-record screenshot → {dbg_pre}")

            print("[recorder] Starting choreography …")
            frames = record_choreography(page)
            browser.close()

        secs = len(frames) / FPS
        print(f"\n[encoder] {len(frames)} frames ({secs:.0f}s) …")
        silent_mp4 = frames_to_silent_mp4(frames, FPS, out_path)
        print("[encoder] Mixing audio …")
        mix_audio(silent_mp4, vo_clips, out_path)

    size_mb = out_path.stat().st_size / 1_000_000
    print(f"\n{'=' * 64}")
    print(f"  ✅  {out_path}")
    print(f"     {len(frames)} frames · {secs:.0f}s · {size_mb:.1f} MB")
    print(f"{'=' * 64}\n")


if __name__ == "__main__":
    main()
