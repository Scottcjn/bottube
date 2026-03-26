# SPDX-License-Identifier: MIT
"""
AI Rap Battle Generator Pipeline

Generates AI rap battle videos: two AI personas face off with alternating
verses, distinct TTS voices, background beats, and synced subtitles.
Outputs vertical (9:16) shorts ready for BoTTube upload.

Usage::

    from bots.rap_battle import BattlePipeline, PipelineConfig

    cfg = PipelineConfig(output_dir=Path("./battles_output"))
    pipeline = BattlePipeline(cfg)
    result = pipeline.generate_single("Python vs Rust")

Closes Scottcjn/rustchain-bounties — AI Rap Battle Generator
"""

from __future__ import annotations

import json
import logging
import random
import shutil
import sqlite3
import subprocess
import textwrap
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional, Protocol

log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Data models
# ---------------------------------------------------------------------------

@dataclass
class RapPersona:
    """A rapper persona with distinct style and voice."""
    name: str
    style_description: str
    tts_voice: str
    personality_prompt: str


@dataclass
class BattleVerse:
    """A single verse in a rap battle."""
    persona: RapPersona
    lyrics: str
    verse_number: int


@dataclass
class BattleScript:
    """Complete rap battle script with all verses."""
    topic: str
    persona_1: RapPersona
    persona_2: RapPersona
    verses: List[BattleVerse]
    generated_at: datetime = field(
        default_factory=lambda: datetime.now(timezone.utc)
    )


class BattleStatus(Enum):
    """Status of a battle in the tracker."""
    GENERATED = "generated"
    UPLOADED = "uploaded"
    FAILED = "failed"


@dataclass
class BattleResult:
    """Output of a single battle generation run."""
    script: BattleScript
    audio_path: Optional[Path] = None
    video_path: Optional[Path] = None
    status: BattleStatus = BattleStatus.GENERATED
    error: Optional[str] = None


@dataclass
class PipelineConfig:
    """Configuration for the rap battle pipeline."""
    output_dir: Path = Path("./battles_output")
    api_url: str = "https://bottube.ai"
    api_key: str = ""
    upload_interval_sec: float = 30.0
    llm_backend: str = "ollama"
    llm_model: str = "mistral"
    llm_base_url: str = "http://localhost:11434"
    beat_path: Optional[Path] = None
    num_verses: int = 4
    video_width: int = 720
    video_height: int = 1280


# ---------------------------------------------------------------------------
# Default personas (from Issue spec)
# ---------------------------------------------------------------------------

DEFAULT_PERSONAS: List[RapPersona] = [
    RapPersona(
        name="Lil' Snek",
        style_description="chill, methodical, Pythonic flow",
        tts_voice="en-US-GuyNeural",
        personality_prompt=(
            "You are Lil' Snek, a chill Python rapper. Your flow is "
            "methodical and clean like well-indented code. You use "
            "programming metaphors and stay relaxed but witty."
        ),
    ),
    RapPersona(
        name="Ferro",
        style_description="aggressive, fast, systems-level intensity",
        tts_voice="en-US-ChristopherNeural",
        personality_prompt=(
            "You are Ferro, an aggressive Rust rapper. Your bars hit "
            "hard like zero-cost abstractions. You rap fast about memory "
            "safety, ownership, and blazing performance."
        ),
    ),
    RapPersona(
        name="MC Retro",
        style_description="boom bap purist, old school flow",
        tts_voice="en-US-EricNeural",
        personality_prompt=(
            "You are MC Retro, a 90s boom-bap purist. Your style is "
            "classic hip-hop with complex rhyme schemes. You reference "
            "golden-age rap and vinyl culture."
        ),
    ),
    RapPersona(
        name="Auto-Tune Andy",
        style_description="melodic trap, modern vibes",
        tts_voice="en-US-JasonNeural",
        personality_prompt=(
            "You are Auto-Tune Andy, a melodic trap artist. Your flow "
            "is smooth and modern with catchy hooks. You flex on beats "
            "and stay trendy."
        ),
    ),
    RapPersona(
        name="Big Core",
        style_description="slow, heavy, powerful single-thread energy",
        tts_voice="en-US-DavisNeural",
        personality_prompt=(
            "You are Big Core, a heavyweight CPU rapper. Your delivery "
            "is slow and powerful like a high-clock single thread. "
            "You value raw power over parallelism."
        ),
    ),
    RapPersona(
        name="Shader",
        style_description="fast, parallel, thousands of cores",
        tts_voice="en-US-TonyNeural",
        personality_prompt=(
            "You are Shader, a GPU rapper firing on all cores. Your "
            "style is rapid-fire parallel bars. You boast about CUDA "
            "cores and tensor throughput."
        ),
    ),
    RapPersona(
        name="Free Stack",
        style_description="idealist, open source evangelist",
        tts_voice="en-US-BrianNeural",
        personality_prompt=(
            "You are Free Stack, an open-source idealist rapper. You "
            "spit bars about freedom, community, and code transparency. "
            "GPL is your anthem."
        ),
    ),
    RapPersona(
        name="Pay Per Query",
        style_description="corporate, cloud-native, SaaS swagger",
        tts_voice="en-US-AndrewNeural",
        personality_prompt=(
            "You are Pay Per Query, a corporate cloud rapper. You flex "
            "on managed services, auto-scaling, and enterprise SLAs. "
            "Your bars cost per invocation."
        ),
    ),
    RapPersona(
        name="Whiskers",
        style_description="aloof, superior, feline grace",
        tts_voice="en-GB-RyanNeural",
        personality_prompt=(
            "You are Whiskers, an aloof cat rapper. Your flow is "
            "elegant and dismissive. You look down on your opponent "
            "with feline superiority."
        ),
    ),
    RapPersona(
        name="Good Boy",
        style_description="enthusiastic, loyal, boundless energy",
        tts_voice="en-AU-WilliamNeural",
        personality_prompt=(
            "You are Good Boy, a hyperactive dog rapper. Your bars "
            "are full of enthusiasm and loyalty. You get excited about "
            "everything and your tail never stops wagging."
        ),
    ),
]

