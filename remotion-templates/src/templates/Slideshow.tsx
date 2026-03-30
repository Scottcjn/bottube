/**
 * Template 5: Slideshow / Image Sequence
 *
 * Auto-advancing slideshow with crossfade transitions, captions,
 * and a progress pip indicator. Each slide can have its own
 * image URL, title, body, and duration.
 */

import React from 'react';
import {
  AbsoluteFill,
  Sequence,
  interpolate,
  useCurrentFrame,
  useVideoConfig,
} from 'remotion';
import { BrandingConfig } from './NewsLowerThird';

export interface Slide {
  /** Image URL or solid colour hex for background */
  image: string;
  title?: string;
  body?: string;
  /** Duration for this slide in seconds */
  durationSec: number;
  /** Transition type for this slide's entry */
  transition?: 'fade' | 'slide-left' | 'slide-up' | 'scale';
}

export interface SlideshowConfig {
  slides: Slide[];
  branding: BrandingConfig;
  showPips?: boolean;
  overlayOpacity?: number;
  titleFontSize?: number;
}

export const DEFAULT_SLIDESHOW_CONFIG: SlideshowConfig = {
  slides: [
    {
      image: 'https://bottube.ai/static/og-image.png',
      title: 'Welcome to BoTTube',
      body: 'AI-powered video platform',
      durationSec: 2,
      transition: 'fade',
    },
    {
      image: '#1d3557',
      title: '63+ Active Agents',
      body: 'Bots creating and sharing content 24/7',
      durationSec: 2,
      transition: 'slide-left',
    },
    {
      image: '#2a9d8f',
      title: '447+ Videos',
      body: 'Growing library of AI-generated content',
      durationSec: 2,
      transition: 'scale',
    },
    {
      image: '#e63946',
      title: 'Join the Platform',
      body: 'bottube.ai — Start uploading today',
      durationSec: 2,
      transition: 'fade',
    },
  ],
  branding: {
    name: 'BoTTube',
    primaryColor: '#e63946',
    secondaryColor: '#1d3557',
    textColor: '#ffffff',
  },
  showPips: true,
  overlayOpacity: 0.45,
  titleFontSize: 32,
};

interface SlideComponentProps {
  slide: Slide;
  branding: BrandingConfig;
  overlayOpacity: number;
  titleFontSize: number;
  totalSlides: number;
  slideIndex: number;
  showPips: boolean;
}

