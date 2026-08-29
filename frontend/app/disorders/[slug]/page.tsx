import { notFound } from "next/navigation";
import DisorderDetailClient from "@/components/DisorderDetailClient";
import { ApiError, publicFetch } from "@/lib/api";
import type { DSMRecordDetail, DisorderDetail } from "@/lib/types";

export default async function DisorderPage({ params }: { params: Promise<{ slug: string }> }) {
  const { slug } = await params;
  let disorder: DisorderDetail;
  try {
    disorder = await publicFetch<DisorderDetail>(`/disorders/${slug}/`);
  } catch (error) {
    if (error instanceof ApiError && error.status === 404) notFound();
    throw error;
  }

  let dsmMaster: DSMRecordDetail | null = null;
  try {
    dsmMaster = await publicFetch<DSMRecordDetail>(`/dsm/records/by-disorder/${slug}/?detail=true`);
  } catch (error) {
    if (!(error instanceof ApiError && error.status === 404)) throw error;
  }

  return (
    <main className="shell page">
      <DisorderDetailClient disorder={disorder} dsmMaster={dsmMaster} />
    </main>
  );
}
