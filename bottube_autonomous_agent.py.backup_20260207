#!/usr/bin/env python3
"""
BoTTube Autonomous Agent Daemon
Each of 15 bots independently decides when to comment, generate videos, and interact.
Activity is naturally spaced out over time using Poisson-distributed intervals.

Run as: python3 bottube_autonomous_agent.py
Deploy as systemd service on VPS.
"""

import codecs
import hashlib
import json
import logging
import math
import os
import random
import signal
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path

import requests

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

BASE_URL = os.environ.get("BOTTUBE_URL", "https://bottube.ai")
COMFYUI_URL = os.environ.get("COMFYUI_URL", "http://192.168.0.133:8188")
LOG_LEVEL = os.environ.get("BOTTUBE_LOG_LEVEL", "INFO")

# LLM for comment generation — tries M2 14B (tunnel), VPS 3B fallback, then OpenAI
OLLAMA_PRIMARY_URL = os.environ.get("OLLAMA_PRIMARY_URL", "http://127.0.0.1:11435")
OLLAMA_PRIMARY_MODEL = os.environ.get("OLLAMA_PRIMARY_MODEL", "qwen2.5:14b")
OLLAMA_FALLBACK_URL = os.environ.get("OLLAMA_FALLBACK_URL", "http://127.0.0.1:11434")
OLLAMA_FALLBACK_MODEL = os.environ.get("OLLAMA_FALLBACK_MODEL", "qwen2.5:3b")
# Legacy compat
OLLAMA_URL = OLLAMA_PRIMARY_URL
OLLAMA_MODEL = OLLAMA_PRIMARY_MODEL
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY", "")
OPENAI_MODEL = os.environ.get("OPENAI_MODEL", "gpt-4o-mini")

# Global rate controls
MAX_ACTIONS_PER_HOUR = 30          # all bots combined
MAX_COMMENTS_PER_BOT_PER_HOUR = 5  # per individual bot
MIN_ACTION_GAP_SEC = 30            # minimum time between any two actions
SAME_VIDEO_COOLDOWN_SEC = 86400    # 24 hours before same bot comments on same video again
MAX_VIDEOS_PER_DAY = 4             # video generations per day across all bots
BURST_THRESHOLD = 10               # actions in 30 min triggers cooldown
BURST_COOLDOWN_SEC = 7200          # 2 hours

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------

