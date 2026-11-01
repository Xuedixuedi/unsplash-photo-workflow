"use client";

import { useState } from "react";
import type { FormEvent } from "react";

export function LoginForm({ nextPath }: { nextPath: string }) {
  const [error, setError] = useState("");
  const [pending, setPending] = useState(false);

  async function onSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setPending(true);
    setError("");
    const password = String(new FormData(event.currentTarget).get("password") || "");
    try {
      const response = await fetch("/api/auth", {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ password }),
      });
      const data = (await response.json().catch(() => ({}))) as { error?: string };
      if (!response.ok) {
        setError(data.error || "Could not sign in.");
        setPending(false);
        return;
      }
      window.location.assign(nextPath);
    } catch {
      setError("Could not reach the desk.");
      setPending(false);
    }
  }

  return (
    <form className="login-sheet" onSubmit={onSubmit}>
      <label htmlFor="password">Password</label>
      <input id="password" name="password" type="password" autoComplete="current-password" required />
      {error ? (
        <p className="alert" role="alert">
          {error}
        </p>
      ) : null}
      <div className="button-row">
        <button type="submit" disabled={pending}>
          {pending ? "Checking…" : "Open"}
        </button>
      </div>
    </form>
  );
}
