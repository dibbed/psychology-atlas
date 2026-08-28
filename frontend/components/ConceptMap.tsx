import Link from "next/link";
import type { DisorderDetail } from "@/lib/types";

export default function ConceptMap({ disorder }: { disorder: DisorderDetail }) {
  const symptoms = disorder.symptoms.slice(0, 6);
  const related = disorder.related.slice(0, 5);

  return (
    <div className="concept-map" aria-label="نقشه مفهومی اختلال">
      <div className="concept-column">
        <div className="meta">نشانه‌ها</div>
        {symptoms.map(item => (
          <div className="concept-node symptom-node" key={item.slug}>
            {item.name_fa || item.name_en}
          </div>
        ))}
      </div>

      <div className="concept-center">
        <div className="concept-node core-node">
          <strong>{disorder.name_fa || disorder.name_en}</strong>
          <span>{disorder.category}</span>
        </div>
      </div>

      <div className="concept-column">
        <div className="meta">مرتبط و افتراقی</div>
        {related.map(item => (
          <Link className="concept-node related-node" href={`/disorders/${item.slug}`} key={`${item.slug}-${item.relationship_type}`}>
            {item.name_fa || item.name_en}
          </Link>
        ))}
        {!related.length && <div className="muted small">هنوز رابطه‌ای برای این موضوع ثبت نشده است.</div>}
      </div>
    </div>
  );
}
