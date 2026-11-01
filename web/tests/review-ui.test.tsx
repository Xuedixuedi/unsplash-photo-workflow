import assert from "node:assert/strict";
import test from "node:test";
import { renderToStaticMarkup } from "react-dom/server";

import { FailureList, ApplyProgress } from "../components/ReviewBoard";
import { PhotoCard } from "../components/PhotoCard";
import type { Photo, ReviewRow } from "../lib/types";

test("a low-confidence location is marked for review", () => {
  const html = renderToStaticMarkup(
    <PhotoCard photo={samplePhoto()} row={sampleRow()} onChange={() => undefined} />,
  );
  assert.match(html, /needs-review/);
  assert.match(html, /Check this/);
  assert.match(html, /abc123/);
});

test("apply progress and failures render", () => {
  const progress = renderToStaticMarkup(<ApplyProgress done={1} total={4} />);
  assert.match(progress, /1 of 4/);
  const failures = renderToStaticMarkup(
    <FailureList failures={[{ photoId: "abc123", error: "Unsplash rate limit reached." }]} />,
  );
  assert.match(failures, /abc123/);
  assert.match(failures, /rate limit/);
  assert.equal(renderToStaticMarkup(<FailureList failures={[]} />), "");
});

function samplePhoto(): Photo {
  return {
    id: "abc123",
    slug: "abc123",
    createdAt: "2026-10-31",
    width: 100,
    height: 80,
    description: null,
    altDescription: "A lake",
    location: null,
    tags: ["lake"],
    downloads: 3,
    likes: 0,
    views: 0,
    camera: null,
    showOnProfile: true,
    showOnProfileKnown: false,
    urls: {},
    collections: [],
    capturedAt: null,
  };
}

function sampleRow(): ReviewRow {
  return {
    photoId: "abc123",
    include: false,
    location: null,
    locationConfidence: 0.3,
    locationFlag: "review",
    locationSource: "ambiguous",
    locationReason: "several places on this day",
    tags: ["lake"],
    tagsConfidence: 0.86,
    tagsFlag: "ok",
    tagsReason: "8 tags",
    description: "",
    descriptionConfidence: 0,
    descriptionFlag: "empty",
    descriptionSource: "none",
    showOnProfile: true,
    showConfidence: 0.6,
    showFlag: "ok",
    showSource: "unchanged",
    showReason: "keeping the current visibility",
    collectionTitle: "Jiuzhaigou Autumn 2026",
    collectionDescription: "",
    notes: "",
    lastStatus: "",
    lastError: "",
  };
}
