"use client";

import Link from "next/link";
import { useDeferredValue, useMemo, useState } from "react";
import { normalizePersianSearch } from "@/lib/text";
import type { Psychologist } from "@/lib/types";
import { faNumber, ReviewStatus } from "./ScientificMeta";

type SortMode = "connections" | "name" | "birth" | "timeline";
type ViewMode = "grid" | "compact";

function connectionScore(item: Psychologist) {
  return item.theory_count + item.concept_count + item.therapy_count + item.timeline_event_count;
}

function searchable(item: Psychologist) {
  return normalizePersianSearch([
    item.name_fa,
    item.name_en,
    item.role_fa,
    item.role_en,
    item.nationality_fa,
    item.nationality_en,
    item.summary_fa,
    item.summary_en,
    ...(item.aliases || []).map(alias => alias.text),
  ].filter(Boolean).join(" "));
}

function lifeYears(item: Psychologist) {
  if (!item.birth_year && !item.death_year) return "سال زندگی ثبت نشده";
  const birth = item.birth_year ? faNumber(item.birth_year) : "؟";
  const death = item.death_year ? faNumber(item.death_year) : "اکنون / نامشخص";
  return `${birth} — ${death}`;
}

function centuryOf(year: number) {
  return Math.floor((year - 1) / 100) + 1;
}

