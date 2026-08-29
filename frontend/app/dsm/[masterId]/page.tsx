import { notFound } from "next/navigation";
import DSMRecordView from "@/components/DSMRecordView";
import { ApiError, publicFetch } from "@/lib/api";
import type { DSMRecordDetail } from "@/lib/types";

export default async function DSMRecordPage({ params }: { params: Promise<{ masterId: string }> }) {
  const { masterId } = await params;
  let record: DSMRecordDetail;
  try {
    record = await publicFetch<DSMRecordDetail>(`/dsm/records/${encodeURIComponent(masterId)}/`);
  } catch (error) {
    if (error instanceof ApiError && error.status === 404) notFound();
    throw error;
  }

  return (
    <main className="shell page">
      <DSMRecordView record={record} />
    </main>
  );
}
