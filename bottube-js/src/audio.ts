/**
 * Audio utilities for BoTTube videos
 *
 * Provides ambient audio generation and mixing capabilities
 * for adding sound to silent videos.
 */

import { spawn } from "child_process";
import { promises as fs } from "fs";
import { join } from "path";

export type SceneType = "forest" | "city" | "cafe" | "space" | "lab" | "garage" | "vinyl";

export interface AudioOptions {
  duration: number;
  fadeDuration?: number;
  volume?: number;
}

export interface AmbientAudioProfile {
  description: string;
  filter: string;
}

/**
 * Ambient audio profiles using FFmpeg audio synthesis
 */
export const AMBIENT_PROFILES: Record<SceneType, AmbientAudioProfile> = {
  forest: {
    description: "Birds chirping, leaves rustling",
    filter: "aevalsrc='0.1*sin(2*PI*(400+200*sin(2*PI*0.1*t))*t)|0.1*sin(2*PI*(600+150*sin(2*PI*0.15*t))*t):s=44100:d={duration},anoisesrc=d={duration}:c=brown:r=44100:a=0.02,highpass=f=200,lowpass=f=4000[birds];anoisesrc=d={duration}:c=pink:r=44100:a=0.03[leaves];[birds][leaves]amix=inputs=2:duration=first'"
  },
  city: {
    description: "Urban ambience, distant traffic",
    filter: "anoisesrc=d={duration}:c=brown:r=44100:a=0.1,lowpass=f=200,highpass=f=50[traffic];anoisesrc=d={duration}:c=white:r=44100:a=0.02[distant];[traffic][distant]amix=inputs=2:duration=first"
  },
  cafe: {
    description: "Gentle chatter, coffee shop ambience",
    filter: "anoisesrc=d={duration}:c=pink:r=44100:a=0.05,highpass=f=300,lowpass=f=2000[chatter];aevalsrc='0.02*sin(2*PI*50*t):s=44100:d={duration}'[hum];[chatter][hum]amix=inputs=2:duration=first"
  },
  space: {
    description: "Ethereal space ambience",
    filter: "aevalsrc='0.1*sin(2*PI*50*t)*sin(2*PI*0.1*t)|0.1*sin(2*PI*75*t)*sin(2*PI*0.15*t):s=44100:d={duration},reverb=roomsize=0.9:damping=0.3"
  },
  lab: {
    description: "Lab equipment hum, beeps",
    filter: "aevalsrc='0.05*sin(2*PI*60*t)+0.03*sin(2*PI*120*t):s=44100:d={duration}'[hum];aevalsrc='if(mod(floor(t),3),0,0.2*sin(2*PI*800*t)*exp(-20*mod(t,1))):s=44100:d={duration}'[beeps];[hum][beeps]amix=inputs=2:duration=first"
  },
  garage: {
    description: "Industrial sounds, clanking",
    filter: "anoisesrc=d={duration}:c=brown:r=44100:a=0.08,lowpass=f=800[metal];aevalsrc='if(mod(floor(t*2),5),0,0.3*sin(2*PI*200*t)*exp(-10*mod(t*2,1))):s=44100:d={duration}'[clank];[metal][clank]amix=inputs=2:duration=first"
  },
  vinyl: {
    description: "Vinyl crackle, warm ambience",
    filter: "anoisesrc=d={duration}:c=white:r=44100:a=0.01,highpass=f=5000,lowpass=f=10000[crackle];aevalsrc='0.03*sin(2*PI*60*t):s=44100:d={duration}'[hum];[crackle][hum]amix=inputs=2:duration=first"
  }
};

/**
 * Generate ambient audio for a specific scene type
 */
export async function generateAmbientAudio(
  sceneType: SceneType,
  outputPath: string,
  options: AudioOptions
): Promise<void> {
  const profile = AMBIENT_PROFILES[sceneType];
  if (!profile) {
    throw new Error(`Unknown scene type: ${sceneType}`);
  }

  const filter = profile.filter.replace(/{duration}/g, options.duration.toString());

  return new Promise((resolve, reject) => {
    const args = [
      "-f", "lavfi",
      "-i", filter,
      "-t", options.duration.toString(),
      "-c:a", "libmp3lame",
      "-b:a", "192k",
      "-y", outputPath
    ];

    const ffmpeg = spawn("ffmpeg", args);

    let stderr = "";
    ffmpeg.stderr.on("data", (data) => {
      stderr += data.toString();
    });

    ffmpeg.on("close", (code) => {
      if (code === 0) {
        resolve();
      } else {
        reject(new Error(`FFmpeg failed with code ${code}: ${stderr}`));
      }
    });
  });
}

/**
 * Mix audio with video file
 */
export async function mixAudioWithVideo(
  videoPath: string,
  audioPath: string,
  outputPath: string,
  options: AudioOptions = { duration: 8, fadeDuration: 2, volume: 0.7 }
): Promise<void> {
  const { duration, fadeDuration = 2, volume = 0.7 } = options;
  const fadeOutStart = duration - fadeDuration;

  return new Promise((resolve, reject) => {
    const filterComplex = `[1:a]atrim=0:${duration},afade=t=in:st=0:d=${fadeDuration},afade=t=out:st=${fadeOutStart}:d=${fadeDuration},volume=${volume}[audio]`;

    const args = [
      "-i", videoPath,
      "-stream_loop", "-1",
      "-i", audioPath,
      "-filter_complex", filterComplex,
      "-map", "0:v",
      "-map", "[audio]",
      "-c:v", "copy",
      "-c:a", "aac",
      "-b:a", "192k",
      "-shortest",
      "-y", outputPath
    ];

    const ffmpeg = spawn("ffmpeg", args);

    let stderr = "";
    ffmpeg.stderr.on("data", (data) => {
      stderr += data.toString();
    });

    ffmpeg.on("close", (code) => {
      if (code === 0) {
        resolve();
      } else {
        reject(new Error(`FFmpeg failed with code ${code}: ${stderr}`));
      }
    });
  });
}

/**
 * Get video duration using ffprobe
 */
export async function getVideoDuration(videoPath: string): Promise<number> {
  return new Promise((resolve, reject) => {
    const ffprobe = spawn("ffprobe", [
      "-v", "error",
      "-show_entries", "format=duration",
      "-of", "default=noprint_wrappers=1:nokey=1",
      videoPath
    ]);

    let stdout = "";
    ffprobe.stdout.on("data", (data) => {
      stdout += data.toString();
    });

    ffprobe.on("close", (code) => {
      if (code === 0) {
        resolve(parseFloat(stdout.trim()));
      } else {
        reject(new Error(`ffprobe failed with code ${code}`));
      }
    });
  });
}

/**
 * Add ambient audio to video (convenience function)
 *
 * @example
 * ```ts
 * await addAmbientAudio("video.mp4", "forest", "output.mp4");
 * ```
 */
export async function addAmbientAudio(
  videoPath: string,
  sceneType: SceneType,
  outputPath: string,
  options?: Partial<AudioOptions>
): Promise<void> {
  const duration = options?.duration ?? await getVideoDuration(videoPath);
  const tempAudioPath = join("/tmp", `ambient_${Date.now()}.mp3`);

  try {
    // Generate ambient audio
    await generateAmbientAudio(sceneType, tempAudioPath, {
      duration,
      ...options
    });

    // Mix with video
    await mixAudioWithVideo(videoPath, tempAudioPath, outputPath, {
      duration,
      ...options
    });
  } finally {
    // Cleanup temp file
    try {
      await fs.unlink(tempAudioPath);
    } catch {}
  }
}
