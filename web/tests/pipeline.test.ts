import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import path from "node:path";
import test from "node:test";
import { parse as parseYaml } from "yaml";

import { applyOne, locationsEqual, updatePayload } from "../lib/apply";
import { EXAMPLE_TRIP } from "../lib/example-trip";
import { loadFixturePhotos } from "../lib/fixtures";
import { photoFromApi } from "../lib/photos";
import { buildPlan, decideApprove, decideVisibility } from "../lib/plan";
import { DEFAULT_RULES, TAG_TEMPLATES } from "../lib/rules";
import { buildTags, normalizeTag } from "../lib/tags";
import type { Location, Photo, ReviewRow, Suggestion } from "../lib/types";

const repoRoot = path.join(process.cwd(), "..");

test("embedded rules and templates match the Python config", () => {
  const rules = parseYaml(readFileSync(path.join(repoRoot, "config/rules.yaml"), "utf8")) as Record<string, unknown>;
  assert.equal(rules.target_tag_count, DEFAULT_RULES.targetTagCount);
  assert.equal(rules.never_hide_above_downloads, DEFAULT_RULES.neverHideAboveDownloads);
  assert.equal(rules.burst_seconds, DEFAULT_RULES.burstSeconds);
  assert.equal(rules.min_auto_approve_confidence, DEFAULT_RULES.minAutoApproveConfidence);
  assert.deepEqual(rules.camera_brands, DEFAULT_RULES.cameraBrands);
  const templates = parseYaml(readFileSync(path.join(repoRoot, "config/tag_templates.yaml"), "utf8")) as {
    templates: Record<string, string[]>;
  };
  assert.deepEqual(templates.templates, TAG_TEMPLATES);
  const example = parseYaml(readFileSync(path.join(repoRoot, "trips/example-jiuzhaigou.yaml"), "utf8")) as {
    name: string;
    collection: string;
    days: { date: string; places: { name: string }[] }[];
  };
  assert.equal(example.name, EXAMPLE_TRIP.name);
  assert.equal(example.collection, EXAMPLE_TRIP.collection);
  assert.equal(example.days[0].date, EXAMPLE_TRIP.days[0].date);
  assert.deepEqual(
    example.days[0].places.map((place) => place.name),
    EXAMPLE_TRIP.days[0].places.map((place) => place.name),
  );
});

test("tags keep owner phrases, drop brands and hashtags, and stop at 20", () => {
  assert.equal(normalizeTag("UNESCO World Heritage Site", DEFAULT_RULES.cameraBrands, 5), "unesco world heritage site");
  assert.equal(normalizeTag("Nikon body", DEFAULT_RULES.cameraBrands, 3), null);
  assert.equal(normalizeTag("#autumn", DEFAULT_RULES.cameraBrands, 3), null);
  const photo = blankPhoto({ tags: ["Travel Photography", "unesco world heritage site", "nikon"] });
  const tags = buildTags(
    photo,
    { name: "Five Flower Lake", city: "Jiuzhaigou County", region: "Ngawa", country: "China", latitude: 1, longitude: 2 },
    EXAMPLE_TRIP,
    ["colorful lakes"],
    TAG_TEMPLATES["mountain-autumn"],
    DEFAULT_RULES,
  );
  assert.ok(tags.value.includes("travel photography"));
  assert.ok(tags.value.includes("unesco world heritage site"));
  assert.equal(tags.value.includes("nikon"), false);
  assert.ok(tags.value.length <= 20);
  assert.equal(new Set(tags.value.map((tag) => tag.toLowerCase())).size, tags.value.length);
});

test("downloads above 100 are never hidden, even in a burst", () => {
  const popular = blankPhoto({ id: "pop", downloads: 200, capturedAt: "2026-10-31T02:00:00Z" });
  const extra = blankPhoto({ id: "extra", downloads: 1, capturedAt: "2026-10-31T02:00:02Z" });
  const visible = decideVisibility(popular, DEFAULT_RULES, "extra");
  assert.equal(visible.value, true);
  assert.equal(visible.source, "rule:downloads");
  const hidden = decideVisibility(extra, DEFAULT_RULES, "extra");
  assert.equal(hidden.value, false);
  assert.equal(hidden.flag, "review");
});

test("fixture photos keep an existing place and flag an ambiguous day", () => {
  const photos = loadFixturePhotos();
  const rows = buildPlan(photos, EXAMPLE_TRIP);
  const located = rows.find((row) => row.photoId === "2RxlZqY3nz8");
  assert.ok(located);
  assert.equal(located.locationSource, "existing");
  assert.equal(located.locationFlag, "ok");
  assert.equal(located.include, true);
  const empty = rows.find((row) => row.location === null && row.locationSource === "ambiguous");
  assert.ok(empty);
  assert.equal(empty.include, false);
  assert.equal(empty.locationFlag, "review");
});

test("one itinerary place fills a photo that has no location", () => {
  const photo = blankPhoto({ id: "bare", createdAt: "2026-10-31", tags: ["lake"] });
  const trip = {
    ...EXAMPLE_TRIP,
    days: [{ ...EXAMPLE_TRIP.days[0], places: [EXAMPLE_TRIP.days[0].places[0]] }],
  };
  const [row] = buildPlan([photo], trip);
  assert.equal(row.location?.name, "Five Flower Lake");
  assert.equal(row.locationSource, "itinerary");
  assert.equal(row.collectionTitle, "Jiuzhaigou Autumn 2026");
  assert.match(row.description, /Five Flower Lake/);
});

