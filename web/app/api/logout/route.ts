import { NextResponse } from "next/server";

export async function POST(request: Request) {
  const response = NextResponse.redirect(new URL("/login", request.url), 303);
  response.cookies.set("upw_session", "", { httpOnly: true, path: "/", maxAge: 0 });
  return response;
}
