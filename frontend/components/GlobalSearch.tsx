"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import { dsmTypeLabel } from "@/lib/dsm";
import type { DSMPaginatedRecords, SearchResults } from "@/lib/types";
import ConceptCard from "./ConceptCard";

export default function GlobalSearch({ initialQuery = "" }: { initialQuery?: string }) {
  const [query, setQuery] = useState(initialQuery);
  const [data, setData] = useState<SearchResults | null>(null);
  const [dsmData, setDsmData] = useState<DSMPaginatedRecords | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    const q = query.trim();
    if (q.length < 2) {
      setData(null);
      setDsmData(null);
      setLoading(false);
      return;
    }
    const controller = new AbortController();
    const timer = setTimeout(() => {
      setLoading(true);
      setError("");
      Promise.all([
        api<SearchResults>(`/search/?q=${encodeURIComponent(q)}`, { signal: controller.signal }),
        api<DSMPaginatedRecords>(`/dsm/records/?q=${encodeURIComponent(q)}&page_size=6`, { signal: controller.signal }),
      ])
        .then(([atlas, dsm]) => {
          setData(atlas);
          setDsmData(dsm);
        })
        .catch((e: any) => {
          if (e?.name !== "AbortError") setError(e.message || "جست‌وجو انجام نشد.");
        })
        .finally(() => {
          if (!controller.signal.aborted) setLoading(false);
        });
    }, 220);
    return () => {
      clearTimeout(timer);
      controller.abort();
    };
  }, [query]);

  const atlasTotal = data ? data.disorders.length + data.concepts.length + data.symptoms.length : 0;
  const total = atlasTotal + (dsmData?.count || 0);

  return (
    <div className="stack">
      <input
        autoFocus
        className="search global-search-input"
        value={query}
        onChange={event => setQuery(event.target.value)}
        placeholder="اختلال، DSM MASTER، مفهوم یا نشانه را جست‌وجو کن..."
        aria-label="جست‌وجوی سراسری اطلس"
      />
      {query.trim().length < 2 && <div className="card"><p>حداقل دو حرف بنویس. جست‌وجو همزمان Atlas و رکوردهای DSM MASTER را بررسی می‌کند.</p></div>}
      {loading && <p className="muted">در حال جست‌وجوی اطلس و DSM MASTER...</p>}
      {error && <div className="card error-state"><p>{error}</p></div>}
      {data && dsmData && !loading && (
        <>
          <div className="results-count">{total.toLocaleString("fa-IR")} نتیجه در Atlas و DSM MASTER پیدا شد.</div>

          <section className="search-section dsm-search-results">
            <div className="search-section-head">
              <div><div className="meta">DSM MASTER · audited educational dataset</div><h2>مرجع DSM-5-TR فارسی</h2></div>
              <span>{dsmData.count.toLocaleString("fa-IR")}</span>
            </div>
            <div className="dsm-search-result-list">
              {dsmData.results.map(item => (
                <Link href={`/dsm/${encodeURIComponent(item.master_id)}`} key={item.master_id}>
                  <div><span>{dsmTypeLabel(item.display_type)}</span><small>{item.master_id}</small></div>
                  <strong>{item.name_fa || item.name_en}</strong>
                  <p>{item.summary}</p>
                </Link>
              ))}
              {!dsmData.results.length && <div className="card muted">نتیجه‌ای در DSM MASTER نیست.</div>}
            </div>
            {dsmData.count > dsmData.results.length && <Link className="button ghost" href={`/dsm?q=${encodeURIComponent(query.trim())}`}>دیدن همه {dsmData.count.toLocaleString("fa-IR")} نتیجه DSM</Link>}
          </section>

          <section className="search-section">
            <div className="search-section-head"><div><div className="meta">Disorders</div><h2>اختلالات Atlas</h2></div><span>{data.disorders.length.toLocaleString("fa-IR")}</span></div>
            <div className="grid">
              {data.disorders.map(item => (
                <Link className="card" href={`/disorders/${item.slug}`} key={item.slug}>
                  <div className="meta">{item.category}</div>
                  <h3>{item.name_fa || item.name_en}</h3>
                  {item.name_en && item.name_en !== item.name_fa && <div className="latin-label">{item.name_en}</div>}
                  <p>{item.short_description}</p>
                </Link>
              ))}
              {!data.disorders.length && <div className="card muted">نتیجه‌ای در اختلالات نیست.</div>}
            </div>
          </section>

          <section className="search-section">
            <div className="search-section-head"><div><div className="meta">Concepts</div><h2>مفاهیم</h2></div><span>{data.concepts.length.toLocaleString("fa-IR")}</span></div>
            <div className="grid">
              {data.concepts.map(item => <ConceptCard concept={item} key={item.slug} />)}
              {!data.concepts.length && <div className="card muted">نتیجه‌ای در مفاهیم نیست.</div>}
            </div>
          </section>

          <section className="search-section">
            <div className="search-section-head"><div><div className="meta">Symptoms</div><h2>نشانه‌ها</h2></div><span>{data.symptoms.length.toLocaleString("fa-IR")}</span></div>
            <div className="grid">
              {data.symptoms.map(item => (
                <div className="card symptom-search-card" key={item.slug}>
                  <div className="meta">نشانه · {item.domain}</div>
                  <h3>{item.name_fa || item.name_en}</h3>
                  <div className="latin-label">{item.name_en}</div>
                  {item.description && <p>{item.description}</p>}
                  {item.disorders.length > 0 && (
                    <div className="symptom-related-links">
                      <span>در اختلال‌های:</span>
                      {item.disorders.map(disorder => (
                        <Link href={`/disorders/${disorder.slug}`} key={disorder.slug}>{disorder.name_fa || disorder.name_en}</Link>
                      ))}
                    </div>
                  )}
                </div>
              ))}
              {!data.symptoms.length && <div className="card muted">نتیجه‌ای در نشانه‌ها نیست.</div>}
            </div>
          </section>
        </>
      )}
    </div>
  );
}
