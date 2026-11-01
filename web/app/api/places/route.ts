import { NextResponse } from "next/server";

import { loadEnv } from "@/lib/env";
import { fail } from "@/lib/http";
import { searchPlaces } from "@/lib/nominatim";

export async function GET(request: Request) {
  try {
    loadEnv();
    const query = new URL(request.url).searchParams.get("q") || "";
    const places = await searchPlaces(query);
    return NextResponse.json({ places });
  } catch (error) {
    return fail(error);
  }
}
