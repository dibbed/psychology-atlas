"use client";

import Link from "next/link";
import { useEffect, useMemo, useRef, useState } from "react";
import { api } from "@/lib/api";
import type { ConceptNeighborhood, KnowledgeGraphEdge, KnowledgeGraphNode } from "@/lib/types";

const relationLabels: Record<string, string> = {
  related: "مرتبط",
  part_of: "جزئی از",
  subtype_of: "زیرنوع",
  prerequisite: "پیش‌نیاز",
  maintains: "حفظ‌کننده",
  influences: "اثرگذار",
  mechanism: "سازوکار",
  contrasts: "مقایسه/تفاوت",
  commonly_confused_with: "اغلب اشتباه می‌شود با",
  associated_with: "همراه/مرتبط با",
  applied_in: "کاربرد",
  core: "مفهوم محوری",
  associated: "مفهوم مرتبط",
  maintaining: "عامل حفظ‌کننده",
  assessment: "ارزیابی",
  treatment: "درمان/مداخله",
  differential: "افتراقی",
  concept_symptom_associated: "مفهوم ↔ نشانه",
  concept_symptom_manifestation: "بازنمایی در نشانه",
  concept_symptom_overlaps_with: "همپوشانی با نشانه",
  concept_symptom_contrasts: "افتراق از نشانه",
  therapy_concept_targets: "درمان → مفهوم · هدف",
  therapy_concept_uses: "درمان → مفهوم · استفاده",
  therapy_concept_addresses: "درمان → مفهوم · پرداختن",
  therapy_concept_teaches: "درمان → مفهوم · آموزش",
  therapy_concept_mechanism: "درمان → مفهوم · سازوکار",
  therapy_concept_applied_to: "درمان → مفهوم · کاربرد",
  technique_concept_targets: "تکنیک → مفهوم · هدف",
  technique_concept_addresses: "تکنیک → مفهوم · پرداختن",
  technique_concept_teaches: "تکنیک → مفهوم · آموزش",
  technique_concept_mechanism: "تکنیک → مفهوم · سازوکار",
  technique_concept_applied_to: "تکنیک → مفهوم · کاربرد",
};

function nodeTypeLabel(type: KnowledgeGraphNode["type"]) {
  if (type === "concept") return "مفهوم";
  if (type === "disorder") return "اختلال";
  if (type === "symptom") return "نشانه";
  if (type === "therapy") return "درمان";
  return "تکنیک";
}

export default function ConceptNeighborhood({ slug }: { slug: string }) {
  const [depth, setDepth] = useState<1 | 2>(1);
  const [data, setData] = useState<ConceptNeighborhood | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const requestIdRef = useRef(0);

  useEffect(() => {
    const controller = new AbortController();
    const requestId = ++requestIdRef.current;
    setLoading(true);
    setData(null);
    setError("");
    api<ConceptNeighborhood>(`/concepts/${slug}/neighborhood/?depth=${depth}`, { signal: controller.signal })
      .then(value => {
        if (requestId === requestIdRef.current) setData(value);
      })
      .catch((reason: any) => {
        if (requestId !== requestIdRef.current || reason?.name === "AbortError") return;
        setError(reason?.message || "همسایگی مفهوم دریافت نشد.");
      })
      .finally(() => {
        if (requestId === requestIdRef.current) setLoading(false);
      });
    return () => controller.abort();
  }, [slug, depth]);

  const rows = useMemo(() => {
    if (!data) return [];
    const byId = new Map(data.nodes.map(node => [node.id, node]));
    const center = data.center;
    return data.edges.map((edge, index) => {
      const neighborId = edge.source === center ? edge.target : edge.target === center ? edge.source : null;
      return {
        edge,
        index,
        direct: Boolean(neighborId),
        node: neighborId ? byId.get(neighborId) : undefined,
      };
    });
  }, [data]);

  if (loading) return <div className="card"><p className="muted">در حال ساخت همسایگی ساختاریافته...</p></div>;
  if (error) return <div className="card error-state"><p>{error}</p></div>;
  if (!data) return null;

  const centerNode = data.nodes.find(node => node.id === data.center);
  const directRows = rows.filter(row => row.direct && row.node);
  const secondLevel = data.nodes.filter(node => node.id !== data.center && node.distance === 2);

  return (
    <div className="stack concept-neighborhood">
      <div className="concept-neighborhood-head">
        <div>
          <div className="meta">Neighborhood Explorer</div>
          <h2>همسایگی {centerNode?.label || slug}</h2>
          <p className="section-copy">این نما فقط edgeهای موجود در دیتابیس را دنبال می‌کند؛ هیچ رابطه حدسی یا similarity score تولید نمی‌شود.</p>
        </div>
        <div className="actions">
          <button className={`button ${depth === 1 ? "primary" : ""}`} onClick={() => setDepth(1)}>عمق ۱</button>
          <button className={`button ${depth === 2 ? "primary" : ""}`} onClick={() => setDepth(2)}>عمق ۲</button>
          <Link className="button" href={`/map?node=concept:${slug}`}>بازکردن در Graph</Link>
        </div>
      </div>

      <div className="graph-overview compact-overview">
        <div><strong>{(data.nodes.length - 1).toLocaleString("fa-IR")}</strong><span>گره همسایه</span></div>
        <div><strong>{data.edges.length.toLocaleString("fa-IR")}</strong><span>edge در شعاع فعلی</span></div>
        <div><strong>{directRows.length.toLocaleString("fa-IR")}</strong><span>اتصال مستقیم</span></div>
        <div><strong>{secondLevel.length.toLocaleString("fa-IR")}</strong><span>گره سطح دوم</span></div>
      </div>

      <div className="grid-2 neighborhood-direct-grid">
        {directRows.map(({ edge, node, index }) => node && (
          <Link className={`card neighborhood-node ${node.type}`} href={node.href} key={`${node.id}-${edge.kind}-${index}`}>
            <div className="meta">{nodeTypeLabel(node.type)} · {relationLabels[edge.kind] || edge.kind}</div>
            <h3>{node.label}</h3>
            <div className="latin-title">{node.name_en}</div>
            <p>{edge.explanation || node.summary}</p>
            {!!edge.sources?.length && <small className="muted">منبع: {edge.sources.map(source => source.organization || source.title).join(" · ")}</small>}
          </Link>
        ))}
      </div>

      {depth === 2 && secondLevel.length > 0 && (
        <section className="card second-level-neighborhood">
          <div className="meta">سطح دوم</div>
          <h3>گره‌هایی که با یک واسطه قابل دسترسی‌اند</h3>
          <div className="category-chips">
            {secondLevel.map(node => <Link className="chip" href={node.href} key={node.id}>{node.label}</Link>)}
          </div>
        </section>
      )}
    </div>
  );
}
