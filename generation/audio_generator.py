import edge_tts
from pathlib import Path
from typing import List, Dict

def generate_audio(verses: List[str], voices: List[str], beat_file: Path) -> Path:
    """
    Generate TTS audio for each verse with synced beats.

    Args:
        verses (List[str]): List of rap verses.
        voices (List[str]): List of voice profiles (e.g., "en-US-Guy" and "en-US-Jess").
        beat_file (Path): Path to the background beat audio file.

    Returns:
        Path: Path to the generated audio file.
    """
    if len(voices) != 2:
        raise ValueError("Exactly two voices are required.")

    output_audio = Path("output_audio.wav")
    combined_audio_tracks = []

    for i, verse in enumerate(verses):
        voice = voices[i % 2]
        tts = edge_tts.Communicate(verse, voice)
        audio_segment = tts.save(Path(f"verse_{i}.wav"))
        combined_audio_tracks.append(audio_segment)

    # Use FFmpeg to merge beat_file and verses if required
    merge_audio_with_ffmpeg(combined_audio_tracks, output_audio, beat_file)
    return output_audio

def merge_audio_with_ffmpeg(audio_tracks: List[Path], output_file: Path, beat_file: Path):
    """Merge verse audio tracks with background beats using FFmpeg."""
    from subprocess import run

    resolved_beat_file = beat_file.resolve()
    resolved_output_file = output_file.resolve()
    resolved_audio_tracks = [track.resolve() for track in audio_tracks]

    input_args = ["-i", str(resolved_beat_file)]
    for track in resolved_audio_tracks:
        input_args.extend(["-i", str(track)])

    input_labels = "".join([f"[{i}]" for i in range(len(resolved_audio_tracks) + 1)])
    filter_complex = f"{input_labels}concat=n={len(resolved_audio_tracks) + 1}:a=1:v=0[out]"

    command = [
        "ffmpeg",
        *input_args,
        "-filter_complex",
        filter_complex,
        "-map",
        "[out]",
        str(resolved_output_file),
    ]
    run(command, check=True)