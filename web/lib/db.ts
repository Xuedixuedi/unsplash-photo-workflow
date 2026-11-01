import path from "node:path";

import { loadEnv } from "./env";
import type { StoredPlan } from "./types";

export type PlanStore = {
  save: (plan: StoredPlan) => Promise<void>;
  get: (id: string) => Promise<StoredPlan | null>;
};

let cached: { key: string; store: PlanStore } | null = null;

export function databaseKind(): "neon" | "sqlite" {
  if (process.env.DATABASE_URL) return "neon";
  if (process.env.VERCEL) {
    throw new Error("Set DATABASE_URL to a Neon Postgres connection string on Vercel. SQLite is only for a local desk.");
  }
  return "sqlite";
}

export function resetDatabaseForTests(): void {
  cached = null;
}

export async function openDatabase(): Promise<PlanStore> {
  loadEnv();
  const kind = databaseKind();
  const key = kind === "neon" ? `neon:${process.env.DATABASE_URL}` : `sqlite:${sqlitePath()}`;
  if (cached?.key === key) return cached.store;
  const store = kind === "neon" ? await openNeonStore() : await openSqliteStore();
  cached = { key, store };
  return store;
}

function sqlitePath(): string {
  return process.env.UPW_SQLITE_PATH || path.join(process.cwd(), "data", "upw.sqlite");
}

async function openSqliteStore(): Promise<PlanStore> {
  const { openSqlite } = await import("./db-sqlite");
  return openSqlite(sqlitePath());
}

async function openNeonStore(): Promise<PlanStore> {
  const url = process.env.DATABASE_URL || "";
  const { openNeon } = await import("./db-neon");
  return openNeon(url);
}

export async function savePlan(plan: StoredPlan): Promise<void> {
  const store = await openDatabase();
  await store.save(plan);
}

export async function getPlan(id: string): Promise<StoredPlan | null> {
  const store = await openDatabase();
  return store.get(id);
}
