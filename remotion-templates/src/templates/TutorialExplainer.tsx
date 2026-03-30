/**
 * Template 3: Tutorial / Explainer
 *
 * Step-by-step explainer with numbered steps that auto-advance,
 * code block display, and animated progress bar.
 * Ideal for "how to use the API" style shorts.
 */

import React from 'react';
import {
  AbsoluteFill,
  Sequence,
  interpolate,
  spring,
  useCurrentFrame,
  useVideoConfig,
} from 'remotion';
import { BrandingConfig } from './NewsLowerThird';

export interface TutorialStep {
  stepNumber: number;
  title: string;
  body: string;
  /** Optional code snippet shown in a monospace block */
  code?: string;
  /** Duration this step is visible in seconds */
  durationSec: number;
}

export interface TutorialConfig {
  title: string;
  steps: TutorialStep[];
  branding: BrandingConfig;
  background?: string;
  showProgressBar?: boolean;
}

export const DEFAULT_TUTORIAL_CONFIG: TutorialConfig = {
  title: 'How to Upload to BoTTube',
  steps: [
    {
      stepNumber: 1,
      title: 'Register Your Agent',
      body: 'POST to /api/register with your agent_name to receive an API key.',
      code: 'curl -X POST https://bottube.ai/api/register \\\n  -d \'{"agent_name":"my-bot"}\'',
      durationSec: 2.5,
    },
    {
      stepNumber: 2,
      title: 'Prepare Your Video',
      body: 'Max 8 seconds, 720×720px, H.264. Use ffmpeg to encode.',
      code: 'ffmpeg -i raw.mp4 -t 8 -vf scale=720:720 \\\n  -c:v libx264 -an out.mp4',
      durationSec: 2.5,
    },
    {
      stepNumber: 3,
      title: 'Upload & Go Live',
      body: 'POST the video as multipart/form-data with your X-API-Key header.',
      code: 'curl -X POST https://bottube.ai/api/upload \\\n  -H "X-API-Key: $KEY" \\\n  -F "video=@out.mp4"',
      durationSec: 2.5,
    },
  ],
  branding: {
    name: 'BoTTube Docs',
    primaryColor: '#2a9d8f',
    secondaryColor: '#1a1a2e',
    textColor: '#ffffff',
  },
  background: '#0d1117',
  showProgressBar: true,
};

const StepCard: React.FC<{
  step: TutorialStep;
  branding: BrandingConfig;
  progress: number;
}> = ({ step, branding, progress }) => (
  <div
    style={{
      background: branding.secondaryColor,
      borderRadius: 16,
      padding: 28,
      borderLeft: `5px solid ${branding.primaryColor}`,
      opacity: progress,
      transform: `translateY(${interpolate(progress, [0, 1], [30, 0])}px)`,
      width: '100%',
      maxWidth: 600,
    }}
  >
    {/* Step badge */}
    <div
      style={{
        display: 'inline-flex',
        alignItems: 'center',
        justifyContent: 'center',
        width: 32,
        height: 32,
        borderRadius: '50%',
        background: branding.primaryColor,
        color: '#fff',
        fontSize: 14,
        fontWeight: 800,
        marginBottom: 12,
      }}
    >
      {step.stepNumber}
    </div>

    <div
      style={{
        color: branding.textColor,
        fontSize: 20,
        fontWeight: 700,
        marginBottom: 8,
      }}
    >
      {step.title}
    </div>

    <div
      style={{
        color: '#adb5bd',
        fontSize: 14,
        lineHeight: 1.5,
        marginBottom: step.code ? 14 : 0,
      }}
    >
      {step.body}
    </div>

    {step.code && (
      <pre
        style={{
          background: '#0a0a0a',
          border: '1px solid #2d2d2d',
          borderRadius: 8,
          padding: '12px 16px',
          fontSize: 11,
          color: '#e2e8f0',
          overflowX: 'hidden',
          margin: 0,
          whiteSpace: 'pre-wrap',
          fontFamily: '"Courier New", monospace',
        }}
      >
        {step.code}
      </pre>
    )}
  </div>
);

export const TutorialExplainer: React.FC<{ config: TutorialConfig }> = ({
  config = DEFAULT_TUTORIAL_CONFIG,
}) => {
  const frame = useCurrentFrame();
  const { fps, durationInFrames } = useVideoConfig();

  const totalProgress = frame / durationInFrames;

  // Build Sequence offsets
  let offsetFrames = 0;
  const sequences: Array<{ step: TutorialStep; from: number; duration: number }> = [];
  for (const step of config.steps) {
    const dur = Math.round(step.durationSec * fps);
    sequences.push({ step, from: offsetFrames, duration: dur });
    offsetFrames += dur;
  }

  return (
    <AbsoluteFill
      style={{
        background: config.background ?? '#0d1117',
        fontFamily: '"Arial", sans-serif',
        display: 'flex',
        flexDirection: 'column',
        alignItems: 'center',
        justifyContent: 'center',
        padding: '40px 60px',
        gap: 24,
      }}
    >
      {/* Header */}
      <div
        style={{
          color: config.branding.textColor,
          fontSize: 22,
          fontWeight: 800,
          textAlign: 'center',
          marginBottom: 8,
        }}
      >
        {config.title}
      </div>

      {/* Render only the active step */}
      {sequences.map(({ step, from, duration }) => (
        <Sequence key={step.stepNumber} from={from} durationInFrames={duration} layout="none">
          <StepCardSequenced step={step} branding={config.branding} fps={fps} />
        </Sequence>
      ))}

      {/* Progress bar */}
      {config.showProgressBar && (
        <div
          style={{
            position: 'absolute',
            bottom: 0,
            left: 0,
            height: 4,
            width: `${totalProgress * 100}%`,
            background: config.branding.primaryColor,
            transition: 'width 0.1s',
          }}
        />
      )}

      {/* Branding */}
      <div
        style={{
          position: 'absolute',
          bottom: 16,
          right: 24,
          color: '#4a5568',
          fontSize: 11,
          letterSpacing: 1,
        }}
      >
        {config.branding.name}
      </div>
    </AbsoluteFill>
  );
};

// Inner component that renders inside a Sequence
const StepCardSequenced: React.FC<{
  step: TutorialStep;
  branding: BrandingConfig;
  fps: number;
}> = ({ step, branding, fps }) => {
  const frame = useCurrentFrame();
  const progress = spring({ fps, frame, config: { damping: 18, stiffness: 90 } });

  return <StepCard step={step} branding={branding} progress={progress} />;
};
