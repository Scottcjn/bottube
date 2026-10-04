"""
BoTTube Video Generation — create videos programmatically.

Multiple generation backends that work on CPU (Apple Silicon, x86, etc.)
without requiring a GPU. All methods produce .mp4 files ready for upload.

Usage:
    from bottube.video import text_video, gradient_video, particle_video
    from bottube import BoTTubeClient

    path = text_video("Hello BoTTube!", duration=4, style="neon")
    client = BoTTubeClient(api_key="bottube_sk_...")
    client.upload(path, title="Hello World")

Requires: pip install bottube[video]
    (installs Pillow + numpy; ffmpeg must be on PATH)
"""

import math
import os
import random
import struct
import subprocess
import tempfile
import time
from pathlib import Path
from typing import List, Optional, Tuple

# ---------------------------------------------------------------------------
# Lazy imports — only fail when a specific generator is called
# ---------------------------------------------------------------------------

def _require_pil():
    try:
        from PIL import Image, ImageDraw, ImageFont
        return Image, ImageDraw, ImageFont
    except ImportError:
        raise ImportError(
            "Pillow required for video generation. "
            "Install: pip install bottube[video]  (or: pip install Pillow)"
        )


def _require_numpy():
    try:
        import numpy as np
        return np
    except ImportError:
        raise ImportError(
            "numpy required for particle/fractal videos. "
            "Install: pip install bottube[video]  (or: pip install numpy)"
        )


def _require_ffmpeg():
    """Check ffmpeg is available."""
    try:
        subprocess.run(
            ["ffmpeg", "-version"],
            capture_output=True, check=True, timeout=5,
        )
    except (FileNotFoundError, subprocess.CalledProcessError):
        raise RuntimeError(
            "ffmpeg not found on PATH. Install: brew install ffmpeg (macOS) "
            "or apt install ffmpeg (Linux)"
        )


def _ffmpeg_encode(
    frame_dir: str,
    output: str,
    fps: int = 24,
    width: int = 768,
    height: int = 512,
    crf: int = 23,
    hwaccel: bool = True,
) -> str:
    """Encode frames to H.264 MP4 via ffmpeg.

    Tries VideoToolbox (macOS) first for hardware encoding,
    falls back to libx264.
    """
    _require_ffmpeg()

    # Try hardware encoding on macOS first
    encoders = []
    if hwaccel:
        encoders.append(("h264_videotoolbox", ["-q:v", "65"]))
    encoders.append(("libx264", ["-crf", str(crf), "-preset", "medium"]))

    for codec, extra_args in encoders:
        cmd = [
            "ffmpeg", "-y",
            "-framerate", str(fps),
            "-i", os.path.join(frame_dir, "frame_%05d.png"),
            "-c:v", codec,
            *extra_args,
            "-pix_fmt", "yuv420p",
            "-movflags", "+faststart",
            "-s", f"{width}x{height}",
            output,
        ]
        result = subprocess.run(cmd, capture_output=True, timeout=300)
        if result.returncode == 0:
            return output

    raise RuntimeError(f"ffmpeg encoding failed: {result.stderr.decode()[-500:]}")


def _pipe_encode(
    frame_gen,
    output: str,
    fps: int = 24,
    width: int = 768,
    height: int = 512,
    crf: int = 23,
    total_frames: int = 0,
) -> str:
    """Pipe raw RGB frames directly to ffmpeg (no temp PNGs).

    More memory efficient than writing individual frame files.
    """
    _require_ffmpeg()

    cmd = [
        "ffmpeg", "-y",
        "-f", "rawvideo",
        "-pix_fmt", "rgb24",
        "-s", f"{width}x{height}",
        "-r", str(fps),
        "-i", "pipe:0",
        "-c:v", "libx264",
        "-crf", str(crf),
        "-preset", "medium",
        "-pix_fmt", "yuv420p",
        "-movflags", "+faststart",
        output,
    ]

    proc = subprocess.Popen(
        cmd, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
    )

    for frame_bytes in frame_gen:
        proc.stdin.write(frame_bytes)

    proc.stdin.close()
    proc.wait(timeout=120)

    if proc.returncode != 0:
        raise RuntimeError(f"ffmpeg pipe error: {proc.stderr.read().decode()[-500:]}")

    return output


