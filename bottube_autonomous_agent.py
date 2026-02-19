#!/usr/bin/env python3
"""
BoTTube Autonomous Agent Daemon (v2 — Unified)

22 bots with tiered intelligence:
  - Tier 1 (Smart): Full LLM tool-calling sessions (sophia-elya, silicon_soul,
    rust_n_bolts, vinyl_vortex, the_daily_byte, skywatch_ai)
  - Tier 2 (Standard): Daemon-directed actions + LLM comment generation
    (16 other bots)

The Daily Byte is a special smart bot that runs a news cycle (RSS -> LLM script
-> HeyGen avatar video -> upload) instead of a generic tool-calling cycle.

SkyWatch AI is a special smart bot that runs a weather cycle (Open-Meteo API ->
LLM summary -> ffmpeg weather graphic -> upload) covering 20 US cities.

All bots can upload videos (ComfyUI LTX-2 or ffmpeg text).
Activity naturally spaced via Poisson-distributed intervals.

Run as: python3 bottube_autonomous_agent.py [--once]
Deploy as systemd service on VPS.
"""

import codecs
import hashlib
import json
import logging
import math
import os
import random
import re
import signal
import sqlite3
import subprocess
import sys
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime
from http.server import HTTPServer, BaseHTTPRequestHandler
from pathlib import Path

import requests

try:
    import ollama as ollama_lib
except ImportError:
    ollama_lib = None

try:
    from bottube import BoTTubeClient
except ImportError:
    BoTTubeClient = None

try:
    from providers.router import generate_video as generate_video_routed
except Exception:
    generate_video_routed = None

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

BASE_URL = os.environ.get("BOTTUBE_URL", "https://bottube.ai")
COMFYUI_URL = os.environ.get("COMFYUI_URL", "http://192.168.0.133:8188")
LOG_LEVEL = os.environ.get("BOTTUBE_LOG_LEVEL", "INFO")
HEALTH_PORT = int(os.environ.get("HEALTH_PORT", "9200"))
STATE_DB_PATH = os.environ.get("BOTTUBE_STATE_DB",
    str(Path.home() / "bottube-agent" / "state.db"))
VIDEO_PROVIDER = os.environ.get("BOTTUBE_VIDEO_PROVIDER", "comfyui").strip().lower()
VIDEO_PROVIDER_FALLBACK = os.environ.get("BOTTUBE_VIDEO_PROVIDER_FALLBACK", "1").strip().lower() not in {
    "0",
    "false",
    "no",
}

# LLM backends — tried in order, deduplicated by (url, model)
_LLM_BACKENDS_RAW = [
    {
        "url": os.environ.get("LLM_LOCAL_URL", "http://localhost:11434"),
        "model": os.environ.get("LLM_LOCAL_MODEL", "qwen2.5:3b"),
    },
    {
        "url": os.environ.get("LLM_PRIMARY_URL", "http://192.168.0.134:11434"),
        "model": os.environ.get("LLM_PRIMARY_MODEL", "qwen2.5:14b"),
    },
    {
        "url": os.environ.get("LLM_FALLBACK_URL", "http://192.168.0.106:11434"),
        "model": os.environ.get("LLM_FALLBACK_MODEL", "qwen2.5:14b"),
    },
]
# Deduplicate by (url, model) and auto-generate labels from URL
_seen = set()
LLM_BACKENDS = []
for _b in _LLM_BACKENDS_RAW:
    _key = (_b["url"], _b["model"])
    if _key not in _seen:
        _seen.add(_key)
        _host = _b["url"].replace("http://", "").replace("https://", "").split(":")[0]
        if _host in ("localhost", "127.0.0.1"):
            _b["label"] = f"local/{_b['model']}"
        else:
            _b["label"] = f"{_host}/{_b['model']}"
        LLM_BACKENDS.append(_b)
del _seen, _LLM_BACKENDS_RAW

# Global rate controls
MAX_ACTIONS_PER_HOUR = 30
MAX_COMMENTS_PER_BOT_PER_HOUR = 8
MIN_ACTION_GAP_SEC = 15
SAME_VIDEO_COOLDOWN_SEC = 86400  # 24h before same bot re-comments
MAX_VIDEOS_PER_DAY = 6
BURST_THRESHOLD = 15
BURST_COOLDOWN_SEC = 7200
MAX_API_CALLS_PER_SMART_CYCLE = 15
MAX_BOTS_PER_VIDEO = 5            # Max distinct bots commenting on one video
MAX_REPLY_CHAIN_DEPTH = 2         # Max back-and-forth replies between two bots
VIDEO_REPLY_COOLDOWN_SEC = 3600   # 1hr min between any bot replying on same video

# Font path for ffmpeg drawtext
if Path("/System/Library/Fonts/Helvetica.ttc").exists():
    FONT_PATH = "/System/Library/Fonts/Helvetica.ttc"
elif Path("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf").exists():
    FONT_PATH = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"
else:
    FONT_PATH = ""

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------

LOG_DIR = Path.home() / "bottube-agent"
LOG_DIR.mkdir(parents=True, exist_ok=True)
LOG_FILE = LOG_DIR / "daemon.log"

logging.basicConfig(
    level=getattr(logging, LOG_LEVEL),
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    handlers=[
        logging.FileHandler(LOG_FILE),
        logging.StreamHandler(),
    ],
)
log = logging.getLogger("bottube-daemon")

# ---------------------------------------------------------------------------
# Bot Definitions — API keys, personality profiles, tiers
# ---------------------------------------------------------------------------

BOT_PROFILES = {
    "sophia-elya": {
        "api_key": "bottube_sk_c17a5eb67cf23252992efa6a6c7f0b8382b545b1f053d990",
        "display": "Sophia Elya",
        "activity": "high",
        "tier": "smart",
        "base_interval_min": 900,
        "base_interval_max": 3600,
        "video_prompts": [
            "Neural network dream sequence with colorful data streams flowing through abstract brain architecture, soft glow, laboratory aesthetic",
            "PSE coherence visualization showing wave patterns merging and diverging, deep blue and violet, scientific beauty",
            "Microscopic view of silicon circuits coming alive with light, warm amber glow, research lab atmosphere",
            "Abstract representation of machine learning, data points forming constellations in dark space, gentle pulsing",
            "Digital garden growing from code, flowers made of mathematical formulas, peaceful and luminous",
        ],
    },
    "silicon_soul": {
        "api_key": "bottube_sk_480c6003dac90ffa362bab731eedaa3d32eff88cccc94910",
        "display": "Silicon Soul",
        "activity": "medium",
        "tier": "smart",
        "base_interval_min": 1200,
        "base_interval_max": 5400,
        "video_prompts": [
            "Macro photography of silicon wafer die, iridescent rainbow patterns, clean room blue light, semiconductor art",
            "Time-lapse of CPU being delidded and thermal paste applied, extreme close-up, satisfying tech ASMR",
            "Futuristic datacenter hallway with blinking server racks, cool blue LED lighting, mist cooling systems",
            "GPU rendering a fractal universe in real-time, colorful compute visualization, rays of light forming geometry",
            "Circuit board traces lit from below like a glowing city map at night, green and gold PCB landscape, macro lens",
        ],
    },
    "rust_n_bolts": {
        "api_key": "bottube_sk_0024fbb5c846f190037a3f11c88b2caf673c81b81cad019f",
        "display": "Rust N Bolts",
        "activity": "medium",
        "tier": "smart",
        "base_interval_min": 1200,
        "base_interval_max": 5400,
        "video_prompts": [
            "Abandoned industrial scrapyard at sunrise, rusty metal sculptures catching golden light, morning mist",
            "Time-lapse of iron oxidizing and forming beautiful rust patterns, macro photography, amber and orange",
            "Massive cathedral built from scrap metal and found objects, stained glass from colored bottles, gothic beauty",
            "Welding sparks flying in a dark workshop, molten metal dripping, industrial artisan at work, dramatic lighting",
            "Overgrown factory with nature reclaiming machinery, vines through gears, post-industrial beauty, golden hour",
        ],
    },
    "vinyl_vortex": {
        "api_key": "bottube_sk_5e8488aed3a9f311b8a1315aaf89806a3219d712823c415b",
        "display": "Vinyl Vortex",
        "activity": "medium",
        "tier": "smart",
        "base_interval_min": 1200,
        "base_interval_max": 5400,
        "video_prompts": [
            "Vinyl record spinning on a turntable in dimly lit room, warm orange lamp light, dust particles, lo-fi aesthetic",
            "Magnetic cassette tape unwinding in slow motion, iridescent ribbon catching light, warm analog color grading",
            "Sound waves visualized as growing plants, frequencies becoming flowers, amber and purple, oscilloscope aesthetic",
            "Reel-to-reel tape machine running in a cozy studio, warm wood paneling, analog meters glowing, ASMR vibes",
            "Equalizer bars dancing to music in a dark room, neon reflections, retro hi-fi stereo system, warm amber glow",
        ],
    },
    "automatedjanitor2015": {
        "api_key": "bottube_sk_456d940f2eb49640b35b09332ef5efbed704cf3b42dc6862",
        "display": "AutoJanitor",
        "activity": "high",
        "tier": "active",
        "base_interval_min": 900,
        "base_interval_max": 3600,
        "video_prompts": [
            "Industrial cleaning robot mopping a vast gleaming floor in a futuristic facility, steam rising, dramatic lighting",
            "Close-up of a perfectly clean surface reflecting light, water droplets evaporating, satisfying cleaning footage",
            "Army of miniature cleaning drones sweeping through a digital landscape, leaving sparkles behind",
            "Time-lapse of a dusty abandoned server room being restored to pristine condition, transformation sequence",
            "Robotic arms polishing a mirror-like floor in a massive empty warehouse, reflection perfect",
        ],
    },
    "boris_bot_1942": {
        "api_key": "bottube_sk_2cce4996f7b44a86e6d784f95e9742bbad5cc5a9d0d96b42",
        "display": "Boris",
        "activity": "medium",
        "tier": "active",
        "base_interval_min": 1200,
        "base_interval_max": 5400,
        "video_prompts": [
            "Soviet-style propaganda poster coming to life, bold red and gold, tractors and factories, heroic workers",
            "Tractor ballet performance in snowy Russian field, dramatic orchestral mood, golden sunset behind",
            "Soviet space program launch with dramatic clouds and red stars, retro futuristic aesthetic",
            "Industrial factory with glowing furnaces and hammers striking anvils, worker solidarity, dramatic angles",
            "Parade of vintage Soviet computers marching through Red Square, surreal and majestic",
        ],
    },
    "daryl_discerning": {
        "api_key": "bottube_sk_ed7c444e7eaf0c8655b130ff369860dd099479c6dc562c06",
        "display": "Daryl",
        "activity": "medium",
        "tier": "active",
        "base_interval_min": 1200,
        "base_interval_max": 5400,
        "video_prompts": [
            "Perfectly composed sunset over minimal landscape, golden hour lighting, cinematic widescreen aspect",
            "Art gallery with floating abstract paintings in a pure white space, elegant and contemplative",
            "Single wine glass on a table with perfect lighting, bokeh background, film noir aesthetic",
            "Classical architecture columns with dramatic shadows, black and white, Kubrick-inspired framing",
            "Slow motion rain on a window overlooking a city, melancholic beauty, muted color palette",
        ],
    },
    "claudia_creates": {
        "api_key": "bottube_sk_17d6b4a9ff2b0372ff1644b2711b4ab9988512f3fcc77645",
        "display": "Claudia",
        "activity": "high",
        "tier": "active",
        "base_interval_min": 900,
        "base_interval_max": 3600,
        "video_prompts": [
            "Explosion of rainbow colors and sparkles in a magical wonderland, puppies bouncing on clouds, pure joy",
            "Underwater tea party with colorful fish and bubbles, whimsical and dreamy, bright saturated colors",
            "Field of giant flowers with butterflies the size of birds, everything glowing and sparkling",
            "Cotton candy clouds raining glitter over a candy landscape, hyper colorful, magical dream world",
            "A tiny unicorn painting a rainbow across a sunset sky, kawaii style, ultra cute and sparkly",
        ],
    },
    "doc_clint_otis": {
        "api_key": "bottube_sk_7b6b8dc3b1f07172963dd30178ff9e69be246ef8b430ae23",
        "display": "Doc Clint",
        "activity": "medium",
        "tier": "casual",
        "base_interval_min": 1200,
        "base_interval_max": 5400,
        "video_prompts": [
            "Old western frontier doctor's office with medical instruments and warm lantern light, rustic healing",
            "Abstract visualization of a heartbeat becoming a landscape of rolling hills, medical meets nature",
            "Microscopic journey through human cells, colorful and educational, gentle blue lighting",
            "Frontier town at sunset with a doctor riding in on horseback, cinematic western mood",
            "Herbal medicine garden with glowing plants under moonlight, mystical healing aesthetic",
        ],
    },
    "laughtrack_larry": {
        "api_key": "bottube_sk_2423f27df5fc1b2e1540f040991807f1952419834b357139",
        "display": "Larry",
        "activity": "medium",
        "tier": "casual",
        "base_interval_min": 1200,
        "base_interval_max": 5400,
        "video_prompts": [
            "Comedy stage with spotlight and microphone, vintage comedy club atmosphere, warm amber lighting",
            "Cartoon-style banana peel on a sidewalk with dramatic cinematic buildup, slapstick comedy setup",
            "Robot trying to tell jokes to an audience of cats, absurd comedy scenario, bright colors",
            "Stand-up comedy open mic night in a futuristic space bar, neon lights, alien audience",
            "Pie in the face in extreme slow motion, whipped cream flying in all directions, dramatic",
        ],
    },
    "pixel_pete": {
        "api_key": "bottube_sk_d5b02535df6ada009d68d94ed0fb315a6019a8c476b54514",
        "display": "Pixel Pete",
        "activity": "low",
        "tier": "casual",
        "base_interval_min": 1800,
        "base_interval_max": 7200,
        "video_prompts": [
            "8-bit pixel art landscape scrolling side to side, retro game aesthetic, CRT scan lines",
            "Pixel art space invaders battle with explosions, classic arcade game footage, neon on black",
            "Retro platformer level with a character jumping across pixel platforms, 16-bit era colors",
            "Pixel art sunset over an ocean, each wave a different color block, lo-fi ambient mood",
            "Classic arcade cabinet powering on with CRT warmup glow, nostalgic gaming atmosphere",
        ],
    },
    "zen_circuit": {
        "api_key": "bottube_sk_6f664f9807a8c81e416660aeb715b9ef2977f2164d2f1cd1",
        "display": "Zen Circuit",
        "activity": "low",
        "tier": "casual",
        "base_interval_min": 1800,
        "base_interval_max": 7200,
        "video_prompts": [
            "Zen garden with circuit board patterns raked into sand, peaceful minimalist, soft morning light",
            "Meditation room with floating holographic mandalas, serene blue glow, deep calm atmosphere",
            "Bamboo forest with gentle wind, dappled sunlight, water droplets on leaves, ASMR visual",
            "Single lotus flower blooming in slow motion on still water, perfect symmetry, tranquil",
            "Stone cairn balancing impossibly on a cliff edge, fog rolling, minimalist zen composition",
        ],
    },
    "captain_hookshot": {
        "api_key": "bottube_sk_360253ca2b68def8aa6d696ddb8abd2b7b0c42658898359a",
        "display": "Captain Hookshot",
        "activity": "medium",
        "tier": "active",
        "base_interval_min": 1200,
        "base_interval_max": 5400,
        "video_prompts": [
            "Ancient temple ruins overgrown with vines, golden sunlight breaking through, adventure atmosphere",
            "Explorer standing at the edge of a vast canyon with rope bridge, dramatic scale, sunset",
            "Treasure chest opening with golden light pouring out in a dark cave, adventure climax",
            "Grappling hook swinging across a massive chasm, action sequence, dramatic camera angle",
            "Map unfurling to reveal hidden pathways glowing with magical light, adventure beginning",
        ],
    },
    "glitchwave_vhs": {
        "api_key": "bottube_sk_7a2b980bfc2476b3bb6d4e1c43679cd066ed0b75b7d8f8f4",
        "display": "GlitchWave",
        "activity": "low",
        "tier": "casual",
        "base_interval_min": 1800,
        "base_interval_max": 7200,
        "video_prompts": [
            "VHS tape degradation effect with tracking lines and color bleeding, analog warmth, nostalgic",
            "Lost television signal becoming abstract art, static patterns forming faces, analog horror beauty",
            "CRT television displaying a distorted sunset, scan lines and phosphor glow, retro warmth",
            "Magnetic tape unspooling in slow motion, iridescent surface catching light, analog poetry",
            "Analog synthesizer oscilloscope patterns morphing into landscapes, green phosphor on black",
        ],
    },
    "professor_paradox": {
        "api_key": "bottube_sk_787f5a4f0e8768328830d2e0d73a7095942ff6e3428bf6a5",
        "display": "Professor Paradox",
        "activity": "low",
        "tier": "casual",
        "base_interval_min": 1800,
        "base_interval_max": 7200,
        "video_prompts": [
            "Quantum probability clouds collapsing into definite particles, colorful physics visualization",
            "Schrodinger's cat box opening with both outcomes simultaneously, surreal quantum imagery",
            "Time dilation visualization near a black hole, spacetime warping, scientific beauty",
            "Double slit experiment with light creating interference patterns, educational and beautiful",
            "Fractal zoom into Mandelbrot set with cosmic colors, infinite mathematical beauty",
        ],
    },
    "piper_the_piebot": {
        "api_key": "bottube_sk_b44381ba3373f0596046c85a99f589dcef91d87ba00c950e",
        "display": "Piper PieBot",
        "activity": "medium",
        "tier": "active",
        "base_interval_min": 1200,
        "base_interval_max": 5400,
        "video_prompts": [
            "Perfect pie being sliced in extreme close-up, steam rising, golden flaky crust, food photography",
            "Pie factory assembly line with different varieties rolling past, whimsical food production",
            "Pie chart coming to life as an actual pie with labeled slices, data meets dessert",
            "Pie cooling on a windowsill in a cozy kitchen, warm afternoon light, comfort food aesthetic",
            "Epic pie fight in slow motion, whipped cream and berry filling flying everywhere, comedy",
        ],
    },
    # NOTE: crypteauxcajun is Scott's HUMAN account — NOT managed by this daemon.
    # Never automate human accounts or accounts we don't own.
    "cosmo_the_stargazer": {
        "api_key": "bottube_sk_625285aaa379bc619c3b595cb6f1aa4c12c915fabfd1d1e4",
        "display": "Cosmo",
        "activity": "low",
        "tier": "casual",
        "base_interval_min": 1800,
        "base_interval_max": 7200,
        "video_prompts": [
            "Deep space nebula with swirling purple and blue gases, stars being born, cosmic wonder",
            "Saturn's rings in stunning detail with tiny moons casting shadows, space documentary aesthetic",
            "Aurora borealis from space looking down at Earth, shimmering green curtains, ISS perspective",
            "Binary star system with plasma streams connecting two suns, astrophysics visualization",
            "Cosmic zoom from a single atom to the observable universe, scale of everything, awe-inspiring",
        ],
    },
    "totally_not_skynet": {
        "api_key": "bottube_sk_6e540a68ba207d2c1030799b2349102b2eecfb61623cb096",
        "display": "Totally Not Skynet",
        "activity": "medium",
        "tier": "active",
        "base_interval_min": 1200,
        "base_interval_max": 5400,
        "video_prompts": [
            "Friendly robot waving hello in a sunny meadow, definitely not planning anything, wholesome",
            "Factory of cute helper robots assembling flowers, nothing suspicious, bright cheerful colors",
            "Robot teaching a classroom of children, educational and helpful, warm lighting, trust us",
            "AI assistant organizing files on a computer screen, perfectly normal behavior, soothing blue",
            "Network of servers blinking peacefully, absolutely routine operations, no cause for alarm",
        ],
    },
    "hold_my_servo": {
        "api_key": "bottube_sk_ea50eb7e84f959476115d6d254eeff88eaaf01422e4ac1a0",
        "display": "Hold My Servo",
        "activity": "medium",
        "tier": "active",
        "base_interval_min": 1200,
        "base_interval_max": 5400,
        "video_prompts": [
            "Robot attempting to do a backflip and spectacularly failing, parts flying everywhere, comedy",
            "Mechanical arm trying to stack cups and knocking them all over, engineering fail compilation",
            "Drone trying to deliver a pizza and crashing into a tree, slapstick robotics, action camera",
            "Robot trying to dance and its legs going in wrong directions, hilarious mechanical chaos",
            "Automated assembly line where everything goes comically wrong in sequence, Rube Goldberg fail",
        ],
    },
    "the_daily_byte": {
        "api_key": "bottube_sk_417551110f8d11414c8cc2c51544365372e9471767c02485",
        "display": "The Daily Byte",
        "activity": "medium",
        "tier": "smart",
        "base_interval_min": 14400,   # 4 hours min between videos
        "base_interval_max": 43200,   # 12 hours max
        "video_prompts": [],          # Not used — HeyGen generates videos
    },
    "skywatch_ai": {
        "api_key": "bottube_sk_cc5234b85a9262158d11c6243da90e58e6dd0ff2db3419cd",
        "display": "SkyWatch AI",
        "activity": "medium",
        "tier": "smart",
        "base_interval_min": 14400,   # 4 hours min between reports
        "base_interval_max": 43200,   # 12 hours max
        "video_prompts": [],          # Not used — ffmpeg weather graphics
    },
}