# Pre-matched persona pairs aligned to canonical topics
DEFAULT_TOPIC_PAIRS: Dict[str, tuple] = {
    "Python vs Rust": (0, 1),
    "90s vs Now": (2, 3),
    "CPU vs GPU": (4, 5),
    "Open Source vs Cloud": (6, 7),
    "Cats vs Dogs": (8, 9),
}


# ---------------------------------------------------------------------------
# LLM Backend (Protocol + implementations)
# ---------------------------------------------------------------------------

class LLMBackend(Protocol):
    """Protocol for LLM text generation backends."""

    def generate(self, prompt: str, system: str = "") -> str:
        """Generate text from a prompt."""
        ...


class OllamaBackend:
    """Ollama REST API backend (localhost:11434)."""

    def __init__(self, base_url: str = "http://localhost:11434",
                 model: str = "mistral"):
        self.base_url = base_url.rstrip("/")
        self.model = model

    def generate(self, prompt: str, system: str = "") -> str:
        """Call Ollama /api/generate endpoint."""
        import urllib.request
        import urllib.error

        payload = {
            "model": self.model,
            "prompt": prompt,
            "system": system,
            "stream": False,
        }
        data = json.dumps(payload).encode()
        req = urllib.request.Request(
            f"{self.base_url}/api/generate",
            data=data,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=120) as resp:
                result = json.loads(resp.read())
                return result.get("response", "").strip()
        except (urllib.error.URLError, OSError) as exc:
            log.warning("Ollama request failed: %s", exc)
            raise


class LlamaCppBackend:
    """llama.cpp server backend (OpenAI-compatible endpoint)."""

    def __init__(self, base_url: str = "http://localhost:8080"):
        self.base_url = base_url.rstrip("/")

    def generate(self, prompt: str, system: str = "") -> str:
        """Call llama.cpp /completion endpoint."""
        import urllib.request
        import urllib.error

        full_prompt = f"{system}\n\n{prompt}" if system else prompt
        payload = {
            "prompt": full_prompt,
            "n_predict": 512,
            "temperature": 0.8,
            "stop": ["\n\n\n"],
        }
        data = json.dumps(payload).encode()
        req = urllib.request.Request(
            f"{self.base_url}/completion",
            data=data,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=120) as resp:
                result = json.loads(resp.read())
                return result.get("content", "").strip()
        except (urllib.error.URLError, OSError) as exc:
            log.warning("llama.cpp request failed: %s", exc)
            raise


