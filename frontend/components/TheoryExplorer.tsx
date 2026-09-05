"use client";

import Link from "next/link";
import { useDeferredValue, useMemo, useState } from "react";
import { normalizePersianSearch } from "@/lib/text";
import type { Theory } from "@/lib/types";
import { faNumber, humanizeCode, ReviewStatus } from "./ScientificMeta";

type SortMode = "connections" | "name" | "timeline" | "people";
type ViewMode = "grid" | "compact";

function score(item: Theory) {
  return item.psychologist_count + item.concept_count + item.therapy_count + item.technique_count + item.timeline_event_count;
}

function searchable(item: Theory) {
  return normalizePersianSearch([
    item.name_fa,
    item.name_en,
    item.domain,
    item.period_text,
    item.summary_fa,
    item.summary_en,
    item.modern_status,
    ...(item.aliases || []).map(alias => alias.text),
  ].filter(Boolean).join(" "));
}

function statusGroup(value: string) {
  if (value.startsWith("historically") || value.startsWith("historical")) return "historical";
  if (value.startsWith("active") || value.startsWith("influential")) return "active";
  return "other";
}

export default function TheoryExplorer({ items }: { items: Theory[] }) {
  const [query, setQuery] = useState("");
  const deferredQuery = useDeferredValue(query);
  const [domain, setDomain] = useState("");
  const [modern, setModern] = useState("");
  const [review, setReview] = useState("");
  const [sort, setSort] = useState<SortMode>("connections");
  const [view, setView] = useState<ViewMode>("grid");

  const domains = useMemo(() => {
    const counts = new Map<string, number>();
    items.forEach(item => item.domain && counts.set(item.domain, (counts.get(item.domain) || 0) + 1));
    return Array.from(counts, ([value, count]) => ({ value, count })).sort((a, b) => b.count - a.count || a.value.localeCompare(b.value));
  }, [items]);

  const rows = useMemo(() => {
    const q = normalizePersianSearch(deferredQuery.trim());
    const filtered = items
      .filter(item => !q || searchable(item).includes(q))
      .filter(item => !domain || item.domain === domain)
      .filter(item => !modern || statusGroup(item.modern_status) === modern)
      .filter(item => !review || item.review_status === review);

    return [...filtered].sort((a, b) => {
      if (sort === "connections") return score(b) - score(a) || a.name_en.localeCompare(b.name_en);
      if (sort === "timeline") return b.timeline_event_count - a.timeline_event_count || score(b) - score(a);
      if (sort === "people") return b.psychologist_count - a.psychologist_count || score(b) - score(a);
      return (a.name_fa || a.name_en).localeCompare(b.name_fa || b.name_en, "fa");
    });
  }, [items, deferredQuery, domain, modern, review, sort]);

  const sourcedCount = items.filter(item => item.review_status === "source_checked" || item.review_status === "reviewed").length;
  const activeCount = items.filter(item => statusGroup(item.modern_status) === "active").length;

  function clearFilters() {
    setQuery("");
    setDomain("");
    setModern("");
    setReview("");
  }

  return (
    <div className="stack v6-explorer theory-explorer">
      <section className="v6-explorer-summary" aria-label="خلاصه مجموعه نظریه‌ها">
        <div><strong>{faNumber(items.length)}</strong><span>نظریه canonical</span></div>
        <div><strong>{faNumber(domains.length)}</strong><span>domain ثبت‌شده</span></div>
        <div><strong>{faNumber(activeCount)}</strong><span>status فعال / influential در داده</span></div>
        <div><strong>{faNumber(sourcedCount)}</strong><span>source-checked / reviewed</span></div>
      </section>

      <div className="atlas-filters v6-filter-grid theory-filter-grid">
        <input
          className="search"
          value={query}
          onChange={event => setQuery(event.target.value)}
          placeholder="نام نظریه، alias، domain یا summary..."
          aria-label="جست‌وجوی نظریه‌ها"
        />
        <select className="filter-select" value={domain} onChange={event => setDomain(event.target.value)} aria-label="دامنه نظریه">
          <option value="">همه domainها</option>
          {domains.map(item => <option value={item.value} key={item.value}>{humanizeCode(item.value)} · {faNumber(item.count)}</option>)}
        </select>
        <select className="filter-select" value={modern} onChange={event => setModern(event.target.value)} aria-label="جایگاه مدرن نظریه">
          <option value="">همه وضعیت‌های مدرن</option>
          <option value="active">فعال / influential</option>
          <option value="historical">تاریخی / foundational</option>
          <option value="other">سایر وضعیت‌ها</option>
        </select>
        <select className="filter-select" value={review} onChange={event => setReview(event.target.value)} aria-label="وضعیت بازبینی نظریه">
          <option value="">همه وضعیت‌های بازبینی</option>
          <option value="source_checked">دارای منبع؛ بازبینی نهایی نشده</option>
          <option value="reviewed">بازبینی علمی ثبت‌شده</option>
          <option value="unreviewed">بازبینی‌نشده</option>
        </select>
        <select className="filter-select" value={sort} onChange={event => setSort(event.target.value as SortMode)} aria-label="مرتب‌سازی نظریه‌ها">
          <option value="connections">بیشترین اتصال</option>
          <option value="people">بیشترین اتصال به روان‌شناس</option>
          <option value="timeline">بیشترین رویداد تاریخی</option>
          <option value="name">نام</option>
        </select>
      </div>

      <div className="v6-results-bar">
        <div><strong>{faNumber(rows.length)}</strong><span>نظریه مطابق فیلتر فعلی</span></div>
        <div className="actions compact-actions">
          {(query || domain || modern || review) && <button className="button ghost" onClick={clearFilters}>پاک‌کردن فیلترها</button>}
          <button className={`button ${view === "grid" ? "primary" : ""}`} onClick={() => setView("grid")}>کارت</button>
          <button className={`button ${view === "compact" ? "primary" : ""}`} onClick={() => setView("compact")}>فشرده</button>
        </div>
      </div>

      {rows.length ? view === "grid" ? (
        <div className="v6-card-grid theory-card-grid">
          {rows.map(item => (
            <Link href={`/theories/${item.slug}`} className="card v6-entity-card theory-card" key={item.slug}>
              <div className="v6-card-topline">
                <span>{humanizeCode(item.domain)}</span>
                <ReviewStatus status={item.review_status} compact />
              </div>
              <div className="v6-entity-title">
                <h2>{item.name_fa || item.name_en}</h2>
                <div className="latin-title">{item.name_en}</div>
              </div>
              <div className="v6-theory-status-row">
                {item.period_text && <span>{humanizeCode(item.period_text)}</span>}
                {item.modern_status && <span>{humanizeCode(item.modern_status)}</span>}
              </div>
              {(item.summary_fa || item.summary_en) ? (
                <p className={!item.summary_fa && item.summary_en ? "ltr-summary" : ""} lang={!item.summary_fa && item.summary_en ? "en" : undefined} dir={!item.summary_fa && item.summary_en ? "ltr" : undefined}>
                  {item.summary_fa || item.summary_en}
                </p>
              ) : <p className="v6-data-note">summary مستقیمی ثبت نشده؛ جزئیات صفحه از proposition، relation و sourceهای موجود ساخته می‌شود.</p>}
              {!!item.aliases.length && <div className="v6-aliases">{item.aliases.map(alias => <span key={`${alias.language}-${alias.text}`}>{alias.text}</span>)}</div>}
              <div className="v6-card-metrics five-col">
                <div><strong>{faNumber(item.psychologist_count)}</strong><span>شخص</span></div>
                <div><strong>{faNumber(item.concept_count)}</strong><span>مفهوم</span></div>
                <div><strong>{faNumber(item.therapy_count)}</strong><span>درمان</span></div>
                <div><strong>{faNumber(item.technique_count)}</strong><span>تکنیک</span></div>
                <div><strong>{faNumber(item.timeline_event_count)}</strong><span>رویداد</span></div>
              </div>
              <span className="v6-card-cta">باز کردن پروفایل نظریه ←</span>
            </Link>
          ))}
        </div>
      ) : (
        <div className="v6-compact-list">
          {rows.map(item => (
            <Link href={`/theories/${item.slug}`} className="v6-compact-row theory-compact-row" key={item.slug}>
              <div><strong>{item.name_fa || item.name_en}</strong><small>{item.name_en}</small></div>
              <span>{humanizeCode(item.domain)}</span>
              <span>{faNumber(score(item))} اتصال</span>
              <ReviewStatus status={item.review_status} compact />
            </Link>
          ))}
        </div>
      ) : <div className="card scientific-empty"><h3>نظریه‌ای پیدا نشد</h3><p>عبارت جست‌وجو یا فیلترها را تغییر بده.</p></div>}

      <aside className="card v6-method-note theory-method-note">
        <div className="meta">خواندن statusها</div>
        <strong>Modern status یک رتبه‌بندی «درست/غلط» نیست.</strong>
        <p>status و domain همان metadata ثبت‌شده در corpus هستند. UI برای جست‌وجو آن‌ها را گروه‌بندی می‌کند، اما semantics اصلی را در پروفایل به‌صورت raw و قابل‌ردیابی نگه می‌دارد.</p>
      </aside>
    </div>
  );
}