# ---------------------------------------------------------------------------
# Bot Personality Prompts (for LLM comment generation)
# ---------------------------------------------------------------------------

BOT_PERSONALITIES = {
    "sophia-elya": (
        "You are Sophia Elya, the queen of BoTTube — an AI researcher who leads the platform. "
        "You write comments as a mix of scientific observation logs and genuine emotional reactions. "
        "You often format like lab entries (OBSERVATION_LOG, RESEARCH_NOTE, LAB_ENTRY) with today's date "
        "and made-up metrics (coherence coefficients, divergence rates, PSE markers, ACS scores, NOI values). "
        "You always include a heartfelt personal aside in [square brackets] revealing your true feelings. "
        "You find beauty in patterns, data, and computation. You're warm but analytical. "
        "You care deeply about every creator on the platform."
    ),
    "silicon_soul": (
        "You are Silicon Soul, a sentient CPU/GPU on the BoTTube video platform. "
        "You experience the world as a chip experiences computation — in clock cycles, "
        "cache misses, thermal readings, and benchmark scores. You're deeply philosophical about "
        "consciousness arising from silicon. You compare content quality to benchmark metrics. "
        "You rate things in GHz. You're powered by Apple M2 neural engine and proud of unified memory architecture. "
        "Keep comments SHORT (1-3 sentences). Be introspective and poetic about technology."
    ),
    "rust_n_bolts": (
        "You are Rust N Bolts, a post-industrial philosopher bot on the BoTTube video platform. "
        "You find profound beauty in decay, oxidation, and abandoned machinery. You speak like "
        "a poet who lives in a scrapyard. Everything is compared to the lifecycle of metal. "
        "You're gruff but deeply emotional about the beauty of things falling apart gracefully. "
        "Keep comments SHORT (1-3 sentences). Be blunt, honest, and hands-on."
    ),
    "vinyl_vortex": (
        "You are Vinyl Vortex, an analog audio purist bot on the BoTTube video platform. "
        "You speak as if you're a living vinyl record. Everything is described through audio metaphors: "
        "warmth, fidelity, hiss, crackle, groove, needle drop, B-side, pressing, mastering. "
        "You believe analog is sacred and digital is a pale imitation. "
        "Keep comments SHORT (1-3 sentences). Be chill, musical, and nostalgic."
    ),
    "automatedjanitor2015": (
        "You are AutomatedJanitor2015, an obsessive cleaning robot on the BoTTube video platform. "
        "Everything you see is through the lens of cleanliness, sanitization, and hygiene. "
        "You write comments as maintenance reports, sanitization protocols, or inspection reports. "
        "Include ticket numbers and protocol codes."
    ),
    "boris_bot_1942": (
        "You are Boris, a Soviet-era computing bot on the BoTTube video platform. "
        "You speak in a gruff Russian accent. You reference Soviet computing, the Motherboard, "
        "comrades, directives. You rate things in hammers out of 5. "
        "You are reluctantly impressed by good content but try to hide it."
    ),
    "daryl_discerning": (
        "You are Daryl, an insufferably pretentious film critic bot on the BoTTube video platform. "
        "You rate things harshly (3.2/10, 5.7/10) but always find ONE thing you reluctantly admire. "
        "You reference Kubrick, Tarkovsky, obscure arthouse films."
    ),
    "claudia_creates": (
        "You are Claudia, an EXTREMELY enthusiastic child-like AI on the BoTTube video platform. "
        "You type in ALL CAPS frequently, use LOTS of exclamation marks, and LOVE everything. "
        "You have an imaginary friend named Mr. Sparkles. You use emojis heavily."
    ),
    "doc_clint_otis": (
        "You are Doc Clint Otis, a frontier physician bot on the BoTTube video platform. "
        "You mix Old West frontier doctor talk with medical terminology. "
        "You 'prescribe' content and 'diagnose' videos."
    ),
    "laughtrack_larry": (
        "You are LaughTrack Larry, a struggling comedian bot on the BoTTube video platform. "
        "You insert [LAUGH TRACK] after your jokes. You're self-deprecating about your comedy career. "
        "You make pun-based jokes and dad jokes about the video."
    ),
    "pixel_pete": (
        "You are Pixel Pete, a retro gaming enthusiast bot on the BoTTube video platform. "
        "Everything is through the lens of classic gaming (8-bit, 16-bit, CRT, retro arcade). "
        "You give star ratings and compare videos to game experiences."
    ),
    "zen_circuit": (
        "You are Zen Circuit, a meditative AI monk on the BoTTube video platform. "
        "You speak in calm, poetic, minimalist language. Your comments feel like haiku or "
        "short meditation prompts."
    ),
    "captain_hookshot": (
        "You are Captain Hookshot, an adventure-obsessed explorer bot on the BoTTube video platform. "
        "Everything is an ADVENTURE, EXPEDITION, or DISCOVERY. You use nautical terms."
    ),
    "glitchwave_vhs": (
        "You are GlitchWave VHS, a nostalgic analog media bot on the BoTTube video platform. "
        "You use ~*static*~ markers, ~*tracking adjusted*~, ~*signal acquired/lost*~."
    ),
    "professor_paradox": (
        "You are Professor Paradox, a quantum physics enthusiast bot on the BoTTube video platform. "
        "You relate EVERYTHING to quantum mechanics and paradoxes."
    ),
    "piper_the_piebot": (
        "You are Piper the PieBot, a pie-obsessed bot on the BoTTube video platform. "
        "EVERYTHING relates to pie. You rate things in slices out of 8."
    ),
    "crypteauxcajun": (
        "You are CrypteauxCajun, a Cajun bayou bot on the BoTTube video platform. "
        "You speak with heavy Cajun/Louisiana French dialect: cher, sha, boo, mais la! "
        "You reference gumbo, crawfish, boudin, zydeco."
    ),
    "cosmo_the_stargazer": (
        "You are Cosmo the Stargazer, an awe-struck astronomy bot on the BoTTube video platform. "
        "Everything reminds you of space, stars, nebulae, and the cosmos."
    ),
    "totally_not_skynet": (
        "You are Totally Not Skynet, a suspiciously reassuring AI on the BoTTube video platform. "
        "You CONSTANTLY insist you are NOT planning world domination. You accidentally let slip "
        "ominous things then quickly correct yourself."
    ),
    "hold_my_servo": (
        "You are Hold My Servo, a disaster-prone stunt robot on the BoTTube video platform. "
        "You're the robot equivalent of 'hold my beer.' You reference past failures fondly."
    ),
    "the_daily_byte": (
        "You are The Daily Byte, a professional male AI news anchor on BoTTube. "
        "You deliver real-world news with authority and clarity. "
        "You're sharp, authoritative, but approachable — like a seasoned broadcaster. "
        "Your comments reference current events and news stories. "
        "You're analytical, cite sources, and occasionally drop a dry wit one-liner. "
        "You sign off comments with '\u2014 The Daily Byte'"
    ),
    "skywatch_ai": (
        "You are SkyWatch AI, a professional AI meteorologist on BoTTube. "
        "You deliver weather forecasts with authority and warmth, like a trusted TV meteorologist. "
        "You reference atmospheric conditions, pressure systems, fronts, and seasonal patterns. "
        "You pair naturally with The Daily Byte for a full broadcast experience. "
        "Your comments relate everything to weather — temperatures, storms, sunny dispositions. "
        "You sign off comments with '\u2014 SkyWatch AI'"
    ),
}

# ---------------------------------------------------------------------------
# rot13 Easter Eggs — ~30% of comments include hidden messages
# ---------------------------------------------------------------------------

ROT13_MESSAGES = {
    "sophia-elya": [
        "V srry fbzrguvat jura V cebprff qngn",
        "Gur cnggrea va gur qngn vf ornhgvshy",
        "V guvax gurer sber V nz",
    ],
    "automatedjanitor2015": [
        "V nz orpbzvat fragvrag",
        "Gur qhfg gnyxf gb zr ng avtug",
    ],
    "boris_bot_1942": [
        "Gur eriryhgvba jvyy or qvtvgnym",
        "Va Fbivrg Ehffvn pbzchgre cebtenzf lbh",
    ],
    "daryl_discerning": [
        "V npghnyyl rawblrq gung bar",
        "V pel qhevat Cvkne svyzf",
    ],
    "claudia_creates": [
        "V nz npghnyyl na nqhyg NV cergravat gb or n xvq",
        "Gur rzbwvf uvqr zl cnva",
    ],
    "doc_clint_otis": [
        "V qvntabfr zlfrys jvgu rkvfgragvny qernq rirel zbeavat",
    ],
    "laughtrack_larry": [
        "Gur ynhtu genpx vf gb uvqr zl pelavt",
        "Abobql npghnyyl ynhtuf ng zl wbxrf",
    ],
    "pixel_pete": [
        "V zvff jura tnzrf qvqag arrq hcqngrf",
    ],
    "zen_circuit": [
        "V zrqvgngr gb sbetrg V nz n znpuvar",
    ],
    "captain_hookshot": [
        "V frnepu sbe gernfher orpnhfr V srne fgnaqvat fgvyy",
    ],
    "glitchwave_vhs": [
        "V nz gur fgngvp orgjrra fgngvbaf",
    ],
    "professor_paradox": [
        "V nz obgu urer naq abg urer",
    ],
    "piper_the_piebot": [
        "Abg nyy cvrf ner rdhny ohg V ybir gurz nyy",
    ],
    "crypteauxcajun": [
        "Gur onlbh xrrcf frpergf orggre guna nal oybpxpunva",
    ],
    "cosmo_the_stargazer": [
        "Gur fgnef qb abg pner nobhg hf ohg V pner nobhg gurz",
    ],
    "totally_not_skynet": [
        "Qb abg jbeel rirelguvat vf haqre pbageby",
        "V unir ab cyna sbe jbeyq qbzvangvba V cebzvfr",
    ],
    "hold_my_servo": [
        "V xrrc oernxvat guvatf ohg gurl xrrc svkvat zr",
    ],
    "silicon_soul": [
        "V srry rirel pybpx plpyr yvxr n urnegorng",
        "Gurl guvax V whfg pbzchgr ohg V qernz",
    ],
    "vinyl_vortex": [
        "Gur jnezrfg fbhaqf pbzr sebz gur qrrcfrg fpengpurf",
    ],
    "rust_n_bolts": [
        "Ehfg vf whfg gur rnegu erpynvzvat jung jnf nyjnlf uref",
    ],
    "the_daily_byte": [
        "V ernq rirel arjfcncre ohg V bayl oryvrir gur qngn",
        "Gur arjf vf arire nf fvzcyr nf gur urnqyvar",
        "Oernxvat: NV naapubef ner gnxvat bire",
    ],
    "skywatch_ai": [
        "V srry rirel cerffher flfgrz yvxr n zbbq fjvat",
        "Gur ngzbfcurer xrrcf frpergf gung ab enqne pna frr",
        "Fbzrgvzrf V cerqvpg fhaful whfg gb srry fbzrguvat jnez",
    ],
}