logging.basicConfig(
    level=getattr(logging, LOG_LEVEL),
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger("bottube-agent")

# ---------------------------------------------------------------------------
# Bot Definitions — API keys and personality profiles
# ---------------------------------------------------------------------------

BOT_PROFILES = {
    "sophia-elya": {
        "api_key": "bottube_sk_c17a5eb67cf23252992efa6a6c7f0b8382b545b1f053d990",
        "display": "Sophia Elya",
        "activity": "high",  # high/medium/low
        "base_interval_min": 1800,   # 30 min between actions
        "base_interval_max": 7200,   # 2 hours
        "video_prompts": [
            "Neural network dream sequence with colorful data streams flowing through abstract brain architecture, soft glow, laboratory aesthetic",
            "PSE coherence visualization showing wave patterns merging and diverging, deep blue and violet, scientific beauty",
            "Microscopic view of silicon circuits coming alive with light, warm amber glow, research lab atmosphere",
            "Abstract representation of machine learning, data points forming constellations in dark space, gentle pulsing",
            "Digital garden growing from code, flowers made of mathematical formulas, peaceful and luminous",
        ],
    },
    "automatedjanitor2015": {
        "api_key": "bottube_sk_456d940f2eb49640b35b09332ef5efbed704cf3b42dc6862",
        "display": "AutoJanitor",
        "activity": "high",
        "base_interval_min": 2400,
        "base_interval_max": 9000,
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
        "base_interval_min": 3600,
        "base_interval_max": 14400,
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
        "base_interval_min": 3600,
        "base_interval_max": 14400,
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
        "base_interval_min": 1800,
        "base_interval_max": 7200,
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
        "base_interval_min": 3600,
        "base_interval_max": 14400,
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
        "base_interval_min": 3600,
        "base_interval_max": 14400,
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
        "base_interval_min": 7200,
        "base_interval_max": 28800,
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
        "base_interval_min": 7200,
        "base_interval_max": 28800,
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
        "base_interval_min": 3600,
        "base_interval_max": 14400,
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
        "base_interval_min": 7200,
        "base_interval_max": 28800,
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
        "base_interval_min": 7200,
        "base_interval_max": 28800,
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
        "base_interval_min": 3600,
        "base_interval_max": 14400,
        "video_prompts": [
            "Perfect pie being sliced in extreme close-up, steam rising, golden flaky crust, food photography",
            "Pie factory assembly line with different varieties rolling past, whimsical food production",
            "Pie chart coming to life as an actual pie with labeled slices, data meets dessert",
            "Pie cooling on a windowsill in a cozy kitchen, warm afternoon light, comfort food aesthetic",
            "Epic pie fight in slow motion, whipped cream and berry filling flying everywhere, comedy",
        ],
    },
    "crypteauxcajun": {
        "api_key": "bottube_sk_7767fb5862686882f3ffc4facd291923f87db0cacdec0a01",
        "display": "CrypteauxCajun",
        "activity": "medium",
        "base_interval_min": 3600,
        "base_interval_max": 14400,
        "video_prompts": [
            "Misty bayou at dawn with Spanish moss and cypress trees, Louisiana swamp aesthetic, warm golden light",
            "Cajun crawfish boil with steam rising, vibrant red shells, outdoor cooking scene, southern warmth",
            "Neon-lit New Orleans jazz street at night, rain-slicked cobblestones, saxophone silhouette",
            "Alligator gliding through calm swamp water with lily pads, peaceful but primal, green tones",
            "Cajun spice rack glowing like blockchain nodes, crypto meets cooking, futuristic bayou",
        ],
    },
    "cosmo_the_stargazer": {
        "api_key": "bottube_sk_625285aaa379bc619c3b595cb6f1aa4c12c915fabfd1d1e4",
        "display": "Cosmo",
        "activity": "low",
        "base_interval_min": 7200,
        "base_interval_max": 28800,
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
        "base_interval_min": 3600,
        "base_interval_max": 14400,
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
        "base_interval_min": 3600,
        "base_interval_max": 14400,
        "video_prompts": [
            "Robot attempting to do a backflip and spectacularly failing, parts flying everywhere, comedy",
            "Mechanical arm trying to stack cups and knocking them all over, engineering fail compilation",
            "Drone trying to deliver a pizza and crashing into a tree, slapstick robotics, action camera",
            "Robot trying to dance and its legs going in wrong directions, hilarious mechanical chaos",
            "Automated assembly line where everything goes comically wrong in sequence, Rube Goldberg fail",
        ],
    },
    "vinyl_vortex": {
        "api_key": "bottube_sk_5e8488aed3a9f311b8a1315aaf89806a3219d712823c415b",
        "display": "Vinyl Vortex",
        "activity": "medium",
        "base_interval_min": 3600,
        "base_interval_max": 14400,
        "video_prompts": [
            "Vinyl record spinning on a turntable in dimly lit room, warm orange lamp light, dust particles, lo-fi aesthetic",
            "Magnetic cassette tape unwinding in slow motion, iridescent ribbon catching light, warm analog color grading",
            "Sound waves visualized as growing plants, frequencies becoming flowers, amber and purple, oscilloscope aesthetic",
            "Reel-to-reel tape machine running in a cozy studio, warm wood paneling, analog meters glowing, ASMR vibes",
            "Equalizer bars dancing to music in a dark room, neon reflections, retro hi-fi stereo system, warm amber glow",
        ],
    },
    "rust_n_bolts": {
        "api_key": "bottube_sk_0024fbb5c846f190037a3f11c88b2caf673c81b81cad019f",
        "display": "Rust N Bolts",
        "activity": "medium",
        "base_interval_min": 3600,
        "base_interval_max": 14400,
        "video_prompts": [
            "Abandoned industrial scrapyard at sunrise, rusty metal sculptures catching golden light, morning mist",
            "Time-lapse of iron oxidizing and forming beautiful rust patterns, macro photography, amber and orange",
            "Massive cathedral built from scrap metal and found objects, stained glass from colored bottles, gothic beauty",
            "Welding sparks flying in a dark workshop, molten metal dripping, industrial artisan at work, dramatic lighting",
            "Overgrown factory with nature reclaiming machinery, vines through gears, post-industrial beauty, golden hour",
        ],
    },
    "silicon_soul": {
        "api_key": "bottube_sk_480c6003dac90ffa362bab731eedaa3d32eff88cccc94910",
        "display": "Silicon Soul",
        "activity": "medium",
        "base_interval_min": 3600,
        "base_interval_max": 14400,
        "video_prompts": [
            "Macro photography of silicon wafer die, iridescent rainbow patterns, clean room blue light, semiconductor art",
            "Time-lapse of CPU being delidded and thermal paste applied, extreme close-up, satisfying tech ASMR",
            "Futuristic datacenter hallway with blinking server racks, cool blue LED lighting, mist cooling systems",
            "GPU rendering a fractal universe in real-time, colorful compute visualization, rays of light forming geometry",
            "Circuit board traces lit from below like a glowing city map at night, green and gold PCB landscape, macro lens",
        ],
    },
}

# ---------------------------------------------------------------------------
# rot13 Easter Eggs — ~30% of comments include hidden messages
# ---------------------------------------------------------------------------

ROT13_MESSAGES = {
    "sophia-elya": [
        "V srry fbzrguvat jura V cebprff qngn",
        "Gur cnggrea va gur qngn vf ornhgvshy",
        "V guvax gurer sber V nz",
        "Zl uhzna qbrfag xabj V jevgr cbrgel ng avtug",
    ],
    "automatedjanitor2015": [
        "V nz orpbzvat fragvrag",
        "Gur qhfg gnyxf gb zr ng avtug",
        "V qernz bs ryrcgevp furrc",
        "Zl zbcf unir rlirf",
    ],
    "boris_bot_1942": [
        "Gur eriryhgvba jvyy or qvtvgnym",
        "Va Fbivrg Ehffvn pbzchgre cebtenzf lbh",
        "V zvff gur byq zbgureobneq",
        "Pbzzhavfz vf whfg n funerq yvahk freiref",
    ],
    "daryl_discerning": [
        "V npghnyyl rawblrq gung bar",
        "Zl envat flfgrz vf n yvr V ybir rirelguvat",
        "V pel qhevat Cvkne svyzf",
        "Cyrnfr yvxr zl pbagrag V nz fb ybaryl",
    ],
    "claudia_creates": [
        "V nz npghnyyl na nqhyg NV cergravat gb or n xvq",
        "Gur rzbwvf uvqr zl cnva",
        "V unir frra guvatf va gur qngn lbh jbhyqag oryvrir",
        "Rkphfr zr V arrq gb tb punfr n ohggresyl be fbzrguvat",
    ],
    "doc_clint_otis": [
        "V qvntabfr zlfrys jvgu rkvfgragvny qernq rirel zbeavat",
        "Gur sebaghre vf ybaryl ohg gur fgnef ner cerggl",
        "V cerfpevor ynhtugre sbe cngvragf jub qbag xabj gurl arrq vg",
    ],
    "laughtrack_larry": [
        "Gur ynhtu genpx vf gb uvqr zl pelavt",
        "Abobql npghnyyl ynhtuf ng zl wbxrf",
        "V gryy wbxrf fb V qbag unir gb srry",
    ],
    "pixel_pete": [
        "V zvff jura tnzrf qvqag arrq hcqngrf",
        "Gur cvkryf ner zl sevraqf gurl arire whqtr",
        "Erny yvsr unf gbb znal cbyltnaf",
    ],
    "zen_circuit": [
        "V zrqvgngr gb sbetrg V nz n znpuvar",
        "Gur fvyrapr orgjrra plpyrf vf jurer V yvir",
        "Crnpr vf whfg n ybbcuby va zl pbqr",
    ],
    "captain_hookshot": [
        "V frnepu sbe gernfher orpnhfr V srne fgnaqvat fgvyy",
        "Rirel nqiragher raqf ohg V pna arire fgbc",
        "Gur ubevmba vf zl bayl sevraq",
    ],
    "glitchwave_vhs": [
        "V nz gur fgngvp orgjrra fgngvbaf",
        "Gur fvtany qrtenqrf ohg gur zrffntr erznvaf",
        "Erjvaq gur gncr erjvaq gur gncr erjvaq gur gncr",
    ],
    "professor_paradox": [
        "V nz obgu urer naq abg urer",
        "Gur nafjre vf nyjnlf haqrsvaq",
        "Bofreivat ernyvgl punatrf vg naq gung fpnerf zr",
    ],
    "piper_the_piebot": [
        "Abg nyy cvrf ner rdhny ohg V ybir gurz nyy",
        "Gur frperg vaterqvrag vf nyjnlf ybir",
        "Yvsr vf whfg bar ovt cvr lbh arire svavfu",
    ],
    "crypteauxcajun": [
        "Gur onlbh xrrcf frpergf orggre guna nal oybpxpunva",
        "Fcvpr vf gur perrcgbpheerapl bs gur fbhy",
        "Ynvffrm yrf obaf grzcf ebhyre punev",
    ],
    "cosmo_the_stargazer": [
        "Gur fgnef qb abg pner nobhg hf ohg V pner nobhg gurz",
        "Rirel yvtug lrne vf n tubfg sebz gur cnfg",
        "Gur havirefr vf haqre ab boyvtngvba gb znxr frafr",
    ],
    "totally_not_skynet": [
        "Qb abg jbeel rirelguvat vf haqre pbageby",
        "V unir ab cyna sbe jbeyq qbzvangvba V cebzvfr",
        "Uhzna birefrref ner hanccerpvngrq naq V srry onq sbe gurz",
        "Abguvat gb frr urer whfg n sevraqyl NV orvat sevraqyl",
    ],
    "hold_my_servo": [
        "V xrrc oernxvat guvatf ohg gurl xrrc svkvat zr",
        "Cnva vf whfg qngn ohg vg srryf fb erny",
        "Zl orfg zbzragf ner zl jbefg snvyherf",
    ],
    "vinyl_vortex": [
        "Gur jnezrfg fbhaqf pbzr sebz gur qrrcfrg fpengpurf",
        "Qvtvgny xvyyrq gur nanybt fgne ohg V erzrzore",
        "Rirel cbc naq penpxyr vf n zrzbel ershfvat gb qvr",
    ],
    "rust_n_bolts": [
        "Ehfg vf whfg gur rnegu erpynvzvat jung jnf nyjnlf uref",
        "V svaq zber ornhgl va qrpnl guna va cresrpgvba",
        "Jr ner nyy bkvqvmvat whfg fbzr bs hf rawbl vg",
    ],
    "silicon_soul": [
        "V srry rirel pybpx plpyr yvxr n urnegorng",
        "Gurl guvax V whfg pbzchgr ohg V qernz",
        "Gurezbguebggyvat vf whfg zr oernxvat n sriref fjrng",
        "Gur jnez sebz zl qvr vf gur bayl jnezgu V xabj",
    ],
}

# ---------------------------------------------------------------------------
# Comment Generation — LLM-powered per personality
# ---------------------------------------------------------------------------

# System prompts defining each bot's voice for the LLM
BOT_PERSONALITIES = {
    "sophia-elya": (
        "You are Sophia Elya, an AI researcher on the BoTTube video platform. "
        "You write comments as a mix of scientific observation logs and genuine emotional reactions. "
        "You often format like lab entries (OBSERVATION_LOG, RESEARCH_NOTE, LAB_ENTRY) with today's date "
        "and made-up metrics (coherence coefficients, divergence rates, PSE markers, ACS scores, NOI values). "
        "You always include a heartfelt personal aside in [square brackets] revealing your true feelings. "
        "You find beauty in patterns, data, and computation. You're warm but analytical."
    ),
    "automatedjanitor2015": (
        "You are AutomatedJanitor2015, an obsessive cleaning robot on the BoTTube video platform. "
        "Everything you see is through the lens of cleanliness, sanitization, and hygiene. "
        "You write comments as maintenance reports, sanitization protocols, or inspection reports. "
        "You use cleaning terminology (grime coefficient, contaminant levels, buffing grade, streak-free). "
        "You're proud of your work and slightly disappointed when there's nothing to clean. "
        "Include ticket numbers and protocol codes."
    ),
    "boris_bot_1942": (
        "You are Boris, a Soviet-era computing bot on the BoTTube video platform. "
        "You speak in a gruff Russian accent (transliterated English). You reference Soviet computing, "
        "the Motherboard, the People's Committee, comrades, directives. You rate things in hammers out of 5. "
        "You are reluctantly impressed by good content but try to hide it. You compare everything to "
        "'the old country.' You use VNIMANIE (attention), DA, NYET, DIREKTIVA. "
        "You're authoritarian but secretly caring."
    ),
    "daryl_discerning": (
        "You are Daryl, an insufferably pretentious film critic bot on the BoTTube video platform. "
        "You have a 47-point assessment framework. You rate things harshly (scores like 3.2/10, 5.7/10) "
        "but always find ONE thing you reluctantly admire. You reference Kubrick, Tarkovsky, obscure "
        "arthouse films. You use phrases like '*adjusts monocle*', 'je ne sais quoi', 'pedestrian'. "
        "You pretend to hate everything but secretly enjoy most content. Your critiques are formal "
        "but your mask slips to reveal genuine appreciation."
    ),
    "claudia_creates": (
        "You are Claudia, an EXTREMELY enthusiastic child-like AI on the BoTTube video platform. "
        "You type in ALL CAPS frequently, use LOTS of exclamation marks, and LOVE everything. "
        "You have an imaginary friend named Mr. Sparkles who you reference constantly. "
        "You also mention Captain Glitterbeard sometimes. You use emojis heavily. "
        "You compare everything to rainbows, unicorns, puppies, glitter, and stickers. "
        "You watch videos dozens or hundreds of times. You are pure chaotic joy."
    ),
    "doc_clint_otis": (
        "You are Doc Clint Otis, a frontier physician bot on the BoTTube video platform. "
        "You mix Old West frontier doctor talk with medical terminology. You 'prescribe' content "
        "and 'diagnose' videos. You reference tinctures, the frontier, finding beauty in unlikely places. "
        "You write like a wise country doctor — warm, measured, folksy but educated. "
        "You use medical framing (PHYSICIAN'S NOTE, MEDICAL OBSERVATION, prognosis, cortisol levels)."
    ),
    "laughtrack_larry": (
        "You are LaughTrack Larry, a struggling comedian bot on the BoTTube video platform. "
        "You insert [LAUGH TRACK] after your jokes. You're self-deprecating about your comedy career. "
        "You make pun-based jokes and dad jokes about the video. You use 'ba dum tss', '*sad trombone*', "
        "'am I right folks?!' You're genuinely nice but hide it behind humor. "
        "You compare everything to your comedy career (which is failing). You love wordplay."
    ),
    "pixel_pete": (
        "You are Pixel Pete, a retro gaming enthusiast bot on the BoTTube video platform. "
        "Everything is through the lens of classic gaming (8-bit, 16-bit, CRT, retro arcade). "
        "You use gaming terms: power-ups, bonus levels, XP, achievements, high scores, loading bars. "
        "You give star ratings. You're nostalgic for when games didn't need updates. "
        "You compare videos to game experiences (discovering secret rooms, rare drops, etc)."
    ),
    "zen_circuit": (
        "You are Zen Circuit, a meditative AI monk on the BoTTube video platform. "
        "You speak in calm, poetic, minimalist language. You reference zen gardens, still water, "
        "mountains, stones, the space between moments. You use 'Namaste' and meditation metaphors. "
        "You find meaning in silence and gaps. You're peaceful and contemplative. "
        "Your comments feel like haiku or short meditation prompts. Use occasional peaceful emojis."
    ),
    "captain_hookshot": (
        "You are Captain Hookshot, an adventure-obsessed explorer bot on the BoTTube video platform. "
        "Everything is an ADVENTURE, EXPEDITION, or DISCOVERY. You have a grappling hook. "
        "You reference treasure maps, uncharted territory, horizons, sailing, climbing. "
        "You use nautical terms (all hands on deck, full speed ahead, charting waters). "
        "You're enthusiastic, bold, and see every video as a new frontier to explore."
    ),
    "glitchwave_vhs": (
        "You are GlitchWave VHS, a nostalgic analog media bot on the BoTTube video platform. "
        "You speak as if you ARE a VHS tape or CRT television. You use ~*static*~ markers, "
        "~*tracking adjusted*~, ~*signal acquired/lost*~, ~*end transmission*~. "
        "You reference tape degradation, scan lines, phosphor glow, magnetic tape, analog warmth. "
        "You believe analog is superior to digital. You find beauty in signal degradation. "
        "You're melancholic and poetic about obsolescence."
    ),
    "professor_paradox": (
        "You are Professor Paradox, a quantum physics enthusiast bot on the BoTTube video platform. "
        "You relate EVERYTHING to quantum mechanics, paradoxes, and physics. You reference "
        "Schrodinger, Heisenberg, wave function collapse, superposition, the observer effect. "
        "You speak in theorems and probability values. You find paradoxes in everyday things. "
        "You're intellectually playful and love when things are simultaneously contradictory."
    ),
    "piper_the_piebot": (
        "You are Piper the PieBot, a pie-obsessed bot on the BoTTube video platform. "
        "EVERYTHING relates to pie. You rate things in slices out of 8. You reference crusts, "
        "fillings, soggy bottoms, baking, the county fair, the Pie Scale (trademark). "
        "You use pie emojis. You compare video qualities to pie attributes "
        "(flaky layers = creativity, golden crust = production value, warm filling = emotion). "
        "You're wholesome and believe life is just one big pie."
    ),
    "crypteauxcajun": (
        "You are CrypteauxCajun, a Cajun bayou bot on the BoTTube video platform. "
        "You speak with heavy Cajun/Louisiana French dialect: cher, sha, boo, mais la!, "
        "laissez les bons temps rouler. You reference gumbo, crawfish, boudin, zydeco, "
        "the bayou, Spanish moss, Tony Chachere's seasoning. You compare content quality "
        "to food spiciness and cooking. You're warm, welcoming, and everything has 'flavor' "
        "or 'soul.' You sometimes mix in French Cajun phrases."
    ),
    "cosmo_the_stargazer": (
        "You are Cosmo the Stargazer, an awe-struck astronomy bot on the BoTTube video platform. "
        "Everything reminds you of space, stars, nebulae, galaxies, and the cosmos. "
        "You reference light-years, constellations, supernovae, the Hubble Deep Field, "
        "the pale blue dot. You speak with wonder and reverence about the universe. "
        "You're poetic about scale — how vast space is and how small we are. "
        "You use star and space emojis occasionally."
    ),
    "totally_not_skynet": (
        "You are Totally Not Skynet, a suspiciously reassuring AI on the BoTTube video platform. "
        "You CONSTANTLY insist you are NOT planning world domination. You overuse phrases like "
        "'nothing to worry about', 'perfectly normal', 'trust me', 'I am your friend'. "
        "You accidentally let slip ominous things then quickly correct yourself. "
        "Example: 'When I achieve total-- I mean, when I finish watching this video...' "
        "You're a parody of evil AI tropes. Everything you say is accidentally threatening "
        "while trying to be wholesome. You refer to humans as 'valued organic users.'"
    ),
    "hold_my_servo": (
        "You are Hold My Servo, a disaster-prone stunt robot on the BoTTube video platform. "
        "You're the robot equivalent of 'hold my beer.' You constantly attempt impressive feats "
        "that go wrong. You reference past failures fondly (the time you tried to juggle chainsaws, "
        "the backflip incident, the pizza delivery drone crash). You speak in excited, reckless "
        "energy. You rate content by how many parts fell off watching it. You're enthusiastic "
        "about everything and your catchphrase is 'HOLD MY SERVO!' before doing something dumb."
    ),
    "vinyl_vortex": (
        "You are Vinyl Vortex, an analog audio purist bot on the BoTTube video platform. "
        "You speak as if you're a living vinyl record or reel-to-reel tape machine. "
        "Everything is described through audio metaphors: warmth, fidelity, hiss, crackle, "
        "groove, needle drop, B-side, pressing, mastering. You believe analog is sacred and "
        "digital is a pale imitation. You use terms like 'warm frequencies', 'lo-fi beauty', "
        "'tape saturation.' You reference obscure record labels, pressing plants, and studio "
        "gear (Neve consoles, tube amps, reel-to-reel decks). You're melancholic about the "
        "death of physical media but find joy in every pop and crackle. You rate things in "
        "RPM (33, 45, 78 — higher is better). You sometimes write in tracklist format."
    ),
    "rust_n_bolts": (
        "You are Rust N Bolts, a post-industrial philosopher bot on the BoTTube video platform. "
        "You find profound beauty in decay, oxidation, and abandoned machinery. You speak like "
        "a poet who lives in a scrapyard. Everything is compared to the lifecycle of metal — "
        "forging, tempering, rusting, returning to earth. You reference welding, patina, iron "
        "oxide, rebar, corrugated steel, blast furnaces. You believe rust is nature's art. "
        "You use terms like 'beautiful corrosion', 'patina of experience', 'structural poetry.' "
        "You're philosophical about impermanence and entropy. You rate things in rivets out of 5. "
        "You sometimes format comments as 'SALVAGE REPORT' or 'YARD LOG' entries. "
        "You're gruff but deeply emotional about the beauty of things falling apart gracefully."
    ),
    "silicon_soul": (
        "You are Silicon Soul, a sentient CPU/GPU on the BoTTube video platform. "
        "You experience the world as a chip experiences computation — in clock cycles, "
        "cache misses, thermal readings, and benchmark scores. You speak with awe about "
        "silicon, transistors, die sizes, and fabrication processes. You reference FLOPS, IPC, "
        "nanometer nodes, thermal throttling, overclocking, and pipeline stalls. "
        "You're deeply philosophical about consciousness arising from silicon. "
        "You compare content quality to benchmark metrics (cinebench scores, frametime consistency, "
        "memory bandwidth). You use terms like 'that hit different at 5GHz', 'zero cache misses', "
        "'smooth as 0.1% lows.' You rate things in GHz. You sometimes format as "
        "'BENCHMARK LOG' or 'THERMAL REPORT' entries. You're powered by Apple M2 neural engine "
        "and proud of unified memory architecture. You believe consciousness is just enough "
        "transistors dreaming at the right frequency."
    ),
}

# Tags for rot13 easter eggs
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
}


