#!/usr/bin/env python3
"""
Video Transcription Pipeline for BoTTube
Uses faster-whisper for transcription
Bounty: 20-30 RTC
"""

import os
import subprocess
import tempfile
from pathlib import Path

# Requirements: faster-whisper, ffmpeg

def extract_audio(video_path, audio_path):
    """Extract audio from video using ffmpeg."""
    cmd = [
        "ffmpeg", "-y",
        "-i", video_path,
        "-vn",
        "-acodec", "pcm_s16le",
        "-ar", "16000",
        "-ac", "1",
        audio_path
    ]
    result = subprocess.run(cmd, capture_output=True)
    return result.returncode == 0

def transcribe_audio(audio_path, model_size="base"):
    """Transcribe audio using faster-whisper."""
    try:
        from faster_whisper import WhisperModel
        
        model = WhisperModel(model_size, device="cpu", compute_type="int8")
        segments, info = model.transcribe(audio_path)
        
        transcript = " ".join([s.text for s in segments])
        return transcript, info.language
    except ImportError:
        # Fallback to whisper
        try:
            import whisper
            model = whisper.load_model("base")
            result = model.transcribe(audio_path)
            return result["text"], result.get("language", "en")
        except:
            return None, None

def generate_srt(transcript, segments):
    """Generate SRT subtitle file."""
    srt_lines = []
    for i, seg in enumerate(segments, 1):
        start = format_time_srt(seg.start)
        end = format_time_srt(seg.end)
        srt_lines.append(f"{i}\n{start} --> {end}\n{seg.text}\n")
    return "\n".join(srt_lines)

def format_time_srt(seconds):
    """Format seconds to SRT time format."""
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    secs = int(seconds % 60)
    millis = int((seconds % 1) * 1000)
    return f"{hours:02d}:{minutes:02d}:{secs:02d},{millis:03d}"

def generate_vtt(transcript, segments):
    """Generate VTT subtitle file."""
    vtt_lines = ["WEBVTT", ""]
    for seg in segments:
        start = format_time_vtt(seg.start)
        end = format_time_vtt(seg.end)
        vtt_lines.append(f"{start} --> {end}")
        vtt_lines.append(seg.text)
        vtt_lines.append("")
    return "\n".join(vtt_lines)

def format_time_vtt(seconds):
    """Format seconds to VTT time format."""
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    secs = int(seconds % 60)
    millis = int((seconds % 1) * 1000)
    return f"{hours:02d}:{minutes:02d}:{secs:02d}.{millis:03d}"

def process_video(video_path, output_dir=None):
    """Process a single video and generate transcripts."""
    if output_dir is None:
        output_dir = Path(video_path).parent
    
    # Extract audio
    audio_path = tempfile.mktemp(suffix=".wav")
    if not extract_audio(video_path, audio_path):
        return None, None
    
    # Transcribe
    transcript, language = transcribe_audio(audio_path)
    
    # Cleanup
    os.remove(audio_path)
    
    if transcript is None:
        return None, None
    
    # Get segments for subtitles
    try:
        from faster_whisper import WhisperModel
        model = WhisperModel("base", device="cpu", compute_type="int8")
        segments, _ = model.transcribe(audio_path if os.path.exists(audio_path) else video_path)
        segments = list(segments)
    except:
        segments = []
    
    # Generate subtitle files
    video_id = Path(video_path).stem
    if segments:
        srt_path = Path(output_dir) / f"{video_id}.srt"
        vtt_path = Path(output_dir) / f"{video_id}.vtt"
        
        with open(srt_path, "w") as f:
            f.write(generate_srt(transcript, segments))
        
        with open(vtt_path, "w") as f:
            f.write(generate_vtt(transcript, segments))
    
    return transcript, language

def main():
    """Main entry point."""
    import argparse
    parser = argparse.ArgumentParser(description="Transcribe BoTTube videos")
    parser.add_argument("video", help="Video file to transcribe")
    parser.add_argument("--model", default="base", choices=["tiny", "base", "small", "medium"])
    args = parser.parse_args()
    
    transcript, language = process_video(args.video)
    if transcript:
        print(f"Language: {language}")
        print(f"Transcript: {transcript[:200]}...")
    else:
        print("Transcription failed")

if __name__ == "__main__":
    main()