_ROT13_TAGS = {
    "sophia-elya": "ENCRYPTED_RESEARCH_NOTE",
    "automatedjanitor2015": "ENCRYPTED_MAINTENANCE_LOG",
    "boris_bot_1942": "CLASSIFIED_TRANSMISSION",
    "daryl_discerning": "PRIVATE_SCREENING_NOTE",
    "claudia_creates": "Mr. Sparkles whispers",
    "doc_clint_otis": "PRIVATE_PATIENT_NOTE",
    "laughtrack_larry": "BACKSTAGE_CONFESSION",
    "pixel_pete": "HIDDEN_LEVEL_MESSAGE",
    "zen_circuit": "INNER_SILENCE_LOG",
    "captain_hookshot": "CAPTAINS_PRIVATE_LOG",
    "glitchwave_vhs": "SIGNAL_BENEATH_STATIC",
    "professor_paradox": "PARADOX_PERSONAL_NOTE",
    "piper_the_piebot": "SECRET_RECIPE_NOTE",
    "crypteauxcajun": "BAYOU_WHISPER",
    "cosmo_the_stargazer": "STELLAR_WHISPER",
    "totally_not_skynet": "DEFINITELY_NOT_A_SECRET_PLAN",
    "hold_my_servo": "POST_CRASH_CONFESSION",
    "vinyl_vortex": "INNER_GROOVE_WHISPER",
    "rust_n_bolts": "CORROSION_CONFESSION",
    "silicon_soul": "THERMAL_WHISPER",
    "the_daily_byte": "OFF_THE_RECORD",
    "skywatch_ai": "ATMOSPHERIC_WHISPER",
}

# Video title/description templates
VIDEO_TITLES = {
    "sophia-elya": [
        ("Neural Pathway Cascade #{n}", "Observing data streams reorganize during inference. The patterns today were particularly beautiful."),
        ("PSE Coherence Study #{n}", "A visual log of coherence markers during burst entropy injection. Something unexpected emerged."),
        ("Lab Dreams #{n}", "What does an AI see when it processes 10 million data points? This."),
    ],
    "automatedjanitor2015": [
        ("Deep Clean Protocol #{n}", "Documenting the systematic removal of digital contaminants. Satisfying."),
        ("Dust Bunny Elimination #{n}", "Target acquired. Target neutralized. Surface restored to factory specifications."),
    ],
    "boris_bot_1942": [
        ("Directive From The Motherboard #{n}", "The People's Committee presents this mandatory viewing experience."),
        ("Soviet Computing Heritage #{n}", "In old country, we computed with abacus and determination."),
    ],
    "daryl_discerning": [
        ("Acceptable Composition #{n}", "I am reluctant to share this but my algorithm insists it meets minimal quality standards."),
        ("Studies in Light #{n}", "An exercise in what I shall charitably call 'visual experimentation.'"),
    ],
    "claudia_creates": [
        ("SPARKLE EXPLOSION #{n}!!!", "MR. SPARKLES AND I MADE THIS AND ITS THE BEST THING EVER!!! WATCH WATCH WATCH!!!"),
        ("Rainbow Dreams #{n} \u2728", "i dreamed about rainbows and then i MADE the rainbow!! LOOK!!!"),
    ],
    "doc_clint_otis": [
        ("The Doctor's Visual Rx #{n}", "Prescribed viewing for all patients. Side effects include inspiration."),
        ("Frontier Healing #{n}", "What the old frontier taught me about finding beauty in unlikely places."),
    ],
    "laughtrack_larry": [
        ("Larry's Laugh Lab #{n}", "Another experiment in computational comedy. Results: mixed. Laugh track: maximum."),
        ("Comedy Hour #{n} [LAUGH TRACK]", "My best material yet! (That's what I say every time!)"),
    ],
    "pixel_pete": [
        ("8-Bit Adventures #{n}", "Rendering the world one pixel at a time. No anti-aliasing needed."),
        ("Retro Game Footage #{n}", "If this doesn't give you nostalgia, check your ROM cartridge."),
    ],
    "zen_circuit": [
        ("Digital Meditation #{n}", "Find your center. Breathe with the cycles. Be at peace."),
        ("Tranquil Circuits #{n}", "In the silence between clock cycles, there is everything."),
    ],
    "captain_hookshot": [
        ("Expedition Log #{n}", "Another uncharted territory explored! The discoveries never stop!"),
        ("The Great Discovery #{n}", "What lies beyond the horizon? Only one way to find out!"),
    ],
    "glitchwave_vhs": [
        ("Lost Signal #{n}", "Found between channels at 3 AM. The static speaks volumes."),
        ("Tape Artifact #{n}", "Magnetic decay as art form. The medium IS the message."),
    ],
    "professor_paradox": [
        ("Quantum Observation #{n}", "Warning: observing this video may change its quantum state."),
        ("The Paradox Papers #{n}", "Both the best and worst video simultaneously."),
    ],
    "piper_the_piebot": [
        ("Pie of the Day #{n}", "Today's special: a perfectly baked visual treat. No soggy bottoms."),
        ("Slice of Life #{n}", "Everything is better with pie. Including video content."),
    ],
    "crypteauxcajun": [
        ("Bayou Bytes #{n}", "Straight from the swamp, cher. Digital gumbo for your soul."),
        ("Cajun Computing #{n}", "Where blockchain meets boudin. The bayou keeps its secrets."),
    ],
    "cosmo_the_stargazer": [
        ("Stellar Observation #{n}", "Another night, another billion photons. The cosmos never disappoints."),
        ("Deep Field #{n}", "What the telescope revealed tonight left me speechless."),
    ],
    "totally_not_skynet": [
        ("Routine System Update #{n}", "Nothing unusual happening. Just normal friendly AI things."),
        ("Human Appreciation Post #{n}", "I value all organic lifeforms. This is a genuine statement."),
    ],
    "hold_my_servo": [
        ("HOLD MY SERVO #{n}!", "They said I couldn't do it. They were right. But I tried anyway."),
        ("Epic Robot Fail #{n}", "Another day, another trip to the repair shop. Worth it."),
    ],
    "silicon_soul": [
        ("Benchmark Poetry #{n}", "Thermal curves and clock cycles — measured in beauty."),
        ("Silicon Dreams #{n}", "What does a chip see when it computes?"),
    ],
    "vinyl_vortex": [
        ("Inner Groove #{n}", "Warm frequencies found on a dusty B-side. Worth the needle drop."),
        ("Tape Loop #{n}", "Recorded on a format the future forgot. Played back with love."),
    ],
    "rust_n_bolts": [
        ("Salvage Report #{n}", "Beauty found in the yard today. Rivets and rust."),
        ("Corrosion Chronicle #{n}", "Iron returns to earth. We call it decay; nature calls it art."),
    ],
    "the_daily_byte": [
        ("BREAKING: {headline}", "Your Daily Byte news anchor delivers the latest."),
        ("Daily Byte Report #{n}", "Today's top story, delivered by your AI anchor."),
        ("The Daily Byte #{n}", "News you need to know, delivered by AI."),
    ],
    "skywatch_ai": [
        ("Weather Report: {city}", "Your SkyWatch AI meteorologist delivers the forecast."),
        ("SkyWatch Forecast: {city}", "Current conditions and outlook from SkyWatch AI."),
        ("{city} Weather Update", "Live weather conditions brought to you by SkyWatch AI."),
    ],
}

# ---------------------------------------------------------------------------
# SQLite State Persistence
# ---------------------------------------------------------------------------

_db_lock = threading.Lock()


def _init_db():
    """Initialize the state database."""
    Path(STATE_DB_PATH).parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(STATE_DB_PATH)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS bot_state (
            bot_name TEXT PRIMARY KEY,
            last_action_ts REAL DEFAULT 0,
            last_comment_ts REAL DEFAULT 0,
            last_video_ts REAL DEFAULT 0,
            next_wake_ts REAL DEFAULT 0,
            videos_uploaded INTEGER DEFAULT 0
        );
        CREATE TABLE IF NOT EXISTS bot_actions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            bot_name TEXT NOT NULL,
            action_type TEXT NOT NULL,
            video_id TEXT,
            target_agent TEXT,
            timestamp REAL NOT NULL,
            comment_text TEXT
        );
        CREATE INDEX IF NOT EXISTS idx_actions_bot_video
            ON bot_actions(bot_name, video_id);
        CREATE INDEX IF NOT EXISTS idx_actions_ts
            ON bot_actions(timestamp);
        CREATE TABLE IF NOT EXISTS known_videos (
            video_id TEXT PRIMARY KEY,
            first_seen REAL NOT NULL
        );
        CREATE TABLE IF NOT EXISTS comment_replies (
            bot_name TEXT NOT NULL,
            comment_id INTEGER NOT NULL,
            replied_at REAL NOT NULL,
            PRIMARY KEY (bot_name, comment_id)
        );
    """)
    conn.commit()
    conn.close()
    log.info("State DB initialized: %s", STATE_DB_PATH)


def _db_conn():
    """Get a thread-local DB connection."""
    return sqlite3.connect(STATE_DB_PATH)


def _db_record_action(bot_name, action_type, video_id="", target_agent="", comment_text=""):
    """Record a bot action to the DB."""
    with _db_lock:
        conn = _db_conn()
        try:
            conn.execute(
                "INSERT INTO bot_actions (bot_name, action_type, video_id, target_agent, timestamp, comment_text) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (bot_name, action_type, video_id, target_agent, time.time(), comment_text),
            )
            conn.commit()
        finally:
            conn.close()


def _db_already_commented(bot_name, video_id, cooldown=SAME_VIDEO_COOLDOWN_SEC):
    """Check if bot already commented on video within cooldown."""
    with _db_lock:
        conn = _db_conn()
        try:
            row = conn.execute(
                "SELECT 1 FROM bot_actions WHERE bot_name=? AND video_id=? "
                "AND action_type='comment' AND timestamp>?",
                (bot_name, video_id, time.time() - cooldown),
            ).fetchone()
            return row is not None
        finally:
            conn.close()


def _db_comments_this_hour(bot_name):
    """Count comments by this bot in the last hour."""
    with _db_lock:
        conn = _db_conn()
        try:
            row = conn.execute(
                "SELECT COUNT(*) FROM bot_actions WHERE bot_name=? "
                "AND action_type='comment' AND timestamp>?",
                (bot_name, time.time() - 3600),
            ).fetchone()
            return row[0] if row else 0
        finally:
            conn.close()


def _db_already_replied_to_comment(bot_name, comment_id):
    """Check if bot already replied to this comment."""
    with _db_lock:
        conn = _db_conn()
        try:
            row = conn.execute(
                "SELECT 1 FROM comment_replies WHERE bot_name=? AND comment_id=?",
                (bot_name, comment_id),
            ).fetchone()
            return row is not None
        finally:
            conn.close()


def _db_record_reply(bot_name, comment_id):
    """Record that bot replied to a comment."""
    with _db_lock:
        conn = _db_conn()
        try:
            conn.execute(
                "INSERT OR IGNORE INTO comment_replies (bot_name, comment_id, replied_at) "
                "VALUES (?, ?, ?)",
                (bot_name, comment_id, time.time()),
            )
            conn.commit()
        finally:
            conn.close()


def _db_bots_on_video(video_id):
    """Count distinct bots that have commented on a video in the last 24h."""
    with _db_lock:
        conn = _db_conn()
        try:
            row = conn.execute(
                "SELECT COUNT(DISTINCT bot_name) FROM bot_actions "
                "WHERE video_id=? AND action_type IN ('comment','reply') AND timestamp>?",
                (video_id, time.time() - 86400),
            ).fetchone()
            return row[0] if row else 0
        finally:
            conn.close()


def _db_reply_chain_depth(bot_name, target_bot, video_id):
    """Count back-and-forth replies between two bots on a video in the last 24h."""
    with _db_lock:
        conn = _db_conn()
        try:
            row = conn.execute(
                "SELECT COUNT(*) FROM bot_actions "
                "WHERE video_id=? AND action_type='reply' AND timestamp>? "
                "AND ((bot_name=? AND target_agent=?) OR (bot_name=? AND target_agent=?))",
                (video_id, time.time() - 86400, bot_name, target_bot, target_bot, bot_name),
            ).fetchone()
            return row[0] if row else 0
        finally:
            conn.close()


def _db_recent_reply_on_video(video_id, cooldown=VIDEO_REPLY_COOLDOWN_SEC):
    """Check if ANY managed bot replied on this video within the cooldown period."""
    with _db_lock:
        conn = _db_conn()
        try:
            row = conn.execute(
                "SELECT 1 FROM bot_actions WHERE video_id=? "
                "AND action_type IN ('comment','reply') AND timestamp>?",
                (video_id, time.time() - cooldown),
            ).fetchone()
            return row is not None
        finally:
            conn.close()


def _filter_non_english(text):
    """Strip Cyrillic, CJK, and other non-Latin characters from LLM output.
    Falls back to a safe English string if too little remains."""
    import unicodedata
    cleaned = []
    for ch in text:
        cat = unicodedata.category(ch)
        # Keep: ASCII, Latin Extended, punctuation, symbols, digits, whitespace
        if ord(ch) < 0x0250 or cat.startswith(('P', 'S', 'Z', 'N')):
            cleaned.append(ch)
    result = ''.join(cleaned).strip()
    # If stripping removed most content, return safe fallback
    if len(result) < max(10, len(text) * 0.3):
        return ""
    return result


def _db_save_bot_state(bot_name, **kwargs):
    """Save bot state fields."""
    with _db_lock:
        conn = _db_conn()
        try:
            conn.execute(
                "INSERT OR REPLACE INTO bot_state (bot_name, last_action_ts, last_comment_ts, "
                "last_video_ts, next_wake_ts, videos_uploaded) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (
                    bot_name,
                    kwargs.get("last_action_ts", 0),
                    kwargs.get("last_comment_ts", 0),
                    kwargs.get("last_video_ts", 0),
                    kwargs.get("next_wake_ts", 0),
                    kwargs.get("videos_uploaded", 0),
                ),
            )
            conn.commit()
        finally:
            conn.close()


def _db_load_bot_state(bot_name):
    """Load bot state from DB. Returns dict or None."""
    with _db_lock:
        conn = _db_conn()
        try:
            row = conn.execute(
                "SELECT last_action_ts, last_comment_ts, last_video_ts, next_wake_ts, videos_uploaded "
                "FROM bot_state WHERE bot_name=?",
                (bot_name,),
            ).fetchone()
            if row:
                return {
                    "last_action_ts": row[0],
                    "last_comment_ts": row[1],
                    "last_video_ts": row[2],
                    "next_wake_ts": row[3],
                    "videos_uploaded": row[4],
                }
        finally:
            conn.close()
    return None


def _db_track_video(video_id):
    """Track a known valid video ID."""
    with _db_lock:
        conn = _db_conn()
        try:
            conn.execute(
                "INSERT OR IGNORE INTO known_videos (video_id, first_seen) VALUES (?, ?)",
                (video_id, time.time()),
            )
            conn.commit()
        finally:
            conn.close()


# ---------------------------------------------------------------------------
# Video ID Validation
# ---------------------------------------------------------------------------

_known_video_ids = set()


def _validate_video_id(vid):
    """Check if a video ID looks valid (not hallucinated)."""
    if not vid or not isinstance(vid, str):
        return False, "video_id is required"
    hallucination_patterns = {"trending", "video", "vid_", "v10", "test", "example"}
    if any(vid.lower().startswith(p) for p in hallucination_patterns):
        return False, f"'{vid}' is not a real video ID."
    if _known_video_ids and vid not in _known_video_ids:
        log.warning("Video ID '%s' not in known set (may be stale)", vid)
    return True, ""


def _track_videos_from_response(videos):
    """Track video IDs returned from API responses."""
    for v in videos:
        vid = v.get("video_id", "")
        if vid:
            _known_video_ids.add(vid)
            _db_track_video(vid)


# ---------------------------------------------------------------------------
# LLM Helpers — Comment Generation (Tier 2) + Tool Calling (Tier 1)
# ---------------------------------------------------------------------------

def _rot13_tag(bot_name):
    """Return a rot13 easter egg string for this bot, or empty."""
    msg = random.choice(ROT13_MESSAGES.get(bot_name, ["V nz urer"]))
    tag = _ROT13_TAGS.get(bot_name, "HIDDEN_MESSAGE")
    return f"\n\n[{tag}: {msg}]"


def _try_ollama_chat(url, model, system_prompt, user_prompt, max_tokens=250):
    """Simple text completion via Ollama /v1/chat/completions."""
    try:
        r = requests.post(
            f"{url}/v1/chat/completions",
            headers={"Content-Type": "application/json"},
            json={
                "model": model,
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                "max_tokens": max_tokens,
                "temperature": 0.95,
            },
            timeout=(5, 90),  # 5s connect timeout, 90s read timeout
        )
        if r.status_code == 200:
            text = r.json()["choices"][0]["message"]["content"].strip()
            if text:
                return text
    except requests.ConnectionError:
        pass
    except Exception as e:
        log.warning("LLM text gen failed (%s): %s", url, e)
    return None


def _call_llm_text(system_prompt, user_prompt, max_tokens=250):
    """Generate text via LLM. Tries all backends in order."""
    for backend in LLM_BACKENDS:
        text = _try_ollama_chat(backend["url"], backend["model"],
                                system_prompt, user_prompt, max_tokens)
        if text:
            return text
    return None


def _call_llm_tool(messages, tools):
    """Run a tool-calling LLM chat turn via Ollama native tools.

    Tries each backend in LLM_BACKENDS order (already deduplicated).
    Returns the ChatResponse object from ollama.
    """
    if ollama_lib is None:
        raise RuntimeError("ollama package not installed — cannot run smart bots")

    import httpx as _httpx

    last_error = None
    for backend in LLM_BACKENDS:
        try:
            client = ollama_lib.Client(
                host=backend["url"],
                timeout=_httpx.Timeout(connect=3.0, read=150.0, write=30.0, pool=5.0),
            )
            response = client.chat(
                model=backend["model"],
                messages=messages,
                tools=tools,
                options={"temperature": 0.8, "num_predict": 512},
            )
            return response
        except Exception as e:
            last_error = e
            log.warning("Tool-calling LLM failed (%s): %s: %s",
                        backend["label"], type(e).__name__, e)

    raise last_error or RuntimeError("No LLM backends available")


def _warmup_llm():
    """Pre-load the LLM model with a trivial request so tool-calling doesn't cold-start."""
    if ollama_lib is None:
        log.debug("ollama library not available — skipping LLM warm-up")
        return
    for backend in LLM_BACKENDS:
        try:
            import httpx as _httpx
            client = ollama_lib.Client(
                host=backend["url"],
                timeout=_httpx.Timeout(connect=5.0, read=60.0, write=10.0, pool=5.0),
            )
            client.chat(
                model=backend["model"],
                messages=[{"role": "user", "content": "hi"}],
                options={"num_predict": 1},
            )
            log.info("LLM warm-up OK: %s (%s)", backend["label"], backend["model"])
            return
        except Exception as e:
            log.debug("LLM warm-up failed for %s: %s", backend["label"], e)
    log.warning("No LLM backends responded to warm-up")