export default function PsychologistExplorer({ items }: { items: Psychologist[] }) {
  const [query, setQuery] = useState("");
  const deferredQuery = useDeferredValue(query);
  const [review, setReview] = useState("");
  const [century, setCentury] = useState("");
  const [sort, setSort] = useState<SortMode>("connections");
  const [view, setView] = useState<ViewMode>("grid");

  const centuries = useMemo(() => Array.from(new Set(
    items.flatMap(item => item.birth_year ? [centuryOf(item.birth_year)] : []),
  )).sort((a, b) => a - b), [items]);

  const rows = useMemo(() => {
    const q = normalizePersianSearch(deferredQuery.trim());
    return items
      .filter(item => !q || searchable(item).includes(q))
      .filter(item => !review || item.review_status === review)
      .filter(item => !century || (item.birth_year != null && centuryOf(item.birth_year) === Number(century)))
      .toSorted((a, b) => {
        if (sort === "connections") return connectionScore(b) - connectionScore(a) || a.name_en.localeCompare(b.name_en);
        if (sort === "timeline") return b.timeline_event_count - a.timeline_event_count || connectionScore(b) - connectionScore(a);
        if (sort === "birth") return (a.birth_year ?? 9999) - (b.birth_year ?? 9999) || a.name_en.localeCompare(b.name_en);
        return (a.name_fa || a.name_en).localeCompare(b.name_fa || b.name_en, "fa");
      });
  }, [items, deferredQuery, review, century, sort]);

  const sourcedCount = items.filter(item => item.review_status === "source_checked" || item.review_status === "reviewed").length;
  const withTimeline = items.filter(item => item.timeline_event_count > 0).length;

  function clearFilters() {
    setQuery("");
    setReview("");
    setCentury("");
  }

  return (
    <div className="stack v6-explorer psychologist-explorer">
      <section className="v6-explorer-summary" aria-label="خلاصه مجموعه روان‌شناسان">
        <div><strong>{faNumber(items.length)}</strong><span>شخصیت canonical</span></div>
        <div><strong>{faNumber(sourcedCount)}</strong><span>دارای وضعیت source-checked / reviewed</span></div>
        <div><strong>{faNumber(withTimeline)}</strong><span>دارای اتصال Timeline</span></div>
        <div><strong>{faNumber(items.reduce((sum, item) => sum + item.theory_count, 0))}</strong><span>اتصال مستقیم به Theory</span></div>
      </section>

      <div className="atlas-filters v6-filter-grid psychologist-filter-grid">
        <input
          className="search"
          value={query}
          onChange={event => setQuery(event.target.value)}
          placeholder="نام فارسی/انگلیسی، alias یا ملیت..."
          aria-label="جست‌وجوی روان‌شناسان"
        />
        <select className="filter-select" value={review} onChange={event => setReview(event.target.value)} aria-label="وضعیت بازبینی">
          <option value="">همه وضعیت‌های بازبینی</option>
          <option value="source_checked">دارای منبع؛ بازبینی نهایی نشده</option>
          <option value="reviewed">بازبینی علمی ثبت‌شده</option>
          <option value="unreviewed">بازبینی‌نشده</option>
        </select>
        <select className="filter-select" value={century} onChange={event => setCentury(event.target.value)} aria-label="قرن تولد">
          <option value="">همه دوره‌های تولد</option>
          {centuries.map(value => <option value={value} key={value}>قرن {faNumber(value)} میلادی</option>)}
        </select>
        <select className="filter-select" value={sort} onChange={event => setSort(event.target.value as SortMode)} aria-label="مرتب‌سازی روان‌شناسان">
          <option value="connections">بیشترین اتصال علمی</option>
          <option value="timeline">بیشترین رویداد تاریخی</option>
          <option value="birth">سال تولد</option>
          <option value="name">نام</option>
        </select>
      </div>

      <div className="v6-results-bar">
        <div><strong>{faNumber(rows.length)}</strong><span>پروفایل مطابق فیلتر فعلی</span></div>
        <div className="actions compact-actions">
          {(query || review || century) && <button className="button ghost" onClick={clearFilters}>پاک‌کردن فیلترها</button>}
          <button className={`button ${view === "grid" ? "primary" : ""}`} onClick={() => setView("grid")}>کارت</button>
          <button className={`button ${view === "compact" ? "primary" : ""}`} onClick={() => setView("compact")}>فشرده</button>
        </div>
      </div>

      {rows.length ? view === "grid" ? (
        <div className="v6-card-grid psychologist-card-grid">
          {rows.map(item => (
            <Link href={`/psychologists/${item.slug}`} className="card v6-entity-card psychologist-card" key={item.slug}>
              <div className="v6-card-topline">
                <span>{lifeYears(item)}</span>
                <ReviewStatus status={item.review_status} compact />
              </div>
              <div className="v6-entity-title">
                <h2>{item.name_fa || item.name_en}</h2>
                <div className="latin-title">{item.name_en}</div>
              </div>
              {(item.nationality_fa || item.nationality_en || item.role_fa || item.role_en) && (
                <div className="v6-entity-context">
                  <span>{item.role_fa || item.role_en}</span>
                  <span>{item.nationality_fa || item.nationality_en}</span>
                </div>
              )}
              {(item.summary_fa || item.summary_en) ? (
                <p className={!item.summary_fa && item.summary_en ? "ltr-summary" : ""} lang={!item.summary_fa && item.summary_en ? "en" : undefined} dir={!item.summary_fa && item.summary_en ? "ltr" : undefined}>
                  {item.summary_fa || item.summary_en}
                </p>
              ) : (
                <p className="v6-data-note">توضیح عمومی مستقلی ثبت نشده؛ پروفایل از contribution، relation و sourceهای موجود استفاده می‌کند.</p>
              )}
              {!!item.aliases.length && <div className="v6-aliases">{item.aliases.map(alias => <span key={`${alias.language}-${alias.text}`}>{alias.text}</span>)}</div>}
              <div className="v6-card-metrics four-col">
                <div><strong>{faNumber(item.theory_count)}</strong><span>نظریه</span></div>
                <div><strong>{faNumber(item.concept_count)}</strong><span>مفهوم</span></div>
                <div><strong>{faNumber(item.therapy_count)}</strong><span>درمان</span></div>
                <div><strong>{faNumber(item.timeline_event_count)}</strong><span>رویداد</span></div>
              </div>
              <span className="v6-card-cta">باز کردن پروفایل تاریخی و علمی ←</span>
            </Link>
          ))}
        </div>
      ) : (
        <div className="v6-compact-list">
          {rows.map(item => (
            <Link href={`/psychologists/${item.slug}`} className="v6-compact-row" key={item.slug}>
              <div><strong>{item.name_fa || item.name_en}</strong><small>{item.name_en}</small></div>
              <span>{lifeYears(item)}</span>
              <span>{faNumber(connectionScore(item))} اتصال</span>
              <ReviewStatus status={item.review_status} compact />
            </Link>
          ))}
        </div>
      ) : (
        <div className="card scientific-empty"><h3>پروفایلی پیدا نشد</h3><p>عبارت جست‌وجو یا فیلترهای فعلی را تغییر بده.</p></div>
      )}

      <aside className="card v6-method-note">
        <div className="meta">مرز داده</div>
        <strong>نبودن biography مفصل به معنی پرکردن حدس‌محور آن نیست.</strong>
        <p>این صفحه فقط فیلدهای موجود در runtime و relationهای source-backed را نمایش می‌دهد. `source_checked` نیز به‌تنهایی معادل بازبینی علمی نهایی نیست.</p>
      </aside>
    </div>
  );
}
