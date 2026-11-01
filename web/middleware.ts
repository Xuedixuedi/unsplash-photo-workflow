import { NextResponse } from "next/server";
import type { NextRequest } from "next/server";

import { verifySession } from "./lib/session";

const PUBLIC_PREFIXES = ["/login", "/api/auth", "/api/health", "/api/logout"];

export async function middleware(request: NextRequest) {
  const { pathname } = request.nextUrl;
  if (PUBLIC_PREFIXES.some((prefix) => pathname === prefix || pathname.startsWith(`${prefix}/`))) {
    return NextResponse.next();
  }
  const secret = process.env.UPW_SESSION_SECRET || "";
  const token = request.cookies.get("upw_session")?.value || "";
  if (secret && (await verifySession(token, secret))) return NextResponse.next();
  if (pathname.startsWith("/api/")) {
    return NextResponse.json({ error: "Sign in required." }, { status: 401 });
  }
  const url = request.nextUrl.clone();
  url.pathname = "/login";
  url.search = "";
  if (pathname !== "/") url.searchParams.set("next", pathname);
  return NextResponse.redirect(url);
}

export const config = {
  matcher: ["/((?!_next/static|_next/image|favicon.ico).*)"],
};
