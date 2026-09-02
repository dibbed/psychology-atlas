"use client";

import Link from "next/link";
import { useMemo, useState } from "react";
import { normalizePersianSearch } from "@/lib/text";
import type { Technique, Therapy, TherapyTaxonomy } from "@/lib/types";

type ExplorerMode = "therapies" | "techniques";
type TherapySort = "connections" | "name";

const classificationKindLabels: Record<string, string> = {
  focus: "تمرکز",
  method: "روش",
  delivery: "شیوه ارائه",
  population: "جمعیت",
  other: "طبقه‌بندی",
};

function fa(value: number) {
  return value.toLocaleString("fa-IR");
}

function searchableTherapy(item: Therapy) {
  return normalizePersianSearch([
    item.name_fa,
    item.name_en,
    item.slug,
    item.summary,
    item.family?.name_fa,
    item.family?.name_en,
    ...(item.aliases || []).map(alias => alias.text),
    ...(item.classifications || []).flatMap(row => [row.name_fa, row.name_en]),
  ].filter(Boolean).join(" "));
}

function searchableTechnique(item: Technique) {
  return normalizePersianSearch([
    item.name_fa,
    item.name_en,
    item.slug,
    item.summary,
    ...(item.aliases || []).map(alias => alias.text),
  ].filter(Boolean).join(" "));
}

