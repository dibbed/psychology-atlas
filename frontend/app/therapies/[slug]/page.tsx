import { notFound } from "next/navigation";
import TherapyDetailView from "@/components/TherapyDetailView";
import { ApiError, publicFetch } from "@/lib/api";
import type { TherapyDetail } from "@/lib/types";

export default async function TherapyPage({ params }: { params: Promise<{ slug: string }> }) {
  const { slug } = await params;
  let therapy: TherapyDetail;
  try {
    therapy = await publicFetch<TherapyDetail>(`/therapies/${slug}/`);
  } catch (error) {
    if (error instanceof ApiError && error.status === 404) notFound();
    throw error;
  }

  return <main className="shell page"><TherapyDetailView therapy={therapy} /></main>;
}