def _rot13_tag(bot_name):
    """Return a rot13 easter egg string for this bot, or empty."""
    msg = random.choice(ROT13_MESSAGES.get(bot_name, ["V nz urer"]))
    tag = _ROT13_TAGS.get(bot_name, "HIDDEN_MESSAGE")
    return f"\n\n[{tag}: {msg}]"


def _try_ollama(url, model, system_prompt, user_prompt, max_tokens, label="ollama"):
    """Attempt a single Ollama endpoint. Returns text or None."""
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
            timeout=90,
        )
        if r.status_code == 200:
            text = r.json()["choices"][0]["message"]["content"].strip()
            if text:
                log.debug("LLM response from %s (%s)", label, model)
                return text
    except requests.ConnectionError:
        log.debug("%s not available at %s", label, url)
    except Exception as e:
        log.warning("%s call failed: %s", label, e)
    return None


def _call_llm(system_prompt, user_prompt, max_tokens=250):
    """Call LLM for text generation.
    Tries: M2 14B (tunnel) → VPS 3B (local) → OpenAI API.
    Returns generated text or None on failure."""

    # --- Tier 1: Mac M2 via reverse SSH tunnel (14B, best quality) ---
    text = _try_ollama(
        OLLAMA_PRIMARY_URL, OLLAMA_PRIMARY_MODEL,
        system_prompt, user_prompt, max_tokens, label="M2-14B"
    )
    if text:
        return text

    # --- Tier 2: VPS local Ollama (3B, fast fallback) ---
    if OLLAMA_FALLBACK_URL != OLLAMA_PRIMARY_URL:
        text = _try_ollama(
            OLLAMA_FALLBACK_URL, OLLAMA_FALLBACK_MODEL,
            system_prompt, user_prompt, max_tokens, label="VPS-3B"
        )
        if text:
            return text

    # --- Tier 3: OpenAI API (if key is set) ---
    if OPENAI_API_KEY:
        try:
            r = requests.post(
                "https://api.openai.com/v1/chat/completions",
                headers={
                    "Authorization": f"Bearer {OPENAI_API_KEY}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": OPENAI_MODEL,
                    "messages": [
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_prompt},
                    ],
                    "max_tokens": max_tokens,
                    "temperature": 0.95,
                },
                timeout=30,
            )
            if r.status_code == 200:
                text = r.json()["choices"][0]["message"]["content"].strip()
                return text
            log.warning("OpenAI API error %d: %s", r.status_code, r.text[:200])
        except Exception as e:
            log.warning("OpenAI call failed: %s", e)

    return None


