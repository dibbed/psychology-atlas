import ConceptExplorer from "@/components/ConceptExplorer";
import { publicFetch } from "@/lib/api";
import type { AtlasOverview } from "@/lib/types";

export default async function ConceptsPage() {
  let overview: AtlasOverview | null = null;
  try {
    overview = await publicFetch<AtlasOverview>("/atlas-overview/");
  } catch {
    overview = null;
  }

  return (
    <main className="shell page stack concepts-page">
      <header className="concepts-page-head">
        <div>
          <div className="eyebrow">اطلس مفاهیم</div>
          <h1>از تعریف تا رابطهٔ مفهومی</h1>
          <p>هر مفهوم را با تعریف و مثال بشناس؛ سپس ارتباط آن را با مفاهیم دیگر، اختلالات و ابزارهای مطالعه دنبال کن.</p>
        </div>
        {overview && (
          <div className="concepts-summary">
            <div><strong>{overview.counts.concepts.toLocaleString("fa-IR")}</strong><span>مفهوم فعال</span></div>
            <div><strong>{overview.counts.flashcards.toLocaleString("fa-IR")}</strong><span>فلش‌کارت</span></div>
            <div><strong>{overview.graph.edges.toLocaleString("fa-IR")}</strong><span>رابطه شبکه</span></div>
          </div>
        )}
      </header>
      {overview && (
        <div className="concept-kind-rail">
          {overview.concept_kinds.map(row => (
            <div key={row.kind}><strong>{row.count.toLocaleString("fa-IR")}</strong><span>{row.label}</span></div>
          ))}
        </div>
      )}
      <ConceptExplorer />
    </main>
  );
}
