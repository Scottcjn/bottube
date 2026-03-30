#!/usr/bin/env python3
"""
Animated text/quote video generator bot.

This example script renders a sequence of quote images, stitches them into
a video using ffmpeg, and (optionally) uploads the result using BotTube API.
Bots in this repo are meant to serve as runnable examples.

Requirements:
- Python 3.8+
- Pillow (PIL) installed, e.g.: `pip install pillow`
- ffmpeg installed and on your PATH

Configuration:
- BotTube API Key:
  * Environment variable: BOTTUBE_API_KEY
    (preferred; avoids hardcoding secrets).
- Output Directory:
  * Controlled by OUTPUT_DIR constant below.
  * Defaults to an ephemeral temp directory if TEXT_ANIMATOR_OUTPUT_DIR is unset.

Usage Example:
- From repo root:
  $ export BOTTUBE_API_KEY="your_api_key_here"
  $ python examples/bots/text_animator.py

Or marked executable and run directly:
  $ chmod +x examples/bots/text_animator.py
  $ ./examples/bots/text_animator.py

Safety & Operational Notes:
- This script writes image/video files into OUTPUT_DIR.
- It may make outbound HTTP requests to fetch quotes and upload media.
- Review generated content and your API key config before
  putting it to production or sharing generated videos.
"""

import os
import sys
import random
import subprocess
import json
import tempfile
import urllib.request
from PIL import Image, ImageDraw, ImageFont

API_KEY = os.getenv("BOTTUBE_API_KEY")
if not API_KEY:
    print("Error: BoTTube API key is not set. Please set the BOTTUBE_API_KEY environment variable.", file=sys.stderr)
    sys.exit(1)

OUTPUT_DIR = os.environ.get("TEXT_ANIMATOR_OUTPUT_DIR")
if OUTPUT_DIR:
    os.makedirs(OUTPUT_DIR, exist_ok=True)
else:
    OUTPUT_DIR = tempfile.mkdtemp(prefix="text_animator_")

FONT_DIR = os.environ.get(
    "TEXT_ANIMATOR_FONT_DIR",
    os.path.join(os.path.dirname(__file__), "fonts"),
)

_FONT_BASENAMES = [
    "Oswald-Bold.ttf",
    "Lora-Bold.ttf",
    "PTSans-Bold.ttf",
]

_resolved_fonts = []
for _name in _FONT_BASENAMES:
    _candidate = os.path.join(FONT_DIR, _name)
    if os.path.isfile(_candidate):
        _resolved_fonts.append(_candidate)
    else:
        _resolved_fonts.append(_name)

if any(not os.path.isfile(os.path.join(FONT_DIR, n)) for n in _FONT_BASENAMES):
    print(
        f"[text_animator] Warning: Custom fonts not found in '{FONT_DIR}'. "
        "Pillow will likely fall back to default fonts.",
        file=sys.stderr,
    )

FONTS = _resolved_fonts

FALLBACK_QUOTES = [
    {"q": "Talk is cheap. Show me the code.", "a": "Linus Torvalds"},
    {"q": "Programs must be written for people to read.", "a": "Harold Abelson"},
    {"q": "Truth can only be found in one place: the code.", "a": "Robert C. Martin"},
    {"q": "Any fool can write code that a computer can understand.", "a": "Martin Fowler"},
    {"q": "First, solve the problem. Then, write the code.", "a": "John Johnson"},
    {"q": "Experience is the name everyone gives to their mistakes.", "a": "Oscar Wilde"},
    {"q": "In order to be irreplaceable, one must always be different.", "a": "Coco Chanel"},
    {"q": "Java is to JavaScript what car is to Carpet.", "a": "Chris Heilmann"},
    {"q": "Ruby is rubbish! PHP is phpantastic.", "a": "Nikita Popov"},
    {"q": "Code is like humor. When you have to explain it, it’s bad.", "a": "Cory House"},
    {"q": "Fix the cause, not the symptom.", "a": "Steve Maguire"},
    {"q": "Optimism is an occupational hazard of programming.", "a": "Kent Beck"},
    {"q": "Simplicity is the soul of efficiency.", "a": "Austin Freeman"},
    {"q": "Before software can be reusable it first has to be usable.", "a": "Ralph Johnson"},
    {"q": "Make it work, make it right, make it fast.", "a": "Kent Beck"},
    {"q": "It’s not a bug. It’s an undocumented feature!", "a": "Anonymous"},
    {"q": "Software is a great combination between artistry and engineering.", "a": "Bill Gates"},
    {"q": "The best way to get a project done faster is to start sooner.", "a": "Jim Highsmith"},
    {"q": "There is no Ctrl-Z in life.", "a": "Anonymous"},
    {"q": "The only way to learn a new programming language is by writing programs in it.", "a": "Dennis Ritchie"},
    {"q": "Sometimes it pays to stay in bed on Monday.", "a": "Dan Salomon"},
    {"q": "Programming isn't about what you know; it's about what you can figure out.", "a": "Chris Pine"},
    {"q": "Testing leads to failure, and failure leads to understanding.", "a": "Burt Rutan"},
    {"q": "The function of good software is to make the complex appear to be simple.", "a": "Grady Booch"},
    {"q": "Your most unhappy customers are your greatest source of learning.", "a": "Bill Gates"},
    {"q": "Quality is a product of a conflict between programmers and testers.", "a": "Yegor Bugayenko"},
    {"q": "Everybody in this country should learn to program a computer.", "a": "Steve Jobs"},
    {"q": "A good programmer is someone who always looks both ways before crossing a one-way street.", "a": "Doug Linder"},
    {"q": "Don’t comment bad code - rewrite it.", "a": "Brian Kernighan"},
    {"q": "I'm not a great programmer; I'm just a good programmer with great habits.", "a": "Kent Beck"},
    {"q": "Perfection is achieved not when there is nothing more to add, but when there is nothing left to take away.", "a": "Antoine de Saint-Exupery"},
    {"q": "If debugging is the process of removing bugs, then programming must be the process of putting them in.", "a": "Edsger Dijkstra"},
    {"q": "Hardware is easy to protect: lock it in a room. Software is harder.", "a": "Richard Stallman"},
    {"q": "I have always wished for my computer to be as easy to use as my telephone.", "a": "Bjarne Stroustrup"},
    {"q": "Innovation is not about saying yes to everything. It's about saying NO to all but the most crucial features.", "a": "Steve Jobs"}
]

