import Link from "next/link";
import type { Concept } from "@/lib/types";

const KIND_LABELS: Record<string, string> = {
  clinical: "بالینی",
  cognitive: "شناختی",
  behavioral: "رفتاری",
  emotional: "هیجانی",
  interpersonal: "بین‌فردی",
  assessment: "ارزیابی",
  treatment: "درمانی",
  general: "عمومی",
};

export function conceptKindLabel(kind: string) {
  return KIND_LABELS[kind] || kind;
}

export default function ConceptCard({ concept }: { concept: Concept }) {
  const metrics = [
    concept.relationship_count != null ? `${concept.relationship_count.toLocaleString("fa-IR")} رابطه` : null,
    concept.disorder_count != null ? `${concept.disorder_count.toLocaleString("fa-IR")} اختلال` : null,
    concept.flashcard_count != null ? `${concept.flashcard_count.toLocaleString("fa-IR")} کارت` : null,
  ].filter(Boolean);

  return (
    <Link className="card concept-card concept-card-v2" href={`/concepts/${concept.slug}`}>
      <div className="concept-card-head">
        <span className="meta">{conceptKindLabel(concept.kind)}</span>
        <span className="concept-arrow" aria-hidden="true">↖</span>
      </div>
      <div>
        <h3>{concept.name_fa || concept.name_en}</h3>
        <div className="latin-label">{concept.name_en}</div>
      </div>
      <p>{concept.simple_definition}</p>
      {metrics.length > 0 && (
        <div className="concept-metrics">
          {metrics.map(metric => <span key={metric}>{metric}</span>)}
        </div>
      )}
    </Link>
  );
}
