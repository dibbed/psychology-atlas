import CaseRunner from "@/components/CaseRunner";
import { publicFetch } from "@/lib/api";
import type { ClinicalCase } from "@/lib/types";

function difficultyLabel(value: string) {
  if (value === "introductory") return "مقدماتی";
  if (value === "intermediate") return "متوسط";
  if (value === "advanced") return "پیشرفته";
  return value;
}

export default async function CasePage({ params }: { params: Promise<{ slug: string }> }) {
  const { slug } = await params;
  const item = await publicFetch<ClinicalCase>(`/cases/${slug}/`);
  return (
    <main className="shell page">
      <div className="detail-header">
        <div className="meta">کیس بالینی {difficultyLabel(item.difficulty)}</div>
        <h1 style={{ fontSize: 48, margin: "8px 0" }}>{item.title}</h1>
        <p className="section-copy">{item.educational_objective}</p>
      </div>
      <CaseRunner item={item} />
    </main>
  );
}
