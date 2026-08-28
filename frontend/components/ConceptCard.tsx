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
  return (
    <Link className="card concept-card" href={`/concepts/${concept.slug}`}>
      <div className="meta">{conceptKindLabel(concept.kind)}</div>
      <h3>{concept.name_fa || concept.name_en}</h3>
      <div className="latin-label">{concept.name_en}</div>
      <p>{concept.simple_definition}</p>
    </Link>
  );
}
