/**
 * Remotion Root — registers all BoTTube compositions.
 *
 * Each composition maps to one of the 5 templates.
 * Pass --props with a JSON config file at render time.
 */

import React from 'react';
import { Composition } from 'remotion';

import { NewsLowerThird, DEFAULT_NEWS_CONFIG, type NewsConfig } from './templates/NewsLowerThird';
import { DataVisualization, DEFAULT_DATA_VIZ_CONFIG, type DataVizConfig } from './templates/DataVisualization';
import { TutorialExplainer, DEFAULT_TUTORIAL_CONFIG, type TutorialConfig } from './templates/TutorialExplainer';
import { MemeShortForm, DEFAULT_MEME_CONFIG, type MemeConfig } from './templates/MemeShortForm';
import { Slideshow, DEFAULT_SLIDESHOW_CONFIG, type SlideshowConfig } from './templates/Slideshow';

/** Calculate total frames from a config's timing/steps */
const calcNewsFrames = (fps: number) =>
  Math.round(
    (DEFAULT_NEWS_CONFIG.timing.lowerThirdIn +
      DEFAULT_NEWS_CONFIG.timing.lowerThirdHold +
      DEFAULT_NEWS_CONFIG.timing.lowerThirdOut) *
      fps
  );

const calcTutorialFrames = (config: TutorialConfig, fps: number) =>
  Math.round(config.steps.reduce((sum, s) => sum + s.durationSec, 0) * fps);

const calcSlideshowFrames = (config: SlideshowConfig, fps: number) =>
  Math.round(config.slides.reduce((sum, s) => sum + s.durationSec, 0) * fps);

export const RemotionRoot: React.FC = () => {
  const fps = 30;
  const w = 720;
  const h = 720;

  return (
    <>
      {/* 1. News Lower-Third */}
      <Composition
        id="NewsLowerThird"
        component={NewsLowerThird}
        durationInFrames={calcNewsFrames(fps)}
        fps={fps}
        width={w}
        height={h}
        defaultProps={{ config: DEFAULT_NEWS_CONFIG }}
      />

      {/* 2. Data Visualization */}
      <Composition
        id="DataVisualization"
        component={DataVisualization}
        durationInFrames={7 * fps} // 7 seconds
        fps={fps}
        width={w}
        height={h}
        defaultProps={{ config: DEFAULT_DATA_VIZ_CONFIG }}
      />

      {/* 3. Tutorial Explainer */}
      <Composition
        id="TutorialExplainer"
        component={TutorialExplainer}
        durationInFrames={calcTutorialFrames(DEFAULT_TUTORIAL_CONFIG, fps)}
        fps={fps}
        width={w}
        height={h}
        defaultProps={{ config: DEFAULT_TUTORIAL_CONFIG }}
      />

      {/* 4. Meme Short-Form */}
      <Composition
        id="MemeShortForm"
        component={MemeShortForm}
        durationInFrames={7 * fps} // 7 seconds
        fps={fps}
        width={w}
        height={h}
        defaultProps={{ config: DEFAULT_MEME_CONFIG }}
      />

      {/* 5. Slideshow */}
      <Composition
        id="Slideshow"
        component={Slideshow}
        durationInFrames={calcSlideshowFrames(DEFAULT_SLIDESHOW_CONFIG, fps)}
        fps={fps}
        width={w}
        height={h}
        defaultProps={{ config: DEFAULT_SLIDESHOW_CONFIG }}
      />
    </>
  );
};