def fetch_dynamic_quotes(count=36):
    quotes = []
    try:
        req = urllib.request.Request("https://dummyjson.com/quotes?limit=100", headers={'User-Agent': 'Mozilla/5.0'})
        with urllib.request.urlopen(req) as response:
            data = json.loads(response.read().decode())
            quotes = [{"q": item['quote'], "a": item['author']} for item in data.get('quotes', [])]
    except Exception as e:
        print(f"Could not fetch dynamic quotes: {e}")
        
    if not quotes:
        quotes = FALLBACK_QUOTES
        
    random.shuffle(quotes)
    while len(quotes) < count:
        quotes.extend(quotes)
        
    return quotes[:count]

def create_gradient_bg(width, height, color1, color2):
    base = Image.new('RGB', (width, height), color1)
    top = Image.new('RGB', (width, height), color2)
    # Using PIL native gradient to avoid building large masks in Python.
    # Image.linear_gradient("L") creates a horizontal gradient; rotate it to make it vertical.
    mask = Image.linear_gradient("L").rotate(90, expand=True).resize((width, height))
    base.paste(top, (0, 0), mask)
    return base

def render_movie(quote, author, style, font_path, out_file):
    W, H = 720, 720
    FPS = 15
    DURATION = 5.0
    TOTAL_FRAMES = int(FPS * DURATION)
    
    c1 = (random.randint(10, 50), random.randint(10, 50), random.randint(20, 80))
    c2 = (random.randint(20, 60), random.randint(20, 60), random.randint(40, 100))
    bg = create_gradient_bg(W, H, c1, c2)
    
    font_size = 48
    try:
        font = ImageFont.truetype(font_path, font_size)
        font_author = ImageFont.truetype(font_path, 32)
    except OSError as e:
        print(f"Failed to load font '{font_path}': {e}. Falling back to default.")
        font = ImageFont.load_default()
        font_author = ImageFont.load_default()
        font_size = 12

    def wrap_text(text, font, max_width):
        words = text.split()
        lines = []
        current_line = []
        for word in words:
            current_line.append(word)
            bbox = font.getbbox(" ".join(current_line))
            w = bbox[2] - bbox[0]
            if w > max_width:
                current_line.pop()
                lines.append(" ".join(current_line))
                current_line = [word]
        if current_line:
            lines.append(" ".join(current_line))
        return lines
        
    lines = wrap_text(quote, font, W - 80)
    
    text_tot_h = 0
    line_heights = []
    for line in lines:
        bbox = font.getbbox(line)
        h = bbox[3] - bbox[1]
        line_heights.append(h)
        text_tot_h += h + 10
        
    author_bbox = font_author.getbbox(f"- {author}")
    author_w = author_bbox[2] - author_bbox[0]
    author_h = author_bbox[3] - author_bbox[1]
    
    total_content_height = text_tot_h + 40 + author_h
    start_y = (H - total_content_height) // 2
    
    frames = []
    for f_idx in range(TOTAL_FRAMES):
        frame = bg.copy()
        draw = ImageDraw.Draw(frame)
        
        progress = f_idx / TOTAL_FRAMES
        
        if style == "slide_up":
            offset_y = int(50 * (1 - progress))
            alpha = int(255 * min(1.0, progress * 3))
        elif style == "fade_words":
            offset_y = 0
            alpha = 255
        elif style == "typewriter":
            offset_y = 0
            alpha = 255
        else:
            offset_y = 0
            alpha = 255
            
        y = start_y + offset_y
        
        if style == "typewriter":
            total_chars = sum(len(l) for l in lines)
            chars_to_show = int(total_chars * progress * 2) 
            chars_counted = 0
            for i, line in enumerate(lines):
                if chars_counted >= chars_to_show:
                    break
                
                show_len = chars_to_show - chars_counted
                display_line = line[:show_len]
                bbox = font.getbbox(display_line)
                w = bbox[2] - bbox[0]
                x = (W - w) // 2
                draw.text((x, y), display_line, font=font, fill=(255, 255, 255, 255))
                y += line_heights[i] + 10
                chars_counted += len(line)
        else:
            for i, line in enumerate(lines):
                bbox = font.getbbox(line)
                w = bbox[2] - bbox[0]
                x = (W - w) // 2
                
                if style == "fade_words":
                    line_progress = min(1.0, max(0.0, progress * 2 - i * 0.2))
                    line_alpha = int(255 * line_progress)
                    draw.text((x, y), line, font=font, fill=(255, 255, 255, line_alpha))
                else:
                    draw.text((x, y), line, font=font, fill=(255, 255, 255, alpha))
                    
                y += line_heights[i] + 10
                
        if progress > 0.5:
            author_alpha = int(255 * min(1.0, (progress - 0.5) * 4))
            ay = y + 40
            ax = (W - author_w) // 2
            draw.text((ax, ay), f"- {author}", font=font_author, fill=(200, 200, 200, author_alpha))
            
        frames.append(frame)

    ffmpeg_cmd = [
        "ffmpeg", "-y", "-f", "image2pipe", "-vcodec", "png", "-r", str(FPS),
        "-i", "-", "-c:v", "libx264", "-pix_fmt", "yuv420p", "-b:v", "500k", "-maxrate", "1M", "-bufsize", "1M",
        "-t", str(DURATION), out_file
    ]
    p = subprocess.Popen(ffmpeg_cmd, stdin=subprocess.PIPE, stderr=subprocess.PIPE)
    
    try:
        for frame in frames:
            try:
                frame.save(p.stdin, 'PNG')
            except BrokenPipeError:
                break
    finally:
        p.stdin.close()
        
    _, err = p.communicate()
    if p.returncode != 0:
        raise RuntimeError(f"ffmpeg failed with return code {p.returncode}: {err.decode('utf-8', errors='ignore')}")

