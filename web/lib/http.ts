import { NextResponse } from "next/server";

import { DeskError } from "./errors";
import { redact } from "./redact";
import { captureException } from "./sentry";
import { TripInputError } from "./trip-input";

export async function fail(error: unknown): Promise<NextResponse> {
  const message = redact(error instanceof Error ? error.message : "Something went wrong.");
  const status = error instanceof DeskError ? error.status : error instanceof TripInputError ? 400 : 500;
  if (status >= 500) await captureException(error);
  return NextResponse.json({ error: message }, { status });
}
