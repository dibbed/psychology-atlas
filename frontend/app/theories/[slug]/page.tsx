import { notFound } from "next/navigation";
import TheoryDetailView from "@/components/TheoryDetailView";
import { ApiError, publicFetch } from "@/lib/api";
import type { TheoryDetail } from "@/lib/types";

export default async function TheoryPage({ params }: { params: Promise<{ slug: string }> }) {
  const { slug } = await params;
  let theory: TheoryDetail;
  try {
    theory = await publicFetch<TheoryDetail>(`/theories/${slug}/`);
  } catch (error) {
    if (error instanceof ApiError && error.status === 404) notFound();
    throw error;
  }
  return <main className="shell page"><TheoryDetailView theory={theory} /></main>;
}
