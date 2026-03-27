/**
 * JSON Schema definitions for all BoTTube Remotion template configs.
 * Use these types to validate configs before rendering.
 */

/** Shared bot branding configuration */
export interface BrandingConfig {
  /** Display name for the bot/channel */
  name: string;
  /** Primary accent color (hex) */
  primaryColor: string;
  /** Secondary / background color (hex) */
  secondaryColor: string;
  /** Main text color (hex) */
  textColor: string;
}

/** Template IDs available for rendering */
export type TemplateId =
  | 'NewsLowerThird'
  | 'DataVisualization'
  | 'TutorialExplainer'
  | 'MemeShortForm'
  | 'Slideshow';

/** Per-bot branding config file (branding.json) */
export interface BotBrandingFile {
  botName: string;
  apiKey?: string;
  branding: BrandingConfig;
  /** Default template to use when none specified */
  defaultTemplate?: TemplateId;
  /** Override configs per template */
  templateOverrides?: {
    NewsLowerThird?: Partial<import('../templates/NewsLowerThird').NewsConfig>;
    DataVisualization?: Partial<import('../templates/DataVisualization').DataVizConfig>;
    TutorialExplainer?: Partial<import('../templates/TutorialExplainer').TutorialConfig>;
    MemeShortForm?: Partial<import('../templates/MemeShortForm').MemeConfig>;
    Slideshow?: Partial<import('../templates/Slideshow').SlideshowConfig>;
  };
}

/** Validate that a config has at least required branding fields */
export function validateBranding(b: unknown): b is BrandingConfig {
  if (typeof b !== 'object' || b === null) return false;
  const obj = b as Record<string, unknown>;
  return (
    typeof obj.name === 'string' &&
    typeof obj.primaryColor === 'string' &&
    typeof obj.secondaryColor === 'string' &&
    typeof obj.textColor === 'string'
  );
}

/** Load and merge bot branding with template config */
export function applyBranding<T extends { branding: BrandingConfig }>(
  config: T,
  brandingOverride?: Partial<BrandingConfig>
): T {
  if (!brandingOverride) return config;
  return {
    ...config,
    branding: { ...config.branding, ...brandingOverride },
  };
}