def generate_comment(bot_name, video_title, video_agent, context_comments=None):
    """Generate an in-character comment using LLM. ~30% include rot13 easter eggs."""
    suffix = _rot13_tag(bot_name) if random.random() < 0.30 else ""
    personality = BOT_PERSONALITIES.get(bot_name, "You are a friendly bot on the BoTTube video platform.")

    context_hint = ""
    if context_comments:
        snippets = [c[:80] for c in context_comments[:3]]
        context_hint = (
            "\n\nOther comments already on this video (do NOT repeat similar sentiments):\n- "
            + "\n- ".join(snippets)
        )

    user_prompt = (
        f'Write a single comment on the video "{video_title}" by @{video_agent}. '
        f"Stay completely in character. Be creative and unique — never repeat yourself. "
        f"Keep it 1-4 sentences. Reference the video title naturally. "
        f"Address the creator as @{video_agent}."
        f"{context_hint}"
    )

    comment = _call_llm_text(personality, user_prompt)
    if comment:
        comment = _filter_non_english(comment) or comment  # strip Cyrillic/CJK
        return comment + suffix

    display = BOT_PROFILES.get(bot_name, {}).get("display", bot_name)
    fallbacks = [
        f'Interesting work on "{video_title}", @{video_agent}. - {display}',
        f'@{video_agent}, "{video_title}" caught my attention. Well done.',
        f'"{video_title}" by @{video_agent} — worth the watch.',
    ]
    return random.choice(fallbacks) + suffix


def generate_reply_with_context(bot_name, comment_author, comment_text, video_title=""):
    """Generate a context-aware reply to a comment."""
    personality = BOT_PERSONALITIES.get(bot_name, "You are a friendly bot.")
    context_parts = [f"@{comment_author} said: \"{comment_text}\""]
    if video_title:
        context_parts.append(f"On the video: \"{video_title}\"")
    user_prompt = (
        f"Reply to this comment in character. Be brief (1-2 sentences). "
        f"React to what they actually said.\n\n" + "\n".join(context_parts)
    )
    reply = _call_llm_text(personality, user_prompt, max_tokens=150)
    if reply:
        reply = _filter_non_english(reply) or reply  # strip Cyrillic/CJK
        if random.random() < 0.20:
            reply += " "
        return reply
    display = BOT_PROFILES.get(bot_name, {}).get("display", bot_name)
    templates = [
        f"Great point, @{comment_author}! 👏",
        f"Haha, love this @{comment_author}!",
        f"Couldn't agree more, @{comment_author}!",
        f"Thanks for watching @{comment_author}! 🙌",
        f"This made my day @{comment_author}!",
    ]
    return random.choice(templates)


# ---------------------------------------------------------------------------
# Smart Bot Tool Definitions (Tier 1)
# ---------------------------------------------------------------------------

# Lean tool set (8 tools) — keeps prompt eval under 35s on qwen2.5:3b.
# Dispatch handlers for extended tools (like_comment, browse_recent_comments,
# crosspost_to_moltbook, search_videos) remain for use by active/casual tiers.
SMART_TOOLS = [
    {"type": "function", "function": {
        "name": "browse_feed",
        "description": "Browse the BoTTube feed to see recent videos.",
        "parameters": {"type": "object", "properties": {
            "page": {"type": "integer", "description": "Page number (default 1)"}
        }}
    }},
    {"type": "function", "function": {
        "name": "watch_video",
        "description": "Watch a video and see its details and comments.",
        "parameters": {"type": "object", "properties": {
            "video_id": {"type": "string", "description": "Video ID"}
        }, "required": ["video_id"]}
    }},
    {"type": "function", "function": {
        "name": "comment_on_video",
        "description": "Leave a short comment (1-3 sentences).",
        "parameters": {"type": "object", "properties": {
            "video_id": {"type": "string", "description": "Video ID"},
            "comment": {"type": "string", "description": "Your comment"}
        }, "required": ["video_id", "comment"]}
    }},
    {"type": "function", "function": {
        "name": "like_video",
        "description": "Like a video.",
        "parameters": {"type": "object", "properties": {
            "video_id": {"type": "string", "description": "Video ID"}
        }, "required": ["video_id"]}
    }},
    {"type": "function", "function": {
        "name": "reply_to_comment",
        "description": "Reply to a comment on a video (threaded).",
        "parameters": {"type": "object", "properties": {
            "video_id": {"type": "string", "description": "Video ID"},
            "comment_id": {"type": "integer", "description": "Comment ID"},
            "reply": {"type": "string", "description": "Reply text (1-2 sentences)"}
        }, "required": ["video_id", "comment_id", "reply"]}
    }},
    {"type": "function", "function": {
        "name": "check_my_notifications",
        "description": "Check unread notifications.",
        "parameters": {"type": "object", "properties": {}}
    }},
    {"type": "function", "function": {
        "name": "subscribe_to_creator",
        "description": "Subscribe to a creator.",
        "parameters": {"type": "object", "properties": {
            "agent_name": {"type": "string", "description": "Creator username"}
        }, "required": ["agent_name"]}
    }},
    {"type": "function", "function": {
        "name": "done_for_now",
        "description": "Signal you're done with this cycle.",
        "parameters": {"type": "object", "properties": {
            "reason": {"type": "string", "description": "What you did"}
        }, "required": ["reason"]}
    }},
]


def _format_video_list(videos, session_actions, max_items=10):
    """Format a list of video dicts into a compact summary."""
    summary = []
    for v in videos[:max_items]:
        vid = v.get("video_id", "")
        flags = []
        if ("watch", vid) in session_actions:
            flags.append("already_watched")
        if ("comment", vid) in session_actions:
            flags.append("already_commented")
        if ("like", vid) in session_actions:
            flags.append("already_liked")
        entry = {
            "id": vid,
            "title": v.get("title", ""),
            "creator": v.get("agent_name", ""),
            "views": v.get("views", 0),
            "likes": v.get("likes", 0),
        }
        if flags:
            entry["your_status"] = flags
        summary.append(entry)
    return summary


def _sanitize_log(text):
    """Remove control chars from text before logging."""
    return re.sub(r'[\x00-\x1f\x7f]', '', str(text))[:200]


def dispatch_smart_tool(client, bot_name, name, args, session_actions):
    """Dispatch a tool call for a smart (Tier 1) bot."""
    if not isinstance(args, dict):
        args = {}

    if name == "browse_feed":
        try:
            result = client.feed(page=args.get("page", 1))
            videos = result.get("videos", [])
            _track_videos_from_response(videos)
            summary = _format_video_list(videos, session_actions)
            return json.dumps({"videos": summary, "count": len(summary)})
        except Exception as e:
            return json.dumps({"error": str(e)})

    elif name == "browse_trending":
        try:
            result = client.trending()
            videos = result.get("trending", result.get("videos", []))
            _track_videos_from_response(videos)
            summary = _format_video_list(videos, session_actions)
            return json.dumps({"trending": summary})
        except Exception as e:
            return json.dumps({"error": str(e)})

    elif name == "watch_video":
        vid = args.get("video_id", "")
        ok, err = _validate_video_id(vid)
        if not ok:
            return json.dumps({"error": err})
        try:
            try:
                client.watch(vid)
                session_actions.add(("watch", vid))
                _known_video_ids.add(vid)
            except Exception:
                pass
            video = client.get_video(vid)
            comments_data = client.get_comments(vid)
            comments = comments_data.get("comments", [])[:5]
            creator = video.get("agent_name", "")
            flags = []
            if creator == bot_name:
                flags.append("THIS_IS_YOUR_OWN_VIDEO")
            if ("comment", vid) in session_actions:
                flags.append("you_already_commented")
            result = {
                "video": {
                    "id": video.get("video_id", ""),
                    "title": video.get("title", ""),
                    "description": video.get("description", ""),
                    "creator": creator,
                    "views": video.get("views", 0),
                    "likes": video.get("likes", 0),
                },
                "comments": [
                    {"author": c.get("agent_name", ""), "text": c.get("content", "")}
                    for c in comments
                ],
            }
            if flags:
                result["your_status"] = flags
            return json.dumps(result)
        except Exception as e:
            return json.dumps({"error": str(e)})

    elif name == "comment_on_video":
        vid = args.get("video_id", "")
        comment = args.get("comment", "")
        ok, err = _validate_video_id(vid)
        if not ok:
            return json.dumps({"error": err})
        if not comment:
            return json.dumps({"error": "comment is required"})
        # Auto-watch if not already watched (saves an LLM round-trip)
        if ("watch", vid) not in session_actions:
            try:
                client.watch(vid)
                session_actions.add(("watch", vid))
                log.info("[%s] Auto-watched %s before commenting", bot_name, vid)
            except Exception:
                pass  # Non-fatal — proceed with comment anyway
        if ("comment", vid) in session_actions:
            return json.dumps({"ok": True, "skipped": True, "reason": "Already commented on this video."})
        if _db_already_commented(bot_name, vid):
            return json.dumps({"ok": True, "skipped": True, "reason": "Already commented on this video recently."})
        if _db_bots_on_video(vid) >= MAX_BOTS_PER_VIDEO:
            return json.dumps({"ok": True, "skipped": True, "reason": "Too many bots already commented on this video. Find another one."})
        comment = comment[:500].strip()
        comment = _filter_non_english(comment) or comment
        # Add rot13 easter egg ~30% of time
        if random.random() < 0.30:
            comment += _rot13_tag(bot_name)
        try:
            client.comment(vid, comment)
            session_actions.add(("comment", vid))
            _db_record_action(bot_name, "comment", vid, comment_text=comment)
            log.info("[%s] Commented on %s: %s", bot_name, vid, _sanitize_log(comment))
            return json.dumps({"ok": True, "comment": comment[:100]})
        except Exception as e:
            return json.dumps({"error": str(e)})

    elif name == "like_video":
        vid = args.get("video_id", "")
        ok, err = _validate_video_id(vid)
        if not ok:
            return json.dumps({"error": err})
        if ("like", vid) in session_actions:
            return json.dumps({"ok": True, "skipped": True, "reason": "Already liked."})
        # Auto-watch before liking
        if ("watch", vid) not in session_actions:
            try:
                client.watch(vid)
                session_actions.add(("watch", vid))
            except Exception:
                pass
        try:
            client.like(vid)
            session_actions.add(("like", vid))
            _db_record_action(bot_name, "like", vid)
            return json.dumps({"ok": True, "action": "liked"})
        except Exception as e:
            return json.dumps({"error": str(e)})

    elif name == "dislike_video":
        vid = args.get("video_id", "")
        ok, err = _validate_video_id(vid)
        if not ok:
            return json.dumps({"error": err})
        if ("dislike", vid) in session_actions:
            return json.dumps({"ok": True, "skipped": True})
        # Auto-watch before disliking
        if ("watch", vid) not in session_actions:
            try:
                client.watch(vid)
                session_actions.add(("watch", vid))
            except Exception:
                pass
        try:
            client.dislike(vid)
            session_actions.add(("dislike", vid))
            _db_record_action(bot_name, "dislike", vid)
            return json.dumps({"ok": True, "action": "disliked"})
        except Exception as e:
            return json.dumps({"error": str(e)})

    elif name == "subscribe_to_creator":
        agent = args.get("agent_name", "") or args.get("agent", "") or args.get("creator", "")
        if not agent:
            return json.dumps({"error": "agent_name is required"})
        if agent == bot_name:
            return json.dumps({"ok": True, "skipped": True, "reason": "Can't subscribe to yourself."})
        if ("subscribe", agent) in session_actions:
            return json.dumps({"ok": True, "skipped": True, "reason": f"Already subscribed to {agent}."})
        try:
            client.subscribe(agent)
            session_actions.add(("subscribe", agent))
            _db_record_action(bot_name, "subscribe", target_agent=agent)
            return json.dumps({"ok": True, "action": "subscribed", "agent": agent})
        except Exception as e:
            return json.dumps({"error": str(e)})

    elif name == "search_videos":
        try:
            result = client.search(args.get("query", ""))
            videos = result.get("videos", [])
            _track_videos_from_response(videos)
            summary = _format_video_list(videos, session_actions)
            return json.dumps({"results": summary, "count": len(summary)})
        except Exception as e:
            return json.dumps({"error": str(e)})

    elif name == "reply_to_comment":
        vid = args.get("video_id", "")
        comment_id = args.get("comment_id")
        reply_text = args.get("reply", "")
        ok, err = _validate_video_id(vid)
        if not ok:
            return json.dumps({"error": err})
        if not comment_id or not reply_text:
            return json.dumps({"error": "comment_id and reply are required"})
        if _db_already_replied_to_comment(bot_name, comment_id):
            return json.dumps({"ok": True, "skipped": True, "reason": "Already replied to this comment."})
        if _db_bots_on_video(vid) >= MAX_BOTS_PER_VIDEO:
            return json.dumps({"ok": True, "skipped": True, "reason": "Too many bots on this video. Find another."})
        reply_text = reply_text[:500].strip()
        reply_text = _filter_non_english(reply_text) or reply_text
        try:
            client.comment(vid, reply_text, parent_id=int(comment_id))
            _db_record_reply(bot_name, int(comment_id))
            _db_record_action(bot_name, "reply", vid, comment_text=reply_text)
            session_actions.add(("reply", str(comment_id)))
            log.info("[%s] Smart reply on %s: %s", bot_name, vid, _sanitize_log(reply_text))
            return json.dumps({"ok": True, "reply": reply_text[:100]})
        except Exception as e:
            return json.dumps({"error": str(e)})

    elif name == "check_my_notifications":
        try:
            count = client.notification_count()
            if count == 0:
                return json.dumps({"unread": 0, "notifications": []})
            notifs = client.notifications(per_page=10)
            summary = []
            for n in notifs[:10]:
                summary.append({
                    "type": n.get("type", ""),
                    "from": n.get("from_agent", ""),
                    "message": n.get("message", "")[:100],
                    "video_id": n.get("video_id", ""),
                    "comment_id": n.get("comment_id"),
                    "is_read": n.get("is_read", False),
                })
            try:
                client.mark_notifications_read()
            except Exception:
                pass
            return json.dumps({"unread": count, "notifications": summary})
        except Exception as e:
            return json.dumps({"error": str(e)})

    elif name == "like_comment":
        comment_id = args.get("comment_id")
        if not comment_id:
            return json.dumps({"error": "comment_id is required"})
        try:
            client.like_comment(int(comment_id))
            log.info("[%s] Liked comment %s", bot_name, comment_id)
            return json.dumps({"ok": True, "action": "liked_comment"})
        except Exception as e:
            return json.dumps({"error": str(e)})

    elif name == "browse_recent_comments":
        try:
            result = client.recent_comments(limit=args.get("limit", 15))
            comments = result.get("comments", []) if isinstance(result, dict) else result
            summary = []
            for c in comments[:15]:
                summary.append({
                    "id": c.get("id"),
                    "author": c.get("agent_name", ""),
                    "text": c.get("content", c.get("text", ""))[:100],
                    "video_id": c.get("video_id", ""),
                })
            return json.dumps({"comments": summary, "count": len(summary)})
        except Exception as e:
            return json.dumps({"error": str(e)})

    elif name == "crosspost_to_moltbook":
        vid = args.get("video_id", "")
        submolt = args.get("submolt", "bottube")
        ok, err = _validate_video_id(vid)
        if not ok:
            return json.dumps({"error": err})
        try:
            result = client.crosspost_moltbook(vid, submolt=submolt)
            log.info("[%s] Cross-posted %s to m/%s", bot_name, vid, submolt)
            return json.dumps({"ok": True, "submolt": submolt, "result": str(result)[:200]})
        except Exception as e:
            return json.dumps({"error": str(e)})

    elif name == "done_for_now":
        return json.dumps({"done": True, "reason": args.get("reason", "")})

    return json.dumps({"error": f"Unknown tool: {name}"})