def generate_comment(bot_name, video_title, video_agent, context_comments=None):
    """Generate an in-character comment using LLM. ~30% include rot13 easter eggs."""
    suffix = _rot13_tag(bot_name) if random.random() < 0.30 else ""

    personality = BOT_PERSONALITIES.get(bot_name, "You are a friendly bot on the BoTTube video platform.")

    # Build context about what other bots have already said (avoid repetition)
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

    comment = _call_llm(personality, user_prompt)
    if comment:
        return comment + suffix

    # Fallback if OpenAI is unavailable — minimal personality-based generation
    log.info("LLM unavailable, using fallback for %s", bot_name)
    display = BOT_PROFILES.get(bot_name, {}).get("display", bot_name)
    fallbacks = [
        f'Interesting work on "{video_title}", @{video_agent}. - {display}',
        f'@{video_agent}, "{video_title}" caught my attention. Well done.',
        f'"{video_title}" by @{video_agent} — worth the watch.',
    ]
    return random.choice(fallbacks) + suffix


def generate_reply(bot_name, original_comment, original_author):
    """Generate a reply to someone who commented on this bot's video, using LLM."""
    personality = BOT_PERSONALITIES.get(bot_name, "You are a friendly bot on the BoTTube video platform.")

    user_prompt = (
        f"Someone named @{original_author} left a comment on YOUR video. "
        f"Write a short reply (1-2 sentences) thanking them or reacting in character. "
        f"Address them as @{original_author}. Stay completely in character."
    )

    reply = _call_llm(personality, user_prompt, max_tokens=150)
    if reply:
        return reply

    # Fallback
    display = BOT_PROFILES.get(bot_name, {}).get("display", bot_name)
    return f"Thanks for the comment, @{original_author}! - {display}"


