import type { Rules } from "./rules";
import type { Location, Photo, Suggestion, Trip } from "./types";

const WORD = /^[a-z0-9][a-z0-9'&/+.-]*$/;

export function normalizeTag(tag: string, brands: string[], maxWords: number): string | null {
  const text = tag.trim().toLowerCase().split(/\s+/).filter(Boolean).join(" ");
  if (!text || text.includes("#")) return null;
  const words = text.split(" ");
  if (words.length < 1 || words.length > maxWords) return null;
  if (words.some((word) => brands.includes(word))) return null;
  if (words.some((word) => WORD.test(word) === false)) return null;
  if (text.length > 40) return null;
  return text;
}

export function buildTags(
  photo: Photo,
  location: Location | null,
  trip: Trip | null,
  dayTags: string[],
  templateTags: string[],
  rules: Rules,
): Suggestion<string[]> {
  const kept: string[] = [];
  const seen = new Set<string>();

  const add = (raw: string, existing: boolean) => {
    const limit = existing ? rules.maxExistingTagWords : rules.maxNewTagWords;
    const cleaned = normalizeTag(raw, rules.cameraBrands, limit);
    if (!cleaned || seen.has(cleaned.toLowerCase())) return;
    if (kept.length >= rules.targetTagCount) return;
    kept.push(cleaned);
    seen.add(cleaned.toLowerCase());
  };

  for (const tag of photo.tags) add(tag, true);
  if (location) {
    for (const part of [location.name, location.city, location.region, location.country]) {
      if (part) add(part, false);
    }
  }
  for (const tag of templateTags) add(tag, false);
  if (trip) {
    for (const tag of [...trip.tags, ...dayTags]) add(tag, false);
  }
  if (kept.length === 0) {
    return { value: [], confidence: 0.2, source: "none", flag: "review", reason: "no usable tags" };
  }
  const confidence = kept.length >= 8 ? 0.86 : 0.78;
  let reason = `${kept.length} tags`;
  if (kept.length < rules.targetTagCount) {
    reason += `; ${rules.targetTagCount - kept.length} slots left for a later image pass`;
  }
  return { value: kept, confidence, source: "deterministic", flag: "ok", reason };
}
