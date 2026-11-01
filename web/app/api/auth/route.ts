import { NextResponse } from "next/server";

import { loadEnv } from "@/lib/env";
import { fail } from "@/lib/http";
import { passwordsMatch } from "@/lib/password";
import { signSession } from "@/lib/session";

export async function POST(request: Request) {
  try {
    loadEnv();
    const expected = process.env.UPW_PASSWORD || "";
    const secret = process.env.UPW_SESSION_SECRET || "";
    if (!expected || !secret) {
      return NextResponse.json(
        { error: "Set UPW_PASSWORD and UPW_SESSION_SECRET before opening the desk." },
        { status: 503 },
      );
    }
    const body = (await request.json().catch(() => ({}))) as { password?: unknown };
    const password = typeof body.password === "string" ? body.password : "";
    if (!passwordsMatch(password, expected)) {
      return NextResponse.json({ error: "That password does not match." }, { status: 401 });
    }
    const token = await signSession(secret);
    const response = NextResponse.json({ ok: true });
    response.cookies.set("upw_session", token, {
      httpOnly: true,
      sameSite: "lax",
      secure: process.env.NODE_ENV === "production",
      path: "/",
      maxAge: 60 * 60 * 24 * 14,
    });
    return response;
  } catch (error) {
    return fail(error);
  }
}
