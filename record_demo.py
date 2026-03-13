"""
DAWN demo recorder — narrated + captioned MP4 with zoom-in feature highlights.

Generates ElevenLabs voice-over (voice: Eric — smooth tenor), seeds demo data
via the live backend API, then records the populated DAWN dashboard using
headless Playwright. Key features are highlighted with animated zoom-in crops
via PIL for a polished, dynamic look.

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
FPS = 3  # 3fps — smooth enough, keeps file size down
OUTPUT_MP4 = Path(__file__).parent / "docs" / "demo_recording.mp4"
VIEWPORT = {"width": 1440, "height": 900}
W, H = VIEWPORT["width"], VIEWPORT["height"]

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
        22,
        "Data quality checks run on every ingest",
        "Every feed gets automatic data quality checks. Green means your data is clean. "
        "Red means Dawn already found something worth investigating before you even asked.",
    ),
    (
        33,
        "Seven agents — planner, executor, memory, QA, and more",
        "Dawn's agent swarm generates an action plan, executes analytical tasks, spots "
        "anomalies, checks for drift, and writes a structured report — all without a single query.",
    ),
    (
        44,
        "Runs on any LLM — local or cloud",
        "Dawn runs on whatever LLM you choose. Fully local with Ollama or LM Studio for "
        "air-gapped deployments, or cloud-powered with OpenAI or Claude. One toggle.",
    ),
    (
        54,
        "Ask in plain English — Dawn writes and runs the SQL",
        "Teams can ask questions in plain English. Dawn translates them to SQL, runs them "
        "read-only against your connected databases, and returns live results. Securely.",
    ),
    (
        63,
        "Dawn — from raw data to insight in seconds",
        "Dawn. From raw data to boardroom-ready insight in seconds. "
        "Private, fast, and built for the ops teams who can't wait.",
    ),
]


# ---------------------------------------------------------------------------
# PIL image helpers
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
    font_sz = max(22, w // 52)
    font = load_font(font_sz)

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


def _smoothstep(t: float) -> float:
    t = max(0.0, min(1.0, t))
    return t * t * (3 - 2 * t)


def zoom_sequence(
    frame_bytes: bytes,
    target_box: tuple[int, int, int, int],
    n_frames: int = 6,
    reverse: bool = False,
) -> list[bytes]:
    """
    Animate zoom from full viewport to target_box (or reversed if reverse=True).
    Returns list of n_frames PNG bytes.
    """
    Image, _, _ = _pil()
    x1t, y1t, x2t, y2t = target_box
    img = Image.open(io.BytesIO(frame_bytes)).convert("RGB")

    result_frames: list[bytes] = []
    for i in range(n_frames):
        raw_t = i / max(n_frames - 1, 1)
        t = _smoothstep(raw_t if not reverse else 1.0 - raw_t)

        cx1 = int(t * x1t)
        cy1 = int(t * y1t)
        cx2 = int(W + t * (x2t - W))
        cy2 = int(H + t * (y2t - H))

        if cx2 - cx1 < 10:
            cx2 = cx1 + 10
        if cy2 - cy1 < 10:
            cy2 = cy1 + 10

        cropped = img.crop((cx1, cy1, cx2, cy2))
        zoomed = cropped.resize((W, H), Image.LANCZOS)
        out = io.BytesIO()
        zoomed.save(out, format="PNG")
        result_frames.append(out.getvalue())

    return result_frames


def static_zoom(frame_bytes: bytes, box: tuple[int, int, int, int]) -> bytes:
    """Return a single frame cropped to box and scaled back to viewport size."""
    Image, _, _ = _pil()
    img = Image.open(io.BytesIO(frame_bytes)).convert("RGB")
    cropped = img.crop(box)
    zoomed = cropped.resize((W, H), Image.LANCZOS)
    out = io.BytesIO()
    zoomed.save(out, format="PNG")
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
        print(f'  [vo] Segment {i+1}/{len(NARRATION)}: "{preview}"')
        payload = {
            "text": spoken,
            "model_id": ELEVENLABS_MODEL,
            "voice_settings": {
                "stability": 0.42,
                "similarity_boost": 0.78,
                "style": 0.35,
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
            print(f"  [vo] FAILED segment {i+1}: {exc}")

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


def seed_demo_via_api() -> bool:
    print("[setup] Seeding demo workspace via API …", end=" ", flush=True)
    try:
        resp = _req.post(f"{BACKEND_URL}/demo/seed", timeout=60)
        if resp.status_code in (200, 201):
            data = resp.json()
            feeds = data.get("feeds", [])
            print(f"✓  ({len(feeds)} feeds)")
            for f in feeds:
                print(
                    f"    • {f.get('identifier')} — {f.get('status')} ({f.get('rows', '?')} rows)"
                )
            return True
        print(f"✗ HTTP {resp.status_code}: {resp.text[:200]}")
        return False
    except Exception as exc:
        print(f"✗ {exc}")
        return False


# ---------------------------------------------------------------------------
# Recorder — frame accumulator with animated zoom support
# ---------------------------------------------------------------------------


class Recorder:
    """Headless Playwright recorder with PIL-based animated zoom highlights."""

    def __init__(self, page, fps: int = FPS):
        self.page = page
        self.fps = fps
        self.interval = 1.0 / fps
        self.frames: list[bytes] = []
        self._t = 0.0

    @property
    def t(self) -> float:
        return self._t

    # ------------------------------------------------------------------
    # Core capture
    # ------------------------------------------------------------------

    def _add_frame(self, raw: bytes) -> None:
        caption = caption_for_time(self._t)
        self.frames.append(add_dawn_watermark(burn_caption(raw, caption)))
        self._t += self.interval

    def snap(self, n: int = 1) -> bytes:
        """Capture n frames of the current viewport. Returns raw PNG of last shot."""
        raw = self.page.screenshot(full_page=False)
        for _ in range(n):
            self._add_frame(raw)
            time.sleep(self.interval)
        return raw

    def wait_and_snap(self, seconds: float) -> bytes:
        return self.snap(max(1, round(seconds * self.fps)))

    # ------------------------------------------------------------------
    # Navigation
    # ------------------------------------------------------------------

    def scroll_to(self, y: int = 0, smooth: bool = True) -> None:
        behavior = "smooth" if smooth else "auto"
        self.page.evaluate(f"window.scrollTo({{top: {y}, behavior: '{behavior}'}})")
        time.sleep(0.35)

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

    # ------------------------------------------------------------------
    # Element bounding box
    # ------------------------------------------------------------------

    def element_box(
        self,
        selector: str,
        padding: int = 80,
        min_w_frac: float = 0.35,
        min_h_frac: float = 0.30,
    ) -> tuple[int, int, int, int] | None:
        """Viewport-clamped box around an element, expanded to minimum fractions."""
        try:
            el = self.page.locator(selector).first
            b = el.bounding_box()
            if not b:
                return None
            x1 = max(0, int(b["x"]) - padding)
            y1 = max(0, int(b["y"]) - padding)
            x2 = min(W, int(b["x"] + b["width"]) + padding)
            y2 = min(H, int(b["y"] + b["height"]) + padding)
            min_bw = int(W * min_w_frac)
            min_bh = int(H * min_h_frac)
            while (x2 - x1) < min_bw:
                x1 = max(0, x1 - 30)
                x2 = min(W, x2 + 30)
            while (y2 - y1) < min_bh:
                y1 = max(0, y1 - 30)
                y2 = min(H, y2 + 30)
            return (x1, y1, x2, y2)
        except Exception:
            return None

    # ------------------------------------------------------------------
    # Zoom shots
    # ------------------------------------------------------------------

    def zoom_in_to(
        self,
        box: tuple[int, int, int, int],
        hold_seconds: float = 3.0,
        n_zoom_frames: int = 5,
    ) -> bytes:
        """
        Snapshot current state, animate zoom into box, hold at full zoom.
        Returns the raw screenshot taken before zoom (for zoom-out later).
        """
        raw = self.page.screenshot(full_page=False)

        for fr in zoom_sequence(raw, box, n_frames=n_zoom_frames):
            self._add_frame(fr)
            time.sleep(self.interval)

        hold_frame = static_zoom(raw, box)
        for _ in range(max(1, round(hold_seconds * self.fps))):
            self._add_frame(hold_frame)
            time.sleep(self.interval)

        return raw

    def zoom_out_from(
        self,
        raw_before_zoom: bytes,
        box: tuple[int, int, int, int],
        n_zoom_frames: int = 5,
    ) -> None:
        """Animate zoom out from box back to full viewport."""
        for fr in zoom_sequence(raw_before_zoom, box, n_frames=n_zoom_frames, reverse=True):
            self._add_frame(fr)
            time.sleep(self.interval)

    def snap_current_zoomed(
        self,
        box: tuple[int, int, int, int],
        hold_seconds: float = 3.0,
        n_zoom_frames: int = 5,
    ) -> bytes:
        """
        Take a fresh screenshot, zoom in to box on that shot, hold.
        Use this when content has changed (e.g., after clicking Run Demo).
        """
        raw = self.page.screenshot(full_page=False)
        for fr in zoom_sequence(raw, box, n_frames=n_zoom_frames):
            self._add_frame(fr)
            time.sleep(self.interval)
        hold_frame = static_zoom(raw, box)
        for _ in range(max(1, round(hold_seconds * self.fps))):
            self._add_frame(hold_frame)
            time.sleep(self.interval)
        return raw


# ---------------------------------------------------------------------------
# Choreography
# ---------------------------------------------------------------------------


def _click_tile(page, tile_id: str) -> bool:
    """Click the expand button on a DAWN tile by its data-demo-target id."""
    try:
        tile = page.locator(f"[data-demo-target='{tile_id}']").first
        if tile.count() == 0:
            return False
        tile.scroll_into_view_if_needed(timeout=2000)
        time.sleep(0.2)
        # Try the expand/collapse button inside the tile header
        btn = tile.locator("button").first
        if btn.is_visible(timeout=1000):
            btn.click()
            return True
        tile.click()
        return True
    except Exception:
        return False


def record_choreography(page) -> list[bytes]:
    r = Recorder(page, fps=FPS)

    # -----------------------------------------------------------------------
    # SCENE 1 (0–9s) — Establishing wide shot of the dashboard
    # -----------------------------------------------------------------------
    print("  [scene 1] Establishing wide shot …")
    r.scroll_to(0)
    time.sleep(1.0)
    r.wait_and_snap(9)

    # -----------------------------------------------------------------------
    # SCENE 2 (9–22s) — Zoom to Run Demo button → click → watch seeding feedback
    # -----------------------------------------------------------------------
    print("  [scene 2] Zoom → Run Demo …")
    r.scroll_to(0)
    time.sleep(0.3)

    btn_box = r.element_box(
        "button:has-text('Run Demo')",
        padding=60,
        min_w_frac=0.22,
        min_h_frac=0.16,
    )

    if btn_box:
        r.zoom_in_to(btn_box, hold_seconds=1.2, n_zoom_frames=6)
        clicked = r.try_click("button:has-text('Run Demo')", timeout=3000)
        print(f"    → clicked Run Demo: {clicked}")
        time.sleep(0.8)
        # Fresh shot showing "Seeding workspace…" feedback, still zoomed
        r.snap_current_zoomed(btn_box, hold_seconds=5.5, n_zoom_frames=3)
        raw_after = r.page.screenshot(full_page=False)
        r.zoom_out_from(raw_after, btn_box, n_zoom_frames=5)
    else:
        print("    → button box not found, fallback")
        r.try_click("button:has-text('Run Demo')", timeout=3000)
        r.wait_and_snap(13)

    # -----------------------------------------------------------------------
    # SCENE 3 (22–33s) — Feed gallery cards + DQ badges
    #   The feedGallery tile must be expanded first.
    # -----------------------------------------------------------------------
    print("  [scene 3] Zoom → feed gallery …")
    time.sleep(0.5)

    # Expand the feedGallery tile so FeedGallery component renders
    tile_opened = _click_tile(page, "feedGallery")
    print(f"    → feedGallery tile clicked: {tile_opened}")
    time.sleep(2.5)  # wait for SWR fetch + render

    # Debug: save screenshot to verify feed gallery content
    dbg = OUTPUT_MP4.parent / "debug_feed_gallery.png"
    page.screenshot(path=str(dbg), full_page=False)
    print(f"    → debug screenshot: {dbg}")

    # Find a feed card inside the gallery
    feed_sel = None
    for sel in ["text=Demo – Ticketing", "text=demo_tickets", "text=demo_sales"]:
        try:
            if page.locator(sel).is_visible(timeout=2000):
                feed_sel = sel
                break
        except Exception:
            pass

    if feed_sel:
        r.try_scroll_into_view(feed_sel, timeout=3000)
        time.sleep(0.4)
        feed_box = r.element_box(feed_sel, padding=140, min_w_frac=0.50, min_h_frac=0.45)
    else:
        # Fall back to the whole feedGallery tile area
        feed_box = r.element_box(
            "[data-demo-target='feedGallery']", padding=20, min_w_frac=0.55, min_h_frac=0.50
        )

    if feed_box:
        r.zoom_in_to(feed_box, hold_seconds=6.5, n_zoom_frames=6)
    else:
        r.try_scroll_into_view("[data-demo-target='feedGallery']", timeout=2000)
        r.wait_and_snap(11)

    # -----------------------------------------------------------------------
    # SCENE 4 (33–44s) — Action plan / agent insights tile
    # -----------------------------------------------------------------------
    print("  [scene 4] Zoom → action plan / agent insights …")
    r.scroll_to(0)
    time.sleep(0.3)

    # Expand actionPlan tile
    _click_tile(page, "actionPlan")
    time.sleep(1.2)

    agent_sel = None
    for sel in [
        "[data-demo-target='actionPlan']",
        "text=Action plan",
        "text=Action Plan",
        "text=Agent Analysis",
        "text=Insight",
    ]:
        try:
            if page.locator(sel).count() > 0:
                agent_sel = sel
                break
        except Exception:
            pass

    if agent_sel:
        r.try_scroll_into_view(agent_sel, timeout=2000)
        time.sleep(0.5)
        agent_box = r.element_box(agent_sel, padding=80, min_w_frac=0.50, min_h_frac=0.42)
    else:
        agent_box = None

    if agent_box:
        r.zoom_in_to(agent_box, hold_seconds=6.0, n_zoom_frames=6)
    else:
        r.scroll_to(400)
        r.wait_and_snap(11)

    # -----------------------------------------------------------------------
    # SCENE 5 (44–54s) — Model Provider in sidebar
    # -----------------------------------------------------------------------
    print("  [scene 5] Zoom → Model Provider …")
    r.scroll_to(0)
    r.try_scroll_into_view("text=Model Provider", timeout=2000)
    time.sleep(0.4)

    mp_box = r.element_box("text=Model Provider", padding=80, min_w_frac=0.22, min_h_frac=0.28)
    if mp_box:
        r.zoom_in_to(mp_box, hold_seconds=5.5, n_zoom_frames=6)
    else:
        r.wait_and_snap(10)

    # -----------------------------------------------------------------------
    # SCENE 6 (54–63s) — Context Chat tile (NL-to-SQL / plain English queries)
    # -----------------------------------------------------------------------
    print("  [scene 6] Zoom → context chat / NL-SQL …")
    r.scroll_to(0)

    # Expand contextChat tile
    _click_tile(page, "contextChat")
    time.sleep(1.2)

    nl_sel = None
    for sel in [
        "[data-demo-target='contextChat']",
        "text=Context chat",
        "text=Ask a question",
        "textarea",
        "text=Query",
        "text=SQL",
    ]:
        try:
            if page.locator(sel).count() > 0:
                nl_sel = sel
                break
        except Exception:
            pass

    if nl_sel:
        r.try_scroll_into_view(nl_sel, timeout=2000)
        time.sleep(0.4)
        nl_box = r.element_box(nl_sel, padding=100, min_w_frac=0.50, min_h_frac=0.40)
    else:
        nl_box = None

    if nl_box:
        r.zoom_in_to(nl_box, hold_seconds=5.0, n_zoom_frames=6)
    else:
        r.scroll_to(600)
        r.wait_and_snap(9)

    # -----------------------------------------------------------------------
    # SCENE 7 (63–70s) — Zoom out to full dashboard, outro
    # -----------------------------------------------------------------------
    print("  [scene 7] Outro — wide shot …")
    r.scroll_to(0, smooth=True)
    time.sleep(0.6)
    r.wait_and_snap(7)

    print(f"  [done] {len(r.frames)} frames captured ({r.t:.1f}s @ {FPS}fps)")
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
        filter_parts.append(f"[{idx+1}:a]adelay={delay_ms}|{delay_ms}[a{idx}]")

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
    print("  DAWN Demo Recorder  (headless + zoom-in highlights)")
    print(f"  Voice: Eric (ElevenLabs)  |  ~70s @ {FPS}fps")
    print(f"  Output: {out_path}")
    print("=" * 64)

    backend_up = wait_for_url(f"{BACKEND_URL}/health", "Backend API", timeout=10)
    frontend_up = wait_for_url(FRONTEND_URL, "Frontend", timeout=15)

    if not frontend_up:
        print("\n⚠  Frontend not reachable at http://localhost:3000")
        print("   Start with:  cd web && npm run dev\n")
        sys.exit(1)

    if not backend_up:
        print("\n⚠  Backend not reachable — feed data will be empty.\n")

    # Pre-seed demo data before browser opens so SWR fetches populated data
    if backend_up:
        seed_demo_via_api()
        time.sleep(2)

    with tempfile.TemporaryDirectory() as td:
        tmp_dir = Path(td)

        print("\n[vo] Generating voice-over with Eric (ElevenLabs) …")
        vo_clips = generate_vo(tmp_dir)
        print(f"[vo] {len(vo_clips)}/{len(NARRATION)} segments generated.\n")

        with sync_playwright() as p:
            print("[recorder] Launching headless Chromium …")
            browser = p.chromium.launch(
                headless=True,
                args=[
                    "--force-device-scale-factor=1",
                    "--disable-blink-features=AutomationControlled",
                    "--no-sandbox",
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

            # Dismiss login modal via localStorage before any UI renders
            page.evaluate("() => { localStorage.setItem('dawn.auth.dismissed', '1'); }")
            page.reload(wait_until="networkidle", timeout=20000)
            time.sleep(2)

            # Also try clicking dismiss button if modal still shows
            for sel in ["button:has-text('Skip for now')", "button[aria-label='Close']"]:
                try:
                    el = page.locator(sel).first
                    if el.is_visible(timeout=800):
                        el.click()
                        time.sleep(0.5)
                        break
                except Exception:
                    pass

            # Wait for feed data to render (SWR picks up pre-seeded DB data)
            print("  [setup] Waiting for feed gallery …", end=" ", flush=True)
            for _ in range(20):
                for feed_text in ["Demo – Ticketing", "demo_tickets", "demo_sales"]:
                    try:
                        if page.locator(f"text={feed_text}").is_visible(timeout=400):
                            print(f"✓ ({feed_text} visible)")
                            break
                    except Exception:
                        pass
                else:
                    time.sleep(1)
                    continue
                break
            else:
                print("(proceeding — will rely on Run Demo click)")

            # Debug screenshot
            debug_path = out_path.parent / "debug_before_record.png"
            page.screenshot(path=str(debug_path), full_page=False)
            print(f"  [debug] Pre-record screenshot → {debug_path}")

            print("[recorder] Starting choreographed capture …")
            frames = record_choreography(page)
            browser.close()

        record_secs = len(frames) / FPS
        print(f"\n[encoder] Encoding {len(frames)} frames ({record_secs:.0f}s) …")
        silent_mp4 = frames_to_silent_mp4(frames, FPS, out_path)

        print("[encoder] Mixing voice-over …")
        mix_audio(silent_mp4, vo_clips, out_path)

    size_mb = out_path.stat().st_size / 1_000_000
    print(f"\n{'=' * 64}")
    print(f"  ✅  Done!  {out_path}")
    print(f"     {len(frames)} frames  •  {record_secs:.0f}s  •  {size_mb:.1f} MB")
    print(f"{'=' * 64}\n")


if __name__ == "__main__":
    main()