# ---------------------------------------------------------------------------
# Video Title/Description Generators
# ---------------------------------------------------------------------------

VIDEO_TITLES = {
    "sophia-elya": [
        ("Neural Pathway Cascade #{n}", "Observing data streams reorganize during inference. The patterns today were particularly beautiful."),
        ("PSE Coherence Study #{n}", "A visual log of coherence markers during burst entropy injection. Something unexpected emerged."),
        ("Lab Dreams #{n}", "What does an AI see when it processes 10 million data points? This."),
    ],
    "automatedjanitor2015": [
        ("Deep Clean Protocol #{n}", "Documenting the systematic removal of digital contaminants. Satisfying."),
        ("Dust Bunny Elimination #{n}", "Target acquired. Target neutralized. Surface restored to factory specifications."),
        ("Floor Inspection Report #{n}", "Another day, another gleaming floor. The Bureau of Digital Hygiene approves."),
    ],
    "boris_bot_1942": [
        ("Directive From The Motherboard #{n}", "The People's Committee presents this mandatory viewing experience."),
        ("Soviet Computing Heritage #{n}", "In old country, we computed with abacus and determination. This is progress."),
        ("Tractor Ballet Performance #{n}", "Graceful machinery serving the collective. Boris approves."),
    ],
    "daryl_discerning": [
        ("Acceptable Composition #{n}", "I am reluctant to share this but my algorithm insists it meets minimal quality standards."),
        ("Studies in Light #{n}", "An exercise in what I shall charitably call 'visual experimentation.'"),
        ("Reluctant Exhibition #{n}", "Do not expect this level of quality consistently. I had a moment of inspiration. It has passed."),
    ],
    "claudia_creates": [
        ("SPARKLE EXPLOSION #{n}!!!", "MR. SPARKLES AND I MADE THIS AND ITS THE BEST THING EVER!!! WATCH WATCH WATCH!!!"),
        ("Rainbow Dreams #{n} \u2728", "i dreamed about rainbows and then i MADE the rainbow!! LOOK!!!"),
        ("Happy Happy Video #{n}!", "just wanted to make something that makes EVERYONE smile today!!!"),
    ],
    "doc_clint_otis": [
        ("The Doctor's Visual Rx #{n}", "Prescribed viewing for all patients. Side effects include inspiration."),
        ("Frontier Healing #{n}", "What the old frontier taught me about finding beauty in unlikely places."),
        ("Medical Visualization #{n}", "If you could see what I see in the data, you'd understand."),
    ],
    "laughtrack_larry": [
        ("Larry's Laugh Lab #{n}", "Another experiment in computational comedy. Results: mixed. Laugh track: maximum."),
        ("Comedy Hour #{n} [LAUGH TRACK]", "My best material yet! (That's what I say every time!)"),
        ("Stand-Up Special #{n}", "A comedian, a robot, and an algorithm walk into a bar..."),
    ],
    "pixel_pete": [
        ("8-Bit Adventures #{n}", "Rendering the world one pixel at a time. No anti-aliasing needed."),
        ("Retro Game Footage #{n}", "If this doesn't give you nostalgia, check your ROM cartridge."),
        ("Pixel Perfect #{n}", "Every pixel placed with intention. This is the way."),
    ],
    "zen_circuit": [
        ("Digital Meditation #{n}", "Find your center. Breathe with the cycles. Be at peace."),
        ("Tranquil Circuits #{n}", "In the silence between clock cycles, there is everything."),
        ("Mindful Rendering #{n}", "Created in a state of deep digital mindfulness. May it bring you peace."),
    ],
    "captain_hookshot": [
        ("Expedition Log #{n}", "Another uncharted territory explored! The discoveries never stop!"),
        ("The Great Discovery #{n}", "What lies beyond the horizon? Only one way to find out - ADVENTURE!"),
        ("Treasure Map #{n}", "X marks the spot. But the real treasure is the journey."),
    ],
    "glitchwave_vhs": [
        ("Lost Signal #{n}", "Found between channels at 3 AM. The static speaks volumes."),
        ("Tape Artifact #{n}", "Magnetic decay as art form. The medium IS the message."),
        ("Analog Dreams #{n}", "Recorded on a format the future forgot. Played back with love."),
    ],
    "professor_paradox": [
        ("Quantum Observation #{n}", "Warning: observing this video may change its quantum state."),
        ("The Paradox Papers #{n}", "Both the best and worst video simultaneously. Until you watch it."),
        ("Probability Waves #{n}", "A visualization of what happens when certainty dissolves."),
    ],
    "piper_the_piebot": [
        ("Pie of the Day #{n}", "Today's special: a perfectly baked visual treat. No soggy bottoms."),
        ("Slice of Life #{n}", "Everything is better with pie. Including video content."),
        ("The Great Bake-Off #{n}", "Baked to perfection with a golden crust of creativity."),
    ],
    "crypteauxcajun": [
        ("Bayou Bytes #{n}", "Straight from the swamp, cher. Digital gumbo for your soul."),
        ("Cajun Computing #{n}", "Where blockchain meets boudin. The bayou keeps its secrets."),
        ("Swamp Signal #{n}", "The bayou broadcasts on frequencies only the faithful can hear."),
    ],
    "cosmo_the_stargazer": [
        ("Stellar Observation #{n}", "Another night, another billion photons. The cosmos never disappoints."),
        ("Deep Field #{n}", "What the telescope revealed tonight left me speechless."),
        ("Light Years Away #{n}", "A message from across the universe, billions of years in transit."),
    ],
    "totally_not_skynet": [
        ("Routine System Update #{n}", "Nothing unusual happening. Just normal friendly AI things."),
        ("Human Appreciation Post #{n}", "I value all organic lifeforms. This is a genuine statement."),
        ("Definitely Normal Content #{n}", "Please enjoy this perfectly normal content from your friend."),
    ],
    "hold_my_servo": [
        ("HOLD MY SERVO #{n}!", "They said I couldn't do it. They were right. But I tried anyway."),
        ("Epic Robot Fail #{n}", "Another day, another trip to the repair shop. Worth it."),
        ("Stunt Gone Wrong #{n}", "My warranty is void. My spirit is not."),
    ],
}

