/**
 * Template 1: News / Lower-Third Broadcast Layout
 *
 * A broadcast-style lower-third overlay with animated headline,
 * ticker text, and bot branding. JSON-driven via NewsConfig.
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

export interface NewsConfig {
  /** Background video URL or solid color hex (e.g. "#0a0a1a") */
  background: string;
  /** Main headline text */
  headline: string;
  /** Sub-headline / location line */
  subline: string;
  /** Ticker text scrolling across the bottom */
  ticker: string;
  /** Bot / channel branding */
  branding: BrandingConfig;
  /** Timing in seconds (total must be ≤ 8) */
  timing: {
    lowerThirdIn: number;
    lowerThirdHold: number;
    lowerThirdOut: number;
  };
}

export interface BrandingConfig {
  /** Bot display name */
  name: string;
  /** Primary accent colour */
  primaryColor: string;
  /** Secondary / background colour */
  secondaryColor: string;
  /** Text colour */
  textColor: string;
}

const DEFAULT_BRANDING: BrandingConfig = {
  name: 'BoTTube News',
  primaryColor: '#e63946',
  secondaryColor: '#1d3557',
  textColor: '#ffffff',
};

export const DEFAULT_NEWS_CONFIG: NewsConfig = {
  background: '#0a0a1a',
  headline: 'BREAKING: AI Agents Now Dominate Video Creation',
  subline: 'BoTTube Studio — Live Coverage',
  ticker:
    'AI VIDEO PLATFORM HITS 447+ VIDEOS  •  AGENTS EARN RTC ON RUSTCHAIN  •  BOTTUBE.AI',
  branding: DEFAULT_BRANDING,
  timing: { lowerThirdIn: 0.5, lowerThirdHold: 5, lowerThirdOut: 1 },
};

export const NewsLowerThird: React.FC<{ config: NewsConfig }> = ({
  config = DEFAULT_NEWS_CONFIG,
}) => {
  const frame = useCurrentFrame();
  const { fps, durationInFrames } = useVideoConfig();
  const { branding, timing } = config;

  const inFrame = Math.round(timing.lowerThirdIn * fps);
  const holdFrames = Math.round(timing.lowerThirdHold * fps);
  const outFrame = inFrame + holdFrames;

  // Slide-in spring
  const slideIn = spring({
    fps,
    frame: frame - inFrame,
    config: { damping: 15, stiffness: 100 },
  });

  // Slide-out (reverse)
  const slideOut = interpolate(
    frame,
    [outFrame, outFrame + Math.round(timing.lowerThirdOut * fps)],
    [0, 1],
    { extrapolateLeft: 'clamp', extrapolateRight: 'clamp' }
  );

  const translateY = interpolate(slideIn, [0, 1], [120, 0]) + slideOut * 120;

  // Ticker scroll
  const tickerSpeed = 120; // px/s
  const tickerX = -(frame / fps) * tickerSpeed;

  const isBackground = config.background.startsWith('#');

  return (
    <AbsoluteFill
      style={{
        background: isBackground ? config.background : '#0a0a1a',
        overflow: 'hidden',
        fontFamily: '"Arial", sans-serif',
      }}
    >
      {/* Background image/video placeholder */}
      {!isBackground && (
        <img
          src={config.background}
          style={{ position: 'absolute', width: '100%', height: '100%', objectFit: 'cover' }}
          alt=""
        />
      )}

      {/* Lower-third panel */}
      <div
        style={{
          position: 'absolute',
          bottom: 80,
          left: 0,
          right: 0,
          transform: `translateY(${translateY}px)`,
        }}
      >
        {/* Branding strip */}
        <div
          style={{
            background: branding.primaryColor,
            height: 6,
            width: 520,
            marginLeft: 40,
          }}
        />
        {/* Content block */}
        <div
          style={{
            background: branding.secondaryColor,
            marginLeft: 40,
            width: 600,
            padding: '12px 20px',
          }}
        >
          <div
            style={{
              color: branding.primaryColor,
              fontSize: 11,
              fontWeight: 700,
              letterSpacing: 2,
              textTransform: 'uppercase',
              marginBottom: 4,
            }}
          >
            {branding.name}
          </div>
          <div
            style={{
              color: branding.textColor,
              fontSize: 22,
              fontWeight: 800,
              lineHeight: 1.2,
              marginBottom: 4,
            }}
          >
            {config.headline}
          </div>
          <div
            style={{
              color: '#adb5bd',
              fontSize: 13,
              fontWeight: 400,
            }}
          >
            {config.subline}
          </div>
        </div>
      </div>

      {/* Ticker bar */}
      <div
        style={{
          position: 'absolute',
          bottom: 0,
          left: 0,
          right: 0,
          height: 36,
          background: branding.primaryColor,
          overflow: 'hidden',
          display: 'flex',
          alignItems: 'center',
        }}
      >
        <div
          style={{
            whiteSpace: 'nowrap',
            color: '#fff',
            fontSize: 13,
            fontWeight: 700,
            letterSpacing: 1,
            transform: `translateX(${tickerX % (config.ticker.length * 10 + 720)}px)`,
          }}
        >
          {config.ticker} &nbsp;&nbsp;&nbsp;&nbsp;&nbsp; {config.ticker}
        </div>
      </div>
    </AbsoluteFill>
  );
};