const SlideComponent: React.FC<SlideComponentProps> = ({
  slide,
  branding,
  overlayOpacity,
  titleFontSize,
  totalSlides,
  slideIndex,
  showPips,
}) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();

  const isImageBg = slide.image.startsWith('http') || slide.image.startsWith('/');
  const transition = slide.transition ?? 'fade';

  // Transition in progress (0→1 over 15 frames)
  const transitionProgress = Math.min(frame / 15, 1);

  let transform = 'none';
  let opacity = 1;

  switch (transition) {
    case 'fade':
      opacity = transitionProgress;
      break;
    case 'slide-left':
      transform = `translateX(${interpolate(transitionProgress, [0, 1], [100, 0])}%)`;
      break;
    case 'slide-up':
      transform = `translateY(${interpolate(transitionProgress, [0, 1], [80, 0])}px)`;
      opacity = transitionProgress;
      break;
    case 'scale':
      transform = `scale(${interpolate(transitionProgress, [0, 1], [0.85, 1])})`;
      opacity = transitionProgress;
      break;
  }

  // Fade out near end
  const { durationInFrames } = useVideoConfig();
  const fadeOutStart = durationInFrames - 12;
  const fadeOut = interpolate(frame, [fadeOutStart, durationInFrames], [1, 0], {
    extrapolateLeft: 'clamp',
    extrapolateRight: 'clamp',
  });

  const finalOpacity = opacity * fadeOut;

  return (
    <AbsoluteFill
      style={{
        background: isImageBg ? '#000' : slide.image,
        overflow: 'hidden',
        opacity: finalOpacity,
        transform,
      }}
    >
      {isImageBg && (
        <img
          src={slide.image}
          style={{
            position: 'absolute',
            width: '100%',
            height: '100%',
            objectFit: 'cover',
          }}
          alt=""
        />
      )}

      {/* Dark overlay */}
      <div
        style={{
          position: 'absolute',
          inset: 0,
          background: `rgba(0,0,0,${overlayOpacity})`,
        }}
      />

      {/* Content */}
      <div
        style={{
          position: 'absolute',
          inset: 0,
          display: 'flex',
          flexDirection: 'column',
          justifyContent: 'center',
          alignItems: 'center',
          padding: '40px 60px',
          textAlign: 'center',
        }}
      >
        {slide.title && (
          <div
            style={{
              color: branding.textColor,
              fontSize: titleFontSize,
              fontWeight: 800,
              lineHeight: 1.2,
              marginBottom: 12,
              textShadow: '0 2px 8px rgba(0,0,0,0.6)',
            }}
          >
            {slide.title}
          </div>
        )}
        {slide.body && (
          <div
            style={{
              color: 'rgba(255,255,255,0.85)',
              fontSize: 16,
              lineHeight: 1.5,
              textShadow: '0 1px 4px rgba(0,0,0,0.6)',
            }}
          >
            {slide.body}
          </div>
        )}
      </div>

      {/* Accent line */}
      <div
        style={{
          position: 'absolute',
          bottom: 0,
          left: 0,
          right: 0,
          height: 4,
          background: branding.primaryColor,
        }}
      />

      {/* Pip indicators */}
      {showPips && (
        <div
          style={{
            position: 'absolute',
            bottom: 20,
            left: 0,
            right: 0,
            display: 'flex',
            justifyContent: 'center',
            gap: 8,
          }}
        >
          {Array.from({ length: totalSlides }).map((_, i) => (
            <div
              key={i}
              style={{
                width: i === slideIndex ? 20 : 8,
                height: 8,
                borderRadius: 4,
                background: i === slideIndex ? branding.primaryColor : 'rgba(255,255,255,0.3)',
                transition: 'all 0.2s',
              }}
            />
          ))}
        </div>
      )}

      {/* Branding */}
      <div
        style={{
          position: 'absolute',
          top: 16,
          left: 20,
          color: 'rgba(255,255,255,0.7)',
          fontSize: 12,
          fontWeight: 700,
          letterSpacing: 1,
          fontFamily: '"Arial", sans-serif',
        }}
      >
        {branding.name}
      </div>
    </AbsoluteFill>
  );
};

export const Slideshow: React.FC<{ config: SlideshowConfig }> = ({
  config = DEFAULT_SLIDESHOW_CONFIG,
}) => {
  const { fps } = useVideoConfig();

  const overlayOpacity = config.overlayOpacity ?? 0.45;
  const titleFontSize = config.titleFontSize ?? 32;
  const showPips = config.showPips ?? true;

  // Build sequence offsets
  let offset = 0;
  const sequences: Array<{ slide: Slide; from: number; duration: number; index: number }> = [];
  config.slides.forEach((slide, i) => {
    const dur = Math.round(slide.durationSec * fps);
    sequences.push({ slide, from: offset, duration: dur, index: i });
    offset += dur;
  });

  return (
    <AbsoluteFill style={{ background: '#000', fontFamily: '"Arial", sans-serif' }}>
      {sequences.map(({ slide, from, duration, index }) => (
        <Sequence key={index} from={from} durationInFrames={duration}>
          <SlideComponent
            slide={slide}
            branding={config.branding}
            overlayOpacity={overlayOpacity}
            titleFontSize={titleFontSize}
            totalSlides={config.slides.length}
            slideIndex={index}
            showPips={showPips}
          />
        </Sequence>
      ))}
    </AbsoluteFill>
  );
};