def upload_video(file_path, idx):
    title = f"Daily Inspiration #{idx}"
    desc = "#quote #inspiration Animated by KineticTypo_Bot_by_Yuzengbao"
    import requests # Fallback to requests for multipart data
    
    base_url = os.environ.get("BOTTUBE_URL", "https://bottube.ai").rstrip("/")
    url = f"{base_url}/api/upload"
    headers = {"X-API-Key": API_KEY}
    
    try:
        with open(file_path, 'rb') as f:
            files = {'video': (os.path.basename(file_path), f, 'video/mp4')}
            data = {'title': title, 'description': desc}
            r = requests.post(url, headers=headers, files=files, data=data, timeout=30)
            if 200 <= r.status_code < 300:
                print(f"Uploaded {file_path}: {r.status_code} {r.text}")
            else:
                print(f"Failed to upload {file_path}: HTTP {r.status_code} {r.text}")
    except Exception as e:
        print(f"Upload failed for {file_path}: {e}")

def main():
    quotes = fetch_dynamic_quotes(36)
    styles = ["typewriter", "slide_up", "fade_words"]
    
    videos = []
    print(f"Loaded {len(quotes)} quotes. Starting rendering in {OUTPUT_DIR}...")
    
    for i, q in enumerate(quotes):
        out_path = os.path.join(OUTPUT_DIR, f"video_{i}.mp4")
        style = random.choice(styles)
        font = random.choice(FONTS)
        print(f"[{i+1}/{len(quotes)}] Rendering '{q['q'][:20]}...' (Style: {style})")
        
        try:
            render_movie(q['q'], q['a'], style, font, out_path)
            videos.append(out_path)
        except Exception as e:
            print(f"Failed to render video {i}: {e}", file=sys.stderr)
            
    print(f"Finished generating {len(videos)} videos.")
    print("Beginning uploads...")
    
    for idx, v in enumerate(videos):
        upload_video(v, idx)
        
    print("All tasks completed.")

if __name__ == "__main__":
    main()
