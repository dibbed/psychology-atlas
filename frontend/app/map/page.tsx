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
          <div className="eyebrow">نقشهٔ دانش</div>
          <h1>{dsmScope ? "ساختار مرجع DSM را دنبال کن." : "رابطه‌ها را ببین، مسیر را دنبال کن."}</h1>
          <p>
            {dsmScope
              ? "این نما فقط پیوندهای ثبت‌شده میان رکوردهای مرجع را نشان می‌دهد. یک گره را انتخاب کن تا رابطه‌هایش را ببینی."
              : "یک گره را انتخاب کن، رابطه‌های مستقیمش را ببین و مسیر کاوشت را ادامه بده. پیوندها از داده‌های ثبت‌شدهٔ اطلس می‌آیند."}
          </p>
          <div className="actions graph-scope-switch">
            <Link className={`button ${!dsmScope ? "primary" : ""}`} href="/map">نقشهٔ اطلس</Link>
            <Link className={`button ${dsmScope ? "primary" : ""}`} href="/map?scope=dsm">نقشهٔ مرجع DSM</Link>
          </div>
        </div>
        <div className="graph-page-note">
          <strong>{nodeCount.toLocaleString("fa-IR")}</strong>
          <span>{dsmScope ? "رکورد مرجع با پیوندهای ثبت‌شده" : "گره در دامنه‌های بالینی، مفهومی، درمانی و تاریخی"}</span>
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
