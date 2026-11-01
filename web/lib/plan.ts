import { locateAll } from "./locate";
import { emptyLocation, photoDay } from "./photos";
import { DEFAULT_RULES, TAG_TEMPLATES, type Rules } from "./rules";
import { buildTags } from "./tags";
import type { Location, Photo, ReviewRow, Suggestion, Trip } from "./types";

export function buildDescription(photo: Photo, location: Location | null, rules: Rules): Suggestion<string> {
  if (photo.description) {
    return {
      value: photo.description,
      confidence: 0.9,
      source: "existing",
      flag: "ok",
      reason: "keeping the current description",
    };
  }
  if (rules.descriptionFromLocation && location && !emptyLocation(location)) {
    const parts: string[] = [];
    for (const part of [location.name, location.city, location.country]) {
      if (part && !parts.includes(part)) parts.push(part);
    }
    if (parts.length) {
      return {
        value: `${parts.join(", ")}.`,
        confidence: 0.8,
        source: "template",
        flag: "ok",
        reason: "built from the location",
      };
    }
  }
  return { value: "", confidence: 0, source: "none", flag: "empty", reason: "no description" };
}

export function burstRoles(photos: Photo[], rules: Rules): Map<string, "single" | "keeper" | "extra"> {
  const roles = new Map<string, "single" | "keeper" | "extra">(photos.map((photo) => [photo.id, "single"]));
  const ordered = photos
    .filter((photo) => parseCaptured(photo) !== null)
    .sort((left, right) => (left.capturedAt || "").localeCompare(right.capturedAt || ""));
  let group: Photo[] = [];

  const close = (previous: Photo, current: Photo) => {
    const left = parseCaptured(previous);
    const right = parseCaptured(current);
    if (left === null || right === null) return false;
    return Math.abs(right - left) / 1000 <= rules.burstSeconds;
  };

  const finish = (items: Photo[]) => {
    if (items.length < 2) return;
    const keeper = [...items].sort((left, right) => {
      return (
        right.downloads - left.downloads ||
        right.likes - left.likes ||
        right.views - left.views ||
        right.width * right.height - left.width * left.height
      );
    })[0];
    for (const photo of items) roles.set(photo.id, photo.id === keeper.id ? "keeper" : "extra");
  };

  for (const photo of ordered) {
    if (group.length === 0 || close(group[group.length - 1], photo)) group.push(photo);
    else {
      finish(group);
      group = [photo];
    }
  }
  finish(group);
  return roles;
}

function parseCaptured(photo: Photo): number | null {
  if (!photo.capturedAt || !photo.capturedAt.includes("T")) return null;
  if (photo.capturedAt.endsWith("T00:00:00Z") || photo.capturedAt.endsWith("T00:00:00+00:00")) return null;
  const parsed = Date.parse(photo.capturedAt);
  return Number.isNaN(parsed) ? null : parsed;
}

export function decideVisibility(photo: Photo, rules: Rules, role: string): Suggestion<boolean> {
  if (photo.downloads > rules.neverHideAboveDownloads) {
    return {
      value: true,
      confidence: 0.99,
      source: "rule:downloads",
      flag: "ok",
      reason: `downloads ${photo.downloads} are above ${rules.neverHideAboveDownloads}`,
    };
  }
  if (rules.forceShowIds.includes(photo.id)) {
    return { value: true, confidence: 0.95, source: "rule:force-show", flag: "ok", reason: "listed in force_show_ids" };
  }
  if (rules.forceHideIds.includes(photo.id)) {
    return { value: false, confidence: 0.9, source: "rule:force-hide", flag: "review", reason: "listed in force_hide_ids" };
  }
  if (rules.hideBurstExtras && role === "extra") {
    return {
      value: false,
      confidence: 0.72,
      source: "rule:burst",
      flag: "review",
      reason: "extra frame in a short burst",
    };
  }
  return {
    value: photo.showOnProfile,
    confidence: 0.6,
    source: "unchanged",
    flag: "ok",
    reason: "keeping the current visibility",
  };
}

