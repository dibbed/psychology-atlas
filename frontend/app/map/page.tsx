import KnowledgeMap from "@/components/KnowledgeMap";
import { publicFetch } from "@/lib/api";

type MapPageProps = {
  searchParams: Promise<{ node?: string }>;
};

export default async function MapPage({ searchParams }: MapPageProps) {
  const [{ node }, data] = await Promise.all([
    searchParams,
    publicFetch<any>("/concept-map/"),
  ]);

  return (
    <main className="shell page stack">
      <div>
        <div className="meta">Knowledge Graph · v0.3</div>
        <h1 className="section-title" style={{ fontSize: 44 }}>از یک مفهوم وارد شبکه روان‌شناسی شو.</h1>
        <p className="section-copy">Nodeها و Edgeها از رابطه‌های واقعی دیتابیس می‌آیند. یک مفهوم، اختلال یا نشانه را انتخاب کن و رابطه‌های مستقیم آن را دنبال کن.</p>
      </div>
      <KnowledgeMap data={data} initialNodeId={node} />
    </main>
  );
}
