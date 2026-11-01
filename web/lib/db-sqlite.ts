import { mkdirSync } from "node:fs";
import path from "node:path";
import { DatabaseSync } from "node:sqlite";

import type { PlanStore } from "./db";
import type { StoredPlan } from "./types";

const SCHEMA = `CREATE TABLE IF NOT EXISTS plans (
  id TEXT PRIMARY KEY,
  created_at TEXT NOT NULL,
  title TEXT NOT NULL,
  body TEXT NOT NULL
)`;

export function openSqlite(file: string): PlanStore {
  if (file !== ":memory:") mkdirSync(path.dirname(file), { recursive: true });
  const db = new DatabaseSync(file);
  db.exec(SCHEMA);
  const write = db.prepare(
    `INSERT INTO plans (id, created_at, title, body) VALUES (?, ?, ?, ?)
     ON CONFLICT(id) DO UPDATE SET created_at = excluded.created_at, title = excluded.title, body = excluded.body`,
  );
  const read = db.prepare("SELECT body FROM plans WHERE id = ?");
  return {
    async save(plan: StoredPlan) {
      write.run(plan.id, plan.createdAt, plan.title, JSON.stringify(plan));
    },
    async get(id: string) {
      const row = read.get(id) as { body?: string } | undefined;
      if (!row?.body) return null;
      return JSON.parse(row.body) as StoredPlan;
    },
  };
}