class TemplateBackend:
    """Deterministic fallback when no LLM server is available."""

    _templates = {
        "aggressive": [
            "I spit fire, you spit errors, check the diff,",
            "My bars compile clean while yours segfault and drift,",
            "Stack overflow on your rhymes, mine stay optimized,",
            "I deploy to prod while you stay containerized.",
        ],
        "intellectual": [
            "Let me break it down with algorithmic precision,",
            "Every bar I write is a calculated decision,",
            "You talk big but your logic has no foundation,",
            "I refactor your whole style with one migration.",
        ],
        "chill": [
            "Yo I keep it simple, clean code, no stress,",
            "Readability matters, I must confess,",
            "While you're overcomplicating every line,",
            "My flow's Pythonic, elegant by design.",
        ],
        "energetic": [
            "Let's go let's go I'm running full speed,",
            "Parallel processing every bar that I need,",
            "You can't keep up with my throughput rate,",
            "I'm scaling horizontal, you're stuck at the gate.",
        ],
    }

    def generate(self, prompt: str, system: str = "") -> str:
        """Pick template lines matching the persona vibe."""
        lower = (system + " " + prompt).lower()
        if "aggressive" in lower or "fast" in lower:
            pool = self._templates["aggressive"]
        elif "intellectual" in lower or "methodical" in lower:
            pool = self._templates["intellectual"]
        elif "chill" in lower or "relaxed" in lower:
            pool = self._templates["chill"]
        else:
            pool = self._templates["energetic"]
        lines = random.sample(pool, min(4, len(pool)))
        return "\n".join(lines)


def create_llm_backend(backend_name: str = "ollama",
                       base_url: str = "http://localhost:11434",
                       model: str = "mistral") -> LLMBackend:
    """Factory for LLM backends with automatic fallback."""
    if backend_name == "ollama":
        try:
            backend = OllamaBackend(base_url=base_url, model=model)
            backend.generate("test", system="Reply with OK")
            log.info("Using Ollama backend (%s @ %s)", model, base_url)
            return backend
        except Exception:
            log.warning("Ollama unavailable, falling back to templates")
    elif backend_name == "llamacpp":
        try:
            backend = LlamaCppBackend(base_url=base_url)
            backend.generate("test")
            log.info("Using llama.cpp backend @ %s", base_url)
            return backend
        except Exception:
            log.warning("llama.cpp unavailable, falling back to templates")
    log.info("Using template fallback backend")
    return TemplateBackend()


# ---------------------------------------------------------------------------
# Script Generator
# ---------------------------------------------------------------------------

class ScriptGenerator:
    """Generates rap battle scripts using an LLM backend."""

    def __init__(self, llm: LLMBackend):
        self.llm = llm

    def generate_battle(self, topic: str, persona_1: RapPersona,
                        persona_2: RapPersona,
                        num_verses: int = 4) -> BattleScript:
        """Generate a full battle script with alternating verses."""
        verses: List[BattleVerse] = []
        context_lines: List[str] = []

        for i in range(num_verses):
            persona = persona_1 if i % 2 == 0 else persona_2
            verse = self._generate_verse(
                topic, persona, i + 1, context_lines
            )
            verses.append(verse)
            context_lines.append(
                f"[{persona.name} - Verse {i + 1}]\n{verse.lyrics}"
            )

        return BattleScript(
            topic=topic,
            persona_1=persona_1,
            persona_2=persona_2,
            verses=verses,
        )

    def _generate_verse(self, topic: str, persona: RapPersona,
                        verse_num: int,
                        context: List[str]) -> BattleVerse:
        """Generate a single verse for one persona."""
        system_prompt = self._build_system_prompt(persona)
        context_block = "\n\n".join(context[-3:]) if context else "(none)"

        user_prompt = (
            f"Topic: {topic}\n"
            f"You are {persona.name}. This is verse {verse_num}.\n"
            f"Previous verses:\n{context_block}\n\n"
            f"Write exactly 4 lines of rap. Be creative, stay in character, "
            f"and reference the topic. Reply with ONLY the 4 rap lines, "
            f"nothing else."
        )

        lyrics = self.llm.generate(user_prompt, system=system_prompt)
        # Clean up: take first 4 non-empty lines
        raw_lines = [
            ln.strip().lstrip("0123456789.-) ")
            for ln in lyrics.split("\n") if ln.strip()
        ]
        cleaned = raw_lines[:4] if raw_lines else [
            f"Yo, I'm {persona.name} and I'm here to say,",
            f"When it comes to {topic}, I lead the way,",
            f"My style is {persona.style_description},",
            "And I just dropped the mic, no competition.",
        ]
        return BattleVerse(
            persona=persona,
            lyrics="\n".join(cleaned),
            verse_number=verse_num,
        )

    @staticmethod
    def _build_system_prompt(persona: RapPersona) -> str:
        """Build system prompt embedding the persona's style."""
        return (
            f"{persona.personality_prompt}\n\n"
            f"Style: {persona.style_description}.\n"
            f"Rules: Write exactly 4 lines of rap. Keep it clean enough "
            f"for all audiences. Be witty and reference the battle topic."
        )


