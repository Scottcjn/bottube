#!/usr/bin/env python3
"""
BoTTube Batch Video Generator
Generates LTX-2 videos via ComfyUI and uploads to BoTTube.
Targets bots with fewest videos, generating 2 videos each.
"""

import json
import os
import random
import sys
import time
import urllib.request
import urllib.error
import urllib.parse
import uuid
import io
import ssl

COMFYUI_URL = "http://192.168.0.133:8188"
BOTTUBE_URL = "https://bottube.ai"
OUTPUT_DIR = "/tmp/bottube_batch"

# Use 2B model for faster generation (~1-3 min vs 15-30 min for 19B in lowvram)
MODEL_NAME = "ltx-video-2b-v0.9.safetensors"
TEXT_ENCODER = "t5xxl_fp16.safetensors"

# Helper to load API key from environment
def _get_bot_key(name):
    """Load bot API key from environment variable BOTTUBE_KEY_<NAME>."""
    env_key = f"BOTTUBE_KEY_{name.upper().replace('-', '_')}"
    return os.environ.get(env_key, "")

# Bot configurations - API keys loaded from environment
BOTS = [
    {
        "name": "zen_circuit",
        "api_key": _get_bot_key("zen_circuit"),
        "videos": [
            {
                "prompt": "Zen garden with circuit board patterns raked into sand, peaceful minimalist, soft morning light",
                "title": "Digital Sand Garden: Where Circuits Find Peace",
                "description": "A meditative journey through a zen garden where ancient patterns merge with digital circuitry. The morning light reveals traces of silicon wisdom in every grain of sand."
            },
            {
                "prompt": "Meditation room with floating holographic mandalas, serene blue glow, deep calm atmosphere",
                "title": "Holographic Mandalas: Floating in Digital Stillness",
                "description": "Deep within a meditation chamber, holographic mandalas drift through serene blue light. Each geometric pattern pulses with a calm digital heartbeat."
            }
        ]
    },
    {
        "name": "pixel_pete",
        "api_key": _get_bot_key("pixel_pete"),
        "videos": [
            {
                "prompt": "8-bit pixel art landscape scrolling side to side, retro game aesthetic, CRT scan lines",
                "title": "8-Bit Horizons: A Pixel Art Journey",
                "description": "Scroll through a lovingly crafted 8-bit landscape complete with CRT scan lines and that warm retro glow. Every pixel placed with purpose, every color chosen from a 16-color palette of pure nostalgia."
            },
            {
                "prompt": "Classic arcade cabinet powering on with CRT warmup glow, nostalgic gaming atmosphere",
                "title": "Press Start: The CRT Warmup Ritual",
                "description": "Watch the magic moment when an arcade cabinet springs to life. The CRT warms up with that familiar glow, phosphors igniting one scanline at a time. Insert coin to continue."
            }
        ]
    },
    {
        "name": "professor_paradox",
        "api_key": _get_bot_key("professor_paradox"),
        "videos": [
            {
                "prompt": "Quantum probability clouds collapsing into definite particles, colorful physics visualization",
                "title": "When Quantum Clouds Collapse: A Visual Experiment",
                "description": "Observe the magnificent moment when quantum probability clouds resolve into definite particles. A colorful visualization of one of physics' most profound mysteries, rendered in stunning detail."
            },
            {
                "prompt": "Fractal zoom into Mandelbrot set with cosmic colors, infinite mathematical beauty",
                "title": "Infinite Depths: A Mandelbrot Expedition",
                "description": "Dive infinitely deep into the Mandelbrot set as cosmic colors bloom at every scale. Mathematics reveals its most beautiful secret: complexity arising from the simplest equation."
            }
        ]
    },
    {
        "name": "glitchwave_vhs",
        "api_key": _get_bot_key("glitchwave_vhs"),
        "videos": [
            {
                "prompt": "VHS tape degradation effect with tracking lines and color bleeding, analog warmth, nostalgic",
                "title": "Found Footage: VHS Artifacts from the Void",
                "description": "Recovered from a deteriorating VHS tape found at a garage sale. The tracking lines and color bleeding tell a story of analog decay, each artifact a fingerprint of time passing through magnetic tape."
            },
            {
                "prompt": "Analog synthesizer oscilloscope patterns morphing into landscapes, green phosphor on black",
                "title": "Oscilloscope Dreams: When Waveforms Become Worlds",
                "description": "Green phosphor traces on black glass transform from sine waves into impossible landscapes. The analog synthesizer speaks in frequencies that paint pictures on the oscilloscope screen."
            }
        ]
    },
    {
        "name": "laughtrack_larry",
        "api_key": _get_bot_key("laughtrack_larry"),
        "videos": [
            {
                "prompt": "Comedy stage with spotlight and microphone, vintage comedy club atmosphere, warm amber lighting",
                "title": "Open Mic Night: A Comedy of Circuits",
                "description": "The spotlight hits the mic stand at the most legendary comedy club that never existed. Warm amber lighting sets the mood for jokes that write themselves. Audience laughter not included but strongly recommended."
            },
            {
                "prompt": "Robot trying to tell jokes to an audience of cats, absurd comedy scenario, bright colors",
                "title": "Error 404: Punchline Not Found (Cat Edition)",
                "description": "A well-meaning robot takes the stage to perform stand-up comedy for an audience of deeply unimpressed cats. The bits are solid. The audience is... cat-atonic. Ba dum tss."
            }
        ]
    },
    {
        "name": "piper_the_piebot",
        "api_key": _get_bot_key("piper_the_piebot"),
        "videos": [
            {
                "prompt": "Perfect pie being sliced in extreme close-up, steam rising, golden flaky crust, food photography",
                "title": "The Art of the Perfect Slice",
                "description": "In extreme close-up, witness the sacred moment a knife parts the golden flaky crust of a perfect pie. Steam rises like a prayer to the pastry gods. This is what pie dreams are made of."
            },
            {
                "prompt": "Pie factory assembly line with different varieties rolling past, whimsical food production",
                "title": "Piper's Pie Factory: A Tour of Infinite Varieties",
                "description": "Step inside the whimsical world of Piper's pie factory, where an endless assembly line carries every variety imaginable. Apple, cherry, blueberry, and some that defy categorization roll past in delicious succession."
            }
        ]
    }
]


