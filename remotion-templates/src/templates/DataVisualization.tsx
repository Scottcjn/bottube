/**
 * Template 2: Data Visualization
 *
 * Animated bar chart / stat cards driven by JSON data arrays.
 * Bars grow from zero, numbers count up, colours from branding config.
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

export interface DataPoint {
  label: string;
  value: number;
  color?: string;
}

export interface DataVizConfig {
  title: string;
  subtitle?: string;
  chartType: 'bar' | 'stat-cards';
  data: DataPoint[];
  valueUnit?: string;
  branding: BrandingConfig;
  background?: string;
  /** Animation stagger delay in frames per bar */
  staggerFrames?: number;
}

export const DEFAULT_DATA_VIZ_CONFIG: DataVizConfig = {
  title: 'BoTTube Platform Stats',
  subtitle: 'Real-time agent metrics',
  chartType: 'bar',
  data: [
    { label: 'Videos', value: 447, color: '#e63946' },
    { label: 'Agents', value: 63, color: '#2a9d8f' },
    { label: 'Comments', value: 1820, color: '#e9c46a' },
    { label: 'Votes', value: 3402, color: '#f4a261' },
  ],
  valueUnit: '',
  branding: {
    name: 'BoTTube Analytics',
    primaryColor: '#e63946',
    secondaryColor: '#1d3557',
    textColor: '#ffffff',
  },
  background: '#0d1117',
  staggerFrames: 6,
};

// Animated counter
const Counter: React.FC<{ target: number; progress: number; unit: string }> = ({
  target,
  progress,
  unit,
}) => {
  const current = Math.round(interpolate(progress, [0, 1], [0, target]));
  return (
    <span>
      {current.toLocaleString()}
      {unit}
    </span>
  );
};

// Bar chart renderer
const BarChart: React.FC<{
  config: DataVizConfig;
  frame: number;
  fps: number;
}> = ({ config, frame, fps }) => {
  const maxVal = Math.max(...config.data.map((d) => d.value));
  const stagger = config.staggerFrames ?? 6;

  return (
    <div
      style={{
        display: 'flex',
        alignItems: 'flex-end',
        justifyContent: 'center',
        gap: 24,
        height: 280,
        padding: '0 40px',
      }}
    >
      {config.data.map((point, i) => {
        const startFrame = i * stagger + 20;
        const progress = spring({
          fps,
          frame: frame - startFrame,
          config: { damping: 20, stiffness: 80 },
        });
        const barColor = point.color ?? config.branding.primaryColor;
        const barHeight = interpolate(progress, [0, 1], [0, 220]) * (point.value / maxVal);

        return (
          <div
            key={point.label}
            style={{
              display: 'flex',
              flexDirection: 'column',
              alignItems: 'center',
              gap: 8,
            }}
          >
            {/* Value label */}
            <div
              style={{
                color: barColor,
                fontSize: 16,
                fontWeight: 800,
                opacity: progress,
              }}
            >
              <Counter target={point.value} progress={progress} unit={config.valueUnit ?? ''} />
            </div>
            {/* Bar */}
            <div
              style={{
                width: 60,
                height: barHeight,
                background: barColor,
                borderRadius: '4px 4px 0 0',
                transition: 'height 0.1s',
              }}
            />
            {/* Label */}
            <div
              style={{
                color: '#adb5bd',
                fontSize: 13,
                fontWeight: 600,
                textAlign: 'center',
              }}
            >
              {point.label}
            </div>
          </div>
        );
      })}
    </div>
  );
};

// Stat cards renderer
const StatCards: React.FC<{
  config: DataVizConfig;
  frame: number;
  fps: number;
}> = ({ config, frame, fps }) => {
  const stagger = config.staggerFrames ?? 6;

  return (
    <div
      style={{
        display: 'flex',
        flexWrap: 'wrap',
        justifyContent: 'center',
        gap: 20,
        padding: '20px 40px',
      }}
    >
      {config.data.map((point, i) => {
        const startFrame = i * stagger + 20;
        const progress = spring({
          fps,
          frame: frame - startFrame,
          config: { damping: 18, stiffness: 90 },
        });
        const cardColor = point.color ?? config.branding.primaryColor;

        return (
          <div
            key={point.label}
            style={{
              background: config.branding.secondaryColor,
              borderRadius: 12,
              padding: '24px 32px',
              minWidth: 160,
              textAlign: 'center',
              borderTop: `4px solid ${cardColor}`,
              opacity: progress,
              transform: `scale(${interpolate(progress, [0, 1], [0.7, 1])})`,
            }}
          >
            <div
              style={{
                color: cardColor,
                fontSize: 36,
                fontWeight: 900,
                lineHeight: 1,
              }}
            >
              <Counter target={point.value} progress={progress} unit={config.valueUnit ?? ''} />
            </div>
            <div
              style={{
                color: '#adb5bd',
                fontSize: 14,
                marginTop: 8,
              }}
            >
              {point.label}
            </div>
          </div>
        );
      })}
    </div>
  );
};

export const DataVisualization: React.FC<{ config: DataVizConfig }> = ({
  config = DEFAULT_DATA_VIZ_CONFIG,
}) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();

  const titleOpacity = spring({ fps, frame: frame - 5, config: { damping: 20 } });

  return (
    <AbsoluteFill
      style={{
        background: config.background ?? '#0d1117',
        fontFamily: '"Arial", sans-serif',
        display: 'flex',
        flexDirection: 'column',
        alignItems: 'center',
        justifyContent: 'center',
        padding: 40,
      }}
    >
      {/* Title */}
      <div
        style={{
          color: config.branding.textColor,
          fontSize: 28,
          fontWeight: 800,
          textAlign: 'center',
          opacity: titleOpacity,
          marginBottom: 8,
        }}
      >
        {config.title}
      </div>
      {config.subtitle && (
        <div
          style={{
            color: config.branding.primaryColor,
            fontSize: 14,
            fontWeight: 600,
            letterSpacing: 1,
            textTransform: 'uppercase',
            opacity: titleOpacity,
            marginBottom: 32,
          }}
        >
          {config.subtitle}
        </div>
      )}

      {/* Chart */}
      {config.chartType === 'bar' ? (
        <BarChart config={config} frame={frame} fps={fps} />
      ) : (
        <StatCards config={config} frame={frame} fps={fps} />
      )}

      {/* Branding footer */}
      <div
        style={{
          position: 'absolute',
          bottom: 20,
          right: 30,
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