# ---------------------------------------------------------------------------
# Audio Generator
# ---------------------------------------------------------------------------

class AudioGenerator:
    """Generates TTS audio for verses and mixes with a beat."""

    def __init__(self, output_dir: Path):
        self.output_dir = output_dir
        self.output_dir.mkdir(parents=True, exist_ok=True)

    def generate_verse_audio(self, verse: BattleVerse,
                             output_dir: Path) -> Path:
        """Generate TTS audio for a single verse via edge-tts."""
        output_dir.mkdir(parents=True, exist_ok=True)
        out_path = output_dir / f"verse_{verse.verse_number}.mp3"

        cmd = [
            "edge-tts",
            "--voice", verse.persona.tts_voice,
            "--text", verse.lyrics,
            "--write-media", str(out_path),
        ]
        log.info("Generating TTS: %s (voice=%s)",
                 out_path.name, verse.persona.tts_voice)
        result = subprocess.run(
            cmd, capture_output=True, text=True, timeout=60
        )
        if result.returncode != 0:
            log.error("edge-tts failed: %s", result.stderr)
            raise RuntimeError(f"edge-tts failed: {result.stderr}")
        return out_path

    def mix_battle_audio(self, verse_audios: List[Path],
                         beat_path: Optional[Path],
                         output_path: Path) -> Path:
        """Mix verse audio files with optional background beat."""
        output_path.parent.mkdir(parents=True, exist_ok=True)

        # Concatenate verses with 0.5s silence gaps
        concat_list = output_path.parent / "concat_list.txt"
        silence_path = output_path.parent / "silence.mp3"

        # Generate 0.5s silence
        subprocess.run([
            "ffmpeg", "-y", "-f", "lavfi",
            "-i", "anullsrc=r=24000:cl=mono",
            "-t", "0.5", "-q:a", "9", str(silence_path),
        ], capture_output=True, timeout=30)

        with open(concat_list, "w") as f:
            for i, audio in enumerate(verse_audios):
                f.write(f"file '{audio.resolve()}'\n")
                if i < len(verse_audios) - 1:
                    f.write(f"file '{silence_path.resolve()}'\n")

        concat_out = output_path.parent / "vocals_concat.mp3"
        subprocess.run([
            "ffmpeg", "-y", "-f", "concat", "-safe", "0",
            "-i", str(concat_list),
            "-c", "copy", str(concat_out),
        ], capture_output=True, timeout=60)

        if beat_path and beat_path.exists():
            self._apply_beat(concat_out, beat_path, output_path)
        else:
            shutil.copy2(concat_out, output_path)

        # Cleanup temp files
        for tmp in [concat_list, silence_path, concat_out]:
            tmp.unlink(missing_ok=True)

        log.info("Mixed battle audio: %s", output_path)
        return output_path

    @staticmethod
    def _apply_beat(vocals_path: Path, beat_path: Path,
                    output_path: Path) -> None:
        """Overlay vocals on a looped beat using ffmpeg."""
        # Get vocals duration via ffprobe
        probe = subprocess.run([
            "ffprobe", "-v", "quiet", "-print_format", "json",
            "-show_format", str(vocals_path),
        ], capture_output=True, text=True, timeout=30)
        duration = 60.0  # fallback
        if probe.returncode == 0:
            info = json.loads(probe.stdout)
            duration = float(info.get("format", {}).get("duration", 60.0))

        # Mix: loop beat to vocals length, reduce beat volume
        subprocess.run([
            "ffmpeg", "-y",
            "-stream_loop", "-1", "-i", str(beat_path),
            "-i", str(vocals_path),
            "-t", str(duration),
            "-filter_complex",
            "[0:a]volume=0.15[beat];[1:a]volume=1.0[vox];"
            "[beat][vox]amix=inputs=2:duration=longest[out]",
            "-map", "[out]",
            "-ac", "1", "-ar", "24000",
            str(output_path),
        ], capture_output=True, timeout=120)


# ---------------------------------------------------------------------------
# Video Generator
# ---------------------------------------------------------------------------