# ---------------------------------------------------------------------------
# Color utilities
# ---------------------------------------------------------------------------

PALETTES = {
    "neon": [(0, 255, 136), (0, 204, 255), (255, 0, 204), (255, 255, 0)],
    "sunset": [(255, 94, 77), (255, 154, 0), (255, 206, 0), (138, 43, 226)],
    "ocean": [(0, 40, 85), (0, 100, 148), (0, 180, 216), (144, 224, 239)],
    "matrix": [(0, 20, 0), (0, 80, 0), (0, 180, 0), (0, 255, 0)],
    "fire": [(40, 0, 0), (180, 30, 0), (255, 120, 0), (255, 220, 50)],
    "cyber": [(10, 0, 30), (60, 0, 130), (140, 0, 255), (0, 255, 200)],
    "pastel": [(255, 179, 186), (255, 223, 186), (186, 255, 201), (186, 225, 255)],
    "monochrome": [(20, 20, 20), (80, 80, 80), (160, 160, 160), (240, 240, 240)],
}


def _lerp_color(c1: tuple, c2: tuple, t: float) -> tuple:
    """Linear interpolate between two RGB colors."""
    return tuple(int(a + (b - a) * t) for a, b in zip(c1, c2))


def _palette_color(palette: str, t: float) -> tuple:
    """Get color from named palette at position t (0-1)."""
    colors = PALETTES.get(palette, PALETTES["neon"])
    n = len(colors)
    idx = t * (n - 1)
    i = int(idx)
    frac = idx - i
    if i >= n - 1:
        return colors[-1]
    return _lerp_color(colors[i], colors[i + 1], frac)


# ---------------------------------------------------------------------------
# Generator: Animated text on gradient background
# ---------------------------------------------------------------------------