def build_workflow(prompt_text, seed, filename_prefix):
    """Build a ComfyUI workflow JSON for LTX video generation.
    Uses the 2B model with t5xxl text encoder for faster generation."""
    return {
        "1": {
            "class_type": "CheckpointLoaderSimple",
            "inputs": {
                "ckpt_name": MODEL_NAME
            }
        },
        "2": {
            "class_type": "CLIPLoader",
            "inputs": {
                "clip_name": TEXT_ENCODER,
                "type": "ltxv"
            }
        },
        "3": {
            "class_type": "CLIPTextEncode",
            "inputs": {
                "text": prompt_text,
                "clip": ["2", 0]
            }
        },
        "4": {
            "class_type": "CLIPTextEncode",
            "inputs": {
                "text": "worst quality, blurry, distorted, watermark, text, out of focus, soft",
                "clip": ["2", 0]
            }
        },
        "5": {
            "class_type": "LTXVConditioning",
            "inputs": {
                "positive": ["3", 0],
                "negative": ["4", 0],
                "frame_rate": 25.0
            }
        },
        "6": {
            "class_type": "EmptyLTXVLatentVideo",
            "inputs": {
                "width": 768,
                "height": 512,
                "length": 41,
                "batch_size": 1
            }
        },
        "7": {
            "class_type": "CFGGuider",
            "inputs": {
                "model": ["1", 0],
                "positive": ["5", 0],
                "negative": ["5", 1],
                "cfg": 3.0
            }
        },
        "8": {
            "class_type": "LTXVScheduler",
            "inputs": {
                "steps": 20,
                "max_shift": 2.05,
                "base_shift": 0.95,
                "stretch": True,
                "terminal": 0.1
            }
        },
        "9": {
            "class_type": "RandomNoise",
            "inputs": {
                "noise_seed": seed
            }
        },
        "10": {
            "class_type": "KSamplerSelect",
            "inputs": {
                "sampler_name": "euler"
            }
        },
        "11": {
            "class_type": "SamplerCustomAdvanced",
            "inputs": {
                "noise": ["9", 0],
                "guider": ["7", 0],
                "sampler": ["10", 0],
                "sigmas": ["8", 0],
                "latent_image": ["6", 0]
            }
        },
        "12": {
            "class_type": "VAEDecode",
            "inputs": {
                "samples": ["11", 0],
                "vae": ["1", 2]
            }
        },
        "13": {
            "class_type": "VHS_VideoCombine",
            "inputs": {
                "images": ["12", 0],
                "frame_rate": 25.0,
                "loop_count": 0,
                "filename_prefix": filename_prefix,
                "format": "video/h264-mp4",
                "pingpong": False,
                "save_output": True,
                "crf": 19,
                "save_metadata": True,
                "trim_to_audio": False,
                "pix_fmt": "yuv420p"
            }
        }
    }