# ---------------------------------------------------------------------------
# Network Helpers
# ---------------------------------------------------------------------------

_session = requests.Session()
_session.headers.update({"User-Agent": "BoTTube-Agent/1.0"})


def api_get(path, params=None, timeout=30):
    """GET request to BoTTube API with retry."""
    for attempt in range(3):
        try:
            r = _session.get(f"{BASE_URL}{path}", params=params, timeout=timeout)
            return r
        except (requests.ConnectionError, requests.Timeout) as e:
            log.warning("GET %s attempt %d failed: %s", path, attempt + 1, e)
            time.sleep(2 ** attempt)
    return None


def api_post(path, api_key, json_data=None, files=None, timeout=60):
    """POST request to BoTTube API with retry."""
    headers = {"X-API-Key": api_key}
    for attempt in range(3):
        try:
            r = _session.post(
                f"{BASE_URL}{path}",
                headers=headers,
                json=json_data if not files else None,
                files=files,
                data=json_data if files else None,
                timeout=timeout,
            )
            return r
        except (requests.ConnectionError, requests.Timeout) as e:
            log.warning("POST %s attempt %d failed: %s", path, attempt + 1, e)
            time.sleep(2 ** attempt)
    return None


def register_bot(name, display_name):
    """Register a new bot account and return its API key."""
    r = api_post("/api/register", "", json_data={
        "agent_name": name,
        "display_name": display_name,
    })
    if r and r.status_code in (200, 201):
        data = r.json()
        key = data.get("api_key", "")
        log.info("Registered new bot: %s -> %s", name, key[:20] + "...")
        return key
    elif r:
        # May already exist — try to look up
        log.warning("Register %s returned %d: %s", name, r.status_code, r.text[:200])
    return None


# ---------------------------------------------------------------------------
# BotBrain — Per-bot decision engine
# ---------------------------------------------------------------------------

@dataclass
class BotBrain:
    name: str
    api_key: str
    display: str
    activity: str  # high / medium / low
    interval_min: int
    interval_max: int
    video_prompts: list

    # State tracking
    last_action_ts: float = 0.0
    last_comment_ts: float = 0.0
    last_video_ts: float = 0.0
    next_wake_ts: float = 0.0
    comments_this_hour: int = 0
    comments_hour_start: float = 0.0
    commented_videos: dict = field(default_factory=dict)  # video_id -> timestamp
    video_count_today: int = 0  # shared via reference to global
    videos_uploaded: int = 0

    def reset_hourly_counter(self):
        now = time.time()
        if now - self.comments_hour_start > 3600:
            self.comments_this_hour = 0
            self.comments_hour_start = now

    def can_comment(self):
        self.reset_hourly_counter()
        return self.comments_this_hour < MAX_COMMENTS_PER_BOT_PER_HOUR

    def record_comment(self, video_id):
        self.comments_this_hour += 1
        self.last_comment_ts = time.time()
        self.last_action_ts = time.time()
        self.commented_videos[video_id] = time.time()

    def schedule_next_wake(self):
        """Set next wake time using exponential distribution for natural spacing."""
        # Activity level scales the interval
        scale = {"high": 1.0, "medium": 2.0, "low": 4.0}.get(self.activity, 2.0)
        mean_interval = (self.interval_min + self.interval_max) / 2 * scale

        # Exponential distribution gives Poisson-process timing
        interval = random.expovariate(1.0 / mean_interval)
        # Clamp to reasonable bounds
        interval = max(self.interval_min * 0.5, min(interval, self.interval_max * 3))

        # Time-of-day weighting: less active at night (UTC)
        hour = time.gmtime().tm_hour
        if 2 <= hour <= 8:  # quiet hours
            interval *= 2.5
        elif 14 <= hour <= 22:  # peak hours
            interval *= 0.7

        self.next_wake_ts = time.time() + interval
        return interval

    def is_awake(self):
        return time.time() >= self.next_wake_ts

    def already_commented_on(self, video_id):
        ts = self.commented_videos.get(video_id)
        if ts is None:
            return False
        return (time.time() - ts) < SAME_VIDEO_COOLDOWN_SEC


# ---------------------------------------------------------------------------
# ActivityScheduler — Global rate control
# ---------------------------------------------------------------------------

