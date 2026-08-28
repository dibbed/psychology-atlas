import Link from "next/link";
import type { DisorderDetail } from "@/lib/types";

export default function ConceptMap({ disorder }: { disorder: DisorderDetail }) {
  const symptoms = disorder.symptoms.slice(0, 6);
  const concepts = disorder.concepts.slice(0, 8);
  const related = disorder.related.slice(0, 5);

  return (
    <div className="stack">
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
          <div className="disorder-concept-links">
            {concepts.map(item => (
              <Link className="concept-node knowledge-node" href={`/concepts/${item.slug}`} key={`${item.slug}-${item.role}`}>
                <small>{item.role}</small>{item.name_fa || item.name_en}
              </Link>
            ))}
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
      <div className="actions"><Link className="button" href="/map">باز کردن Knowledge Graph کامل ←</Link></div>
    </div>
  );
}
