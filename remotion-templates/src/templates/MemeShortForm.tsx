/**
 * Template 4: Meme / Short-Form
 *
 * Classic impact-font meme layout (top text / bottom text) with
 * optional background image URL, shake/zoom animations, and
 * sub-title caption. Perfect for viral BoTTube shorts.
 */

import React from 'react';
import {
  AbsoluteFill,
  interpolate,
  spring,
  useCurrentFrame,
  useVideoConfig,
} from 'remotion';
import { BrandingConfig } from './NewsLowerThird';

export interface MemeConfig {
  /** URL of the meme background image, or solid colour hex */
  background: string;
  topText?: string;
  bottomText?: string;
  /** Optional caption beneath the meme */
  caption?: string;
  /** Animation style */
  animation: 'zoom-in' | 'shake' | 'bounce' | 'none';
  branding: BrandingConfig;
  /** Text stroke colour (default black) */
  strokeColor?: string;
  fontSize?: number;
}

export const DEFAULT_MEME_CONFIG: MemeConfig = {
  background: '#1a1a2e',
  topText: 'WHEN THE AI UPLOADS',
  bottomText: 'BEFORE YOU EVEN CLICK RENDER',
  caption: '🤖 BoTTube agents are fast',
  animation: 'zoom-in',
  branding: {
    name: 'BoTTube Memes',
    primaryColor: '#f72585',
    secondaryColor: '#3a0ca3',
    textColor: '#ffffff',
  },
  strokeColor: '#000000',
  fontSize: 48,
};

const ImpactText: React.FC<{
  text: string;
  position: 'top' | 'bottom';
  fontSize: number;
  strokeColor: string;
  textColor: string;
  animScale: number;
}> = ({ text, position, fontSize, strokeColor, textColor, animScale }) => (
  <div
    style={{
      position: 'absolute',
      [position]: 20,
      left: 0,
      right: 0,
      textAlign: 'center',
      padding: '0 16px',
    }}
  >
    <span
      style={{
        fontFamily: '"Impact", "Arial Black", sans-serif',
        fontSize,
        fontWeight: 900,
        color: textColor,
        textTransform: 'uppercase',
        textShadow: `
          -2px -2px 0 ${strokeColor},
           2px -2px 0 ${strokeColor},
          -2px  2px 0 ${strokeColor},
           2px  2px 0 ${strokeColor},
           0    0  6px rgba(0,0,0,0.5)
        `,
        letterSpacing: 1,
        lineHeight: 1.1,
        display: 'inline-block',
        transform: `scale(${animScale})`,
        transformOrigin: position === 'top' ? 'top center' : 'bottom center',
      }}
    >
      {text}
    </span>
  </div>
);

export const MemeShortForm: React.FC<{ config: MemeConfig }> = ({
  config = DEFAULT_MEME_CONFIG,
}) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();

  const fontSize = config.fontSize ?? 48;
  const strokeColor = config.strokeColor ?? '#000000';
  const isImageBg = config.background.startsWith('http') || config.background.startsWith('/');

  // Animation calculations
  let scaleAnim = 1;
  let shakeX = 0;

  if (config.animation === 'zoom-in') {
    const s = spring({ fps, frame, config: { damping: 20, stiffness: 60 } });
    scaleAnim = interpolate(s, [0, 1], [0.6, 1]);
  } else if (config.animation === 'bounce') {
    const s = spring({ fps, frame, config: { damping: 8, stiffness: 200, mass: 0.5 } });
    scaleAnim = interpolate(s, [0, 1], [1.3, 1]);
  } else if (config.animation === 'shake') {
    scaleAnim = 1;
    shakeX = frame < 10 ? Math.sin(frame * 3) * 8 : 0;
  }

  // Caption fade-in
  const captionOpacity = interpolate(frame, [10, 25], [0, 1], {
    extrapolateLeft: 'clamp',
    extrapolateRight: 'clamp',
  });

  return (
    <AbsoluteFill
      style={{
        background: isImageBg ? '#000' : config.background,
        fontFamily: '"Arial", sans-serif',
        overflow: 'hidden',
      }}
    >
      {/* Background */}
      {isImageBg && (
        <img
          src={config.background}
          style={{
            position: 'absolute',
            width: '100%',
            height: '100%',
            objectFit: 'cover',
          }}
          alt=""
        />
      )}

      {/* Dark overlay for readability */}
      <div
        style={{
          position: 'absolute',
          inset: 0,
          background: 'rgba(0,0,0,0.25)',
        }}
      />

      {/* Main meme container with animation */}
      <div
        style={{
          position: 'absolute',
          inset: 0,
          transform: `translateX(${shakeX}px) scale(${scaleAnim})`,
        }}
      >
        {config.topText && (
          <ImpactText
            text={config.topText}
            position="top"
            fontSize={fontSize}
            strokeColor={strokeColor}
            textColor={config.branding.textColor}
            animScale={1}
          />
        )}

        {config.bottomText && (
          <ImpactText
            text={config.bottomText}
            position="bottom"
            fontSize={fontSize}
            strokeColor={strokeColor}
            textColor={config.branding.textColor}
            animScale={1}
          />
        )}
      </div>

      {/* Caption */}
      {config.caption && (
        <div
          style={{
            position: 'absolute',
            bottom: 70,
            left: 0,
            right: 0,
            textAlign: 'center',
            color: '#fff',
            fontSize: 18,
            fontWeight: 600,
            opacity: captionOpacity,
            textShadow: '0 1px 4px rgba(0,0,0,0.8)',
          }}
        >
          {config.caption}
        </div>
      )}

      {/* Branding watermark */}
      <div
        style={{
          position: 'absolute',
          top: 12,
          right: 16,
          color: 'rgba(255,255,255,0.5)',
          fontSize: 10,
          letterSpacing: 1,
          fontWeight: 700,
        }}
      >
        {config.branding.name}
      </div>
    </AbsoluteFill>
  );
};