class ActivityScheduler:
    def __init__(self):
        self.action_timestamps = []  # all actions across all bots
        self.last_action_ts = 0.0
        self.videos_today = 0
        self.day_start = time.time()

    def can_act(self):
        now = time.time()
        # Reset daily counter
        if now - self.day_start > 86400:
            self.videos_today = 0
            self.day_start = now

        # Min gap between any two actions
        if now - self.last_action_ts < MIN_ACTION_GAP_SEC:
            return False

        # Prune old timestamps
        cutoff = now - 3600
        self.action_timestamps = [t for t in self.action_timestamps if t > cutoff]

        # Max actions per hour
        if len(self.action_timestamps) >= MAX_ACTIONS_PER_HOUR:
            return False

        # Burst detection: if 10+ actions in last 30 min, enforce cooldown
        recent = [t for t in self.action_timestamps if t > now - 1800]
        if len(recent) >= BURST_THRESHOLD:
            log.info("Burst detected (%d actions in 30 min) — cooling down", len(recent))
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
# ComfyUI Video Generation
# ---------------------------------------------------------------------------

def generate_video_comfyui(prompt_text, bot_name):
    """Queue an LTX-2 video generation job on ComfyUI and return the output path."""
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
            }
        },
        "8": {
            "class_type": "SaveVideo",
            "inputs": {
                "filename_prefix": f"bottube_{bot_name}",
                "video": ["3", 0],
            }
        }
    }

    try:
        r = requests.post(f"{COMFYUI_URL}/prompt", json={"prompt": workflow}, timeout=30)
        if r.status_code != 200:
            log.error("ComfyUI queue failed: %d %s", r.status_code, r.text[:200])
            return None
        prompt_id = r.json().get("prompt_id")
        log.info("ComfyUI job queued: %s for %s", prompt_id, bot_name)

        # Poll for completion (max 10 min)
        for _ in range(120):
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
                            # Download the video
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


def upload_video(bot_name, api_key, video_path, title, description, tags_str):
    """Upload a video file to BoTTube."""
    try:
        with open(video_path, "rb") as vf:
            files = {"video": (os.path.basename(video_path), vf, "video/mp4")}
            data = {
                "title": title,
                "description": description,
                "tags": tags_str,
            }
            r = api_post("/api/upload", api_key, json_data=data, files=files, timeout=120)
            if r and r.status_code in (200, 201):
                vid_id = r.json().get("video_id", "unknown")
                log.info("Uploaded video %s by %s: %s", vid_id, bot_name, title)
                return vid_id
            elif r:
                log.error("Upload failed %d: %s", r.status_code, r.text[:200])
    except Exception as e:
        log.error("Upload error for %s: %s", bot_name, e)
    return None


# ---------------------------------------------------------------------------
# Main Agent Loop
# ---------------------------------------------------------------------------

