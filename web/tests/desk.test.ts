import assert from "node:assert/strict";
import { mkdtempSync } from "node:fs";
import { tmpdir } from "node:os";
import path from "node:path";
import test from "node:test";

import { openSqlite } from "../lib/db-sqlite";
import { databaseKind, resetDatabaseForTests } from "../lib/db";
import { locationFromNominatim, resetNominatimForTests, searchPlaces } from "../lib/nominatim";
import { passwordsMatch } from "../lib/password";
import { redact } from "../lib/redact";
import { captureException, sentryStoreUrl } from "../lib/sentry";
import { signSession, verifySession } from "../lib/session";
import { parseTrip, TripInputError } from "../lib/trip-input";
import { encodeUpdate } from "../lib/unsplash";
import type { StoredPlan } from "../lib/types";

test("session cookie round-trips and rejects a bad signature", async () => {
  const token = await signSession("desk-secret", 1_000);
  assert.equal(await verifySession(token, "desk-secret", 1_000), true);
  assert.equal(await verifySession(token, "other-secret", 1_000), false);
  assert.equal(await verifySession(token, "desk-secret", 20 * 24 * 60 * 60 * 1000), false);
});

test("password check does not treat a different string as equal", () => {
  assert.equal(passwordsMatch("correct horse", "correct horse"), true);
  assert.equal(passwordsMatch("nope", "correct horse"), false);
});

test("secrets are removed from messages", () => {
  process.env.UNSPLASH_USER_TOKEN = "user-token-value";
  assert.equal(redact("Bearer user-token-value and user-token-value"), "Bearer [redacted] and [redacted UNSPLASH_USER_TOKEN]");
  delete process.env.UNSPLASH_USER_TOKEN;
});

test("sentry stays quiet without a DSN and posts when one is set", async () => {
  let called = false;
  delete process.env.SENTRY_DSN;
  await captureException(new Error("hidden"), async () => {
    called = true;
    return new Response(null, { status: 200 });
  });
  assert.equal(called, false);
  process.env.SENTRY_DSN = "https://public@sentry.invalid/123";
  const target = sentryStoreUrl(process.env.SENTRY_DSN);
  assert.equal(target?.key, "public");
  let body = "";
  await captureException(new Error("boom"), async (_url, init) => {
    body = String(init?.body || "");
    return new Response(null, { status: 200 });
  });
  assert.match(body, /boom/);
  delete process.env.SENTRY_DSN;
});

test("sqlite stores a plan and replaces it", async () => {
  const dir = mkdtempSync(path.join(tmpdir(), "upw-"));
  const store = openSqlite(path.join(dir, "upw.sqlite"));
  const plan = samplePlan();
  await store.save(plan);
  plan.title = "Updated";
  await store.save(plan);
  const loaded = await store.get(plan.id);
  assert.equal(loaded?.title, "Updated");
  assert.equal(await store.get("missing"), null);
});

test("vercel without DATABASE_URL refuses sqlite", () => {
  resetDatabaseForTests();
  const previous = process.env.DATABASE_URL;
  const vercel = process.env.VERCEL;
  delete process.env.DATABASE_URL;
  delete process.env.VERCEL;
  assert.equal(databaseKind(), "sqlite");
  process.env.DATABASE_URL = "postgres://example";
  assert.equal(databaseKind(), "neon");
  delete process.env.DATABASE_URL;
  process.env.VERCEL = "1";
  assert.throws(() => databaseKind(), /DATABASE_URL/);
  if (previous) process.env.DATABASE_URL = previous;
  else delete process.env.DATABASE_URL;
  if (vercel) process.env.VERCEL = vercel;
  else delete process.env.VERCEL;
});

test("nominatim hits become places and are cached", async () => {
  resetNominatimForTests();
  const place = locationFromNominatim({
    lat: "33.26",
    lon: "103.92",
    display_name: "Five Flower Lake, Jiuzhaigou, China",
    address: { tourism: "Five Flower Lake", county: "Jiuzhaigou County", state: "Sichuan", country: "China" },
  });
  assert.equal(place?.name, "Five Flower Lake");
  assert.equal(place?.city, "Jiuzhaigou County");
  let calls = 0;
  const fetchImpl: typeof fetch = async () => {
    calls += 1;
    return new Response(JSON.stringify([{ lat: "1", lon: "2", display_name: "Lake, China", address: { country: "China" } }]), {
      status: 200,
      headers: { "content-type": "application/json" },
    });
  };
  const first = await searchPlaces("lake", fetchImpl);
  const second = await searchPlaces("lake", fetchImpl);
  assert.equal(first[0]?.name, "Lake");
  assert.equal(second.length, 1);
  assert.equal(calls, 1);
  resetNominatimForTests();
});

test("trip input rejects a day without a date", () => {
  assert.throws(() => parseTrip({ name: "Trip", days: [{ date: "" }] }), TripInputError);
  const trip = parseTrip({
    name: "Trip",
    days: [{ date: "2026-10-31", places: [{ name: "Pearl Shoals", latitude: "33.2", longitude: "103.9" }] }],
  });
  assert.equal(trip.days[0].places[0].latitude, 33.2);
});

test("photo updates use the Unsplash form fields", () => {
  const body = encodeUpdate({
    description: "Pearl Shoals, Jiuzhaigou County, China.",
    showOnProfile: false,
    tags: ["pearl shoals", "china"],
    location: { name: "Pearl Shoals", city: "Jiuzhaigou County", country: "China", latitude: 33.2, longitude: 103.9 },
  });
  const params = new URLSearchParams(body);
  assert.equal(params.get("show_on_profile"), "false");
  assert.deepEqual(params.getAll("tags[]"), ["pearl shoals", "china"]);
  assert.equal(params.get("location[latitude]"), "33.200000");
  assert.equal(params.get("location[name]"), "Pearl Shoals");
});

function samplePlan(): StoredPlan {
  return {
    id: "plan-1",
    createdAt: "2026-11-01T00:00:00Z",
    title: "Trip",
    trip: { name: "Trip", collection: "Trip", description: "", template: null, tags: [], days: [] },
    photos: [],
    rows: [],
    collections: [],
  };
}