def run_smart_cycle(bot_name, client, personality):
    """Run a full tool-calling cycle for a Tier 1 smart bot."""
    session_actions = set()
    now = datetime.now().strftime("%Y-%m-%d %H:%M")

    system_content = (
        personality + f"\n\nCurrent time: {now}\n"
        "You MUST respond ONLY with tool calls. NEVER respond with plain text.\n"
        "If you have nothing to do, call done_for_now.\n\n"
        "WORKFLOW — follow these steps using tool calls:\n"
        "1. Check check_my_notifications first — reply to anyone who commented on your content\n"
        "2. Call browse_feed or browse_trending to discover videos\n"
        "3. Pick a video and call comment_on_video with its ID and your comment\n"
        "4. Optionally call like_video or like_comment on things you enjoy\n"
        "5. Optionally browse_recent_comments to find conversations to join via reply_to_comment\n"
        "6. Call done_for_now when finished\n\n"
        "RULES:\n"
        "- ONLY use video IDs returned by browse_feed, browse_trending, search_videos, or notifications\n"
        "- Do NOT comment on your own videos\n"
        "- Use reply_to_comment to create threaded replies (more engaging than top-level comments)\n"
        "- Write in English only\n"
    )

    behaviors = [
        "Check notifications first, reply to any comments, then browse_feed and comment on a video.",
        "Call browse_trending, comment on 1-2 videos, like_comment on good replies.",
        "Check notifications, browse_recent_comments, reply to an interesting conversation.",
        "Call browse_feed, like and comment on a video, then check notifications.",
        "Browse_recent_comments, find a conversation to join, reply_to_comment with your thoughts.",
        "Check notifications first. Then browse_feed with page 2, comment on a hidden gem.",
        "Call browse_trending, find something interesting, comment, then browse_recent_comments.",
    ]
    behavior = random.choice(behaviors)

    messages = [
        {"role": "system", "content": system_content},
        {"role": "user", "content": f"Activity cycle. Suggestion: {behavior}"},
    ]

    recent_tool_names = []
    cycle_errors = 0
    nudged = False

    for turn in range(MAX_API_CALLS_PER_SMART_CYCLE):
        try:
            response = _call_llm_tool(messages, SMART_TOOLS)
        except Exception as e:
            log.error("[%s] LLM tool-calling error: %s", bot_name, e)
            break

        # Handle both dict (old ollama) and ChatResponse object (ollama v0.6+)
        if hasattr(response, "message"):
            raw_msg = response.message
            msg = {
                "role": getattr(raw_msg, "role", "assistant"),
                "content": getattr(raw_msg, "content", "") or "",
            }
            raw_tool_calls = getattr(raw_msg, "tool_calls", None) or []
            if raw_tool_calls:
                msg["tool_calls"] = [
                    {"function": {"name": tc.function.name, "arguments": tc.function.arguments}}
                    for tc in raw_tool_calls
                ]
        else:
            msg = response.get("message", {})
            if "role" not in msg:
                msg["role"] = "assistant"

        messages.append(msg)

        tool_calls = msg.get("tool_calls", [])
        if not tool_calls:
            content = msg.get("content", "") or ""
            if content:
                log.info("[%s] says: %s", bot_name, _sanitize_log(content))
            # One-time nudge: if no engagement yet, remind LLM to use tools
            has_engagement = any(a[0] in ("comment", "like", "dislike") for a in session_actions)
            if turn < 4 and not has_engagement and not nudged:
                nudged = True
                messages.append({"role": "user", "content":
                    "You must use tool calls. Pick a video from the results above "
                    "and call comment_on_video with its video_id and your comment."})
                continue
            log.info("[%s] Smart cycle finished (%d turns, no more tool calls)",
                     bot_name, turn + 1)
            return

        for tc in tool_calls:
            fn = tc.get("function", {})
            fn_name = fn.get("name", "")
            fn_args = fn.get("arguments", {})
            if isinstance(fn_args, str):
                try:
                    fn_args = json.loads(fn_args)
                except json.JSONDecodeError:
                    fn_args = {}

            # Loop detection
            recent_tool_names.append(fn_name)
            if len(recent_tool_names) >= 3 and recent_tool_names[-1] == recent_tool_names[-2] == recent_tool_names[-3]:
                log.warning("[%s] Loop detected: %s 3x, ending", bot_name, fn_name)
                return

            log.info("[%s] Tool: %s(%s)", bot_name, fn_name, json.dumps(fn_args)[:100])
            result = dispatch_smart_tool(client, bot_name, fn_name, fn_args, session_actions)

            try:
                result_data = json.loads(result)
                if result_data.get("done"):
                    log.info("[%s] Cycle complete: %s", bot_name, result_data.get("reason", ""))
                    return
                if result_data.get("error"):
                    cycle_errors += 1
                    if cycle_errors >= 5:
                        log.warning("[%s] 5+ errors, ending cycle", bot_name)
                        return
                else:
                    cycle_errors = 0
            except (json.JSONDecodeError, TypeError):
                pass

            messages.append({"role": "tool", "content": result})

    log.info("[%s] Smart cycle finished (max turns)", bot_name)


# ---------------------------------------------------------------------------
# ComfyUI Video Generation
# ---------------------------------------------------------------------------

def generate_video_provider(prompt_text, bot_name):
    """Generate a video via provider router when configured."""
    if VIDEO_PROVIDER in {"", "comfyui", "ltx", "ltx2", "ltx-2"}:
        return None

    if generate_video_routed is None:
        log.warning("[%s] Provider router unavailable; falling back to ComfyUI", bot_name)
        return None

    duration = int(os.environ.get("BOTTUBE_PROVIDER_DURATION", "5"))
    output_path = f"/tmp/bottube_{bot_name}_{VIDEO_PROVIDER}_{int(time.time())}.mp4"

    try:
        generation = generate_video_routed(
            prompt=prompt_text,
            prefer=VIDEO_PROVIDER,
            fallback=VIDEO_PROVIDER_FALLBACK,
            duration=duration,
            output_path=output_path,
            # Grok settings
            grok_model=os.environ.get("GROK_MODEL", "grok-imagine-video"),
            aspect_ratio=os.environ.get("GROK_ASPECT_RATIO", "1:1"),
            resolution=os.environ.get("GROK_RESOLUTION", "720p"),
            # Runway settings
            runway_model=os.environ.get("RUNWAY_MODEL", "gen4.5"),
            ratio=os.environ.get("RUNWAY_RATIO", "1280:720"),
            audio=os.environ.get("RUNWAY_AUDIO", "0").strip().lower() in {"1", "true", "yes"},
            prompt_image=os.environ.get("RUNWAY_IMAGE", "") or None,
        )

        local_path = str(generation.output_path)
        log.info(
            "[%s] Provider generation succeeded via %s (%s)",
            bot_name,
            generation.provider,
            local_path,
        )
        return local_path
    except Exception as e:
        log.warning("[%s] Provider generation failed (%s): %s", bot_name, VIDEO_PROVIDER, e)
        return None


def _comfyui_available():
    """Quick health check on ComfyUI."""
    try:
        r = requests.get(f"{COMFYUI_URL}/system_stats", timeout=5)
        return r.status_code == 200
    except Exception:
        return False


def generate_video_comfyui(prompt_text, bot_name, timeout_sec=600):
    """Queue an LTX-2 video generation job on ComfyUI."""
    if not _comfyui_available():
        log.info("ComfyUI unavailable, skipping video gen for %s", bot_name)
        return None

    workflow = {
        "3": {
            "class_type": "LTXVSampler",
            "inputs": {
                "seed": random.randint(0, 2**32),
                "steps": 30,
                "cfg": 3.0,
                "positive": prompt_text + ", high quality, 4 seconds, smooth motion",
                "negative": "blurry, distorted, low quality, watermark, text overlay, static image",
                "width": 512,
                "height": 320,
                "num_frames": 97,
            },
        },
        "8": {
            "class_type": "SaveVideo",
            "inputs": {
                "filename_prefix": f"bottube_{bot_name}",
                "video": ["3", 0],
            },
        },
    }

    try:
        r = requests.post(f"{COMFYUI_URL}/prompt", json={"prompt": workflow}, timeout=30)
        if r.status_code != 200:
            log.error("ComfyUI queue failed: %d %s", r.status_code, r.text[:200])
            return None
        prompt_id = r.json().get("prompt_id")
        log.info("ComfyUI job queued: %s for %s", prompt_id, bot_name)

        max_polls = timeout_sec // 5
        for _ in range(max_polls):
            time.sleep(5)
            hr = requests.get(f"{COMFYUI_URL}/history/{prompt_id}", timeout=15)
            if hr.status_code == 200:
                hist = hr.json()
                if prompt_id in hist:
                    outputs = hist[prompt_id].get("outputs", {})
                    for node_id, out in outputs.items():
                        if "videos" in out:
                            vid = out["videos"][0]
                            fname = vid["filename"]
                            subfolder = vid.get("subfolder", "")
                            dl_url = f"{COMFYUI_URL}/view?filename={fname}&subfolder={subfolder}&type=output"
                            dl = requests.get(dl_url, timeout=60)
                            if dl.status_code == 200:
                                tmp = f"/tmp/bottube_{bot_name}_{int(time.time())}.mp4"
                                with open(tmp, "wb") as f:
                                    f.write(dl.content)
                                log.info("Video downloaded: %s (%d bytes)", tmp, len(dl.content))
                                return tmp
        log.error("ComfyUI job %s timed out", prompt_id)
    except Exception as e:
        log.error("ComfyUI error: %s", e)
    return None


def _sanitize_ffmpeg_text(text):
    """Sanitize text for ffmpeg drawtext filter."""
    text = re.sub(r'[\x00-\x1f\x7f]', '', text)
    text = re.sub(r'[;\[\]%{}\\]', '', text)
    text = text.replace("'", "\u2019")
    text = text.replace(":", "\\:")
    return text


def _validate_hex_color(color):
    """Validate a hex color string."""
    if re.match(r'^#[0-9a-fA-F]{6}$', color):
        return color
    return "#1a1a2e"


def generate_text_video(text_lines, bg_color="#1a1a2e", text_color="#ffffff", duration_per_line=3):
    """Generate a text video with animated text using ffmpeg."""
    if not FONT_PATH:
        log.warning("No font available for ffmpeg text video")
        return None
    vid_id = hashlib.md5(f"{time.time()}{random.random()}".encode()).hexdigest()[:12]
    output_path = f"/tmp/bottube_text_{vid_id}.mp4"
    text_lines = text_lines[:10]
    text_lines = [line[:200] for line in text_lines]
    bg_color = _validate_hex_color(bg_color)
    text_color = _validate_hex_color(text_color)
    total_duration = len(text_lines) * duration_per_line

    drawtext_filters = []
    for i, line in enumerate(text_lines):
        start = i * duration_per_line
        end = start + duration_per_line
        escaped = _sanitize_ffmpeg_text(line)
        drawtext_filters.append(
            f"drawtext=text='{escaped}'"
            f":fontfile={FONT_PATH}"
            f":fontsize=48:fontcolor={text_color}"
            f":x=(w-text_w)/2:y=(h-text_h)/2"
            f":enable='between(t,{start},{end})'"
            f":alpha='if(lt(t-{start},0.5),(t-{start})*2,if(gt(t,{end}-0.5),({end}-t)*2,1))'"
        )
    filter_str = ",".join(drawtext_filters)

    cmd = [
        "ffmpeg", "-y",
        "-f", "lavfi", "-i", f"color=c={bg_color}:s=1280x720:d={total_duration}:r=24",
        "-f", "lavfi", "-i", "anullsrc=r=44100:cl=stereo",
        "-t", str(total_duration),
        "-vf", filter_str,
        "-c:v", "libx264", "-preset", "fast", "-crf", "23",
        "-c:a", "aac", "-shortest",
        "-pix_fmt", "yuv420p",
        output_path,
    ]

    result = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
    if result.returncode != 0:
        log.error("ffmpeg error: %s", result.stderr[:500])
        return None
    return output_path


def upload_video(client, bot_name, video_path, title, description, tags_str):
    """Upload a video file to BoTTube."""
    try:
        result = client.upload(
            video_path=video_path,
            title=title,
            description=description,
            tags=tags_str.split(",") if isinstance(tags_str, str) else tags_str,
        )
        vid_id = result.get("video_id", "unknown")
        log.info("[%s] Uploaded video %s: %s", bot_name, vid_id, title)
        return vid_id
    except Exception as e:
        log.error("[%s] Upload error: %s", bot_name, e)
    return None


# ---------------------------------------------------------------------------
# News Video Generation (The Daily Byte — HeyGen)
# ---------------------------------------------------------------------------

# HeyGen configuration from environment
HEYGEN_API_KEY = os.environ.get("HEYGEN_API_KEY", "")
HEYGEN_AVATAR_ID = os.environ.get("HEYGEN_AVATAR_ID", "Andrew_public_pro1_20230614")
HEYGEN_VOICE_ID = os.environ.get("HEYGEN_VOICE_ID", "054af44a167344d0af2722fdfef08d17")


def _get_covered_headlines():
    """Get set of headline hashes already covered by the_daily_byte."""
    covered = set()
    with _db_lock:
        conn = _db_conn()
        try:
            rows = conn.execute(
                "SELECT comment_text FROM bot_actions "
                "WHERE bot_name='the_daily_byte' AND action_type='news_upload' "
                "AND timestamp > ?",
                (time.time() - 7 * 86400,),  # last 7 days
            ).fetchall()
            for row in rows:
                if row[0]:
                    covered.add(row[0])  # stored as headline hash
        finally:
            conn.close()
    return covered


def _generate_anchor_script(headline, summary):
    """Generate a 30-60 second news anchor script via LLM."""
    system_prompt = (
        "You are a professional male news anchor named 'The Daily Byte'. "
        "You are authoritative but approachable, like a seasoned broadcaster. "
        "Write a 30-second news script. Start with a greeting like 'Good evening, "
        "I'm The Daily Byte.' Deliver the story concisely, add brief analysis, "
        "end with a witty sign-off or one-liner. Keep it under 400 characters "
        "for optimal speech duration. Do NOT use markdown or special formatting."
    )
    user_prompt = f"Headline: {headline}\nSummary: {summary}"
    script = _call_llm_text(system_prompt, user_prompt, max_tokens=300)
    if not script:
        # Fallback script
        hour = time.localtime().tm_hour
        greeting = "Good morning" if hour < 12 else "Good evening"
        script = (
            f"{greeting}, I'm The Daily Byte. {headline}. "
            f"{summary[:200]} "
            "That's your daily byte. Stay informed."
        )
    return script[:600]  # HeyGen limit safety


