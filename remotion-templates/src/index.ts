export type BrandConfig = {
  primaryColor?: string;
  secondaryColor?: string;
  fontFamily?: string;
  logoUrl?: string;
};

export type TemplateInput = {
  template: "news" | "dataviz" | "tutorial" | "meme" | "slideshow";
  title?: string;
  subtitle?: string;
  tags?: string[];
  data?: any;
  brand?: BrandConfig;
  resolution?: "1920x1080" | "1280x720" | "1080x1920";
  durationInFrames?: number;
};

export const templates = [
  "news-broadcast-overlay",
  "data-visualization",
  "tutorial-explainer",
  "meme-short-form",
  "slideshow-ken-burns"
];
