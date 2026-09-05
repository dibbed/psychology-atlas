import { notFound } from "next/navigation";
import PsychologistDetailView from "@/components/PsychologistDetailView";
import { ApiError, publicFetch } from "@/lib/api";
import type { PsychologistDetail } from "@/lib/types";

export default async function PsychologistPage({ params }: { params: Promise<{ slug: string }> }) {
  const { slug } = await params;
  let psychologist: PsychologistDetail;
  try {
    psychologist = await publicFetch<PsychologistDetail>(`/psychologists/${slug}/`);
  } catch (error) {
    if (error instanceof ApiError && error.status === 404) notFound();
    throw error;
  }
  return <main className="shell page"><PsychologistDetailView psychologist={psychologist} /></main>;
}
