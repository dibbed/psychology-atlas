import DisorderDetailClient from "@/components/DisorderDetailClient";
import { publicFetch } from "@/lib/api";
import type { DisorderDetail } from "@/lib/types";

export default async function DisorderPage({ params }: { params: Promise<{ slug: string }> }) {
  const { slug } = await params;
  const disorder = await publicFetch<DisorderDetail>(`/disorders/${slug}/`);

  return (
    <main className="shell page">
      <DisorderDetailClient disorder={disorder} />
    </main>
  );
}