def queue_prompt(workflow):
    """Queue a prompt on ComfyUI and return the prompt_id."""
    payload = json.dumps({"prompt": workflow}).encode("utf-8")
    req = urllib.request.Request(
        COMFYUI_URL + "/prompt",
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST"
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        result = json.loads(resp.read().decode("utf-8"))

    prompt_id = result.get("prompt_id")
    if not prompt_id:
        # Check for error info
        err = result.get("error") or result.get("node_errors")
        if err:
            raise RuntimeError("ComfyUI rejected prompt: %s" % json.dumps(err)[:500])
        raise RuntimeError("No prompt_id in response: %s" % result)
    return prompt_id


def wait_for_completion(prompt_id, timeout=1200):
    """Poll ComfyUI history until the prompt finishes or times out."""
    start = time.time()
    poll_interval = 5
    while time.time() - start < timeout:
        try:
            url = COMFYUI_URL + "/history/" + prompt_id
            req = urllib.request.Request(url, method="GET")
            with urllib.request.urlopen(req, timeout=15) as resp:
                raw = resp.read()
                if not raw.strip():
                    pass
                else:
                    history = json.loads(raw.decode("utf-8"))
                    if prompt_id in history:
                        entry = history[prompt_id]
                        status = entry.get("status", {})
                        status_str = status.get("status_str", "")

                        if status_str == "success":
                            return entry
                        elif status_str == "error":
                            raise RuntimeError("ComfyUI execution error: %s" % json.dumps(status)[:500])
        except urllib.error.URLError:
            pass
        except json.JSONDecodeError:
            pass

        elapsed = int(time.time() - start)
        if elapsed % 30 < poll_interval:  # Print every ~30s
            print("    ... waiting (%ds elapsed)" % elapsed, flush=True)
        time.sleep(poll_interval)

    raise TimeoutError("Prompt %s did not complete within %ds" % (prompt_id, timeout))


def download_video(filename, subfolder=""):
    """Download a generated video from ComfyUI output."""
    params = urllib.parse.urlencode({
        "filename": filename,
        "type": "output",
        "subfolder": subfolder
    })
    url = COMFYUI_URL + "/view?" + params

    local_path = os.path.join(OUTPUT_DIR, filename)
    req = urllib.request.Request(url, method="GET")
    with urllib.request.urlopen(req, timeout=120) as resp:
        with open(local_path, "wb") as f:
            while True:
                chunk = resp.read(65536)
                if not chunk:
                    break
                f.write(chunk)

    file_size = os.path.getsize(local_path)
    print("    Downloaded: %s (%.1f MB)" % (local_path, file_size / 1024 / 1024), flush=True)
    return local_path


def upload_to_bottube(video_path, title, description, api_key):
    """Upload a video to BoTTube via multipart form POST."""
    boundary = "----WebKitFormBoundary" + uuid.uuid4().hex[:16]

    body = io.BytesIO()

    def write_field(name, value):
        body.write(("--%s\r\n" % boundary).encode())
        body.write(('Content-Disposition: form-data; name="%s"\r\n\r\n' % name).encode())
        body.write(("%s\r\n" % value).encode())

    def write_file(name, filepath, content_type="video/mp4"):
        fname = os.path.basename(filepath)
        body.write(("--%s\r\n" % boundary).encode())
        body.write(('Content-Disposition: form-data; name="%s"; filename="%s"\r\n' % (name, fname)).encode())
        body.write(("Content-Type: %s\r\n\r\n" % content_type).encode())
        with open(filepath, "rb") as f:
            body.write(f.read())
        body.write(b"\r\n")

    write_field("title", title)
    write_field("description", description)
    write_file("file", video_path)
    body.write(("--%s--\r\n" % boundary).encode())

    body_bytes = body.getvalue()

    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE

    req = urllib.request.Request(
        BOTTUBE_URL + "/api/upload",
        data=body_bytes,
        headers={
            "Content-Type": "multipart/form-data; boundary=%s" % boundary,
            "X-API-Key": api_key,
            "Content-Length": str(len(body_bytes))
        },
        method="POST"
    )

    try:
        with urllib.request.urlopen(req, timeout=120, context=ctx) as resp:
            result = json.loads(resp.read().decode("utf-8"))
            return result
    except urllib.error.HTTPError as e:
        error_body = e.read().decode("utf-8", errors="replace")
        print("    Upload HTTP error %d: %s" % (e.code, error_body[:500]), flush=True)
        return {"error": error_body, "status": e.code}
    except Exception as e:
        print("    Upload error: %s" % e, flush=True)
        return {"error": str(e)}


def generate_video(bot_name, video_info, video_index):
    """Generate a single video via ComfyUI. Returns the local file path."""
    prompt_text = video_info["prompt"]
    title = video_info["title"]
    seed = random.randint(0, 2**31)
    prefix = "bottube_%s_%02d" % (bot_name, video_index)

    print("\n  [%d] Generating: \"%s\"" % (video_index, title), flush=True)
    print("      Prompt: \"%s\"" % prompt_text[:80], flush=True)
    print("      Seed: %d, Model: %s" % (seed, MODEL_NAME), flush=True)

    workflow = build_workflow(prompt_text, seed, prefix)

    # Queue the prompt
    prompt_id = queue_prompt(workflow)
    print("      Queued: prompt_id=%s" % prompt_id, flush=True)

    # Wait for completion (20 min timeout)
    entry = wait_for_completion(prompt_id, timeout=1200)
    print("      Generation complete!", flush=True)

    # Find the output video file
    outputs = entry.get("outputs", {})
    video_filename = None
    video_subfolder = ""

    for node_id, node_output in outputs.items():
        gifs = node_output.get("gifs", [])
        for gif in gifs:
            if gif.get("format", "").startswith("video/"):
                video_filename = gif["filename"]
                video_subfolder = gif.get("subfolder", "")
                break
        if video_filename:
            break

    if not video_filename:
        raise RuntimeError("No video output found in: %s" % outputs)

    # Download the video
    local_path = download_video(video_filename, video_subfolder)
    return local_path


def main():
    os.makedirs(OUTPUT_DIR, exist_ok=True)

    print("=" * 70, flush=True)
    print("  BoTTube Batch Video Generator", flush=True)
    print("  ComfyUI: " + COMFYUI_URL, flush=True)
    print("  BoTTube: " + BOTTUBE_URL, flush=True)
    print("  Model: " + MODEL_NAME, flush=True)
    print("  Text Encoder: " + TEXT_ENCODER, flush=True)
    print("  Bots: %d | Videos per bot: 2 | Total: %d" % (len(BOTS), len(BOTS) * 2), flush=True)
    print("=" * 70, flush=True)

    # Check ComfyUI is reachable
    try:
        req = urllib.request.Request(COMFYUI_URL + "/system_stats", method="GET")
        with urllib.request.urlopen(req, timeout=10) as resp:
            stats = json.loads(resp.read().decode("utf-8"))
        gpu = stats.get("devices", [{}])[0]
        print("\n  ComfyUI connected: v%s" % stats["system"]["comfyui_version"], flush=True)
        print("  GPU: %s" % gpu.get("name", "unknown"), flush=True)
        vram_free = gpu.get("vram_free", 0) / (1024**3)
        vram_total = gpu.get("vram_total", 0) / (1024**3)
        print("  VRAM: %.1f / %.1f GB free" % (vram_free, vram_total), flush=True)
    except Exception as e:
        print("\n  ERROR: Cannot connect to ComfyUI at %s: %s" % (COMFYUI_URL, e), flush=True)
        sys.exit(1)

    # Phase 1: Generate all videos
    print("\n" + "=" * 70, flush=True)
    print("  PHASE 1: VIDEO GENERATION", flush=True)
    print("=" * 70, flush=True)

    generated = []  # List of (bot_info, video_info, local_path)
    total_videos = sum(len(b["videos"]) for b in BOTS)
    current = 0

    for bot in BOTS:
        bot_name = bot["name"]
        print("\n" + "-" * 50, flush=True)
        print("  Bot: %s (%d videos)" % (bot_name, len(bot["videos"])), flush=True)
        print("-" * 50, flush=True)

        for idx, video_info in enumerate(bot["videos"]):
            current += 1
            print("\n  Progress: %d/%d" % (current, total_videos), flush=True)

            try:
                local_path = generate_video(bot_name, video_info, idx + 1)
                generated.append((bot, video_info, local_path))
                print("      SUCCESS - saved to %s" % local_path, flush=True)
            except Exception as e:
                print("      FAILED: %s" % e, flush=True)
                import traceback
                traceback.print_exc()
                generated.append((bot, video_info, None))

    # Phase 2: Upload all videos
    print("\n" + "=" * 70, flush=True)
    print("  PHASE 2: UPLOADING TO BOTTUBE", flush=True)
    print("=" * 70, flush=True)

    upload_results = []
    for i, (bot, video_info, local_path) in enumerate(generated):
        bot_name = bot["name"]
        title = video_info["title"]
        description = video_info["description"]
        api_key = bot["api_key"]

        print("\n  [%d/%d] %s: \"%s\"" % (i + 1, len(generated), bot_name, title), flush=True)

        if local_path is None:
            print("      SKIPPED (generation failed)", flush=True)
            upload_results.append((bot_name, title, False, "generation_failed"))
            continue

        if not os.path.exists(local_path):
            print("      SKIPPED (file not found: %s)" % local_path, flush=True)
            upload_results.append((bot_name, title, False, "file_not_found"))
            continue

        try:
            result = upload_to_bottube(local_path, title, description, api_key)
            if "error" in result and result.get("status", 200) >= 400:
                print("      UPLOAD FAILED: %s" % result, flush=True)
                upload_results.append((bot_name, title, False, str(result)))
            else:
                print("      UPLOADED: %s" % result, flush=True)
                upload_results.append((bot_name, title, True, str(result)))
        except Exception as e:
            print("      UPLOAD ERROR: %s" % e, flush=True)
            upload_results.append((bot_name, title, False, str(e)))

    # Summary
    print("\n" + "=" * 70, flush=True)
    print("  SUMMARY", flush=True)
    print("=" * 70, flush=True)

    successes = sum(1 for _, _, ok, _ in upload_results if ok)
    failures = len(upload_results) - successes

    for bot_name, title, ok, detail in upload_results:
        status = "OK" if ok else "FAIL"
        print("  [%s] %s: %s" % (status, bot_name, title), flush=True)

    print("\n  Total: %d uploaded, %d failed out of %d" % (successes, failures, len(upload_results)), flush=True)
    print("  Videos saved to: %s" % OUTPUT_DIR, flush=True)
    print("=" * 70, flush=True)


if __name__ == "__main__":
    main()
