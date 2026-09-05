"use client";

import Link from "next/link";
import { useDeferredValue, useMemo, useState } from "react";
import { normalizePersianSearch } from "@/lib/text";
import type { TimelineEvent } from "@/lib/types";
import { faNumber, humanizeCode, ReviewStatus } from "./ScientificMeta";

type SortMode = "asc" | "desc";
type LinkFilter = "" | "psychologist" | "theory" | "therapy" | "technique" | "concept";

const eventTypeLabels: Record<string, string> = {
  publication: "انتشار",
  theory_development: "توسعه نظریه",
  therapy_development: "توسعه درمان",
  research_finding: "یافته پژوهشی",
  institutional: "نقطه عطف نهادی",
  professional: "نقطه عطف حرفه‌ای",
  classification: "طبقه‌بندی / nosology",
  guideline: "راهنما",
  other: "سایر",
  unspecified: "نوع مشخص نشده",
};

function displayDate(item: TimelineEvent) {
  if (item.date_precision === "exact_date" && item.exact_date) return item.exact_date;
  if (item.date_precision === "year_range" && item.year_start) {
    return `${faNumber(item.year_start)} — ${item.year_end ? faNumber(item.year_end) : "؟"}`;
  }
  if (item.date_precision === "approximate_year" && item.year_start) return `حدود ${faNumber(item.year_start)}`;
  if (item.year_start) return faNumber(item.year_start);
  return item.date_text || "تاریخ نامشخص";
}

function searchable(item: TimelineEvent) {
  return normalizePersianSearch([
    item.title_fa,
    item.title_en,
    item.category,
    item.event_type,
    item.event_type_label,
    item.date_text,
  ].filter(Boolean).join(" "));
}

function matchesLink(item: TimelineEvent, link: LinkFilter) {
  if (!link) return true;
  if (link === "psychologist") return item.psychologist_count > 0;
  if (link === "theory") return item.theory_count > 0;
  if (link === "therapy") return item.therapy_count > 0;
  if (link === "technique") return item.technique_count > 0;
  return item.concept_count > 0;
}

function linkCount(item: TimelineEvent) {
  return item.psychologist_count + item.theory_count + item.therapy_count + item.technique_count + item.concept_count;
}

