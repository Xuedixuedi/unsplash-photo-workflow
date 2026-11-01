import { NextResponse } from "next/server";

import { fail } from "@/lib/http";
import { createPlanFromTrip } from "@/lib/service";

export const runtime = "nodejs";

export async function POST(request: Request) {
  try {
    const body = (await request.json()) as { trip?: unknown };
    const plan = await createPlanFromTrip(body.trip);
    return NextResponse.json({
      id: plan.id,
      title: plan.title,
      photos: plan.rows.length,
      ready: plan.rows.filter((row) => row.include).length,
    });
  } catch (error) {
    return fail(error);
  }
}