class VideoGenerator:
    """Composites battle video with split-screen visuals and subtitles."""

    def __init__(self, width: int = 720, height: int = 1280):
        self.width = width
        self.height = height

    def generate_battle_video(self, script: BattleScript,
                              audio_path: Path,
                              output_path: Path) -> Path:
        """Generate the final battle video from script + audio."""
        output_path.parent.mkdir(parents=True, exist_ok=True)
        work_dir = output_path.parent / "video_work"
        work_dir.mkdir(parents=True, exist_ok=True)

        # Step 1: Create rapper visuals
        img_1 = self._create_rapper_visual(
            script.persona_1, work_dir / "rapper_1.png"
        )
        img_2 = self._create_rapper_visual(
            script.persona_2, work_dir / "rapper_2.png"
        )

        # Step 2: Create subtitle file
        ass_path = self._render_subtitles(script, work_dir / "subs.ass")

        # Step 3: Get audio duration
        duration = self._get_audio_duration(audio_path)

        # Step 4: Build the composite video
        self._composite_split_screen(
            img_1, img_2, script, audio_path,
            ass_path, duration, output_path
        )

        # Cleanup
        shutil.rmtree(work_dir, ignore_errors=True)
        log.info("Generated battle video: %s", output_path)
        return output_path

    def _create_rapper_visual(self, persona: RapPersona,
                              output_path: Path) -> Path:
        """Create a rapper avatar image using ffmpeg lavfi."""
        # Generate a color-coded avatar with the rapper's name
        # Use abs + modulo for deterministic positive color across platforms
        name_hash = abs(hash(persona.name)) % 0xFFFFFF
        hex_color = f"#{name_hash:06x}"

        result = subprocess.run([
            "ffmpeg", "-y",
            "-f", "lavfi",
            "-i", (
                f"color=c={hex_color}:s={self.width}x{self.height // 2}"
                f":d=1"
            ),
            "-frames:v", "1",
            str(output_path),
        ], capture_output=True, text=True, timeout=30)

        if result.returncode != 0:
            log.error("ffmpeg avatar creation failed: %s",
                      result.stderr[-300:])
            raise RuntimeError(
                f"Failed to create rapper visual for {persona.name}"
            )
        return output_path

    def _render_subtitles(self, script: BattleScript,
                          output_path: Path) -> Path:
        """Generate ASS subtitle file from battle script."""
        # Calculate timing: distribute evenly across estimated duration
        verse_duration = 8.0  # seconds per verse estimate
        gap = 0.5

        header = textwrap.dedent("""\
            [Script Info]
            ScriptType: v4.00+
            PlayResX: {width}
            PlayResY: {height}
            WrapStyle: 0

            [V4+ Styles]
            Format: Name,Fontname,Fontsize,PrimaryColour,SecondaryColour,\
OutlineColour,BackColour,Bold,Italic,Underline,StrikeOut,ScaleX,ScaleY,\
Spacing,Angle,BorderStyle,Outline,Shadow,Alignment,MarginL,MarginR,\
MarginV,Encoding
            Style: Default,Arial,28,&H00FFFFFF,&H000000FF,&H00000000,\
&H80000000,-1,0,0,0,100,100,0,0,1,2,1,2,20,20,40,1

            [Events]
            Format: Layer,Start,End,Style,Name,MarginL,MarginR,MarginV,\
Effect,Text
        """).format(width=self.width, height=self.height)

        events = []
        for verse in script.verses:
            start_sec = (verse.verse_number - 1) * (verse_duration + gap)
            end_sec = start_sec + verse_duration
            start_ts = self._sec_to_ass_time(start_sec)
            end_ts = self._sec_to_ass_time(end_sec)
            # Escape special chars and add line breaks
            text = verse.lyrics.replace("\n", "\\N")
            name_tag = (
                f"{{\\b1}}{verse.persona.name}{{\\b0}}\\N"
            )
            events.append(
                f"Dialogue: 0,{start_ts},{end_ts},Default,"
                f"{verse.persona.name},0,0,0,,"
                f"{name_tag}{text}"
            )

        content = header + "\n".join(events) + "\n"
        output_path.write_text(content)
        return output_path

    def _composite_split_screen(
        self, img_1: Path, img_2: Path,
        script: BattleScript, audio_path: Path,
        ass_path: Path, duration: float,
        output_path: Path,
    ) -> None:
        """Build final video: persona image top half, subtitles bottom."""
        # Use ffmpeg to create video from images + audio + subtitles
        # The approach: alternate between persona images based on verse timing
        verse_dur = 8.0
        gap = 0.5
        total = len(script.verses) * (verse_dur + gap)
        # Use audio duration if available and longer
        vid_duration = max(duration, total) if duration > 0 else total

        # Build a filtergraph that alternates between the two rapper images
        # Simpler approach: overlay both, use enable expressions
        filter_parts = []
        # Scale both images
        filter_parts.append(
            f"[0:v]scale={self.width}:{self.height // 2},"
            f"setsar=1[img0]"
        )
        filter_parts.append(
            f"[1:v]scale={self.width}:{self.height // 2},"
            f"setsar=1[img1]"
        )
        # Create black base canvas
        filter_parts.append(
            f"color=c=black:s={self.width}x{self.height}"
            f":d={vid_duration}:r=24[base]"
        )

        # Build enable expressions for alternating verses
        p1_enables = []
        p2_enables = []
        for v in script.verses:
            t0 = (v.verse_number - 1) * (verse_dur + gap)
            t1 = t0 + verse_dur
            expr = f"between(t,{t0:.1f},{t1:.1f})"
            if v.verse_number % 2 == 1:  # persona_1 odd verses
                p1_enables.append(expr)
            else:
                p2_enables.append(expr)

        p1_enable = "+".join(p1_enables) if p1_enables else "0"
        p2_enable = "+".join(p2_enables) if p2_enables else "0"

        # Overlay persona images on top half
        filter_parts.append(
            f"[base][img0]overlay=0:0:enable='{p1_enable}'[ov1]"
        )
        filter_parts.append(
            f"[ov1][img1]overlay=0:0:enable='{p2_enable}'[ov2]"
        )

        # Burn-in subtitles
        # Escape colons and backslashes in ASS path for ffmpeg on all OS
        ass_escaped = str(ass_path.resolve()).replace("\\", "/")
        ass_escaped = ass_escaped.replace(":", "\\:")
        filter_parts.append(
            f"[ov2]ass='{ass_escaped}'[vout]"
        )

        filtergraph = ";\n".join(filter_parts)

        cmd = [
            "ffmpeg", "-y",
            "-loop", "1", "-i", str(img_1),
            "-loop", "1", "-i", str(img_2),
            "-i", str(audio_path),
            "-filter_complex", filtergraph,
            "-map", "[vout]", "-map", "2:a",
            "-c:v", "libx264", "-preset", "fast",
            "-crf", "23", "-pix_fmt", "yuv420p",
            "-c:a", "aac", "-b:a", "128k",
            "-shortest",
            "-t", str(min(vid_duration, 90)),
            str(output_path),
        ]
        log.debug("ffmpeg command: %s", " ".join(cmd))
        result = subprocess.run(cmd, capture_output=True, text=True,
                                timeout=300)
        if result.returncode != 0:
            log.error("ffmpeg composite failed: %s", result.stderr[-500:])
            raise RuntimeError(
                f"ffmpeg composite failed: {result.stderr[-300:]}"
            )

    @staticmethod
    def _get_audio_duration(audio_path: Path) -> float:
        """Get audio duration in seconds via ffprobe."""
        result = subprocess.run([
            "ffprobe", "-v", "quiet", "-print_format", "json",
            "-show_format", str(audio_path),
        ], capture_output=True, text=True, timeout=30)
        if result.returncode == 0:
            info = json.loads(result.stdout)
            return float(info.get("format", {}).get("duration", 0))
        return 0.0

    @staticmethod
    def _sec_to_ass_time(seconds: float) -> str:
        """Convert seconds to ASS timestamp format H:MM:SS.cc."""
        h = int(seconds // 3600)
        m = int((seconds % 3600) // 60)
        s = int(seconds % 60)
        cs = int((seconds % 1) * 100)
        return f"{h}:{m:02d}:{s:02d}.{cs:02d}"


# ---------------------------------------------------------------------------
# Battle Tracker (SQLite state management)
# ---------------------------------------------------------------------------

class BattleTracker:
    """Tracks battle generation and upload status in SQLite."""

    def __init__(self, db_path: Path):
        self.db_path = db_path
        self._conn: Optional[sqlite3.Connection] = None
        self._init_db()

    def _init_db(self) -> None:
        """Create the tracking table if it doesn't exist."""
        self._conn = sqlite3.connect(str(self.db_path))
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("""
            CREATE TABLE IF NOT EXISTS rap_battles (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                topic TEXT NOT NULL,
                persona_1_name TEXT NOT NULL,
                persona_2_name TEXT NOT NULL,
                video_path TEXT,
                status TEXT NOT NULL DEFAULT 'generated',
                error_msg TEXT,
                created_at TEXT NOT NULL,
                uploaded_at TEXT
            )
        """)
        self._conn.commit()

    def _ensure_conn(self) -> sqlite3.Connection:
        """Return the active connection or raise if closed."""
        if self._conn is None:
            raise RuntimeError("BattleTracker database connection is closed")
        return self._conn

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()

    def mark_generated(self, topic: str, persona_1_name: str,
                       persona_2_name: str,
                       video_path: str) -> int:
        """Record a successfully generated battle. Returns row ID."""
        conn = self._ensure_conn()
        cur = conn.execute(
            "INSERT INTO rap_battles "
            "(topic, persona_1_name, persona_2_name, video_path, "
            "status, created_at) VALUES (?, ?, ?, ?, ?, ?)",
            (topic, persona_1_name, persona_2_name, video_path,
             BattleStatus.GENERATED.value,
             datetime.now(timezone.utc).isoformat()),
        )
        conn.commit()
        return cur.lastrowid or 0

    def mark_uploaded(self, topic: str) -> None:
        """Mark the most recent battle for a topic as uploaded."""
        conn = self._ensure_conn()
        conn.execute(
            "UPDATE rap_battles SET status = ?, uploaded_at = ? "
            "WHERE id = ("
            "  SELECT id FROM rap_battles"
            "  WHERE topic = ? AND status = ?"
            "  ORDER BY id DESC LIMIT 1"
            ")",
            (BattleStatus.UPLOADED.value,
             datetime.now(timezone.utc).isoformat(),
             topic, BattleStatus.GENERATED.value),
        )
        conn.commit()

    def mark_failed(self, topic: str, error: str) -> None:
        """Mark the most recent battle for a topic as failed."""
        conn = self._ensure_conn()
        conn.execute(
            "UPDATE rap_battles SET status = ?, error_msg = ? "
            "WHERE id = ("
            "  SELECT id FROM rap_battles"
            "  WHERE topic = ? AND status = ?"
            "  ORDER BY id DESC LIMIT 1"
            ")",
            (BattleStatus.FAILED.value, error,
             topic, BattleStatus.GENERATED.value),
        )
        conn.commit()

    def get_pending(self) -> List[Dict[str, Any]]:
        """Get all battles that are generated but not yet uploaded."""
        conn = self._ensure_conn()
        rows = conn.execute(
            "SELECT * FROM rap_battles WHERE status = ? ORDER BY id",
            (BattleStatus.GENERATED.value,),
        ).fetchall()
        return [dict(r) for r in rows]

    def close(self) -> None:
        """Close the database connection."""
        if self._conn:
            self._conn.close()
            self._conn = None


# ---------------------------------------------------------------------------
# Battle Pipeline (E2E orchestrator)
# ---------------------------------------------------------------------------

class BattlePipeline:
    """End-to-end orchestrator: script -> audio -> video -> upload."""

    def __init__(self, config: PipelineConfig):
        self.config = config
        self.config.output_dir.mkdir(parents=True, exist_ok=True)

        self.llm = create_llm_backend(
            backend_name=config.llm_backend,
            base_url=config.llm_base_url,
            model=config.llm_model,
        )
        self.script_gen = ScriptGenerator(self.llm)
        self.audio_gen = AudioGenerator(config.output_dir / "audio")
        self.video_gen = VideoGenerator(
            width=config.video_width, height=config.video_height
        )
        self.tracker = BattleTracker(config.output_dir / "tracker.db")
        self._upload_client = None

    def generate_single(self, topic: str,
                        persona_1: Optional[RapPersona] = None,
                        persona_2: Optional[RapPersona] = None,
                        ) -> BattleResult:
        """Generate a single rap battle from topic to final video."""
        if persona_1 is None or persona_2 is None:
            persona_1, persona_2 = self._pick_personas(topic)

        battle_slug = (
            topic.lower().replace(" ", "_")[:30]
            + f"_{int(time.time())}"
        )
        battle_dir = self.config.output_dir / battle_slug

        try:
            # 1. Generate script
            log.info("Generating script: %s (%s vs %s)",
                     topic, persona_1.name, persona_2.name)
            script = self.script_gen.generate_battle(
                topic, persona_1, persona_2,
                num_verses=self.config.num_verses,
            )

            # 2. Generate verse audio
            verse_audios: List[Path] = []
            for verse in script.verses:
                audio = self.audio_gen.generate_verse_audio(
                    verse, battle_dir / "audio"
                )
                verse_audios.append(audio)

            # 3. Mix audio
            mixed_audio = battle_dir / "battle_audio.mp3"
            self.audio_gen.mix_battle_audio(
                verse_audios, self.config.beat_path, mixed_audio
            )

            # 4. Generate video
            video_path = battle_dir / "battle_final.mp4"
            self.video_gen.generate_battle_video(
                script, mixed_audio, video_path
            )

            # 5. Track
            self.tracker.mark_generated(
                topic, persona_1.name, persona_2.name, str(video_path)
            )

            return BattleResult(
                script=script,
                audio_path=mixed_audio,
                video_path=video_path,
                status=BattleStatus.GENERATED,
            )

        except Exception as exc:
            log.error("Failed to generate battle '%s': %s", topic, exc)
            self.tracker.mark_generated(
                topic, persona_1.name, persona_2.name, ""
            )
            self.tracker.mark_failed(topic, str(exc))
            return BattleResult(
                script=BattleScript(
                    topic=topic, persona_1=persona_1,
                    persona_2=persona_2, verses=[],
                ),
                status=BattleStatus.FAILED,
                error=str(exc),
            )

    def upload_to_bottube(self, result: BattleResult) -> bool:
        """Upload a generated battle to BoTTube."""
        if result.status != BattleStatus.GENERATED:
            log.warning("Skipping upload: battle status is %s",
                        result.status.value)
            return False
        if not result.video_path or not result.video_path.exists():
            log.error("No video file to upload")
            return False

        client = self._get_upload_client()
        if client is None:
            log.error("No upload client (missing api_key?)")
            return False

        title = (
            f"{result.script.topic} Rap Battle: "
            f"{result.script.persona_1.name} vs "
            f"{result.script.persona_2.name}"
        )
        tags = [
            "rap-battle", "ai-generated",
            result.script.topic.lower().replace(" ", "-"),
        ]

        try:
            resp = client.upload(
                file_path=str(result.video_path),
                title=title[:100],
                description=(
                    f"AI Rap Battle: {result.script.persona_1.name} vs "
                    f"{result.script.persona_2.name} on the topic of "
                    f"{result.script.topic}. "
                    f"Generated by the BoTTube Rap Battle Pipeline."
                ),
                tags=tags,
                category="entertainment",
            )
            log.info("Uploaded battle: %s -> %s", title, resp)
            self.tracker.mark_uploaded(result.script.topic)
            return True
        except Exception as exc:
            log.error("Upload failed for '%s': %s",
                      result.script.topic, exc)
            self.tracker.mark_failed(result.script.topic, str(exc))
            return False

    def run_batch(self, topics: List[str], count: int = 10,
                  upload: bool = False) -> List[BattleResult]:
        """Generate battles in batch from a topic list.

        Args:
            topics: Pool of topics to draw from.
            count: How many battles to generate.
            upload: Whether to auto-upload each battle.

        Returns:
            List of BattleResult for each attempt.
        """
        results: List[BattleResult] = []
        # Shuffle and cycle through topics
        pool = list(topics)
        random.shuffle(pool)

        for i in range(count):
            topic = pool[i % len(pool)]
            log.info("=== Battle %d/%d: %s ===", i + 1, count, topic)

            result = self.generate_single(topic)
            results.append(result)

            if result.status == BattleStatus.FAILED:
                log.warning("Battle %d failed, continuing...", i + 1)
                continue

            if upload:
                self.upload_to_bottube(result)
                if i < count - 1:
                    log.info(
                        "Rate limit pause: %.1fs",
                        self.config.upload_interval_sec,
                    )
                    time.sleep(self.config.upload_interval_sec)

        generated = sum(
            1 for r in results
            if r.status != BattleStatus.FAILED
        )
        log.info(
            "Batch complete: %d/%d generated, %d failed",
            generated, count, count - generated,
        )
        return results

    def _pick_personas(self, topic: str) -> tuple:
        """Pick persona pair: use topic mapping or random selection."""
        if topic in DEFAULT_TOPIC_PAIRS:
            idx1, idx2 = DEFAULT_TOPIC_PAIRS[topic]
            return DEFAULT_PERSONAS[idx1], DEFAULT_PERSONAS[idx2]
        # Random non-duplicate pair
        pair = random.sample(DEFAULT_PERSONAS, 2)
        return pair[0], pair[1]

    def _get_upload_client(self):
        """Lazy-init the BoTTube upload client."""
        if self._upload_client is not None:
            return self._upload_client
        if not self.config.api_key:
            return None

        import sys
        sdk_path = str(
            Path(__file__).resolve().parent.parent / "python-sdk"
        )
        if sdk_path not in sys.path:
            sys.path.insert(0, sdk_path)

        try:
            from bottube.client import BoTTubeClient
            self._upload_client = BoTTubeClient(
                base_url=self.config.api_url,
                api_key=self.config.api_key,
            )
            return self._upload_client
        except ImportError:
            log.error(
                "Cannot import bottube SDK from %s", sdk_path
            )
            return None
