"use client";

import Link from "next/link";
import { useEffect, useMemo, useState } from "react";
import { api } from "@/lib/api";
import { DSM_TYPE_LABELS, dsmTypeLabel, faNumber } from "@/lib/dsm";
import type { DSMDisplayType, DSMOverview, DSMPaginatedRecords } from "@/lib/types";

const FILTER_TYPES: DSMDisplayType[] = [
  "diagnosis",
  "clinical_attention",
  "research",
  "alternative_model",
  "specifier",
  "reference",
  "structural",
  "code",
];

export default function DSMExplorer({
  overview,
  initialQuery = "",
  initialType = "all",
  initialChapter = "all",
}: {
  overview: DSMOverview;
  initialQuery?: string;
  initialType?: "all" | DSMDisplayType;
  initialChapter?: string;
}) {
  const [query, setQuery] = useState(initialQuery);
  const [displayType, setDisplayType] = useState<"all" | DSMDisplayType>(initialType);
  const [chapter, setChapter] = useState(initialChapter);
  const [page, setPage] = useState(1);
  const [data, setData] = useState<DSMPaginatedRecords | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  const searchPath = useMemo(() => {
    const params = new URLSearchParams();
    const trimmed = query.trim();
    if (trimmed) params.set("q", trimmed);
    if (displayType !== "all") params.set("type", displayType);
    if (chapter !== "all") params.set("chapter", chapter);
    params.set("page", String(page));
    params.set("page_size", "36");
    return `/dsm/records/?${params.toString()}`;
  }, [chapter, displayType, page, query]);

  useEffect(() => {
    const controller = new AbortController();
    const timer = setTimeout(() => {
      setLoading(true);
      setError("");
      api<DSMPaginatedRecords>(searchPath, { signal: controller.signal })
        .then(setData)
        .catch((reason: any) => {
          if (reason?.name !== "AbortError") setError(reason?.message || "دریافت داده DSM انجام نشد.");
        })
        .finally(() => {
          if (!controller.signal.aborted) setLoading(false);
        });
    }, query.trim() ? 180 : 0);

    return () => {
      clearTimeout(timer);
      controller.abort();
    };
  }, [searchPath, query]);

  const changeQuery = (value: string) => {
    setQuery(value);
    setPage(1);
  };

  const changeType = (value: "all" | DSMDisplayType) => {
    setDisplayType(value);
    setPage(1);
  };

  const changeChapter = (value: string) => {
    setChapter(value);
    setPage(1);
  };

  return (
    <section className="dsm-explorer stack">
      <div className="dsm-controls card">
        <div className="dsm-search-row">
          <div>
            <div className="meta">جست‌وجوی MASTER</div>
            <h2>{faNumber(overview.counts.records)} گره را بر اساس نام، خلاصه، ارزیابی، افتراق و کلیدواژه جست‌وجو کن.</h2>
          </div>
          <input
            className="search dsm-search"
            value={query}
            onChange={event => changeQuery(event.target.value)}
            placeholder="مثلاً اضطراب اجتماعی، delirium، افتراق، خواب..."
            aria-label="جست‌وجوی DSM MASTER"
          />
        </div>

        <div className="dsm-filter-grid">
          <div className="dsm-type-filter">
            <button className={`chip ${displayType === "all" ? "active" : ""}`} onClick={() => changeType("all")}>همه · {faNumber(overview.counts.records)}</button>
            {FILTER_TYPES.map(type => {
              const count = overview.counts.types[type] || 0;
              if (!count) return null;
              return (
                <button className={`chip ${displayType === type ? "active" : ""}`} onClick={() => changeType(type)} key={type}>
                  {DSM_TYPE_LABELS[type]} · {faNumber(count)}
                </button>
              );
            })}
          </div>
          <select className="filter-select dsm-chapter-select" value={chapter} onChange={event => changeChapter(event.target.value)} aria-label="فیلتر فصل DSM">
            <option value="all">همه فصل‌ها</option>
            {overview.chapters.map(item => (
              <option value={item.chapter_number} key={item.chapter_number}>
                فصل {faNumber(item.chapter_number)} · {item.chapter_name_fa} ({faNumber(item.record_count)})
              </option>
            ))}
          </select>
        </div>
      </div>

      <div className="dsm-results-head">
        <div>
          <strong>{data ? faNumber(data.count) : "..."}</strong>
          <span> نتیجه با حفظ وضعیت طبقه‌بندی</span>
        </div>
        <span className="muted small">تشخیص رسمی، مشخص‌کننده، شرط پژوهشی و کانون توجه بالینی عمداً یکی نشده‌اند.</span>
      </div>

      {loading && <div className="card"><p>در حال خواندن نمایه DSM MASTER...</p></div>}
      {error && <div className="card error-state"><p>{error}</p></div>}

      {!loading && data && (
        <>
          <div className="dsm-record-list">
            {data.results.map(record => (
              <Link className={`dsm-record-row dsm-type-${record.display_type}`} href={`/dsm/${encodeURIComponent(record.master_id)}`} key={record.master_id}>
                <div className="dsm-record-index">{record.master_id.replace("DSM5TR-FA-", "")}</div>
                <div className="dsm-record-main">
                  <div className="dsm-record-topline">
                    <span className="dsm-type-label">{dsmTypeLabel(record.display_type)}</span>
                    {record.chapter_number && <span>فصل {faNumber(record.chapter_number)}</span>}
                    {record.group_name && <span>{record.group_name}</span>}
                  </div>
                  <h3>{record.name_fa || record.name_en}</h3>
                  {record.name_en && <div className="latin-label">{record.name_en}</div>}
                  <p>{record.summary}</p>
                </div>
                <div className="dsm-record-aside">
                  {record.linked_disorder && <span className="dsm-atlas-link">متصل به Atlas</span>}
                  <span>{record.specialization_level}</span>
                  <b>←</b>
                </div>
              </Link>
            ))}
            {!data.results.length && <div className="card"><p>برای این ترکیب فیلتر نتیجه‌ای پیدا نشد.</p></div>}
          </div>

          <div className="dsm-pagination">
            <button className="button" disabled={!data.previous || page <= 1} onClick={() => setPage(value => Math.max(1, value - 1))}>صفحه قبل</button>
            <span>صفحه {faNumber(page)} از {faNumber(Math.max(1, Math.ceil(data.count / 36)))}</span>
            <button className="button" disabled={!data.next} onClick={() => setPage(value => value + 1)}>صفحه بعد</button>
          </div>
        </>
      )}
    </section>
  );
}
