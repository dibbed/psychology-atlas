import { notFound } from "next/navigation";
import TimelineDetailView from "@/components/TimelineDetailView";
import { ApiError, publicFetch } from "@/lib/api";
import type { Paginated, TimelineEvent, TimelineEventDetail } from "@/lib/types";

export default async function TimelineEventPage({ params }: { params: Promise<{ slug: string }> }) {
  const { slug } = await params;
  const detailPromise = publicFetch<TimelineEventDetail>(`/timeline/${slug}/`);
  const listPromise = publicFetch<Paginated<TimelineEvent>>("/timeline/?page_size=300").catch(() => null);

  let event: TimelineEventDetail;
  try {
    event = await detailPromise;
  } catch (error) {
    if (error instanceof ApiError && error.status === 404) notFound();
    throw error;
  }

  const listData = await listPromise;
  let previous: TimelineEvent | null = null;
  let next: TimelineEvent | null = null;
  if (listData) {
    const ordered = [...listData.results].sort((a, b) => (a.year_start ?? 9999) - (b.year_start ?? 9999) || a.id - b.id);
    const index = ordered.findIndex(item => item.slug === slug);
    if (index > 0) previous = ordered[index - 1];
    if (index >= 0 && index < ordered.length - 1) next = ordered[index + 1];
  }

  return <main className="shell page"><TimelineDetailView event={event} previous={previous} next={next} /></main>;
}