test("a neighbour with a clock time is flagged, and date-only uploads are not chained", () => {
  const first = blankPhoto({
    id: "a",
    createdAt: "2026-10-31T01:00:00Z",
    capturedAt: "2026-10-31T01:00:00Z",
    location: place("Pearl Shoals"),
  });
  const second = blankPhoto({ id: "b", createdAt: "2026-10-31T01:02:00Z", capturedAt: "2026-10-31T01:02:00Z" });
  const trip = { ...EXAMPLE_TRIP, days: [{ date: "2026-11-02", tags: [], places: [] }] };
  const rows = buildPlan([first, second], trip);
  const inherited = rows.find((row) => row.photoId === "b");
  assert.equal(inherited?.locationSource, "neighbour");
  assert.equal(inherited?.locationFlag, "review");
  assert.equal(inherited?.include, false);
});

test("apply sends only changed fields and skips a second identical write", async () => {
  const photo = blankPhoto({ tags: ["lake"], description: "Already written." });
  const row = rowFor(photo, {
    location: place("Pearl Shoals"),
    tags: ["lake", "china"],
    description: "Already written.",
    showOnProfile: false,
    include: true,
  });
  const payload = updatePayload(photo, row);
  assert.equal(payload.description, undefined);
  assert.deepEqual(payload.tags, ["lake", "china"]);
  assert.equal(payload.showOnProfile, false);
  assert.equal(payload.location?.name, "Pearl Shoals");
  const calls: string[] = [];
  const writer = {
    async updatePhoto() {
      calls.push("update");
    },
    async listCollections() {
      return [];
    },
    async createCollection(title: string) {
      calls.push(`create:${title}`);
      return { id: "9", title };
    },
    async addPhoto() {
      calls.push("add");
    },
  };
  const first = await applyOne(photo, row, new Map(), writer, "live");
  assert.equal(first.result.status, "updated");
  assert.deepEqual(calls, ["update", "create:Jiuzhaigou Autumn 2026", "add"]);
  const known = first.known;
  photo.tags = ["lake", "china"];
  photo.location = place("Pearl Shoals");
  photo.showOnProfile = false;
  photo.showOnProfileKnown = true;
  photo.collections = [{ id: "9", title: "Jiuzhaigou Autumn 2026" }];
  const second = await applyOne(photo, row, known, writer, "live");
  assert.equal(second.result.status, "skipped");
  assert.equal(calls.length, 3);
});

test("unchanged visibility does not block an otherwise confident row", () => {
  const location: Suggestion<Location | null> = {
    value: place("Pearl Shoals"),
    confidence: 0.92,
    source: "existing",
    flag: "ok",
    reason: "",
  };
  const tags: Suggestion<string[]> = { value: ["a", "b", "c", "d", "e", "f", "g", "h"], confidence: 0.86, source: "deterministic", flag: "ok", reason: "" };
  const description: Suggestion<string> = { value: "", confidence: 0, source: "none", flag: "empty", reason: "" };
  const show: Suggestion<boolean> = { value: true, confidence: 0.6, source: "unchanged", flag: "ok", reason: "" };
  assert.equal(decideApprove(location, tags, description, show, DEFAULT_RULES), "yes");
  assert.equal(locationsEqual(place("Pearl Shoals"), { ...place("Pearl Shoals"), region: "Somewhere" }), true);
});

test("public photo resources become the desk model", () => {
  const photo = photoFromApi({
    id: "abc",
    created_at: "2026-10-31T03:04:05Z",
    location: { name: "Jiuzhaigou Valley, Jiuzhaigou County, Ngawa, China", position: { latitude: 33.2, longitude: 103.9 } },
    tags: [{ title: "Lake" }],
    downloads: 12,
    show_on_profile: false,
  });
  assert.equal(photo.location?.city, "Jiuzhaigou County");
  assert.equal(photo.location?.country, "China");
  assert.equal(photo.location?.latitude, 33.2);
  assert.equal(photo.showOnProfile, false);
  assert.equal(photo.showOnProfileKnown, true);
  assert.deepEqual(photo.tags, ["Lake"]);
});

function place(name: string): Location {
  return { name, city: "Jiuzhaigou County", region: "Ngawa", country: "China", latitude: 33.2, longitude: 103.9 };
}

function blankPhoto(overrides: Partial<Photo> = {}): Photo {
  return {
    id: "p",
    slug: "p",
    createdAt: "2026-10-31",
    width: 1000,
    height: 800,
    description: null,
    altDescription: null,
    location: null,
    tags: [],
    downloads: 0,
    likes: 0,
    views: 0,
    camera: null,
    showOnProfile: true,
    showOnProfileKnown: false,
    urls: {},
    collections: [],
    capturedAt: null,
    ...overrides,
  };
}

function rowFor(photo: Photo, overrides: Partial<ReviewRow>): ReviewRow {
  return {
    photoId: photo.id,
    include: true,
    location: null,
    locationConfidence: 1,
    locationFlag: "ok",
    locationSource: "human",
    locationReason: "",
    tags: photo.tags,
    tagsConfidence: 1,
    tagsFlag: "ok",
    tagsReason: "",
    description: photo.description || "",
    descriptionConfidence: 1,
    descriptionFlag: "ok",
    descriptionSource: "human",
    showOnProfile: true,
    showConfidence: 1,
    showFlag: "ok",
    showSource: "human",
    showReason: "",
    collectionTitle: "Jiuzhaigou Autumn 2026",
    collectionDescription: "Autumn",
    notes: "",
    lastStatus: "",
    lastError: "",
    ...overrides,
  };
}
