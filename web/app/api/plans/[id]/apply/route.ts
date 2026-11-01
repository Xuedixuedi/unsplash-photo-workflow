import { NextResponse } from "next/server";

import { fail } from "@/lib/http";
import { applyStoredPhoto } from "@/lib/service";

export const runtime = "nodejs";

export async function POST(request: Request, context: { params: Promise<{ id: string }> }) {
  try {
    const { id } = await context.params;
    const body = (await request.json()) as { photoId?: unknown };
    const photoId = typeof body.photoId === "string" ? body.photoId : "";
    if (!photoId) return NextResponse.json({ error: "Missing photoId." }, { status: 400 });
    const result = await applyStoredPhoto(id, photoId);
    return NextResponse.json(result);
  } catch (error) {
    return fail(error);
  }
}