export function decideApprove(
  location: Suggestion<Location | null>,
  tags: Suggestion<string[]>,
  description: Suggestion<string>,
  visibility: Suggestion<boolean>,
  rules: Rules,
): "yes" | "no" {
  const checks: [string, Suggestion<unknown>][] = [
    ["location", location],
    ["tags", tags],
    ["description", description],
    ["show_on_profile", visibility],
  ];
  for (const [kind, suggestion] of checks) {
    if (kind === "description" && (!suggestion.value || suggestion.flag === "empty")) continue;
    if (kind === "show_on_profile" && suggestion.source === "unchanged") continue;
    if (suggestion.flag === "review" || suggestion.flag === "empty") return "no";
    if (suggestion.confidence < rules.minAutoApproveConfidence) return "no";
  }
  return "yes";
}

export function assignCollections(photos: Photo[], trip: Trip, rules: Rules): Map<string, { title: string; description: string }> {
  const assigned = new Map<string, { title: string; description: string }>();
  const loose: Photo[] = [];
  for (const photo of photos) {
    const day = photoDay(photo);
    const covered = day !== null && trip.days.some((item) => item.date === day);
    if (!covered) {
      loose.push(photo);
      continue;
    }
    assigned.set(photo.id, {
      title: trip.collection || trip.name,
      description: trip.description || trip.name,
    });
  }
  for (const group of clusters(loose, rules.clusterGapDays)) {
    const days = group.map(photoDay).filter((day): day is string => day !== null).sort();
    const title = days.length === 0 ? "Untitled trip" : days[0] === days[days.length - 1] ? `Trip ${days[0]}` : `Trip ${days[0]} to ${days[days.length - 1]}`;
    const description =
      days.length === 0
        ? "Photos that did not match a trip itinerary."
        : `Grouped by date from ${days[0]} to ${days[days.length - 1]}.`;
    for (const photo of group) assigned.set(photo.id, { title, description });
  }
  return assigned;
}

function clusters(photos: Photo[], gapDays: number): Photo[][] {
  const ordered = [...photos].sort((left, right) => (photoDay(left) || "").localeCompare(photoDay(right) || ""));
  const groups: Photo[][] = [];
  let current: Photo[] = [];
  for (const photo of ordered) {
    if (current.length === 0) {
      current = [photo];
      continue;
    }
    const previous = photoDay(current[current.length - 1]);
    const day = photoDay(photo);
    if (previous && day && dayDistance(previous, day) > gapDays) {
      groups.push(current);
      current = [photo];
    } else current.push(photo);
  }
  if (current.length) groups.push(current);
  return groups;
}

function dayDistance(left: string, right: string): number {
  const start = Date.parse(`${left}T00:00:00Z`);
  const end = Date.parse(`${right}T00:00:00Z`);
  return Math.round((end - start) / 86_400_000);
}

export function buildPlan(photos: Photo[], trip: Trip, rules: Rules = DEFAULT_RULES, templates: Record<string, string[]> = TAG_TEMPLATES): ReviewRow[] {
  const locations = locateAll(photos, trip, rules);
  const roles = burstRoles(photos, rules);
  const groups = assignCollections(photos, trip, rules);
  const templateTags = trip.template ? (templates[trip.template] ?? []) : [];
  return photos.map((photo) => {
    const located = locations.get(photo.id)!;
    const day = trip.days.find((item) => item.date === photoDay(photo));
    const tags = buildTags(photo, located.value, trip, day?.tags ?? [], templateTags, rules);
    const description = buildDescription(photo, located.value, rules);
    const show = decideVisibility(photo, rules, roles.get(photo.id) ?? "single");
    const group = groups.get(photo.id)!;
    const notes = [located.reason, tags.reason, description.reason, show.reason].filter(Boolean).join(" · ");
    return {
      photoId: photo.id,
      include: decideApprove(located, tags, description, show, rules) === "yes",
      location: located.value,
      locationConfidence: located.confidence,
      locationFlag: located.flag,
      locationSource: located.source,
      locationReason: located.reason,
      tags: tags.value,
      tagsConfidence: tags.confidence,
      tagsFlag: tags.flag,
      tagsReason: tags.reason,
      description: description.value,
      descriptionConfidence: description.confidence,
      descriptionFlag: description.flag,
      descriptionSource: description.source,
      showOnProfile: show.value,
      showConfidence: show.confidence,
      showFlag: show.flag,
      showSource: show.source,
      showReason: show.reason,
      collectionTitle: group.title,
      collectionDescription: group.description,
      notes,
      lastStatus: "",
      lastError: "",
    };
  });
}
