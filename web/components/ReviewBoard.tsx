"use client";

import { useMemo, useState } from "react";

import type { ApplyResult, ReviewRow, StoredPlan } from "@/lib/types";

import { PhotoCard } from "./PhotoCard";

export function ApplyProgress({ done, total }: { done: number; total: number }) {
  if (total === 0) return null;
  return (
    <p className="progress">
      <progress value={done} max={total} />
      <span>
        {done} of {total}
      </span>
    </p>
  );
}

export function FailureList({ failures }: { failures: { photoId: string; error: string }[] }) {
  if (failures.length === 0) return null;
  return (
    <section aria-live="polite">
      <h2>Not written</h2>
      <ul className="failures">
        {failures.map((item) => (
          <li key={item.photoId}>
            <span className="frame-id">{item.photoId}</span> {item.error}
          </li>
        ))}
      </ul>
    </section>
  );
}

export function ReviewBoard({ plan }: { plan: StoredPlan }) {
  const [rows, setRows] = useState(plan.rows);
  const [busy, setBusy] = useState(false);
  const [done, setDone] = useState(0);
  const [total, setTotal] = useState(0);
  const [failures, setFailures] = useState<{ photoId: string; error: string }[]>([]);
  const [message, setMessage] = useState("");
  const photos = useMemo(() => new Map(plan.photos.map((photo) => [photo.id, photo])), [plan.photos]);
  const flagged = rows.filter((row) => row.locationFlag !== "ok" || row.tagsFlag !== "ok" || row.showFlag !== "ok").length;

  function update(next: ReviewRow) {
    setRows((current) => current.map((row) => (row.photoId === next.photoId ? next : row)));
  }

  async function applySelected() {
    const chosen = rows.filter((row) => row.include);
    if (chosen.length === 0) {
      setMessage("Select at least one photo. Unchecked rows are left untouched.");
      return;
    }
    setBusy(true);
    setMessage("");
    setFailures([]);
    setDone(0);
    setTotal(chosen.length);
    const saved = await fetch(`/api/plans/${plan.id}`, {
      method: "PUT",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ rows }),
    });
    if (!saved.ok) {
      const data = (await saved.json().catch(() => ({}))) as { error?: string };
      setMessage(data.error || "Could not save the edits.");
      setBusy(false);
      return;
    }
    const problems: { photoId: string; error: string }[] = [];
    let fixture = false;
    for (let index = 0; index < chosen.length; index += 1) {
      const row = chosen[index];
      try {
        const response = await fetch(`/api/plans/${plan.id}/apply`, {
          method: "POST",
          headers: { "content-type": "application/json" },
          body: JSON.stringify({ photoId: row.photoId }),
        });
        const result = (await response.json()) as ApplyResult & { error?: string };
        if (!response.ok || result.status === "failed") {
          problems.push({ photoId: row.photoId, error: result.error || "Unsplash did not accept this photo." });
        }
        if (result.mode === "fixture") fixture = true;
        setRows((current) =>
          current.map((item) =>
            item.photoId === row.photoId ? { ...item, lastStatus: result.status || "failed", lastError: result.error || "" } : item,
          ),
        );
      } catch {
        problems.push({ photoId: row.photoId, error: "The apply request did not finish." });
      }
      setDone(index + 1);
    }
    setFailures(problems);
    setBusy(false);
    if (fixture) setMessage("Fixture mode checked the plan and did not call Unsplash.");
    else if (problems.length) setMessage("Some photos were not written. The rest were sent.");
    else setMessage("Unsplash accepted the selected photos.");
  }

  return (
    <div>
      <p className="lede">
        {rows.length} photos. {rows.filter((row) => row.include).length} selected. {flagged} still have a field to check.
        Amber marks a location, tag list, or profile choice the code would not approve on its own.
      </p>
      <div className="button-row">
        <button type="button" onClick={applySelected} disabled={busy}>
          {busy ? "Applying…" : "Apply"}
        </button>
        <ApplyProgress done={done} total={total} />
      </div>
      {message ? <p role="status">{message}</p> : null}
      <FailureList failures={failures} />
      <div className="contact">
        {rows.map((row) => {
          const photo = photos.get(row.photoId);
          if (!photo) return null;
          return <PhotoCard key={row.photoId} photo={photo} row={row} onChange={update} />;
        })}
      </div>
    </div>
  );
}