export default function TimelineExplorer({ items }: { items: TimelineEvent[] }) {
  const [query, setQuery] = useState("");
  const deferredQuery = useDeferredValue(query);
  const [category, setCategory] = useState("");
  const [review, setReview] = useState("");
  const [linkFilter, setLinkFilter] = useState<LinkFilter>("");
  const [sort, setSort] = useState<SortMode>("asc");

  const categories = useMemo(() => {
    const counts = new Map<string, number>();
    items.forEach(item => item.category && counts.set(item.category, (counts.get(item.category) || 0) + 1));
    return Array.from(counts, ([value, count]) => ({ value, count })).sort((a, b) => b.count - a.count || a.value.localeCompare(b.value));
  }, [items]);

  const rows = useMemo(() => {
    const q = normalizePersianSearch(deferredQuery.trim());
    const filtered = items
      .filter(item => !q || searchable(item).includes(q))
      .filter(item => !category || item.category === category)
      .filter(item => !review || item.review_status === review)
      .filter(item => matchesLink(item, linkFilter));
    return [...filtered].sort((a, b) => {
      const aYear = a.year_start ?? (sort === "asc" ? 9999 : 0);
      const bYear = b.year_start ?? (sort === "asc" ? 9999 : 0);
      return sort === "asc" ? aYear - bYear || a.id - b.id : bYear - aYear || b.id - a.id;
    });
  }, [items, deferredQuery, category, review, linkFilter, sort]);

  const grouped = useMemo(() => {
    const groups = new Map<string, TimelineEvent[]>();
    rows.forEach(item => {
      const label = item.year_start ? `${Math.floor(item.year_start / 10) * 10}s` : "unknown";
      const existing = groups.get(label) || [];
      existing.push(item);
      groups.set(label, existing);
    });
    return Array.from(groups, ([label, events]) => ({ label, events }));
  }, [rows]);

  const years = items.flatMap(item => item.year_start ? [item.year_start] : []);
  const minYear = years.length ? Math.min(...years) : null;
  const maxYear = years.length ? Math.max(...years) : null;
  const sourcedCount = items.filter(item => item.review_status === "source_checked" || item.review_status === "reviewed").length;
  const crossLinkedCount = items.filter(item => linkCount(item) > 0).length;

  function clearFilters() {
    setQuery("");
    setCategory("");
    setReview("");
    setLinkFilter("");
  }

  return (
    <div className="stack timeline-explorer">
      <section className="timeline-overview" aria-label="خلاصه Timeline">
        <div><strong>{faNumber(items.length)}</strong><span>رویداد canonical</span></div>
        <div><strong>{minYear && maxYear ? `${faNumber(minYear)}—${faNumber(maxYear)}` : "—"}</strong><span>بازه سال‌های ثبت‌شده</span></div>
        <div><strong>{faNumber(sourcedCount)}</strong><span>source-checked / reviewed</span></div>
        <div><strong>{faNumber(crossLinkedCount)}</strong><span>دارای اتصال cross-domain</span></div>
      </section>

      <div className="atlas-filters timeline-filter-grid">
        <input
          className="search"
          value={query}
          onChange={event => setQuery(event.target.value)}
          placeholder="عنوان فارسی/انگلیسی، دسته یا سال..."
          aria-label="جست‌وجوی خط زمانی"
        />
        <select className="filter-select" value={category} onChange={event => setCategory(event.target.value)} aria-label="دسته رویداد">
          <option value="">همه دسته‌ها</option>
          {categories.map(item => <option value={item.value} key={item.value}>{humanizeCode(item.value)} · {faNumber(item.count)}</option>)}
        </select>
        <select className="filter-select" value={linkFilter} onChange={event => setLinkFilter(event.target.value as LinkFilter)} aria-label="نوع اتصال رویداد">
          <option value="">همه اتصال‌ها</option>
          <option value="psychologist">دارای Psychologist</option>
          <option value="theory">دارای Theory</option>
          <option value="therapy">دارای Therapy</option>
          <option value="technique">دارای Technique</option>
          <option value="concept">دارای Concept</option>
        </select>
        <select className="filter-select" value={review} onChange={event => setReview(event.target.value)} aria-label="وضعیت بازبینی رویداد">
          <option value="">همه وضعیت‌های بازبینی</option>
          <option value="source_checked">دارای منبع؛ بازبینی نهایی نشده</option>
          <option value="reviewed">بازبینی علمی ثبت‌شده</option>
          <option value="unreviewed">بازبینی‌نشده</option>
        </select>
        <select className="filter-select" value={sort} onChange={event => setSort(event.target.value as SortMode)} aria-label="ترتیب زمانی">
          <option value="asc">قدیمی → جدید</option>
          <option value="desc">جدید → قدیمی</option>
        </select>
      </div>

      <div className="v6-results-bar timeline-results-bar">
        <div><strong>{faNumber(rows.length)}</strong><span>رویداد مطابق فیلتر فعلی</span></div>
        {(query || category || review || linkFilter) && <button className="button ghost" onClick={clearFilters}>پاک‌کردن فیلترها</button>}
      </div>

      {grouped.length ? (
        <div className="timeline-stream">
          {grouped.map(group => (
            <section className="timeline-decade-block" key={group.label}>
              <div className="timeline-decade-marker">
                <strong>{group.label === "unknown" ? "نامشخص" : group.label.replace("s", "")}</strong>
                <span>{faNumber(group.events.length)} رویداد</span>
              </div>
              <div className="timeline-decade-events">
                {group.events.map(item => (
                  <Link href={`/timeline/${item.slug}`} className="timeline-event-row" key={item.slug}>
                    <div className="timeline-event-date" dir={item.date_precision === "exact_date" ? "ltr" : undefined}>{displayDate(item)}</div>
                    <div className="timeline-event-node" aria-hidden="true"><span /></div>
                    <article className="card timeline-event-card">
                      <div className="timeline-event-topline">
                        <span>{eventTypeLabels[item.event_type] || item.event_type_label || humanizeCode(item.event_type)}</span>
                        {item.category && <small>{humanizeCode(item.category)}</small>}
                        <ReviewStatus status={item.review_status} compact />
                      </div>
                      <h2>{item.title_fa || item.title_en}</h2>
                      {item.title_fa && item.title_en && <div className="latin-title">{item.title_en}</div>}
                      <div className="timeline-event-links">
                        {item.psychologist_count > 0 && <span>{faNumber(item.psychologist_count)} شخص</span>}
                        {item.theory_count > 0 && <span>{faNumber(item.theory_count)} نظریه</span>}
                        {item.therapy_count > 0 && <span>{faNumber(item.therapy_count)} درمان</span>}
                        {item.technique_count > 0 && <span>{faNumber(item.technique_count)} تکنیک</span>}
                        {item.concept_count > 0 && <span>{faNumber(item.concept_count)} مفهوم</span>}
                        {linkCount(item) === 0 && <span>بدون اتصال cross-domain در runtime</span>}
                      </div>
                      <div className="timeline-event-footer">
                        <span>{item.date_precision_label || humanizeCode(item.date_precision)}</span>
                        <b>جزئیات رویداد ←</b>
                      </div>
                    </article>
                  </Link>
                ))}
              </div>
            </section>
          ))}
        </div>
      ) : <div className="card scientific-empty"><h3>رویدادی پیدا نشد</h3><p>جست‌وجو یا فیلترهای Timeline را تغییر بده.</p></div>}

      <aside className="card v6-method-note timeline-precision-note">
        <div className="meta">Date precision</div>
        <strong>محور زمان دقتی بیشتر از منبع ادعا نمی‌کند.</strong>
        <p>سال، بازه سال، تاریخ دقیق یا سال تقریبی همان‌طور که در API ثبت شده نمایش داده می‌شود. سال تنها به تاریخ ساختگی اول ژانویه تبدیل نمی‌شود.</p>
      </aside>
    </div>
  );
}
