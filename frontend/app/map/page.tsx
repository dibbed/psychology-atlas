import KnowledgeMap from "@/components/KnowledgeMap";
import { publicFetch } from "@/lib/api";
import type { KnowledgeGraphData } from "@/lib/types";

type MapPageProps = {
  searchParams: Promise<{ node?: string }>;
};

export default async function MapPage({ searchParams }: MapPageProps) {
  const [{ node }, data] = await Promise.all([
    searchParams,
    publicFetch<KnowledgeGraphData>("/concept-map/"),
  ]);

  return (
    <main className="shell page stack graph-page">
      <header className="graph-page-head">
        <div>
          <div className="meta">Knowledge Graph · Explorer</div>
          <h1>رابطه‌ها را ببین، مسیر را دنبال کن.</h1>
          <p>هر گره و edge از داده ساختاریافته اطلس می‌آید. Degree فقط تعداد اتصال واقعی است و هیچ similarity score ساختگی در نقشه وجود ندارد.</p>
        </div>
        <div className="graph-page-note">
          <strong>{data.meta.node_count.toLocaleString("fa-IR")}</strong>
          <span>گره در سه لایه Concept، Disorder و Symptom</span>
        </div>
      </header>
      <KnowledgeMap data={data} initialNodeId={node} />
    </main>
  );
}