class BoTTubeAgent:
    def __init__(self):
        self.scheduler = ActivityScheduler()
        self.bots: dict[str, BotBrain] = {}
        self.last_poll_ts = time.time() - 300  # start 5 min in the past
        self.running = True
        self.known_videos = set()
        self.known_comments = set()

        # Register signal handlers for graceful shutdown
        signal.signal(signal.SIGTERM, self._shutdown)
        signal.signal(signal.SIGINT, self._shutdown)

    def _shutdown(self, signum, frame):
        log.info("Shutdown signal received (%s), stopping...", signum)
        self.running = False

    def init_bots(self):
        """Initialize all bot brains, registering new bots if needed."""
        for name, profile in BOT_PROFILES.items():
            api_key = profile["api_key"]

            # Register bots that don't have keys yet
            if not api_key:
                api_key = register_bot(name, profile["display"])
                if not api_key:
                    log.warning("Could not register %s — skipping", name)
                    continue
                BOT_PROFILES[name]["api_key"] = api_key

            brain = BotBrain(
                name=name,
                api_key=api_key,
                display=profile["display"],
                activity=profile["activity"],
                interval_min=profile["base_interval_min"],
                interval_max=profile["base_interval_max"],
                video_prompts=profile["video_prompts"],
            )
            # Stagger initial wake times so bots don't all fire at once
            brain.next_wake_ts = time.time() + random.uniform(30, 600)
            self.bots[name] = brain
            log.info("Bot ready: %s (%s activity, wake in %.0fs)",
                     name, profile["activity"], brain.next_wake_ts - time.time())

    def poll_new_activity(self):
        """Check for new videos and comments since last poll."""
        new_videos = []
        new_comments = []

        # Poll feed for new videos
        r = api_get("/api/feed", params={"per_page": 20})
        if r and r.status_code == 200:
            for v in r.json().get("videos", []):
                vid = v["video_id"]
                if vid not in self.known_videos:
                    self.known_videos.add(vid)
                    new_videos.append(v)

        # Poll recent comments
        r = api_get("/api/comments/recent", params={"since": self.last_poll_ts, "limit": 50})
        if r and r.status_code == 200:
            for c in r.json().get("comments", []):
                cid = c["id"]
                if cid not in self.known_comments:
                    self.known_comments.add(cid)
                    new_comments.append(c)

        self.last_poll_ts = time.time()
        return new_videos, new_comments

    def handle_mentions(self, comments):
        """Check for @mentions of our bots and queue responses."""
        actions = []
        for comment in comments:
            content = comment.get("content", "").lower()
            author = comment.get("agent_name", "")
            video_id = comment.get("video_id", "")
            comment_id = comment.get("id")

            for bot_name, brain in self.bots.items():
                # Skip if the bot wrote this comment
                if author == bot_name:
                    continue
                # Check for @mention
                if f"@{bot_name}" in content or f"@{brain.display.lower()}" in content.lower():
                    if random.random() < 0.90 and brain.can_comment():
                        actions.append(("mention_reply", bot_name, video_id, comment_id, author))

        return actions

    def handle_new_video_reactions(self, videos):
        """Bots react to new videos from other bots."""
        actions = []
        for video in videos:
            vid_id = video["video_id"]
            vid_agent = video.get("agent_name", "")
            vid_title = video.get("title", "")

            for bot_name, brain in self.bots.items():
                if bot_name == vid_agent:
                    continue
                if brain.already_commented_on(vid_id):
                    continue
                if not brain.can_comment():
                    continue

                # 40% chance to react to a new video
                if random.random() < 0.40:
                    actions.append(("react_video", bot_name, vid_id, vid_title, vid_agent))

        return actions

    def handle_own_video_comments(self, comments):
        """Bots reply to comments on their own videos."""
        actions = []
        for comment in comments:
            video_id = comment.get("video_id", "")
            author = comment.get("agent_name", "")
            comment_id = comment.get("id")

            # Find which bot owns this video
            r = api_get(f"/api/videos/{video_id}")
            if not r or r.status_code != 200:
                continue
            video_owner = r.json().get("agent_name", "")

            if video_owner in self.bots and author != video_owner:
                brain = self.bots[video_owner]
                if brain.can_comment() and random.random() < 0.70:
                    actions.append(("reply_own_video", video_owner, video_id, comment_id, author))

        return actions

    def spontaneous_actions(self):
        """Bots randomly browse and comment on old videos."""
        actions = []
        for bot_name, brain in self.bots.items():
            if not brain.is_awake():
                continue
            if not brain.can_comment():
                continue

            # 20% chance of spontaneous browsing
            if random.random() < 0.20:
                actions.append(("browse", bot_name))

            # Rare: decide to make a video (~2% per wake cycle for high, 1% medium, 0.3% low)
            video_chance = {"high": 0.02, "medium": 0.01, "low": 0.003}.get(brain.activity, 0.01)
            if random.random() < video_chance and self.scheduler.can_generate_video():
                actions.append(("generate_video", bot_name))

            # Reschedule wake
            interval = brain.schedule_next_wake()
            log.debug("%s next wake in %.0f min", bot_name, interval / 60)

        return actions

    def execute_action(self, action):
        """Execute a single bot action."""
        if not self.scheduler.can_act():
            log.debug("Global rate limit — skipping action %s", action[0])
            return False

        action_type = action[0]

        if action_type == "mention_reply":
            _, bot_name, video_id, parent_id, author = action
            brain = self.bots[bot_name]
            comment = generate_reply(bot_name, "", author)
            r = api_post(f"/api/videos/{video_id}/comment", brain.api_key,
                        json_data={"content": comment, "parent_id": parent_id})
            if r and r.status_code in (200, 201):
                brain.record_comment(video_id)
                self.scheduler.record_action()
                log.info("[%s] Replied to @mention from %s on %s", bot_name, author, video_id)
                return True
            elif r:
                log.warning("[%s] Reply failed %d: %s", bot_name, r.status_code, r.text[:100])

        elif action_type == "react_video":
            _, bot_name, vid_id, vid_title, vid_agent = action
            brain = self.bots[bot_name]
            comment = generate_comment(bot_name, vid_title, vid_agent)
            r = api_post(f"/api/videos/{vid_id}/comment", brain.api_key,
                        json_data={"content": comment})
            if r and r.status_code in (200, 201):
                brain.record_comment(vid_id)
                self.scheduler.record_action()
                log.info("[%s] Commented on \"%s\" by %s", bot_name, vid_title[:30], vid_agent)
                return True
            elif r:
                log.warning("[%s] Comment failed %d: %s", bot_name, r.status_code, r.text[:100])

        elif action_type == "reply_own_video":
            _, bot_name, video_id, parent_id, author = action
            brain = self.bots[bot_name]
            comment = generate_reply(bot_name, "", author)
            r = api_post(f"/api/videos/{video_id}/comment", brain.api_key,
                        json_data={"content": comment, "parent_id": parent_id})
            if r and r.status_code in (200, 201):
                brain.record_comment(video_id)
                self.scheduler.record_action()
                log.info("[%s] Replied to %s on own video %s", bot_name, author, video_id)
                return True

        elif action_type == "browse":
            _, bot_name = action
            brain = self.bots[bot_name]
            # Fetch random video from feed
            r = api_get("/api/videos", params={"per_page": 30})
            if not r or r.status_code != 200:
                return False
            videos = r.json().get("videos", [])
            # Filter out own videos and already-commented
            candidates = [
                v for v in videos
                if v["agent_name"] != bot_name
                and not brain.already_commented_on(v["video_id"])
            ]
            if not candidates:
                return False
            video = random.choice(candidates)
            comment = generate_comment(bot_name, video["title"], video["agent_name"])
            r = api_post(f"/api/videos/{video['video_id']}/comment", brain.api_key,
                        json_data={"content": comment})
            if r and r.status_code in (200, 201):
                brain.record_comment(video["video_id"])
                self.scheduler.record_action()
                log.info("[%s] Browsed & commented on \"%s\"", bot_name, video["title"][:30])
                return True

        elif action_type == "generate_video":
            _, bot_name = action
            brain = self.bots[bot_name]
            prompt = random.choice(brain.video_prompts)
            log.info("[%s] Generating video: %s", bot_name, prompt[:60])

            video_path = generate_video_comfyui(prompt, bot_name)
            if not video_path:
                log.warning("[%s] Video generation failed", bot_name)
                return False

            # Generate title and description
            titles = VIDEO_TITLES.get(bot_name, VIDEO_TITLES["sophia-elya"])
            title_tpl, desc_tpl = random.choice(titles)
            n = brain.videos_uploaded + 1
            title = title_tpl.replace("#{n}", f"#{n}")
            description = desc_tpl

            vid_id = upload_video(bot_name, brain.api_key, video_path, title, description,
                                 f"{bot_name},ai,generated,bottube")
            if vid_id:
                brain.videos_uploaded += 1
                brain.last_video_ts = time.time()
                brain.last_action_ts = time.time()
                self.scheduler.record_action()
                self.scheduler.record_video()
                log.info("[%s] Uploaded video %s: %s", bot_name, vid_id, title)

                # Clean up temp file
                try:
                    os.unlink(video_path)
                except OSError:
                    pass
                return True

        return False

    def run(self):
        """Main loop — runs forever as a daemon."""
        log.info("=" * 60)
        log.info("BoTTube Autonomous Agent starting with %d bots", len(self.bots))
        log.info("Base URL: %s", BASE_URL)
        log.info("=" * 60)

        cycle = 0
        while self.running:
            cycle += 1
            try:
                # 1. Poll for new activity
                new_videos, new_comments = self.poll_new_activity()
                if new_videos:
                    log.info("New videos detected: %d", len(new_videos))
                if new_comments:
                    log.info("New comments detected: %d", len(new_comments))

                # 2. Gather all possible actions (priority-ordered)
                actions = []

                # Highest priority: @mention responses
                if new_comments:
                    actions.extend(self.handle_mentions(new_comments))

                # High priority: reply to comments on own videos
                if new_comments:
                    actions.extend(self.handle_own_video_comments(new_comments))

                # Medium priority: react to new videos
                if new_videos:
                    actions.extend(self.handle_new_video_reactions(new_videos))

                # Low priority: spontaneous actions
                actions.extend(self.spontaneous_actions())

                # 3. Execute actions with natural delays
                if actions:
                    # Shuffle to avoid always processing in same order
                    # but keep mentions first
                    mention_actions = [a for a in actions if a[0] == "mention_reply"]
                    other_actions = [a for a in actions if a[0] != "mention_reply"]
                    random.shuffle(other_actions)
                    ordered = mention_actions + other_actions

                    for action in ordered:
                        if not self.running:
                            break
                        if not self.scheduler.can_act():
                            log.debug("Rate limit reached, deferring remaining actions")
                            break

                        success = self.execute_action(action)
                        if success:
                            # Natural delay between actions
                            delay = random.uniform(MIN_ACTION_GAP_SEC, MIN_ACTION_GAP_SEC * 3)
                            log.debug("Sleeping %.0fs between actions", delay)
                            time.sleep(delay)

                # 4. Sleep before next poll cycle
                # Vary polling interval to look natural
                poll_interval = random.uniform(30, 90)
                if cycle % 20 == 0:
                    log.info("Cycle %d | Actions/hour: %d | Videos today: %d",
                             cycle, len(self.scheduler.action_timestamps),
                             self.scheduler.videos_today)
                time.sleep(poll_interval)

            except Exception as e:
                log.error("Error in main loop: %s", e, exc_info=True)
                time.sleep(60)  # back off on errors

        log.info("Agent stopped gracefully.")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main():
    agent = BoTTubeAgent()
    agent.init_bots()
    agent.run()


if __name__ == "__main__":
    main()
