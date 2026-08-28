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
          <div className="meta">Concepts Atlas</div>
          <h1>مفهوم را مستقل یاد بگیر، بعد اتصالش را ببین.</h1>
          <p>هر Concept یک واحد یادگیری مستقل است، اما ارزش اصلی اطلس وقتی دیده می‌شود که رابطه آن با اختلال‌ها، مفاهیم دیگر و فلش‌کارت‌ها روشن باشد.</p>
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
