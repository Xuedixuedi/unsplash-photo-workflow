const SECRET_NAMES = [
  "UNSPLASH_ACCESS_KEY",
  "UNSPLASH_SECRET_KEY",
  "UNSPLASH_USER_TOKEN",
  "LLM_API_KEY",
  "UPW_PASSWORD",
  "UPW_SESSION_SECRET",
  "DATABASE_URL",
  "SENTRY_DSN",
];

export function redact(text: string): string {
  let out = text.replace(/Bearer\s+\S+/gi, "Bearer [redacted]");
  for (const name of SECRET_NAMES) {
    const value = process.env[name];
    if (value && value.length >= 4) out = out.split(value).join(`[redacted ${name}]`);
  }
  return out;
}