export default function TherapyExplorer({
  therapies,
  techniques,
  taxonomy,
}: {
  therapies: Therapy[];
  techniques: Technique[];
  taxonomy: TherapyTaxonomy;
}) {
  const [mode, setMode] = useState<ExplorerMode>("therapies");
  const [query, setQuery] = useState("");
  const [family, setFamily] = useState("");
  const [classification, setClassification] = useState("");
  const [sort, setSort] = useState<TherapySort>("connections");
  const [view, setView] = useState<"grid" | "compact">("grid");

  const familyCounts = useMemo(() => {
    const map = new Map<string, number>();
    therapies.forEach(item => map.set(item.family.slug, (map.get(item.family.slug) || 0) + 1));
    return map;
  }, [therapies]);

  const filteredTherapies = useMemo(() => {
    const q = normalizePersianSearch(query.trim());
    const rows = therapies.filter(item => {
      const matchesFamily = !family || item.family.slug === family;
      const matchesClassification = !classification || item.classifications.some(row => row.slug === classification);
      const matchesQuery = !q || searchableTherapy(item).includes(q);
      return matchesFamily && matchesClassification && matchesQuery;
    });

    return rows.sort((a, b) => {
      if (sort === "connections") {
        const scoreA = a.technique_count + a.disorder_count + a.concept_count;
        const scoreB = b.technique_count + b.disorder_count + b.concept_count;
        return scoreB - scoreA || (a.name_fa || a.name_en).localeCompare(b.name_fa || b.name_en, "fa");
      }
      return (a.name_fa || a.name_en).localeCompare(b.name_fa || b.name_en, "fa");
    });
  }, [therapies, query, family, classification, sort]);

  const filteredTechniques = useMemo(() => {
    const q = normalizePersianSearch(query.trim());
    return techniques
      .filter(item => !q || searchableTechnique(item).includes(q))
      .sort((a, b) => {
        if (sort === "connections") {
          return (b.therapy_count + b.concept_count) - (a.therapy_count + a.concept_count)
            || (a.name_fa || a.name_en).localeCompare(b.name_fa || b.name_en, "fa");
        }
        return (a.name_fa || a.name_en).localeCompare(b.name_fa || b.name_en, "fa");
      });
  }, [techniques, query, sort]);

  function reset() {
    setQuery("");
    setFamily("");
    setClassification("");
  }

  const activeCount = mode === "therapies" ? filteredTherapies.length : filteredTechniques.length;

  return (
    <div className="stack therapy-explorer">
      <div className="therapy-mode-switch" role="tablist" aria-label="نوع محتوای اطلس درمان">
        <button className={mode === "therapies" ? "active" : ""} onClick={() => setMode("therapies")} role="tab" aria-selected={mode === "therapies"}>
          <span>رویکردهای درمانی</span><strong>{fa(therapies.length)}</strong>
        </button>
        <button className={mode === "techniques" ? "active" : ""} onClick={() => { setMode("techniques"); setFamily(""); setClassification(""); }} role="tab" aria-selected={mode === "techniques"}>
          <span>تکنیک‌ها</span><strong>{fa(techniques.length)}</strong>
        </button>
      </div>

      {mode === "therapies" && (
        <section className="therapy-family-rail card" aria-label="خانواده‌های درمانی">
          <button className={!family ? "active" : ""} onClick={() => setFamily("")}>
            <strong>{fa(therapies.length)}</strong><span>همه خانواده‌ها</span>
          </button>
          {taxonomy.families.map(item => (
            <button className={family === item.slug ? "active" : ""} onClick={() => setFamily(item.slug)} key={item.slug}>
              <strong>{fa(familyCounts.get(item.slug) || 0)}</strong>
              <span>{item.name_fa || item.name_en}</span>
              <small>{item.name_en}</small>
            </button>
          ))}
        </section>
      )}

      <div className="atlas-filters therapy-filters">
        <input
          className="search"
          value={query}
          onChange={event => setQuery(event.target.value)}
          placeholder={mode === "therapies" ? "نام، مخفف، خانواده یا توضیح درمان..." : "نام، مخفف یا توضیح تکنیک..."}
          aria-label={mode === "therapies" ? "جست‌وجوی درمان‌ها" : "جست‌وجوی تکنیک‌ها"}
        />
        <select className="filter-select" value={sort} onChange={event => setSort(event.target.value as TherapySort)} aria-label="مرتب‌سازی">
          <option value="connections">بیشترین اتصال</option>
          <option value="name">نام</option>
        </select>
      </div>

      {mode === "therapies" && taxonomy.classifications.length > 0 && (
        <div className="therapy-classification-strip">
          <button className={!classification ? "chip active" : "chip"} onClick={() => setClassification("")}>همه طبقه‌بندی‌ها</button>
          {taxonomy.classifications.map(item => (
            <button className={`chip ${classification === item.slug ? "active" : ""}`} onClick={() => setClassification(item.slug)} key={item.slug}>
              {item.name_fa || item.name_en}
            </button>
          ))}
        </div>
      )}

      <div className="therapy-results-bar">
        <div>
          <strong>{fa(activeCount)}</strong>
          <span>{mode === "therapies" ? "درمان مطابق فیلتر فعلی" : "تکنیک مطابق جست‌وجو"}</span>
        </div>
        <div className="actions compact-actions">
          {(query || family || classification) && <button className="button ghost" onClick={reset}>پاک‌کردن فیلترها</button>}
          <button className={`button ${view === "grid" ? "primary" : ""}`} onClick={() => setView("grid")}>کارت</button>
          <button className={`button ${view === "compact" ? "primary" : ""}`} onClick={() => setView("compact")}>فشرده</button>
        </div>
      </div>

      {mode === "therapies" ? (
        filteredTherapies.length ? (
          view === "grid" ? (
            <div className="therapy-card-grid">
              {filteredTherapies.map(item => (
                <Link href={`/therapies/${item.slug}`} className="card therapy-card" key={item.slug}>
                  <div className="therapy-card-topline">
                    <span>{item.family.name_fa || item.family.name_en}</span>
                    <small>{item.review_status === "source_checked" ? "منبع بررسی‌شده" : item.review_status}</small>
                  </div>
                  <div>
                    <h2>{item.name_fa || item.name_en}</h2>
                    <div className="latin-title">{item.name_en}</div>
                  </div>
                  <p>{item.summary}</p>
                  {!!item.aliases.length && <div className="therapy-aliases">{item.aliases.map(alias => <span key={`${alias.language}-${alias.text}`}>{alias.text}</span>)}</div>}
                  {!!item.classifications.length && (
                    <div className="therapy-classifications">
                      {item.classifications.map(row => (
                        <span key={row.slug} title={classificationKindLabels[row.kind] || row.kind}>{row.name_fa || row.name_en}</span>
                      ))}
                    </div>
                  )}
                  <div className="therapy-card-metrics">
                    <div><strong>{fa(item.technique_count)}</strong><span>تکنیک</span></div>
                    <div><strong>{fa(item.disorder_count)}</strong><span>اختلال</span></div>
                    <div><strong>{fa(item.concept_count)}</strong><span>مفهوم</span></div>
                  </div>
                  <span className="therapy-card-cta">باز کردن پروفایل علمی ←</span>
                </Link>
              ))}
            </div>
          ) : (
            <div className="therapy-compact-list">
              {filteredTherapies.map(item => (
                <Link href={`/therapies/${item.slug}`} className="card therapy-compact-row" key={item.slug}>
                  <div>
                    <div className="meta">{item.family.name_fa || item.family.name_en}</div>
                    <strong>{item.name_fa || item.name_en}</strong>
                    <small>{item.name_en}</small>
                  </div>
                  <p>{item.summary}</p>
                  <div className="therapy-compact-metrics">
                    <span>{fa(item.technique_count)} تکنیک</span>
                    <span>{fa(item.disorder_count)} اختلال</span>
                    <span>{fa(item.concept_count)} مفهوم</span>
                  </div>
                </Link>
              ))}
            </div>
          )
        ) : <EmptyState label="درمانی" />
      ) : (
        filteredTechniques.length ? (
          <div className={view === "grid" ? "therapy-card-grid technique-card-grid" : "therapy-compact-list"}>
            {filteredTechniques.map(item => (
              <Link href={`/techniques/${item.slug}`} className={view === "grid" ? "card technique-card" : "card therapy-compact-row technique-compact-row"} key={item.slug}>
                {view === "grid" ? (
                  <>
                    <div className="therapy-card-topline"><span>Technique</span><small>{item.review_status === "source_checked" ? "منبع بررسی‌شده" : item.review_status}</small></div>
                    <div><h2>{item.name_fa || item.name_en}</h2><div className="latin-title">{item.name_en}</div></div>
                    <p>{item.summary}</p>
                    {!!item.aliases.length && <div className="therapy-aliases">{item.aliases.map(alias => <span key={`${alias.language}-${alias.text}`}>{alias.text}</span>)}</div>}
                    <div className="therapy-card-metrics two-col">
                      <div><strong>{fa(item.therapy_count)}</strong><span>درمان</span></div>
                      <div><strong>{fa(item.concept_count)}</strong><span>مفهوم</span></div>
                    </div>
                    <span className="therapy-card-cta">جزئیات تکنیک ←</span>
                  </>
                ) : (
                  <>
                    <div><div className="meta">Technique</div><strong>{item.name_fa || item.name_en}</strong><small>{item.name_en}</small></div>
                    <p>{item.summary}</p>
                    <div className="therapy-compact-metrics"><span>{fa(item.therapy_count)} درمان</span><span>{fa(item.concept_count)} مفهوم</span></div>
                  </>
                )}
              </Link>
            ))}
          </div>
        ) : <EmptyState label="تکنیکی" />
      )}

      <aside className="therapy-evidence-note card">
        <div className="meta">قید علمی مهم</div>
        <strong>Evidence Basis رتبه‌بندی شخصی درمان نیست.</strong>
        <p>{taxonomy.note}</p>
      </aside>
    </div>
  );
}

function EmptyState({ label }: { label: string }) {
  return (
    <div className="card therapy-empty-state">
      <h3>{label} پیدا نشد</h3>
      <p>عبارت جست‌وجو یا فیلترهای فعلی را تغییر بده.</p>
    </div>
  );
}
