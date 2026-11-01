import { NextResponse } from "next/server";

import { getPlan } from "@/lib/db";
import { fail } from "@/lib/http";
import { replaceRows } from "@/lib/service";
import type { ReviewRow } from "@/lib/types";

export const runtime = "nodejs";

type Context = { params: Promise<{ id: string }> };

export async function GET(_request: Request, context: Context) {
  try {
    const { id } = await context.params;
    const plan = await getPlan(id);
    if (!plan) return NextResponse.json({ error: "That review no longer exists." }, { status: 404 });
    return NextResponse.json(plan);
  } catch (error) {
    return fail(error);
  }
}

export async function PUT(request: Request, context: Context) {
  try {
    const { id } = await context.params;
    const body = (await request.json()) as { rows?: ReviewRow[] };
    if (!Array.isArray(body.rows)) return NextResponse.json({ error: "Send the edited rows." }, { status: 400 });
    const plan = await replaceRows(id, body.rows);
    return NextResponse.json({ id: plan.id, rows: plan.rows.length });
  } catch (error) {
    return fail(error);
  }
}
