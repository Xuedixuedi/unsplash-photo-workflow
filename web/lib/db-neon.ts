import { neon } from "@neondatabase/serverless";

import type { PlanStore } from "./db";
import type { StoredPlan } from "./types";

export function openNeon(url: string): PlanStore {
  const sql = neon(url);
  let ready: Promise<unknown> | null = null;
  const migrate = () => {
    ready ??= sql`CREATE TABLE IF NOT EXISTS plans (
      id TEXT PRIMARY KEY,
      created_at TEXT NOT NULL,
      title TEXT NOT NULL,
      body TEXT NOT NULL
    )`;
    return ready;
  };
  return {
    async save(plan: StoredPlan) {
      await migrate();
      const body = JSON.stringify(plan);
      await sql`INSERT INTO plans (id, created_at, title, body) VALUES (${plan.id}, ${plan.createdAt}, ${plan.title}, ${body})
        ON CONFLICT (id) DO UPDATE SET created_at = EXCLUDED.created_at, title = EXCLUDED.title, body = EXCLUDED.body`;
    },
    async get(id: string) {
      await migrate();
      const rows = await sql`SELECT body FROM plans WHERE id = ${id}`;
      const row = rows[0] as { body?: string } | undefined;
      if (!row?.body) return null;
      return JSON.parse(row.body) as StoredPlan;
    },
  };
}
