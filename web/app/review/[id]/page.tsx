import { notFound } from "next/navigation";

import { ReviewBoard } from "@/components/ReviewBoard";
import { getPlan } from "@/lib/db";

export const dynamic = "force-dynamic";

export default async function ReviewPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  const plan = await getPlan(id);
  if (!plan) notFound();
  return (
    <main id="content">
      <p className="eyebrow">Review</p>
      <h1>{plan.title}</h1>
      <ReviewBoard plan={plan} />
    </main>
  );
}
