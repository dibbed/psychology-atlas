"use client";

import Link from "next/link";
import { useEffect, useMemo, useState } from "react";
import { api } from "@/lib/api";
import { normalizePersianSearch } from "@/lib/text";
import type { Concept } from "@/lib/types";
import ConceptCard, { conceptKindLabel } from "./ConceptCard";

const kinds = ["cognitive", "clinical", "behavioral", "emotional", "interpersonal", "treatment", "assessment", "general"];
const domainLabels: Record<string, string> = {
  psychopathology: "آسیب‌شناسی روانی",
  cognitive_psychology: "روان‌شناسی شناختی",
  cbt: "CBT",
  behavioral_science: "علوم رفتاری",
  emotion: "هیجان",
  interpersonal: "بین‌فردی",
  assessment: "ارزیابی",
  general: "روان‌شناسی عمومی",
};

export default function ConceptExplorer() {
  const [concepts, setConcepts] = useState<Concept[]>([]);
  const [query, setQuery] = useState("");
  const [kind, setKind] = useState("");
  const [domain, setDomain] = useState("");
  const [subtype, setSubtype] = useState("");
  const [sort, setSort] = useState<"connections" | "name">("connections");
  const [view, setView] = useState<"grid" | "compact">("grid");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  useEffect(() => {
    const controller = new AbortController();
    api<{ results: Concept[] }>("/concepts/?page_size=100", { signal: controller.signal })
      .then(data => setConcepts(data.results))
      .catch((e: any) => {
        if (e?.name !== "AbortError") setError(e.message || "دریافت مفاهیم انجام نشد.");
      })
      .finally(() => setLoading(false));
    return () => controller.abort();
  }, []);

  const domains = useMemo(() => {
    const counts = new Map<string, number>();
    concepts.forEach(item => counts.set(item.domain, (counts.get(item.domain) || 0) + 1));
    return [...counts.entries()].sort((a, b) => b[1] - a[1]);
  }, [concepts]);

  const filtered = useMemo(() => {
    const q = normalizePersianSearch(query.trim());
    const rows = concepts.filter(item => {
      const matchesKind = !kind || item.kind === kind;
      const matchesDomain = !domain || item.domain === domain;
      const matchesSubtype = !subtype || item.subtype === subtype;
      const aliases = item.aliases?.map(alias => alias.text).join(" ") || "";
      const haystack = normalizePersianSearch(`${item.name_fa} ${item.name_en} ${item.simple_definition} ${aliases}`);
      return matchesKind && matchesDomain && matchesSubtype && (!q || haystack.includes(q));
    });
    return rows.sort((a, b) => {
      if (sort === "connections") {
        return (b.relationship_count ?? 0) - (a.relationship_count ?? 0) || (b.disorder_count ?? 0) - (a.disorder_count ?? 0);
      }
      return (a.name_fa || a.name_en).localeCompare(b.name_fa || b.name_en, "fa");
    });
  }, [concepts, query, kind, domain, subtype, sort]);

  function resetFilters() {
    setQuery("");
    setKind("");
    setDomain("");
    setSubtype("");
  }

  if (loading) return <p className="muted">در حال دریافت مفاهیم...</p>;
  if (error) return <div className="card error-state"><p>{error}</p></div>;

  return (
    <div className="stack concept-explorer-v2">
      <section className="concept-domain-rail card">
        <button className={!domain ? "active" : ""} onClick={() => setDomain("")}>
          <strong>{concepts.length.toLocaleString("fa-IR")}</strong><span>همه حوزه‌ها</span>
        </button>
        {domains.map(([value, count]) => (
          <button className={domain === value ? "active" : ""} onClick={() => setDomain(value)} key={value}>
            <strong>{count.toLocaleString("fa-IR")}</strong><span>{domainLabels[value] || value}</span>
          </button>
        ))}
      </section>

      <div className="atlas-filters concept-filters-v2">
        <input
          className="search"
          value={query}
          onChange={event => setQuery(event.target.value)}
          placeholder="نام، alias، اصطلاح یا تعریف..."
          aria-label="جست‌وجوی مفاهیم"
        />
        <select className="filter-select" value={kind} onChange={event => setKind(event.target.value)} aria-label="نوع مفهوم">
          <option value="">همه انواع</option>
          {kinds.map(value => <option value={value} key={value}>{conceptKindLabel(value)}</option>)}
        </select>
        <select className="filter-select" value={subtype} onChange={event => setSubtype(event.target.value)} aria-label="زیرنوع مفهوم">
          <option value="">همه زیرنوع‌ها</option>
          <option value="cognitive_distortion">تحریف شناختی</option>
          <option value="general">مفهوم عمومی</option>
        </select>
      </div>

      <div className="concept-explorer-toolbar">
        <div className="category-chips compact-chips">
          <button className={!kind ? "chip active" : "chip"} onClick={() => setKind("")}>همه</button>
          {kinds.map(value => (
            <button className={`chip ${kind === value ? "active" : ""}`} onClick={() => setKind(value)} key={value}>
              {conceptKindLabel(value)}
            </button>
          ))}
        </div>
        <div className="actions compact-actions">
          <select className="filter-select" value={sort} onChange={event => setSort(event.target.value as typeof sort)} aria-label="مرتب‌سازی مفاهیم">
            <option value="connections">بیشترین اتصال</option>
            <option value="name">نام</option>
          </select>
          <button className={`button ${view === "grid" ? "primary" : ""}`} onClick={() => setView("grid")}>کارت</button>
          <button className={`button ${view === "compact" ? "primary" : ""}`} onClick={() => setView("compact")}>فشرده</button>
        </div>
      </div>

      <div className="concept-results-summary">
        <div>
          <strong>{filtered.length.toLocaleString("fa-IR")}</strong>
          <span>مفهوم مطابق فیلتر فعلی</span>
        </div>
        <div className="actions">
          {subtype === "cognitive_distortion" && <Link className="button primary" href="/cognitive-distortions">رفتن به Distortions Explorer</Link>}
          {(query || kind || domain || subtype) && <button className="button ghost" onClick={resetFilters}>پاک‌کردن فیلترها</button>}
        </div>
      </div>

      {filtered.length ? (
        view === "grid" ? (
          <div className="grid">{filtered.map(item => <ConceptCard concept={item} key={item.slug} />)}</div>
        ) : (
          <div className="concept-compact-list">
            {filtered.map(item => (
              <Link className="card concept-compact-row" href={`/concepts/${item.slug}`} key={item.slug}>
                <div>
                  <div className="meta">{domainLabels[item.domain] || item.domain} · {conceptKindLabel(item.kind)}</div>
                  <strong>{item.name_fa || item.name_en}</strong>
                  <small>{item.name_en}</small>
                </div>
                <p>{item.simple_definition}</p>
                <div className="concept-compact-metrics">
                  <span>{(item.relationship_count ?? 0).toLocaleString("fa-IR")} رابطه</span>
                  <span>{(item.disorder_count ?? 0).toLocaleString("fa-IR")} اختلال</span>
                  <span>{(item.flashcard_count ?? 0).toLocaleString("fa-IR")} کارت</span>
                </div>
              </Link>
            ))}
          </div>
        )
      ) : (
        <div className="card"><h3>مفهومی پیدا نشد</h3><p>عبارت جست‌وجو یا فیلترها را تغییر بده.</p></div>
      )}
    </div>
  );
}
