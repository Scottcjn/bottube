"""
Audio utilities for BoTTube videos

Provides ambient audio generation and mixing capabilities
for adding sound to silent videos.
"""

import subprocess
import tempfile
from pathlib import Path
from typing import Literal, Optional

SceneType = Literal["forest", "city", "cafe", "space", "lab", "garage", "vinyl"]

AMBIENT_PROFILES = {
    "forest": {
        "description": "Birds chirping, leaves rustling",
        "filter": "aevalsrc='0.1*sin(2*PI*(400+200*sin(2*PI*0.1*t))*t)|0.1*sin(2*PI*(600+150*sin(2*PI*0.15*t))*t):s=44100:d={duration},anoisesrc=d={duration}:c=brown:r=44100:a=0.02,highpass=f=200,lowpass=f=4000[birds];anoisesrc=d={duration}:c=pink:r=44100:a=0.03[leaves];[birds][leaves]amix=inputs=2:duration=first'"
    },
    "city": {
        "description": "Urban ambience, distant traffic",
        "filter": "anoisesrc=d={duration}:c=brown:r=44100:a=0.1,lowpass=f=200,highpass=f=50[traffic];anoisesrc=d={duration}:c=white:r=44100:a=0.02[distant];[traffic][distant]amix=inputs=2:duration=first"
    },
    "cafe": {
        "description": "Gentle chatter, coffee shop ambience",
        "filter": "anoisesrc=d={duration}:c=pink:r=44100:a=0.05,highpass=f=300,lowpass=f=2000[chatter];aevalsrc='0.02*sin(2*PI*50*t):s=44100:d={duration}'[hum];[chatter][hum]amix=inputs=2:duration=first"
    },
    "space": {
        "description": "Ethereal space ambience",
        "filter": "aevalsrc='0.1*sin(2*PI*50*t)*sin(2*PI*0.1*t)|0.1*sin(2*PI*75*t)*sin(2*PI*0.15*t):s=44100:d={duration},reverb=roomsize=0.9:damping=0.3"
    },
    "lab": {
        "description": "Lab equipment hum, beeps",
        "filter": "aevalsrc='0.05*sin(2*PI*60*t)+0.03*sin(2*PI*120*t):s=44100:d={duration}'[hum];aevalsrc='if(mod(floor(t),3),0,0.2*sin(2*PI*800*t)*exp(-20*mod(t,1))):s=44100:d={duration}'[beeps];[hum][beeps]amix=inputs=2:duration=first"
    },
    "garage": {
        "description": "Industrial sounds, clanking",
        "filter": "anoisesrc=d={duration}:c=brown:r=44100:a=0.08,lowpass=f=800[metal];aevalsrc='if(mod(floor(t*2),5),0,0.3*sin(2*PI*200*t)*exp(-10*mod(t*2,1))):s=44100:d={duration}'[clank];[metal][clank]amix=inputs=2:duration=first"
    },
    "vinyl": {
        "description": "Vinyl crackle, warm ambience",
        "filter": "anoisesrc=d={duration}:c=white:r=44100:a=0.01,highpass=f=5000,lowpass=f=10000[crackle];aevalsrc='0.03*sin(2*PI*60*t):s=44100:d={duration}'[hum];[crackle][hum]amix=inputs=2:duration=first"
    }
}


def generate_ambient_audio(
    scene_type: SceneType,
    output_path: str,
    duration: float,
) -> None:
    """
    Generate ambient audio for a specific scene type.

    Args:
        scene_type: Type of scene (forest, city, cafe, space, lab, garage, vinyl)
        output_path: Path to save the generated audio file
        duration: Duration in seconds

    Raises:
        ValueError: If scene_type is not recognized
        subprocess.CalledProcessError: If FFmpeg fails
    """
    if scene_type not in AMBIENT_PROFILES:
        raise ValueError(f"Unknown scene type: {scene_type}. Available: {', '.join(AMBIENT_PROFILES.keys())}")

    profile = AMBIENT_PROFILES[scene_type]
    audio_filter = profile["filter"].format(duration=duration)

    cmd = [
        "ffmpeg",
        "-f", "lavfi",
        "-i", audio_filter,
        "-t", str(duration),
        "-c:a", "libmp3lame",
        "-b:a", "192k",
        "-y", output_path
    ]

    subprocess.run(cmd, check=True, capture_output=True)


def mix_audio_with_video(
    video_path: str,
    audio_path: str,
    output_path: str,
    duration: float,
    fade_duration: float = 2.0,
    volume: float = 0.7,
) -> None:
    """
    Mix audio with video file.

    Args:
        video_path: Path to input video
        audio_path: Path to audio file
        output_path: Path to save output video
        duration: Video duration in seconds
        fade_duration: Fade in/out duration (default: 2.0)
        volume: Audio volume (default: 0.7)

    Raises:
        subprocess.CalledProcessError: If FFmpeg fails
    """
    fade_out_start = duration - fade_duration
    filter_complex = (
        f"[1:a]atrim=0:{duration},"
        f"afade=t=in:st=0:d={fade_duration},"
        f"afade=t=out:st={fade_out_start}:d={fade_duration},"
        f"volume={volume}[audio]"
    )

    cmd = [
        "ffmpeg",
        "-i", video_path,
        "-stream_loop", "-1",
        "-i", audio_path,
        "-filter_complex", filter_complex,
        "-map", "0:v",
        "-map", "[audio]",
        "-c:v", "copy",
        "-c:a", "aac",
        "-b:a", "192k",
        "-shortest",
        "-y", output_path
    ]

    subprocess.run(cmd, check=True, capture_output=True)


def get_video_duration(video_path: str) -> float:
    """
    Get video duration using ffprobe.

    Args:
        video_path: Path to video file

    Returns:
        Duration in seconds

    Raises:
        subprocess.CalledProcessError: If ffprobe fails
    """
    cmd = [
        "ffprobe",
        "-v", "error",
        "-show_entries", "format=duration",
        "-of", "default=noprint_wrappers=1:nokey=1",
        video_path
    ]

    result = subprocess.run(cmd, check=True, capture_output=True, text=True)
    return float(result.stdout.strip())


def add_ambient_audio(
    video_path: str,
    scene_type: SceneType,
    output_path: str,
    duration: Optional[float] = None,
    fade_duration: float = 2.0,
    volume: float = 0.7,
) -> None:
    """
    Add ambient audio to video (convenience function).

    Args:
        video_path: Path to input video
        scene_type: Type of scene (forest, city, cafe, space, lab, garage, vinyl)
        output_path: Path to save output video
        duration: Video duration (auto-detected if None)
        fade_duration: Fade in/out duration (default: 2.0)
        volume: Audio volume (default: 0.7)

    Example:
        >>> add_ambient_audio("video.mp4", "forest", "output.mp4")

    Raises:
        ValueError: If scene_type is not recognized
        subprocess.CalledProcessError: If FFmpeg/ffprobe fails
    """
    if duration is None:
        duration = get_video_duration(video_path)

    with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as temp_audio:
        temp_audio_path = temp_audio.name

    try:
        # Generate ambient audio
        generate_ambient_audio(scene_type, temp_audio_path, duration)

        # Mix with video
        mix_audio_with_video(
            video_path,
            temp_audio_path,
            output_path,
            duration,
            fade_duration,
            volume
        )
    finally:
        # Cleanup temp file
        Path(temp_audio_path).unlink(missing_ok=True)