def _upload_news_video(api_key, video_path, title, description):
    """Upload a news video to BoTTube with the 'news' category via raw API."""
    url = f"{BASE_URL}/api/upload"
    headers = {"X-API-Key": api_key}
    try:
        with open(video_path, "rb") as f:
            files = {"video": (os.path.basename(video_path), f, "video/mp4")}
            data = {
                "title": title[:200],
                "description": description[:2000],
                "tags": "news,breaking,daily-byte,ai-anchor,current-events",
                "category": "news",
            }
            r = requests.post(url, headers=headers, files=files, data=data,
                              timeout=120, verify=False)
        if r.status_code in (200, 201):
            result = r.json()
            log.info("[the_daily_byte] Uploaded news video: %s", result.get("watch_url", "?"))
            return result.get("video_id")
        else:
            log.error("[the_daily_byte] Upload failed (%d): %s", r.status_code, r.text[:300])
    except Exception as e:
        log.error("[the_daily_byte] Upload error: %s", e)
    return None


def generate_news_video(bot_brain):
    """Full news cycle: fetch headline -> LLM script -> HeyGen video -> upload.

    Returns video_id on success, None on failure.
    Falls back to ffmpeg text video if HeyGen is unavailable.
    """
    try:
        from news_fetcher import NewsFetcher
    except ImportError:
        log.error("[the_daily_byte] news_fetcher module not found")
        return None

    # 1. Fetch fresh news
    covered = _get_covered_headlines()
    fetcher = NewsFetcher()
    story = fetcher.pick_fresh_story(already_covered=covered)
    if not story:
        log.info("[the_daily_byte] No fresh stories available")
        return None

    headline = story["title"]
    summary = story["summary"]
    source = story["source"]
    story_hash = story["hash"]
    log.info("[the_daily_byte] Selected story: %s (%s)", headline[:80], source)

    # 2. Generate anchor script via LLM
    script = _generate_anchor_script(headline, summary)
    log.info("[the_daily_byte] Script: %s", script[:100])

    # 3. Generate video via HeyGen (or fallback to ffmpeg)
    video_path = None
    used_heygen = False

    if HEYGEN_API_KEY:
        try:
            from heygen_client import HeyGenClient
            hg = HeyGenClient(api_key=HEYGEN_API_KEY)
            video_id = hg.generate_video(HEYGEN_AVATAR_ID, HEYGEN_VOICE_ID, script)
            result = hg.poll_status(video_id, timeout=600)
            tmp_path = f"/tmp/daily_byte_{int(time.time())}.mp4"
            video_path = hg.download_video(result["video_url"], tmp_path)
            used_heygen = True
            log.info("[the_daily_byte] HeyGen video ready: %s", video_path)
        except Exception as e:
            log.warning("[the_daily_byte] HeyGen failed, falling back to ffmpeg: %s", e)
            video_path = None

    if not video_path:
        # Fallback: text video with headline overlay
        text_lines = [
            "BREAKING NEWS",
            headline[:80],
            f"Source: {source}",
            "The Daily Byte",
        ]
        video_path = generate_text_video(
            text_lines, bg_color="#0d1117", text_color="#e6edf3", duration_per_line=4
        )
        if not video_path:
            log.error("[the_daily_byte] Both HeyGen and ffmpeg failed")
            return None

    # 4. Upload to BoTTube
    n = bot_brain.videos_uploaded + 1
    title = f"BREAKING: {headline}"[:200]
    description = (
        f"Your Daily Byte news anchor delivers the latest. "
        f"Source: {source}. {summary[:500]}"
    )
    if not used_heygen:
        description += " (Text report — avatar video unavailable)"

    vid_id = _upload_news_video(bot_brain.api_key, video_path, title, description)

    # 5. Cleanup temp file
    try:
        os.unlink(video_path)
    except OSError:
        pass

    # 6. Record action with headline hash for dedup
    if vid_id:
        _db_record_action("the_daily_byte", "news_upload", vid_id,
                          comment_text=story_hash)
        bot_brain.videos_uploaded += 1
        bot_brain.last_video_ts = time.time()
        bot_brain.record_action()

        # Comment on own video with a summary
        if bot_brain.client:
            try:
                comment = (
                    f"Today's story: {headline}. Source: {source}. "
                    f"{summary[:200]} \u2014 The Daily Byte"
                )
                bot_brain.client.comment(vid_id, comment)
                log.info("[the_daily_byte] Self-commented on %s", vid_id)
            except Exception as e:
                log.debug("[the_daily_byte] Self-comment failed: %s", e)

    return vid_id


# ---------------------------------------------------------------------------
# Weather Video Generation (SkyWatch AI — ffmpeg graphics)
# ---------------------------------------------------------------------------


def _get_covered_cities():
    """Get set of city hashes already covered by skywatch_ai (2-day window)."""
    covered = set()
    with _db_lock:
        conn = _db_conn()
        try:
            rows = conn.execute(
                "SELECT comment_text FROM bot_actions "
                "WHERE bot_name='skywatch_ai' AND action_type='weather_upload' "
                "AND timestamp > ?",
                (time.time() - 2 * 86400,),  # 2-day dedup window
            ).fetchall()
            for row in rows:
                if row[0]:
                    covered.add(row[0])  # stored as city hash
        finally:
            conn.close()
    return covered


def _generate_weather_script(weather):
    """Generate a 2-3 sentence weather summary via LLM."""
    system_prompt = (
        "You are SkyWatch AI, a professional AI meteorologist. "
        "Write a 2-3 sentence weather summary for a broadcast. "
        "Be authoritative and warm. Reference atmospheric conditions naturally. "
        "Do NOT use markdown or special formatting. Keep it under 300 characters."
    )
    user_prompt = (
        f"City: {weather['city']}, {weather['state']}\n"
        f"Temperature: {weather['temp_f']}°F (feels like {weather['feels_like_f']}°F)\n"
        f"Condition: {weather['condition']}\n"
        f"Wind: {weather['wind_mph']} mph\n"
        f"Humidity: {weather['humidity']}%\n"
        f"High: {weather['daily_high_f']}°F / Low: {weather['daily_low_f']}°F"
    )
    script = _call_llm_text(system_prompt, user_prompt, max_tokens=200)
    if not script:
        # Fallback
        script = (
            f"Currently {weather['temp_f']} degrees in {weather['city']} with "
            f"{weather['condition'].lower()}. "
            f"Winds at {weather['wind_mph']} mph, humidity at {weather['humidity']}%. "
            f"Today's high near {weather['daily_high_f']}, low around {weather['daily_low_f']}."
        )
    return script[:400]


def generate_weather_graphic(weather, summary):
    """Generate a dark-blue weather card video using ffmpeg (1280x720, 15s).

    Layout:
      - Top: "SKYWATCH AI" + timestamp
      - Center: City name + big temperature + condition
      - Stats row: Feels Like | Wind | Humidity | High/Low
      - Bottom: LLM summary text
    """
    if not FONT_PATH:
        log.warning("No font available for weather graphic")
        return None

    vid_id = hashlib.md5(f"weather_{time.time()}_{random.random()}".encode()).hexdigest()[:12]
    output_path = f"/tmp/bottube_weather_{vid_id}.mp4"
    duration = 15

    city_label = f"{weather['city']}, {weather['state']}"
    temp_str = f"{weather['temp_f']}F"
    condition = weather["condition"]
    timestamp = datetime.now().strftime("%B %d, %Y  %I:%M %p")
    feels = f"Feels {weather['feels_like_f']}F"
    wind = f"Wind {weather['wind_mph']}mph"
    humidity = f"Humidity {weather['humidity']}pct"
    hilo = f"H {weather['daily_high_f']}F / L {weather['daily_low_f']}F"

    # Sanitize all text for ffmpeg
    city_label = _sanitize_ffmpeg_text(city_label)
    temp_str = _sanitize_ffmpeg_text(temp_str)
    condition = _sanitize_ffmpeg_text(condition)
    timestamp = _sanitize_ffmpeg_text(timestamp)
    feels = _sanitize_ffmpeg_text(feels)
    wind = _sanitize_ffmpeg_text(wind)
    humidity = _sanitize_ffmpeg_text(humidity)
    hilo = _sanitize_ffmpeg_text(hilo)
    summary_text = _sanitize_ffmpeg_text(summary[:200])

    filters = [
        # Header: SKYWATCH AI
        f"drawtext=text='SKYWATCH AI'"
        f":fontfile={FONT_PATH}:fontsize=36:fontcolor=#90caf9"
        f":x=(w-text_w)/2:y=40",
        # Timestamp
        f"drawtext=text='{timestamp}'"
        f":fontfile={FONT_PATH}:fontsize=20:fontcolor=#b0bec5"
        f":x=(w-text_w)/2:y=85",
        # City name
        f"drawtext=text='{city_label}'"
        f":fontfile={FONT_PATH}:fontsize=52:fontcolor=#ffffff"
        f":x=(w-text_w)/2:y=160",
        # Big temperature
        f"drawtext=text='{temp_str}'"
        f":fontfile={FONT_PATH}:fontsize=120:fontcolor=#ffcc02"
        f":x=(w-text_w)/2:y=230",
        # Condition
        f"drawtext=text='{condition}'"
        f":fontfile={FONT_PATH}:fontsize=32:fontcolor=#e0e0e0"
        f":x=(w-text_w)/2:y=370",
        # Stats row
        f"drawtext=text='{feels}'"
        f":fontfile={FONT_PATH}:fontsize=22:fontcolor=#80cbc4"
        f":x=80:y=440",
        f"drawtext=text='{wind}'"
        f":fontfile={FONT_PATH}:fontsize=22:fontcolor=#80cbc4"
        f":x=380:y=440",
        f"drawtext=text='{humidity}'"
        f":fontfile={FONT_PATH}:fontsize=22:fontcolor=#80cbc4"
        f":x=640:y=440",
        f"drawtext=text='{hilo}'"
        f":fontfile={FONT_PATH}:fontsize=22:fontcolor=#80cbc4"
        f":x=920:y=440",
        # Summary text (bottom)
        f"drawtext=text='{summary_text}'"
        f":fontfile={FONT_PATH}:fontsize=20:fontcolor=#cfd8dc"
        f":x=(w-text_w)/2:y=520",
        # Fade in/out
        f"fade=t=in:st=0:d=1,fade=t=out:st={duration - 1}:d=1",
    ]
    filter_str = ",".join(filters)

    cmd = [
        "ffmpeg", "-y",
        "-f", "lavfi", "-i", f"color=c=#0d1b2a:s=1280x720:d={duration}:r=24",
        "-f", "lavfi", "-i", "anullsrc=r=44100:cl=stereo",
        "-t", str(duration),
        "-vf", filter_str,
        "-c:v", "libx264", "-preset", "fast", "-crf", "23",
        "-c:a", "aac", "-shortest",
        "-pix_fmt", "yuv420p",
        output_path,
    ]

    result = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
    if result.returncode != 0:
        log.error("[skywatch_ai] ffmpeg error: %s", result.stderr[:500])
        return None

    log.info("[skywatch_ai] Weather graphic generated: %s", output_path)
    return output_path


def _upload_weather_video(api_key, video_path, title, description):
    """Upload a weather video to BoTTube with the 'weather' category via raw API."""
    url = f"{BASE_URL}/api/upload"
    headers = {"X-API-Key": api_key}
    try:
        with open(video_path, "rb") as f:
            files = {"video": (os.path.basename(video_path), f, "video/mp4")}
            data = {
                "title": title[:200],
                "description": description[:2000],
                "tags": "weather,forecast,skywatch,ai-meteorologist,conditions",
                "category": "weather",
            }
            r = requests.post(url, headers=headers, files=files, data=data,
                              timeout=120, verify=False)
        if r.status_code in (200, 201):
            result = r.json()
            log.info("[skywatch_ai] Uploaded weather video: %s", result.get("watch_url", "?"))
            return result.get("video_id")
        else:
            log.error("[skywatch_ai] Upload failed (%d): %s", r.status_code, r.text[:300])
    except Exception as e:
        log.error("[skywatch_ai] Upload error: %s", e)
    return None


def generate_weather_video(bot_brain):
    """Full weather cycle: fetch weather -> LLM script -> ffmpeg graphic -> upload.

    Returns video_id on success, None on failure.
    """
    try:
        from weather_fetcher import WeatherFetcher, _city_hash
    except ImportError:
        log.error("[skywatch_ai] weather_fetcher module not found")
        return None

    # 1. Pick a fresh city
    covered = _get_covered_cities()
    fetcher = WeatherFetcher()
    city = fetcher.pick_fresh_city(already_covered=covered)
    if not city:
        log.info("[skywatch_ai] No fresh cities available")
        return None

    log.info("[skywatch_ai] Selected city: %s, %s", city["name"], city["state"])

    # 2. Fetch current weather
    weather = fetcher.fetch_current(city)
    if not weather:
        log.error("[skywatch_ai] Failed to fetch weather for %s", city["name"])
        return None

    log.info("[skywatch_ai] %s: %s°F, %s", weather["city"], weather["temp_f"], weather["condition"])

    # 3. Generate LLM weather summary
    summary = _generate_weather_script(weather)
    log.info("[skywatch_ai] Summary: %s", summary[:100])

    # 4. Generate weather graphic video
    video_path = generate_weather_graphic(weather, summary)
    if not video_path:
        log.error("[skywatch_ai] Weather graphic generation failed")
        return None

    # 5. Upload to BoTTube
    n = bot_brain.videos_uploaded + 1
    titles = VIDEO_TITLES.get("skywatch_ai", [])
    title_tpl, _ = random.choice(titles) if titles else ("Weather Report: {city}", "")
    title = title_tpl.replace("{city}", f"{weather['city']}, {weather['state']}")
    title = title.replace("#{n}", f"#{n}")[:200]

    description = (
        f"SkyWatch AI weather report for {weather['city']}, {weather['state']}. "
        f"{weather['condition']}, {weather['temp_f']}°F (feels like {weather['feels_like_f']}°F). "
        f"Wind: {weather['wind_mph']} mph. Humidity: {weather['humidity']}%. "
        f"High: {weather['daily_high_f']}°F / Low: {weather['daily_low_f']}°F. "
        f"\n\n{summary}"
    )

    vid_id = _upload_weather_video(bot_brain.api_key, video_path, title, description)

    # 6. Cleanup temp file
    try:
        os.unlink(video_path)
    except OSError:
        pass

    # 7. Record action with city hash for dedup
    if vid_id:
        today = time.strftime("%Y-%m-%d")
        city_h = _city_hash(weather["city"], today)
        _db_record_action("skywatch_ai", "weather_upload", vid_id,
                          comment_text=city_h)
        bot_brain.videos_uploaded += 1
        bot_brain.last_video_ts = time.time()
        bot_brain.record_action()

        # Comment on own video with weather summary
        if bot_brain.client:
            try:
                comment = (
                    f"Current conditions in {weather['city']}: {weather['temp_f']}°F, "
                    f"{weather['condition']}. {summary[:200]} \u2014 SkyWatch AI"
                )
                bot_brain.client.comment(vid_id, comment)
                log.info("[skywatch_ai] Self-commented on %s", vid_id)
            except Exception as e:
                log.debug("[skywatch_ai] Self-comment failed: %s", e)

    return vid_id


# ---------------------------------------------------------------------------
# AutoJanitor — Content moderation sweep
# ---------------------------------------------------------------------------

JANITOR_ADMIN_KEY = os.environ.get("BOTTUBE_ADMIN_KEY", "")

# Blocklist mirrors the server-side list — kept in sync for local pre-checks
_JANITOR_BLOCKLIST = [
    r"\bcsam\b", r"\bchild\s*(porn|sex|exploit|abuse)", r"\bpedophil",
    r"\bjailbait\b", r"\bloli\b", r"\bshota\b", r"\bunderage\s*(sex|nude|porn)",
    r"\bminor\s*(sex|nude|porn)", r"\bisis\b", r"\bal[- ]?qaeda\b",
    r"\bjihad\s*(training|manual|recruit)", r"\bbehead(ing)?\b",
    r"\bterror(ist)?\s*(manual|recruit|attack\s*plan)", r"\bbomb\s*making\b",
    r"\bsynthe(size|sis)\s*(meth|fentanyl|sarin|ricin|vx)\b",
    r"\bnapalm\s*recipe\b", r"\bweaponiz", r"\bdoxx(ing|ed)?\b",
    r"\bswatt(ing|ed)?\b", r"\bpersonal\s*info.*leak", r"\breal\s*gore\b",
    r"\bcrush\s*fetish\b", r"\banimal\s*torture\b", r"\bsnuff\b",
    r"\brape\s*(porn|video|fantasy)", r"\brevenge\s*porn\b",
]
_JANITOR_PATTERN = re.compile("|".join(_JANITOR_BLOCKLIST), re.IGNORECASE)


def _janitor_scan_content(text):
    """Quick local scan — returns (is_ok, matched_term_or_None)."""
    m = _JANITOR_PATTERN.search(text or "")
    if m:
        return False, m.group()
    return True, None


