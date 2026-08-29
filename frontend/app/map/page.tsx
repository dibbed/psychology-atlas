import Link from "next/link";
import DSMGraphLoader from "@/components/DSMGraphLoader";
import KnowledgeMapLoader from "@/components/KnowledgeMapLoader";
import { publicFetch } from "@/lib/api";
import type { AtlasOverview, DSMOverview } from "@/lib/types";

type MapPageProps = {
  searchParams: Promise<{ node?: string; scope?: string }>;
};

export default async function MapPage({ searchParams }: MapPageProps) {
  const params = await searchParams;
  const dsmScope = params.scope === "dsm";

  const atlasOverview = dsmScope ? null : await publicFetch<AtlasOverview>("/atlas-overview/");
  const dsmOverview = dsmScope ? await publicFetch<DSMOverview>("/dsm/overview/") : null;
  const nodeCount = dsmScope ? dsmOverview?.counts.records ?? 0 : atlasOverview?.graph.nodes ?? 0;

  return (
    <main className="shell page stack graph-page">
      <header className="graph-page-head">
        <div>
          <div className="meta">Knowledge Graph · Explorer</div>
          <h1>{dsmScope ? "ساختار DSM MASTER را مثل یک شبکه دنبال کن." : "رابطه‌ها را ببین، مسیر را دنبال کن."}</h1>
          <p>
            {dsmScope
              ? "این نما از parent/child، عنوان‌های نزدیک و افتراق‌هایی که واقعاً به رکورد MASTER دیگری resolve شده‌اند ساخته می‌شود. عبارت‌های افتراقی عمومی به زور به node تبدیل نشده‌اند."
              : "هر گره و edge از داده ساختاریافته اطلس می‌آید. Degree فقط تعداد اتصال واقعی است و هیچ similarity score ساختگی در نقشه وجود ندارد."}
          </p>
          <div className="actions graph-scope-switch">
            <Link className={`button ${!dsmScope ? "primary" : ""}`} href="/map">Atlas Graph</Link>
            <Link className={`button ${dsmScope ? "primary" : ""}`} href="/map?scope=dsm">DSM MASTER Graph</Link>
          </div>
        </div>
        <div className="graph-page-note">
          <strong>{nodeCount.toLocaleString("fa-IR")}</strong>
          <span>{dsmScope ? "گره MASTER با ساختار و روابط منبع" : "گره در سه لایه Concept، Disorder و Symptom"}</span>
        </div>
      </header>
      {dsmScope ? (
        <DSMGraphLoader initialNodeId={params.node} />
      ) : (
        <KnowledgeMapLoader initialNodeId={params.node} />
      )}
    </main>
  );
}
