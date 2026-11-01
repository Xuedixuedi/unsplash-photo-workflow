export type Rules = {
  targetTagCount: number;
  neverHideAboveDownloads: number;
  burstSeconds: number;
  hideBurstExtras: boolean;
  minAutoApproveConfidence: number;
  cameraBrands: string[];
  neighbourMaxSeconds: number;
  clusterGapDays: number;
  maxNewTagWords: number;
  maxExistingTagWords: number;
  descriptionFromLocation: boolean;
  forceHideIds: string[];
  forceShowIds: string[];
};

/** Mirrors `config/rules.yaml`. A test locks the two together. */
export const DEFAULT_RULES: Rules = {
  targetTagCount: 20,
  neverHideAboveDownloads: 100,
  burstSeconds: 4,
  hideBurstExtras: true,
  minAutoApproveConfidence: 0.75,
  cameraBrands: ["canon", "nikon", "sony", "fuji", "fujifilm", "eos", "dslr", "iphone", "adobe", "lightroom"],
  neighbourMaxSeconds: 900,
  clusterGapDays: 2,
  maxNewTagWords: 3,
  maxExistingTagWords: 5,
  descriptionFromLocation: true,
  forceHideIds: [],
  forceShowIds: [],
};

/** Mirrors `config/tag_templates.yaml`. */
export const TAG_TEMPLATES: Record<string, string[]> = {
  "mountain-autumn": ["autumn foliage", "alpine lakes", "fall colors", "mountain landscape", "colorful forest"],
  "island-beach": ["tropical beach", "turquoise water", "ocean view", "island"],
  "city-street": ["street photography", "cityscape", "urban"],
  temple: ["ancient temple", "heritage site", "stone carving"],
};

export const TEMPLATE_NAMES = Object.keys(TAG_TEMPLATES);