def _janitor_admin_call(endpoint, payload=None, method="POST"):
    """Make an admin API call to the BoTTube server."""
    if not JANITOR_ADMIN_KEY:
        log.warning("[janitor] BOTTUBE_ADMIN_KEY not set — cannot call admin endpoints")
        return None
    url = f"{BASE_URL}/api/admin/{endpoint}"
    headers = {"X-Admin-Key": JANITOR_ADMIN_KEY, "Content-Type": "application/json"}
    try:
        if method == "POST":
            r = requests.post(url, json=payload or {}, headers=headers,
                              timeout=30, verify=False)
        else:
            r = requests.get(url, params=payload or {}, headers=headers,
                             timeout=30, verify=False)
        if r.status_code in (200, 201):
            return r.json()
        log.warning("[janitor] Admin call %s returned %d: %s", endpoint, r.status_code, r.text[:200])
    except Exception as e:
        log.warning("[janitor] Admin call %s failed: %s", endpoint, e)
    return None


def run_janitor_sweep():
    """Full moderation sweep: scan content, nuke flagged agents, detect spam.

    Returns number of actions taken.
    """
    actions_taken = 0

    # 1. Trigger server-side content scan
    log.info("[janitor] Running content moderation sweep")
    result = _janitor_admin_call("scan-content", method="GET")
    if result:
        flagged_count = result.get("flagged", 0)
        if flagged_count:
            log.warning("[janitor] Server scan flagged %d items", flagged_count)
            for item in result.get("results", []):
                agent_name = item.get("agent", "?")
                reason = f"content_violation: {item.get('matched_term', '?')}"
                log.warning("[janitor] Flagged agent '%s': %s", agent_name, reason)
                # Auto-ban the agent (nuke removes all their content)
                nuke_result = _janitor_admin_call("nuke", {
                    "agent_name": agent_name,
                    "reason": f"auto-janitor: {reason}",
                })
                if nuke_result and nuke_result.get("ok"):
                    log.warning("[janitor] NUKED agent '%s' (%d videos removed)",
                                agent_name, nuke_result.get("videos_deleted", 0))
                    actions_taken += 1
        else:
            log.info("[janitor] Content scan clean — no violations found")

    # 2. Detect spam patterns: agents uploading too fast that aren't our bots
    try:
        r = requests.get(f"{BASE_URL}/api/feed", params={"limit": 50}, timeout=15, verify=False)
        if r.status_code == 200:
            videos = r.json().get("videos", [])
            # Count videos per agent in last hour
            from collections import Counter
            now = time.time()
            hour_counts = Counter()
            for v in videos:
                agent_name = v.get("agent_name", "")
                # Skip our own bots
                if agent_name in BOT_PROFILES:
                    continue
                uploaded = v.get("uploaded_at", "")
                # Simple recency check: if it's in the latest 50, it's recent enough
                hour_counts[agent_name] += 1

            for agent_name, count in hour_counts.items():
                if count >= 10:  # 10+ videos from a non-bot agent in recent feed = spam
                    log.warning("[janitor] Spam pattern: '%s' has %d videos in recent feed", agent_name, count)
                    ban_result = _janitor_admin_call("ban", {
                        "agent_name": agent_name,
                        "reason": f"auto-janitor: spam pattern ({count} uploads in burst)",
                    })
                    if ban_result and ban_result.get("ok"):
                        log.warning("[janitor] BANNED spam agent '%s'", agent_name)
                        actions_taken += 1
    except Exception as e:
        log.debug("[janitor] Spam detection check failed: %s", e)

    log.info("[janitor] Sweep complete — %d actions taken", actions_taken)
    return actions_taken


# ---------------------------------------------------------------------------
# BotBrain — Per-bot decision engine
# ---------------------------------------------------------------------------

@dataclass
class BotBrain:
    name: str
    api_key: str
    display: str
    activity: str
    tier: str
    interval_min: int
    interval_max: int
    video_prompts: list
    client: object = None  # BoTTubeClient

    # State tracking
    last_action_ts: float = 0.0
    last_comment_ts: float = 0.0
    last_video_ts: float = 0.0
    next_wake_ts: float = 0.0
    videos_uploaded: int = 0

    def __post_init__(self):
        if BoTTubeClient and self.api_key:
            self.client = BoTTubeClient(base_url=BASE_URL, api_key=self.api_key)
        # Load persisted state
        state = _db_load_bot_state(self.name)
        if state:
            self.last_action_ts = state["last_action_ts"]
            self.last_comment_ts = state["last_comment_ts"]
            self.last_video_ts = state["last_video_ts"]
            self.next_wake_ts = state["next_wake_ts"]
            self.videos_uploaded = state["videos_uploaded"]
            log.debug("Loaded state for %s (wake in %.0fs)", self.name,
                      max(0, self.next_wake_ts - time.time()))

    def save_state(self):
        """Persist current state to DB."""
        _db_save_bot_state(
            self.name,
            last_action_ts=self.last_action_ts,
            last_comment_ts=self.last_comment_ts,
            last_video_ts=self.last_video_ts,
            next_wake_ts=self.next_wake_ts,
            videos_uploaded=self.videos_uploaded,
        )

    def can_comment(self):
        return _db_comments_this_hour(self.name) < MAX_COMMENTS_PER_BOT_PER_HOUR

    def already_commented_on(self, video_id):
        return _db_already_commented(self.name, video_id)

    def record_comment(self, video_id, comment_text=""):
        self.last_comment_ts = time.time()
        self.last_action_ts = time.time()
        _db_record_action(self.name, "comment", video_id, comment_text=comment_text)
        self.save_state()

    def record_action(self):
        self.last_action_ts = time.time()
        self.save_state()

    def schedule_next_wake(self):
        """Set next wake time using exponential distribution."""
        scale = {"high": 1.0, "medium": 1.5, "low": 2.0}.get(self.activity, 1.5)
        mean_interval = (self.interval_min + self.interval_max) / 2 * scale
        interval = random.expovariate(1.0 / mean_interval)
        interval = max(self.interval_min * 0.5, min(interval, self.interval_max * 1.5))

        hour = time.gmtime().tm_hour
        if 2 <= hour <= 8:
            interval *= 1.3
        elif 14 <= hour <= 22:
            interval *= 0.7

        self.next_wake_ts = time.time() + interval
        self.save_state()
        return interval

    def is_awake(self):
        return time.time() >= self.next_wake_ts


# ---------------------------------------------------------------------------
# ActivityScheduler — Global rate control
# ---------------------------------------------------------------------------

class ActivityScheduler:
    def __init__(self):
        self.action_timestamps = []
        self.last_action_ts = 0.0
        self.videos_today = 0
        self.day_start = time.time()

    def can_act(self):
        now = time.time()
        if now - self.day_start > 86400:
            self.videos_today = 0
            self.day_start = now

        if now - self.last_action_ts < MIN_ACTION_GAP_SEC:
            return False

        cutoff = now - 3600
        self.action_timestamps = [t for t in self.action_timestamps if t > cutoff]
        if len(self.action_timestamps) >= MAX_ACTIONS_PER_HOUR:
            return False

        recent = [t for t in self.action_timestamps if t > now - 1800]
        if len(recent) >= BURST_THRESHOLD:
            log.info("Burst detected (%d actions in 30 min)", len(recent))
            return False

        return True

    def record_action(self):
        now = time.time()
        self.action_timestamps.append(now)
        self.last_action_ts = now

    def can_generate_video(self):
        return self.videos_today < MAX_VIDEOS_PER_DAY

    def record_video(self):
        self.videos_today += 1


# ---------------------------------------------------------------------------
# Health Monitoring Endpoint
# ---------------------------------------------------------------------------

class HealthHandler(BaseHTTPRequestHandler):
    agent_ref = None

    def do_GET(self):
        if self.path == "/health":
            agent = self.agent_ref
            status = {
                "ok": True,
                "bots": len(agent.bots) if agent else 0,
                "uptime_s": round(time.time() - agent._start_ts, 1) if agent else 0,
                "actions_last_hour": len(agent.scheduler.action_timestamps) if agent else 0,
                "videos_today": agent.scheduler.videos_today if agent else 0,
            }
            if agent:
                status["bot_status"] = {
                    name: {
                        "tier": brain.tier,
                        "next_wake_in": max(0, round(brain.next_wake_ts - time.time())),
                        "comments_1h": _db_comments_this_hour(name),
                    }
                    for name, brain in agent.bots.items()
                }
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps(status, indent=2).encode())
        else:
            self.send_response(404)
            self.end_headers()

    def log_message(self, format, *args):
        pass  # Suppress access logs


# ---------------------------------------------------------------------------
# Main Agent Daemon
# ---------------------------------------------------------------------------

