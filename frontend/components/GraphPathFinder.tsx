"use client";

import Link from "next/link";
import { useEffect, useMemo, useRef, useState } from "react";
import { api } from "@/lib/api";
import type { GraphPathResult, KnowledgeGraphNode } from "@/lib/types";

const edgeLabels: Record<string, string> = {
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
  symptom_core: "نشانه محوری",
  symptom_common: "نشانه رایج",
  symptom_possible: "نشانه ممکن",
  symptom_contextual: "نشانه زمینه‌ای",
  concept_symptom_associated: "مفهوم ↔ نشانه",
  concept_symptom_manifestation: "بازنمایی در نشانه",
  concept_symptom_overlaps_with: "همپوشانی با نشانه",
  concept_symptom_contrasts: "افتراق از نشانه",
  dsm_nearby: "عنوان نزدیک DSM",
  therapy_disorder_guideline_recommended: "درمان ↔ اختلال · توصیه راهنما",
  therapy_disorder_context_dependent: "درمان ↔ اختلال · وابسته به زمینه",
  therapy_disorder_commonly_used: "درمان ↔ اختلال · کاربرد رایج",
  therapy_disorder_adjunctive: "درمان ↔ اختلال · کمکی",
  therapy_disorder_alternative: "درمان ↔ اختلال · جایگزین",
  therapy_disorder_not_first_line: "درمان ↔ اختلال · نه خط اول",
  therapy_disorder_research_context: "درمان ↔ اختلال · پژوهشی",
  therapy_concept_targets: "درمان → مفهوم · هدف",
  therapy_concept_uses: "درمان → مفهوم · استفاده",
  therapy_concept_addresses: "درمان → مفهوم · پرداختن",
  therapy_concept_teaches: "درمان → مفهوم · آموزش",
  therapy_concept_mechanism: "درمان → مفهوم · سازوکار",
  therapy_concept_applied_to: "درمان → مفهوم · کاربرد",
  therapy_technique_core: "درمان → تکنیک · محوری",
  therapy_technique_common: "درمان → تکنیک · رایج",
  therapy_technique_optional: "درمان → تکنیک · اختیاری",
  therapy_technique_adapted: "درمان → تکنیک · انطباق‌یافته",
  therapy_technique_component: "درمان → تکنیک · مؤلفه",
  technique_concept_targets: "تکنیک → مفهوم · هدف",
  technique_concept_addresses: "تکنیک → مفهوم · پرداختن",
  technique_concept_teaches: "تکنیک → مفهوم · آموزش",
  technique_concept_mechanism: "تکنیک → مفهوم · سازوکار",
  technique_concept_applied_to: "تکنیک → مفهوم · کاربرد",
};

export default function GraphPathFinder({ nodes, initialFrom }: { nodes: KnowledgeGraphNode[]; initialFrom?: string }) {
  const options = useMemo(() => [...nodes].sort((a, b) => a.label.localeCompare(b.label, "fa")), [nodes]);
  const [from, setFrom] = useState(initialFrom && nodes.some(node => node.id === initialFrom) ? initialFrom : nodes[0]?.id || "");
  const [to, setTo] = useState(nodes.find(node => node.id !== from)?.id || "");
  const [result, setResult] = useState<GraphPathResult | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const requestRef = useRef<AbortController | null>(null);

  useEffect(() => {
    if (initialFrom && nodes.some(node => node.id === initialFrom)) {
      setFrom(initialFrom);
      setTo(current => current === initialFrom ? nodes.find(node => node.id !== initialFrom)?.id || "" : current);
      setResult(null);
      setError("");
    }
  }, [initialFrom, nodes]);

  useEffect(() => () => requestRef.current?.abort(), []);

  async function findPath() {
    if (!from || !to || from === to) {
      setError("دو گره متفاوت برای شروع و پایان انتخاب کن.");
      return;
    }
    requestRef.current?.abort();
    const controller = new AbortController();
    requestRef.current = controller;
    setLoading(true);
    setError("");
    setResult(null);
    try {
      const data = await api<GraphPathResult>(
        `/concept-map/path/?from=${encodeURIComponent(from)}&to=${encodeURIComponent(to)}`,
        { signal: controller.signal },
      );
      if (!controller.signal.aborted) setResult(data);
    } catch (reason: any) {
      if (reason?.name !== "AbortError") setError(reason?.message || "محاسبه مسیر انجام نشد.");
    } finally {
      if (!controller.signal.aborted) setLoading(false);
    }
  }

  return (
    <section className="card graph-path-finder stack">
      <div>
        <div className="meta">Structured Path Finder</div>
        <h3>دو گره را انتخاب کن و کوتاه‌ترین مسیر واقعی را پیدا کن.</h3>
        <p className="muted">مسیر فقط از edgeهای ثبت‌شده در Atlas ساخته می‌شود؛ Therapy و Technique نیز از relationهای واقعی DB وارد مسیر می‌شوند. اتصال ساختاری «عنوان نزدیک DSM» به‌طور پیش‌فرض shortcut مسیر مفهومی نیست.</p>
      </div>
      <div className="graph-path-controls">
        <label>
          <span>شروع</span>
          <select className="filter-select" value={from} disabled={loading} onChange={event => { setFrom(event.target.value); setResult(null); setError(""); }}>
            {options.map(node => <option value={node.id} key={node.id}>{node.label} · {node.type}</option>)}
          </select>
        </label>
        <label>
          <span>پایان</span>
          <select className="filter-select" value={to} disabled={loading} onChange={event => { setTo(event.target.value); setResult(null); setError(""); }}>
            {options.map(node => <option value={node.id} key={node.id}>{node.label} · {node.type}</option>)}
          </select>
        </label>
        <button className="button primary" onClick={findPath} disabled={loading}>{loading ? "در حال محاسبه..." : "پیدا کردن مسیر"}</button>
      </div>
      {error && <div className="error-state"><p>{error}</p></div>}
      {result && !result.found && <div className="empty-relation">بین این دو گره در graph فعلی مسیر ساختاریافته‌ای پیدا نشد.</div>}
      {result?.found && (
        <div className="graph-path-result">
          <div className="graph-path-summary"><strong>{result.hops?.toLocaleString("fa-IR")}</strong><span>edge در کوتاه‌ترین مسیر</span></div>
          <div className="graph-path-chain">
            {result.nodes.map((node, index) => (
              <div className="graph-path-step" key={node.id}>
                <Link href={node.href}><span>{node.label}</span><small>{node.type}</small></Link>
                {index < result.edges.length && (
                  <div className="graph-path-edge">
                    {result.edges[index].traversal_direction === "reverse"
                      ? `حرکت معکوس روی رابطه: ${edgeLabels[result.edges[index].kind] || result.edges[index].kind}`
                      : edgeLabels[result.edges[index].kind] || result.edges[index].kind}
                  </div>
                )}
              </div>
            ))}
          </div>
        </div>
      )}
    </section>
  );
}
