import { notFound } from "next/navigation";
import TechniqueDetailView from "@/components/TechniqueDetailView";
import { ApiError, publicFetch } from "@/lib/api";
import type { TechniqueDetail } from "@/lib/types";

export default async function TechniquePage({ params }: { params: Promise<{ slug: string }> }) {
  const { slug } = await params;
  let technique: TechniqueDetail;
  try {
    technique = await publicFetch<TechniqueDetail>(`/techniques/${slug}/`);
  } catch (error) {
    if (error instanceof ApiError && error.status === 404) notFound();
    throw error;
  }

  return <main className="shell page"><TechniqueDetailView technique={technique} /></main>;
}
