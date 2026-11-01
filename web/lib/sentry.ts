import { redact } from "./redact";

type FetchLike = (input: string, init: RequestInit) => Promise<Response>;

export function sentryStoreUrl(dsn: string): { store: string; key: string } | null {
  try {
    const url = new URL(dsn);
    const project = url.pathname.replaceAll("/", "");
    if (!url.username || !project) return null;
    return { store: `${url.protocol}//${url.host}/api/${project}/store/`, key: url.username };
  } catch {
    return null;
  }
}

/** Send one exception when SENTRY_DSN is set. Missing or broken DSN does nothing. */
export async function captureException(error: unknown, fetchImpl: FetchLike = fetch): Promise<void> {
  const dsn = process.env.SENTRY_DSN || "";
  const target = dsn ? sentryStoreUrl(dsn) : null;
  if (!target) return;
  const message = redact(error instanceof Error ? error.message : String(error));
  const name = error instanceof Error ? error.name : "Error";
  const body = {
    event_id: crypto.randomUUID().replaceAll("-", ""),
    message,
    timestamp: Date.now() / 1000,
    platform: "node",
    exception: { values: [{ type: name, value: message }] },
  };
  try {
    await fetchImpl(target.store, {
      method: "POST",
      headers: {
        "content-type": "application/json",
        "x-sentry-auth": `Sentry sentry_version=7, sentry_key=${target.key}, sentry_client=upw-web/0.1`,
      },
      body: JSON.stringify(body),
    });
  } catch {
    // Reporting must not replace the original failure.
  }
}
