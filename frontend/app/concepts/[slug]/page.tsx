import { notFound } from "next/navigation";
import ConceptDetailClient from "@/components/ConceptDetailClient";
import { ApiError, publicFetch } from "@/lib/api";
import type { ConceptDetail } from "@/lib/types";

export default async function ConceptPage({ params }: { params: Promise<{ slug: string }> }) {
  const { slug } = await params;
  let concept: ConceptDetail;
  try {
    concept = await publicFetch<ConceptDetail>(`/concepts/${slug}/`);
  } catch (error) {
    if (error instanceof ApiError && error.status === 404) notFound();
    throw error;
  }

  return <main className="shell page"><ConceptDetailClient concept={concept} /></main>;
}