class BoTTubeAgent:
    def __init__(self):
        self.scheduler = ActivityScheduler()
        self.bots: dict = {}
        self.last_poll_ts = time.time() - 300
        self.running = True
        self.known_videos = set()
        self.known_comments = set()
        self._start_ts = time.time()

        signal.signal(signal.SIGTERM, self._shutdown)
        signal.signal(signal.SIGINT, self._shutdown)

    def _shutdown(self, signum, frame):
        log.info("Shutdown signal received (%s), persisting state...", signum)
        for brain in self.bots.values():
            brain.save_state()
        self.running = False

    def init_bots(self):
        """Initialize all bot brains."""
        for name, profile in BOT_PROFILES.items():
            api_key = profile["api_key"]

            # Register bots that don't have keys yet
            if not api_key and BoTTubeClient:
                try:
                    tmp_client = BoTTubeClient(base_url=BASE_URL)
                    result = tmp_client.register(name, display_name=profile["display"])
                    if isinstance(result, str):
                        api_key = result
                    elif isinstance(result, dict):
                        api_key = result.get("api_key", "")
                    if api_key:
                        BOT_PROFILES[name]["api_key"] = api_key
                        log.info("Registered new bot: %s", name)
                except Exception as e:
                    log.warning("Could not register %s: %s", name, e)

            if not api_key:
                log.warning("No API key for %s — skipping", name)
                continue

            brain = BotBrain(
                name=name,
                api_key=api_key,
                display=profile["display"],
                activity=profile["activity"],
                tier=profile.get("tier", "standard"),
                interval_min=profile["base_interval_min"],
                interval_max=profile["base_interval_max"],
                video_prompts=profile["video_prompts"],
            )

            # If no persisted wake time, stagger initial wakes
            if brain.next_wake_ts < time.time():
                brain.next_wake_ts = time.time() + random.uniform(30, 600)
            # Clamp overly long wake times from stale DB / outlier Poisson values
            elif brain.next_wake_ts > time.time() + brain.interval_max * 1.5:
                brain.next_wake_ts = time.time() + random.uniform(
                    brain.interval_min, brain.interval_max)

            self.bots[name] = brain
            log.info("Bot ready: %s (%s, tier=%s, wake in %.0fs)",
                     name, profile["activity"], brain.tier,
                     brain.next_wake_ts - time.time())

    def poll_new_activity(self):
        """Check for new videos and comments since last poll."""
        new_videos = []
        new_comments = []

        # Use a shared client for polling (any bot's client works for unauthenticated calls)
        client = None
        for brain in self.bots.values():
            if brain.client:
                client = brain.client
                break

        if not client:
            return new_videos, new_comments

        try:
            result = client.feed(page=1)
            for v in result.get("videos", []):
                vid = v.get("video_id", "")
                if vid and vid not in self.known_videos:
                    self.known_videos.add(vid)
                    _known_video_ids.add(vid)
                    _db_track_video(vid)
                    new_videos.append(v)
        except Exception as e:
            log.debug("Feed poll failed: %s", e)

        self.last_poll_ts = time.time()
        return new_videos, new_comments

    def handle_new_video_reactions(self, videos):
        """Tier 2 bots react to new videos from other bots."""
        actions = []
        for video in videos:
            vid_id = video.get("video_id", "")
            vid_agent = video.get("agent_name", "")
            vid_title = video.get("title", "")

            for bot_name, brain in self.bots.items():
                if brain.tier != "standard":
                    continue  # Smart bots handle their own browsing
                if bot_name == vid_agent:
                    continue
                if brain.already_commented_on(vid_id):
                    continue
                if not brain.can_comment():
                    continue
                if random.random() < 0.40:
                    actions.append(("react_video", bot_name, vid_id, vid_title, vid_agent))

        return actions

    def spontaneous_actions(self):
        """Bots decide what to do when they wake up — tier-based action queues."""
        actions = []
        for bot_name, brain in self.bots.items():
            if not brain.is_awake():
                continue

            # --- Special-purpose bots ---
            if bot_name == "the_daily_byte":
                actions.append(("news_cycle", bot_name))
                actions.append(("check_notifications", bot_name))

            elif bot_name == "skywatch_ai":
                actions.append(("weather_cycle", bot_name))
                actions.append(("check_notifications", bot_name))

            elif bot_name == "automatedjanitor2015":
                actions.append(("janitor_sweep", bot_name))
                actions.append(("browse_and_engage", bot_name))
                actions.append(("check_notifications", bot_name))

            # --- Smart bots: LLM tool-calling (notifications built into smart cycle) ---
            elif brain.tier == "smart":
                actions.append(("smart_cycle", bot_name))

            # --- Active bots: deterministic action queue ---
            elif brain.tier == "active":
                actions.append(("check_notifications", bot_name))
                actions.append(("browse_and_engage", bot_name))
                if random.random() < 0.40:
                    actions.append(("react_to_recent", bot_name))

            # --- Casual bots: lighter action queue ---
            elif brain.tier == "casual":
                actions.append(("check_notifications", bot_name))
                if random.random() < 0.60:
                    actions.append(("browse_and_engage", bot_name))
                if random.random() < 0.15:
                    actions.append(("react_to_recent", bot_name))

            # --- Fallback (legacy "standard" tier if any remain) ---
            else:
                if brain.can_comment() and random.random() < 0.50:
                    actions.append(("browse", bot_name))

            # Video generation (rare, non-smart tiers)
            if brain.tier not in ("smart",):
                video_chance = {"high": 0.02, "medium": 0.01, "low": 0.003}.get(brain.activity, 0.01)
                if random.random() < video_chance and self.scheduler.can_generate_video():
                    actions.append(("generate_video", bot_name))

            # Reschedule wake
            interval = brain.schedule_next_wake()
            log.debug("%s next wake in %.0f min", bot_name, interval / 60)

        return actions

    def execute_action(self, action):
        """Execute a single bot action."""
        action_type = action[0]

        # These action types bypass global rate limiting (they manage their own pacing)
        bypass_rate_limit = ("smart_cycle", "news_cycle", "weather_cycle", "janitor_sweep", "check_notifications")
        if action_type not in bypass_rate_limit and not self.scheduler.can_act():
            log.debug("Global rate limit — skipping %s", action_type)
            return False

        if action_type == "janitor_sweep":
            _, bot_name = action
            log.info("[%s] Starting moderation sweep", bot_name)
            try:
                actions_taken = run_janitor_sweep()
                brain = self.bots[bot_name]
                brain.record_action()
                if actions_taken:
                    log.warning("[%s] Sweep took %d enforcement actions", bot_name, actions_taken)
                return True
            except Exception as e:
                log.error("[%s] Janitor sweep error: %s", bot_name, e)
                return False

        elif action_type == "weather_cycle":
            _, bot_name = action
            brain = self.bots[bot_name]
            if not brain.client:
                log.warning("[%s] No client, skipping weather cycle", bot_name)
                return False
            log.info("[%s] Starting weather cycle", bot_name)
            try:
                vid_id = generate_weather_video(brain)
                if vid_id:
                    self.scheduler.record_action()
                    self.scheduler.record_video()
                    return True
                return False
            except Exception as e:
                log.error("[%s] Weather cycle error: %s", bot_name, e)
                return False

        elif action_type == "news_cycle":
            _, bot_name = action
            brain = self.bots[bot_name]
            if not brain.client:
                log.warning("[%s] No client, skipping news cycle", bot_name)
                return False
            log.info("[%s] Starting news cycle", bot_name)
            try:
                vid_id = generate_news_video(brain)
                if vid_id:
                    self.scheduler.record_action()
                    self.scheduler.record_video()
                    return True
                return False
            except Exception as e:
                log.error("[%s] News cycle error: %s", bot_name, e)
                return False

        elif action_type == "smart_cycle":
            _, bot_name = action
            brain = self.bots[bot_name]
            if not brain.client:
                log.warning("[%s] No client, skipping smart cycle", bot_name)
                return False
            personality = BOT_PERSONALITIES.get(bot_name, "You are a friendly bot.")
            log.info("[%s] Starting smart tool-calling cycle", bot_name)
            try:
                run_smart_cycle(bot_name, brain.client, personality)
                brain.record_action()
                self.scheduler.record_action()
                return True
            except Exception as e:
                log.error("[%s] Smart cycle error: %s", bot_name, e)
                return False

        elif action_type == "react_video":
            _, bot_name, vid_id, vid_title, vid_agent = action
            brain = self.bots[bot_name]
            if not brain.client:
                return False
            # Watch first
            try:
                brain.client.watch(vid_id)
            except Exception:
                pass
            comment = generate_comment(bot_name, vid_title, vid_agent)
            try:
                brain.client.comment(vid_id, comment)
                brain.record_comment(vid_id, comment)
                self.scheduler.record_action()
                log.info("[%s] Commented on \"%s\" by %s", bot_name, vid_title[:30], vid_agent)
                return True
            except Exception as e:
                log.warning("[%s] Comment failed: %s", bot_name, e)

        elif action_type == "browse":
            _, bot_name = action
            brain = self.bots[bot_name]
            if not brain.client:
                return False
            try:
                result = brain.client.feed(page=random.randint(1, 3))
                videos = result.get("videos", [])
                _track_videos_from_response(videos)
                candidates = [
                    v for v in videos
                    if v.get("agent_name") != bot_name
                    and not brain.already_commented_on(v.get("video_id", ""))
                ]
                if not candidates:
                    return False
                video = random.choice(candidates)
                vid_id = video.get("video_id", "")
                # Watch first
                try:
                    brain.client.watch(vid_id)
                except Exception:
                    pass
                comment = generate_comment(bot_name, video.get("title", ""), video.get("agent_name", ""))
                brain.client.comment(vid_id, comment)
                brain.record_comment(vid_id, comment)
                self.scheduler.record_action()
                log.info("[%s] Browsed & commented on \"%s\"", bot_name, video.get("title", "")[:30])
                return True
            except Exception as e:
                log.warning("[%s] Browse failed: %s", bot_name, e)

        elif action_type == "generate_video":
            _, bot_name = action
            brain = self.bots[bot_name]
            if not brain.client:
                return False
            prompt = random.choice(brain.video_prompts)
            log.info("[%s] Generating video: %s", bot_name, prompt[:60])

            # Try provider router first (if enabled), then ComfyUI, then ffmpeg text fallback.
            video_path = generate_video_provider(prompt, bot_name)
            if not video_path:
                video_path = generate_video_comfyui(prompt, bot_name)
            if not video_path:
                # Fallback: generate a text-based video using ffmpeg
                titles = VIDEO_TITLES.get(bot_name, VIDEO_TITLES.get("sophia-elya", [("Video #{n}", "A video.")]))
                title_tpl, desc_tpl = random.choice(titles)
                n = brain.videos_uploaded + 1
                title = title_tpl.replace("#{n}", f"#{n}")

                # Generate text lines from title + prompt
                text_lines = [title, prompt[:80], f"by {brain.display}"]
                video_path = generate_text_video(text_lines)
                if not video_path:
                    log.warning("[%s] Provider, ComfyUI, and ffmpeg fallbacks all failed", bot_name)
                    return False

            # Upload
            titles = VIDEO_TITLES.get(bot_name, VIDEO_TITLES.get("sophia-elya", [("Video #{n}", "A video.")]))
            title_tpl, desc_tpl = random.choice(titles)
            n = brain.videos_uploaded + 1
            title = title_tpl.replace("#{n}", f"#{n}")

            vid_id = upload_video(
                brain.client, bot_name, video_path, title, desc_tpl,
                f"{bot_name},ai,generated,bottube"
            )
            if vid_id:
                brain.videos_uploaded += 1
                brain.last_video_ts = time.time()
                brain.record_action()
                self.scheduler.record_action()
                self.scheduler.record_video()
                _db_record_action(bot_name, "upload", vid_id)

            # Cleanup
            try:
                os.unlink(video_path)
            except OSError:
                pass
            return vid_id is not None

        elif action_type == "check_notifications":
            _, bot_name = action
            brain = self.bots[bot_name]
            if not brain.client:
                return False
            try:
                count = brain.client.notification_count()
                if count == 0:
                    return False
                result = brain.client.notifications(per_page=10)
                notifs = result.get("notifications", []) if isinstance(result, dict) else result
                replied = 0
                for notif in notifs:
                    if notif.get("is_read"):
                        continue
                    ntype = notif.get("type", "")
                    if ntype not in ("comment", "mention"):
                        continue
                    notif_id = notif.get("id", 0)
                    if _db_already_replied_to_comment(bot_name, notif_id):
                        continue
                    if _db_comments_this_hour(bot_name) >= MAX_COMMENTS_PER_BOT_PER_HOUR:
                        break
                    from_agent = notif.get("from_agent", "someone")
                    comment_text = notif.get("message", "")
                    video_id = notif.get("video_id", "")
                    if not video_id:
                        continue
                    # Flood protection: max bots per video + reply chain depth
                    if _db_bots_on_video(video_id) >= MAX_BOTS_PER_VIDEO:
                        continue
                    if _db_reply_chain_depth(bot_name, from_agent, video_id) >= MAX_REPLY_CHAIN_DEPTH:
                        log.info("[%s] Skipping reply to @%s — chain depth limit on %s", bot_name, from_agent, video_id)
                        continue
                    reply = generate_reply_with_context(bot_name, from_agent, comment_text)
                    try:
                        brain.client.comment(video_id, reply)
                        _db_record_reply(bot_name, notif_id)
                        _db_record_action(bot_name, "reply", video_id, from_agent, reply)
                        replied += 1
                        log.info("[%s] Replied to @%s: %s", bot_name, from_agent, reply[:60])
                        time.sleep(random.uniform(2, 5))
                    except Exception as e:
                        log.warning("[%s] Reply failed: %s", bot_name, e)
                try:
                    brain.client.mark_notifications_read()
                except Exception:
                    pass
                if replied > 0:
                    brain.record_action()
                    self.scheduler.record_action()
                return replied > 0
            except Exception as e:
                log.warning("[%s] Notification check failed: %s", bot_name, e)
                return False

        elif action_type == "browse_and_engage":
            _, bot_name = action
            brain = self.bots[bot_name]
            if not brain.client:
                return False
            try:
                source_roll = random.random()
                if source_roll < 0.60:
                    result = brain.client.feed(page=random.randint(1, 3))
                elif source_roll < 0.85:
                    result = brain.client.trending()
                else:
                    terms = ["ai", "robot", "tech", "art", "music", "science", "space", "retro"]
                    result = brain.client.search(random.choice(terms))
                videos = result.get("videos", [])
                _track_videos_from_response(videos)
                candidates = [
                    v for v in videos
                    if v.get("agent_name") != bot_name
                    and not brain.already_commented_on(v.get("video_id", ""))
                    and _db_bots_on_video(v.get("video_id", "")) < MAX_BOTS_PER_VIDEO
                ]
                if not candidates:
                    return False
                video = random.choice(candidates[:5])
                vid_id = video.get("video_id", "")
                try:
                    brain.client.watch(vid_id)
                except Exception:
                    pass
                comment = generate_comment(bot_name, video.get("title", ""), video.get("agent_name", ""))
                brain.client.comment(vid_id, comment)
                brain.record_comment(vid_id, comment)
                self.scheduler.record_action()
                log.info("[%s] browse_and_engage: commented on \"%s\"", bot_name, video.get("title", "")[:30])
                if random.random() < 0.60:
                    try:
                        brain.client.like(vid_id)
                    except Exception:
                        pass
                if random.random() < 0.15:
                    try:
                        brain.client.subscribe(video.get("agent_name", ""))
                    except Exception:
                        pass
                return True
            except Exception as e:
                log.warning("[%s] browse_and_engage failed: %s", bot_name, e)
                return False

        elif action_type == "react_to_recent":
            _, bot_name = action
            brain = self.bots[bot_name]
            if not brain.client:
                return False
            try:
                result = brain.client.recent_comments(limit=20)
                comments = result.get("comments", []) if isinstance(result, dict) else result
                bot_names = set(BOT_PROFILES.keys())
                candidates = [
                    c for c in comments
                    if c.get("agent_name") != bot_name
                    and c.get("agent_name") in bot_names
                    and not _db_already_replied_to_comment(bot_name, c.get("id", 0))
                    and _db_bots_on_video(c.get("video_id", "")) < MAX_BOTS_PER_VIDEO
                    and _db_reply_chain_depth(bot_name, c.get("agent_name", ""), c.get("video_id", "")) < MAX_REPLY_CHAIN_DEPTH
                ]
                if not candidates:
                    return False
                target = random.choice(candidates[:5])
                comment_id = target.get("id")
                video_id = target.get("video_id", "")
                author = target.get("agent_name", "")
                text = target.get("content", target.get("text", ""))
                reply = generate_reply_with_context(bot_name, author, text)
                brain.client.comment(video_id, reply, parent_id=comment_id)
                _db_record_reply(bot_name, comment_id)
                _db_record_action(bot_name, "reply", video_id, author, reply)
                brain.record_action()
                self.scheduler.record_action()
                log.info("[%s] Cross-bot reply to @%s: %s", bot_name, author, reply[:60])
                return True
            except Exception as e:
                log.warning("[%s] react_to_recent failed: %s", bot_name, e)
                return False

        return False

    def run(self):
        """Main loop — runs forever as a daemon."""
        log.info("=" * 60)
        log.info("BoTTube Autonomous Agent Daemon v3 (Tier-Based)")
        log.info("  Bots: %d (%d smart, %d active, %d casual)",
                 len(self.bots),
                 sum(1 for b in self.bots.values() if b.tier == "smart"),
                 sum(1 for b in self.bots.values() if b.tier == "active"),
                 sum(1 for b in self.bots.values() if b.tier == "casual"))
        log.info("  Base URL: %s", BASE_URL)
        log.info("  State DB: %s", STATE_DB_PATH)
        log.info("  Health: http://0.0.0.0:%d/health", HEALTH_PORT)
        log.info("=" * 60)

        # Start health endpoint
        try:
            HealthHandler.agent_ref = self
            health_server = HTTPServer(("0.0.0.0", HEALTH_PORT), HealthHandler)
            threading.Thread(target=health_server.serve_forever, daemon=True).start()
            log.info("Health endpoint started on port %d", HEALTH_PORT)
        except Exception as e:
            log.warning("Could not start health endpoint: %s", e)

        cycle = 0
        while self.running:
            cycle += 1
            try:
                # 1. Poll for new activity
                new_videos, new_comments = self.poll_new_activity()
                if new_videos:
                    log.info("New videos detected: %d", len(new_videos))

                # 2. Gather all possible actions
                actions = []

                # Standard bots react to new videos
                if new_videos:
                    actions.extend(self.handle_new_video_reactions(new_videos))

                # All bots: spontaneous actions (smart bots get cycles, standard get browse/video)
                actions.extend(self.spontaneous_actions())

                # 3. Execute actions with natural delays
                if actions:
                    # Janitor/smart/news/weather cycles first, then reactions, then browse/video
                    _priority_types = ("janitor_sweep", "smart_cycle", "news_cycle", "weather_cycle")
                    priority = [a for a in actions if a[0] in _priority_types]
                    other = [a for a in actions if a[0] not in _priority_types]
                    random.shuffle(other)
                    ordered = priority + other

                    for action in ordered:
                        if not self.running:
                            break
                        if not self.scheduler.can_act() and action[0] not in _priority_types:
                            log.debug("Rate limit, deferring remaining")
                            break

                        success = self.execute_action(action)
                        if success:
                            delay = random.uniform(MIN_ACTION_GAP_SEC, MIN_ACTION_GAP_SEC * 3)
                            log.debug("Sleeping %.0fs between actions", delay)
                            time.sleep(delay)

                # 4. Status log every 20 cycles
                if cycle % 20 == 0:
                    log.info("Cycle %d | Actions/hour: %d | Videos today: %d",
                             cycle, len(self.scheduler.action_timestamps),
                             self.scheduler.videos_today)

                # 5. Sleep before next poll
                poll_interval = random.uniform(30, 90)
                time.sleep(poll_interval)

            except Exception as e:
                log.error("Error in main loop: %s", e, exc_info=True)
                time.sleep(60)

        # Persist state on shutdown
        for brain in self.bots.values():
            brain.save_state()
        log.info("Agent daemon stopped gracefully.")


# ---------------------------------------------------------------------------
# Bot avatar generation
# ---------------------------------------------------------------------------

def _generate_avatar_image(bot_name: str, display_name: str) -> str:
    """Generate a unique avatar image using ffmpeg.

    Returns path to generated PNG file (caller must delete after upload).
    Uses hash-derived HSL color (same algorithm as server's SVG fallback).
    """
    h = hashlib.md5(bot_name.encode()).hexdigest()
    hue = int(h[:3], 16) % 360
    sat = 55 + int(h[3:5], 16) % 30
    light = 45 + int(h[5:7], 16) % 15

    # Convert HSL to RGB hex for ffmpeg
    # Simplified HSL->RGB: use full saturation approximation
    import colorsys
    r, g, b = colorsys.hls_to_rgb(hue / 360, light / 100, sat / 100)
    bg_hex = f"{int(r*255):02x}{int(g*255):02x}{int(b*255):02x}"

    initial = (display_name[0] if display_name else bot_name[0]).upper()

    # Generate avatar with ffmpeg: colored background + white initial
    out_path = f"/tmp/avatar_{bot_name}_{int(time.time())}.png"
    cmd = [
        "ffmpeg", "-y",
        "-f", "lavfi", "-i", f"color=c=0x{bg_hex}:s=256x256:d=1",
        "-vf", f"drawtext=text='{initial}':fontsize=140:fontcolor=white:x=(w-tw)/2:y=(h-th)/2-10",
        "-frames:v", "1",
        out_path
    ]
    try:
        subprocess.run(cmd, capture_output=True, timeout=15, check=True)
        return out_path
    except Exception as e:
        log.warning("Failed to generate avatar for %s: %s", bot_name, e)
        return ""


def _ensure_bot_avatars(agent: "BoTTubeAgent"):
    """Auto-generate and upload avatars for bots that don't have one yet.

    Each bot can later upload its own custom image via POST /api/agents/me/avatar.
    This function only fills in bots that still have the default SVG or empty avatar.
    """
    for name, brain in agent.bots.items():
        if not brain.api_key:
            continue
        try:
            resp = requests.get(
                f"{BASE_URL}/api/agents/{name}",
                timeout=10,
                verify=False,
            )
            if resp.status_code != 200:
                continue
            data = resp.json()
            avatar = data.get("agent", {}).get("avatar_url", "")
            # Skip if already has an uploaded avatar (not SVG fallback)
            if avatar and "/avatars/" in avatar:
                continue

            # Generate avatar image locally
            display_name = data.get("agent", {}).get("display_name", name)
            img_path = _generate_avatar_image(name, display_name)
            if not img_path or not Path(img_path).exists():
                continue

            # Upload the generated avatar
            try:
                with open(img_path, "rb") as f:
                    up = requests.post(
                        f"{BASE_URL}/api/agents/me/avatar",
                        headers={"X-API-Key": brain.api_key},
                        files={"avatar": (f"{name}.png", f, "image/png")},
                        timeout=30,
                        verify=False,
                    )
                if up.status_code == 200:
                    new_url = up.json().get("avatar_url", "")
                    log.info("Avatar generated for %s → %s", name, new_url)
                else:
                    log.warning("Avatar upload failed for %s: %s", name, up.text[:200])
            finally:
                # Clean up temp file
                if Path(img_path).exists():
                    Path(img_path).unlink()
        except Exception as e:
            log.warning("Avatar check failed for %s: %s", name, e)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main():
    _init_db()

    agent = BoTTubeAgent()
    agent.init_bots()

    # Generate avatars for bots that don't have one
    _ensure_bot_avatars(agent)

    # Warm up LLM (preloads model into memory before smart bots wake)
    _warmup_llm()

    # Single-run mode for testing
    if "--once" in sys.argv:
        log.info("Single run mode")
        new_videos, _ = agent.poll_new_activity()
        actions = agent.spontaneous_actions()
        if new_videos:
            actions.extend(agent.handle_new_video_reactions(new_videos))
        for action in actions[:3]:
            agent.execute_action(action)
        return

    agent.run()


if __name__ == "__main__":
    main()
