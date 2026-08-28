"use client";

import { useEffect, useMemo, useState } from "react";
import { api } from "@/lib/api";
import type { Concept } from "@/lib/types";
import ConceptCard, { conceptKindLabel } from "./ConceptCard";

const kinds = ["cognitive", "clinical", "behavioral", "emotional", "interpersonal", "treatment", "assessment", "general"];

export default function ConceptExplorer() {
  const [concepts, setConcepts] = useState<Concept[]>([]);
  const [query, setQuery] = useState("");
  const [kind, setKind] = useState("");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  useEffect(() => {
    api<{ results: Concept[] }>("/concepts/?page_size=100")
      .then(data => setConcepts(data.results))
      .catch((e: any) => setError(e.message || "دریافت مفاهیم انجام نشد."))
      .finally(() => setLoading(false));
  }, []);

  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase();
    return concepts.filter(item => {
      const matchesKind = !kind || item.kind === kind;
      const haystack = `${item.name_fa} ${item.name_en} ${item.simple_definition}`.toLowerCase();
      return matchesKind && (!q || haystack.includes(q));
    });
  }, [concepts, query, kind]);

  if (loading) return <p className="muted">در حال دریافت مفاهیم...</p>;
  if (error) return <div className="card error-state"><p>{error}</p></div>;

  return (
    <div className="stack">
      <div className="atlas-filters">
        <input
          className="search"
          value={query}
          onChange={event => setQuery(event.target.value)}
          placeholder="جست‌وجوی مفهوم، اصطلاح یا تعریف..."
          aria-label="جست‌وجوی مفاهیم"
        />
        <select className="filter-select" value={kind} onChange={event => setKind(event.target.value)} aria-label="نوع مفهوم">
          <option value="">همه انواع</option>
          {kinds.map(value => <option value={value} key={value}>{conceptKindLabel(value)}</option>)}
        </select>
      </div>
      <div className="category-chips">
        <button className={`chip ${kind === "" ? "active" : ""}`} onClick={() => setKind("")}>همه</button>
        {kinds.map(value => (
          <button className={`chip ${kind === value ? "active" : ""}`} onClick={() => setKind(value)} key={value}>
            {conceptKindLabel(value)}
          </button>
        ))}
      </div>
      <div className="results-count">{filtered.length.toLocaleString("fa-IR")} مفهوم نمایش داده می‌شود.</div>
      {filtered.length ? (
        <div className="grid">{filtered.map(item => <ConceptCard concept={item} key={item.slug} />)}</div>
      ) : (
        <div className="card"><h3>مفهومی پیدا نشد</h3><p>عبارت جست‌وجو یا نوع مفهوم را تغییر بده.</p></div>
      )}
    </div>
  );
}