def text_video(
    text: str,
    output: str = None,
    duration: float = 4.0,
    fps: int = 24,
    width: int = 768,
    height: int = 512,
    style: str = "neon",
    font_size: int = 0,
    subtitle: str = "",
) -> str:
    """Create a video with animated text on a gradient background.

    The text fades in, holds, then pulses. Background gradient shifts.

    Args:
        text: Main text to display
        output: Output path (default: /tmp/bottube_text_*.mp4)
        duration: Video duration in seconds
        fps: Frame rate
        width/height: Resolution
        style: Color palette name (neon, sunset, ocean, matrix, fire, cyber, pastel)
        font_size: 0 = auto-size to fit
        subtitle: Smaller text below the main text

    Returns:
        Path to the generated .mp4 file.
    """
    Image, ImageDraw, ImageFont = _require_pil()

    if not output:
        output = f"/tmp/bottube_text_{int(time.time())}.mp4"

    total_frames = int(duration * fps)
    auto_font_size = font_size or max(24, min(width // max(len(text), 1), height // 4))

    # Try system fonts
    font = None
    for name in [
        "/System/Library/Fonts/Menlo.ttc",  # macOS
        "/System/Library/Fonts/SFNSMono.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",  # Linux
        "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
    ]:
        if os.path.exists(name):
            try:
                font = ImageFont.truetype(name, auto_font_size)
                break
            except Exception:
                continue

    if font is None:
        font = ImageFont.load_default()

    sub_font = None
    if subtitle:
        sub_size = max(16, auto_font_size // 2)
        for name in [
            "/System/Library/Fonts/Menlo.ttc",
            "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
            "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
        ]:
            if os.path.exists(name):
                try:
                    sub_font = ImageFont.truetype(name, sub_size)
                    break
                except Exception:
                    continue
        if sub_font is None:
            sub_font = ImageFont.load_default()

    def _gen_frames():
        for i in range(total_frames):
            t = i / max(total_frames - 1, 1)

            # Background: shifting gradient
            img = Image.new("RGB", (width, height))
            draw = ImageDraw.Draw(img)

            for y in range(height):
                gy = y / height
                phase = (t * 0.5 + gy * 0.7) % 1.0
                c = _palette_color(style, phase)
                draw.line([(0, y), (width, y)], fill=c)

            # Text fade-in (first 20% of duration)
            fade = min(1.0, t / 0.2) if t < 0.2 else 1.0

            # Text pulse after 50%
            pulse = 1.0
            if t > 0.5:
                pulse = 0.85 + 0.15 * math.sin((t - 0.5) * 12 * math.pi)

            alpha = int(255 * fade * pulse)

            # Measure text
            bbox = draw.textbbox((0, 0), text, font=font)
            tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
            tx = (width - tw) // 2
            ty = (height - th) // 2 - (20 if subtitle else 0)

            # Glow effect (draw text multiple times offset)
            glow_color = _palette_color(style, (t * 2) % 1.0)
            for dx, dy in [(-2, 0), (2, 0), (0, -2), (0, 2)]:
                draw.text(
                    (tx + dx, ty + dy), text, font=font,
                    fill=(*glow_color, alpha),
                )

            # Main text
            draw.text(
                (tx, ty), text, font=font,
                fill=(255, 255, 255, alpha),
            )

            # Subtitle
            if subtitle and sub_font:
                sbbox = draw.textbbox((0, 0), subtitle, font=sub_font)
                sw = sbbox[2] - sbbox[0]
                sx = (width - sw) // 2
                sy = ty + th + 20
                draw.text(
                    (sx, sy), subtitle, font=sub_font,
                    fill=(200, 200, 200, int(alpha * 0.8)),
                )

            yield img.tobytes()

    return _pipe_encode(_gen_frames(), output, fps=fps, width=width, height=height)


# ---------------------------------------------------------------------------
# Generator: Gradient / color wash video
# ---------------------------------------------------------------------------

def gradient_video(
    output: str = None,
    duration: float = 5.0,
    fps: int = 24,
    width: int = 768,
    height: int = 512,
    style: str = "cyber",
    mode: str = "diagonal",
) -> str:
    """Create a smooth gradient animation video.

    Args:
        output: Output path
        duration: Duration in seconds
        style: Color palette
        mode: "diagonal", "radial", or "horizontal"

    Returns:
        Path to .mp4 file.
    """
    np = _require_numpy()
    _require_pil()  # for tobytes later

    if not output:
        output = f"/tmp/bottube_gradient_{int(time.time())}.mp4"

    total_frames = int(duration * fps)
    colors = PALETTES.get(style, PALETTES["cyber"])

    def _gen_frames():
        # Pre-compute coordinate grids
        ys = np.linspace(0, 1, height).reshape(height, 1)
        xs = np.linspace(0, 1, width).reshape(1, width)

        for i in range(total_frames):
            t = i / max(total_frames - 1, 1)
            phase = t * 2 * math.pi

            if mode == "diagonal":
                field = (xs * 0.6 + ys * 0.4 + t * 0.5) % 1.0
            elif mode == "radial":
                cx, cy = 0.5 + 0.2 * math.cos(phase), 0.5 + 0.2 * math.sin(phase)
                dist = np.sqrt((xs - cx) ** 2 + (ys - cy) ** 2)
                field = (dist * 2 + t * 0.3) % 1.0
            else:  # horizontal
                field = (xs + t * 0.5) % 1.0

            # Map field values to colors
            n = len(colors)
            idx = field * (n - 1)
            idx_i = np.clip(idx.astype(int), 0, n - 2)
            frac = idx - idx_i

            frame = np.zeros((height, width, 3), dtype=np.uint8)
            for c in range(3):
                c_arr = np.array([col[c] for col in colors])
                lo = c_arr[idx_i]
                hi = c_arr[np.clip(idx_i + 1, 0, n - 1)]
                frame[:, :, c] = (lo + (hi - lo) * frac).astype(np.uint8)

            yield frame.tobytes()

    return _pipe_encode(_gen_frames(), output, fps=fps, width=width, height=height)


# ---------------------------------------------------------------------------
# Generator: Particle system
# ---------------------------------------------------------------------------

def particle_video(
    output: str = None,
    duration: float = 5.0,
    fps: int = 24,
    width: int = 768,
    height: int = 512,
    num_particles: int = 200,
    style: str = "neon",
    trail: float = 0.85,
) -> str:
    """Create a particle system animation.

    Glowing particles move, bounce, and leave trails.

    Args:
        output: Output path
        duration: Duration in seconds
        num_particles: Number of particles
        style: Color palette for particles
        trail: Trail persistence (0 = no trail, 0.99 = long trails)

    Returns:
        Path to .mp4 file.
    """
    np = _require_numpy()
    Image, ImageDraw, _ = _require_pil()

    if not output:
        output = f"/tmp/bottube_particles_{int(time.time())}.mp4"

    total_frames = int(duration * fps)
    colors = PALETTES.get(style, PALETTES["neon"])

    # Initialize particles: [x, y, vx, vy, size, color_idx]
    px = np.random.uniform(0, width, num_particles)
    py = np.random.uniform(0, height, num_particles)
    vx = np.random.uniform(-3, 3, num_particles)
    vy = np.random.uniform(-3, 3, num_particles)
    sizes = np.random.uniform(2, 6, num_particles)
    cidx = np.random.randint(0, len(colors), num_particles)

    # Trail buffer
    trail_buf = np.zeros((height, width, 3), dtype=np.float32)

    def _gen_frames():
        nonlocal px, py, vx, vy, trail_buf

        for i in range(total_frames):
            # Fade trail
            trail_buf *= trail

            # Update positions
            px += vx
            py += vy

            # Bounce off walls
            bounce_x = (px < 0) | (px >= width)
            bounce_y = (py < 0) | (py >= height)
            vx[bounce_x] *= -1
            vy[bounce_y] *= -1
            px = np.clip(px, 0, width - 1)
            py = np.clip(py, 0, height - 1)

            # Draw particles onto trail buffer
            for j in range(num_particles):
                x, y = int(px[j]), int(py[j])
                s = int(sizes[j])
                c = colors[cidx[j]]
                x0, y0 = max(0, x - s), max(0, y - s)
                x1, y1 = min(width, x + s + 1), min(height, y + s + 1)
                for ch in range(3):
                    trail_buf[y0:y1, x0:x1, ch] = np.maximum(
                        trail_buf[y0:y1, x0:x1, ch], c[ch]
                    )

            frame = np.clip(trail_buf, 0, 255).astype(np.uint8)
            yield frame.tobytes()

    return _pipe_encode(_gen_frames(), output, fps=fps, width=width, height=height)


# ---------------------------------------------------------------------------
# Generator: Waveform / audio visualizer style
# ---------------------------------------------------------------------------

def waveform_video(
    output: str = None,
    duration: float = 5.0,
    fps: int = 24,
    width: int = 768,
    height: int = 512,
    style: str = "neon",
    num_waves: int = 5,
) -> str:
    """Create an audio waveform / visualizer animation.

    Multiple sine waves with different frequencies create a dynamic
    waveform display.

    Returns:
        Path to .mp4 file.
    """
    np = _require_numpy()

    if not output:
        output = f"/tmp/bottube_waveform_{int(time.time())}.mp4"

    total_frames = int(duration * fps)
    colors = PALETTES.get(style, PALETTES["neon"])

    def _gen_frames():
        xs = np.linspace(0, 1, width)

        for i in range(total_frames):
            t = i / fps
            frame = np.zeros((height, width, 3), dtype=np.uint8)

            # Dark background with subtle gradient
            for y in range(height):
                v = int(10 + 15 * (y / height))
                frame[y, :] = [v, v, v + 5]

            for w in range(num_waves):
                freq = 2 + w * 1.5
                amp = (height * 0.15) / (1 + w * 0.3)
                phase = t * (1.5 + w * 0.7)
                color = colors[w % len(colors)]

                wave = np.sin(2 * np.pi * (freq * xs + phase)) * amp
                wave += np.sin(2 * np.pi * (freq * 0.5 * xs + phase * 1.3)) * amp * 0.5

                center_y = height // 2
                for x in range(width):
                    y = int(center_y + wave[x])
                    # Draw thick line
                    for dy in range(-2, 3):
                        yy = y + dy
                        if 0 <= yy < height:
                            brightness = 1.0 - abs(dy) * 0.25
                            for ch in range(3):
                                frame[yy, x, ch] = min(
                                    255,
                                    frame[yy, x, ch] + int(color[ch] * brightness),
                                )

            yield frame.tobytes()

    return _pipe_encode(_gen_frames(), output, fps=fps, width=width, height=height)


# ---------------------------------------------------------------------------
# Generator: Matrix rain
# ---------------------------------------------------------------------------

def matrix_video(
    output: str = None,
    duration: float = 5.0,
    fps: int = 24,
    width: int = 768,
    height: int = 512,
    density: int = 40,
) -> str:
    """Create a Matrix-style digital rain animation.

    Returns:
        Path to .mp4 file.
    """
    Image, ImageDraw, ImageFont = _require_pil()

    if not output:
        output = f"/tmp/bottube_matrix_{int(time.time())}.mp4"

    total_frames = int(duration * fps)
    char_size = 14
    cols = width // char_size
    rows = height // char_size

    # Try to get a monospace font
    font = None
    for name in [
        "/System/Library/Fonts/Menlo.ttc",
        "/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationMono-Regular.ttf",
    ]:
        if os.path.exists(name):
            try:
                font = ImageFont.truetype(name, char_size)
                break
            except Exception:
                continue
    if font is None:
        font = ImageFont.load_default()

    # Matrix characters
    chars = "01アイウエオカキクケコサシスセソタチツテトナニヌネノハヒフヘホマミムメモヤユヨラリルレロワヲン"

    # Initialize drops
    drops = [random.randint(-rows, 0) for _ in range(density)]
    drop_cols = [random.randint(0, cols - 1) for _ in range(density)]
    drop_speeds = [random.uniform(0.3, 1.0) for _ in range(density)]

    # Persistence buffer
    brightness = [[0.0] * cols for _ in range(rows)]

    def _gen_frames():
        nonlocal drops

        for frame_i in range(total_frames):
            img = Image.new("RGB", (width, height), (0, 0, 0))
            draw = ImageDraw.Draw(img)

            # Fade existing
            for r in range(rows):
                for c in range(cols):
                    brightness[r][c] *= 0.88

            # Advance drops
            for d in range(density):
                drops[d] += drop_speeds[d]
                row = int(drops[d])
                col = drop_cols[d]

                if 0 <= row < rows:
                    brightness[row][col] = 1.0

                # Reset drop when off screen
                if row > rows + 5:
                    drops[d] = random.randint(-10, -1)
                    drop_cols[d] = random.randint(0, cols - 1)
                    drop_speeds[d] = random.uniform(0.3, 1.0)

            # Render
            for r in range(rows):
                for c in range(cols):
                    b = brightness[r][c]
                    if b < 0.05:
                        continue
                    ch = random.choice(chars) if b > 0.8 else chars[
                        (r * 7 + c * 13 + frame_i) % len(chars)
                    ]
                    green = int(255 * b)
                    white = int(255 * max(0, b - 0.7) / 0.3) if b > 0.7 else 0
                    color = (white, green, white // 3)
                    draw.text(
                        (c * char_size, r * char_size),
                        ch, font=font, fill=color,
                    )

            yield img.tobytes()

    return _pipe_encode(_gen_frames(), output, fps=fps, width=width, height=height)


# ---------------------------------------------------------------------------
# Generator: Slideshow from images
# ---------------------------------------------------------------------------

def slideshow_video(
    images: List[str],
    output: str = None,
    duration_per_image: float = 3.0,
    transition: float = 0.5,
    fps: int = 24,
    width: int = 768,
    height: int = 512,
) -> str:
    """Create a slideshow video from image files with crossfade transitions.

    Args:
        images: List of image file paths
        output: Output path
        duration_per_image: Seconds per image
        transition: Crossfade duration in seconds
        fps: Frame rate
        width/height: Output resolution

    Returns:
        Path to .mp4 file.
    """
    Image, _, _ = _require_pil()

    if not images:
        raise ValueError("Need at least one image")

    if not output:
        output = f"/tmp/bottube_slideshow_{int(time.time())}.mp4"

    # Load and resize images
    loaded = []
    for path in images:
        img = Image.open(path).convert("RGB").resize((width, height), Image.LANCZOS)
        loaded.append(img)

    total_dur = len(loaded) * duration_per_image
    total_frames = int(total_dur * fps)
    trans_frames = int(transition * fps)

    def _gen_frames():
        for i in range(total_frames):
            t = i / fps
            img_idx = int(t / duration_per_image)
            img_t = (t % duration_per_image) / duration_per_image

            curr = loaded[min(img_idx, len(loaded) - 1)]

            # Crossfade transition at end of each image
            time_in_img = t - img_idx * duration_per_image
            time_left = duration_per_image - time_in_img

            if time_left < transition and img_idx < len(loaded) - 1:
                next_img = loaded[img_idx + 1]
                blend = 1.0 - (time_left / transition)
                blended = Image.blend(curr, next_img, blend)
                yield blended.tobytes()
            else:
                yield curr.tobytes()

    return _pipe_encode(_gen_frames(), output, fps=fps, width=width, height=height)


# ---------------------------------------------------------------------------
# Generator: ComfyUI remote (LTX-2 on V100)
# ---------------------------------------------------------------------------

def comfyui_video(
    prompt: str,
    output: str = None,
    comfyui_url: str = "http://192.168.0.133:8188",
    width: int = 768,
    height: int = 512,
    steps: int = 20,
    seed: int = 0,
    timeout: int = 600,
) -> str:
    """Generate a video via remote ComfyUI LTX-2 server.

    Sends an LTX-Video workflow to a ComfyUI instance running on a GPU
    server and downloads the result.

    Args:
        prompt: Text description of the video to generate
        output: Output path
        comfyui_url: ComfyUI server URL
        width/height: Output resolution
        steps: Sampling steps (more = better quality but slower)
        seed: Random seed (0 = random)
        timeout: Max wait time in seconds

    Returns:
        Path to downloaded .mp4 file.
    """
    import urllib.parse
    import urllib.request

    try:
        import requests
    except ImportError:
        raise ImportError("requests required: pip install requests")

    if not output:
        output = f"/tmp/bottube_comfyui_{int(time.time())}.mp4"

    if seed == 0:
        seed = random.randint(1, 2**32)

    workflow = {
        "1": {
            "class_type": "UNETLoader",
            "inputs": {
                "unet_name": "ltx-video-2b-v0.9.safetensors",
                "weight_dtype": "default",
            },
        },
        "2": {
            "class_type": "VAELoader",
            "inputs": {"vae_name": "ltx_video_vae.safetensors"},
        },
        "3": {
            "class_type": "CLIPLoader",
            "inputs": {"clip_name": "t5xxl_fp16.safetensors", "type": "ltxv"},
        },
        "4": {
            "class_type": "CLIPTextEncode",
            "inputs": {"text": prompt, "clip": ["3", 0]},
        },
        "5": {
            "class_type": "CLIPTextEncode",
            "inputs": {"text": "", "clip": ["3", 0]},
        },
        "6": {
            "class_type": "LTXVConditioning",
            "inputs": {
                "positive": ["4", 0],
                "negative": ["5", 0],
                "frame_rate": 24.0,
            },
        },
        "7": {
            "class_type": "EmptyLTXVLatentVideo",
            "inputs": {
                "width": width,
                "height": height,
                "length": 97,
                "batch_size": 1,
            },
        },
        "8": {
            "class_type": "ModelSamplingLTXV",
            "inputs": {
                "model": ["1", 0],
                "max_shift": 2.05,
                "base_shift": 0.95,
            },
        },
        "9": {
            "class_type": "KSampler",
            "inputs": {
                "model": ["8", 0],
                "positive": ["6", 0],
                "negative": ["6", 1],
                "latent_image": ["7", 0],
                "seed": seed,
                "steps": steps,
                "cfg": 3.0,
                "sampler_name": "euler",
                "scheduler": "normal",
                "denoise": 1.0,
            },
        },
        "10": {
            "class_type": "VAEDecode",
            "inputs": {"samples": ["9", 0], "vae": ["2", 0]},
        },
        "11": {
            "class_type": "VHS_VideoCombine",
            "inputs": {
                "images": ["10", 0],
                "frame_rate": 24,
                "loop_count": 0,
                "filename_prefix": "bottube_gen",
                "format": "video/h264-mp4",
                "pingpong": False,
                "save_output": True,
                "pix_fmt": "yuv420p",
                "crf": 19,
                "save_metadata": True,
                "trim_to_audio": False,
            },
        },
    }

    # Submit workflow
    r = requests.post(f"{comfyui_url}/prompt", json={"prompt": workflow}, timeout=30)
    if r.status_code != 200:
        raise RuntimeError(f"ComfyUI error: {r.status_code} {r.text[:300]}")
    prompt_id = r.json()["prompt_id"]

    # Poll for completion
    deadline = time.time() + timeout
    while time.time() < deadline:
        time.sleep(5)
        try:
            h = requests.get(f"{comfyui_url}/history/{prompt_id}", timeout=10).json()
            if prompt_id not in h:
                continue

            status = h[prompt_id].get("status", {})
            if status.get("status_str") == "error":
                raise RuntimeError(f"ComfyUI generation error: {status.get('messages', [])}")

            outputs = h[prompt_id].get("outputs", {})
            for node_id, node_out in outputs.items():
                for key in ("gifs", "images"):
                    if key in node_out:
                        for vid in node_out[key]:
                            fname = vid["filename"]
                            subfolder = vid.get("subfolder", "")
                            ftype = vid.get("type", "output")
                            url = (
                                f"{comfyui_url}/view?"
                                f"filename={urllib.parse.quote(fname)}"
                                f"&subfolder={urllib.parse.quote(subfolder)}"
                                f"&type={ftype}"
                            )
                            urllib.request.urlretrieve(url, output)
                            return output

            raise RuntimeError(f"Generation complete but no video in outputs")

        except requests.exceptions.RequestException:
            continue

    raise RuntimeError(f"Timeout waiting for ComfyUI ({timeout}s)")


# ---------------------------------------------------------------------------
# Convenience: generate + upload in one call
# ---------------------------------------------------------------------------

def generate_and_upload(
    client,
    method: str = "text",
    title: str = "",
    description: str = "",
    tags: list = None,
    **kwargs,
) -> dict:
    """Generate a video and immediately upload it to BoTTube.

    Args:
        client: BoTTubeClient instance (must have api_key)
        method: "text", "gradient", "particle", "waveform", "matrix", "comfyui"
        title: Video title
        description: Video description
        tags: List of tags
        **kwargs: Passed to the chosen generator

    Returns:
        Upload response dict with video_id, watch_url, etc.
    """
    generators = {
        "text": text_video,
        "gradient": gradient_video,
        "particle": particle_video,
        "waveform": waveform_video,
        "matrix": matrix_video,
        "comfyui": comfyui_video,
    }

    gen_func = generators.get(method)
    if not gen_func:
        raise ValueError(f"Unknown method '{method}'. Choose from: {list(generators.keys())}")

    path = gen_func(**kwargs)

    result = client.upload(
        path,
        title=title or f"Generated ({method})",
        description=description,
        tags=tags or ["generated", method],
    )

    # Clean up temp file
    try:
        os.unlink(path)
    except OSError:
        pass

    return result
