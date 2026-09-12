"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import { dsmTypeLabel } from "@/lib/dsm";
import type { DSMPaginatedRecords, SearchResults } from "@/lib/types";
import ConceptCard from "./ConceptCard";
import { ReviewStatus, humanizeCode } from "./ScientificMeta";

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

  const atlasTotal = data
    ? data.disorders.length
      + data.concepts.length
      + data.symptoms.length
      + data.therapies.length
      + data.techniques.length
      + data.psychologists.length
      + data.theories.length
      + data.timeline_events.length
    : 0;
  const total = atlasTotal + (dsmData?.count || 0);

  return (
    <div className="stack">
      <input
        autoFocus
        className="search global-search-input"
        value={query}
        onChange={event => setQuery(event.target.value)}
        placeholder="اختلال، مفهوم، درمان، روان‌شناس، نظریه، رویداد تاریخی یا DSM MASTER..."
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
            <div className="search-section-head"><div><div className="meta">Psychologists</div><h2>روان‌شناسان و پژوهشگران</h2></div><span>{data.psychologists.length.toLocaleString("fa-IR")}</span></div>
            <div className="grid">
              {data.psychologists.map(item => (
                <Link className="card" href={`/psychologists/${item.slug}`} key={item.slug}>
                  <div className="meta">{item.role_fa || item.role_en || "Psychologist"}</div>
                  <h3>{item.name_fa || item.name_en}</h3>
                  {item.name_fa && <div className="latin-label">{item.name_en}</div>}
                  {item.summary_fa || item.summary_en ? <p>{item.summary_fa || item.summary_en}</p> : <p className="muted">خلاصه مستقیمی ثبت نشده است.</p>}
                  <div className="search-v6-card-meta">
                    <ReviewStatus status={item.review_status} compact />
                    <small>{item.theory_count.toLocaleString("fa-IR")} نظریه · {item.timeline_event_count.toLocaleString("fa-IR")} رویداد</small>
                  </div>
                </Link>
              ))}
              {!data.psychologists.length && <div className="card muted">نتیجه‌ای در روان‌شناسان نیست.</div>}
            </div>
          </section>

          <section className="search-section">
            <div className="search-section-head"><div><div className="meta">Theories</div><h2>نظریه‌ها و مدل‌ها</h2></div><span>{data.theories.length.toLocaleString("fa-IR")}</span></div>
            <div className="grid">
              {data.theories.map(item => (
                <Link className="card" href={`/theories/${item.slug}`} key={item.slug}>
                  <div className="meta">{humanizeCode(item.domain || "theory")}</div>
                  <h3>{item.name_fa || item.name_en}</h3>
                  {item.name_fa && <div className="latin-label">{item.name_en}</div>}
                  {item.summary_fa || item.summary_en ? <p>{item.summary_fa || item.summary_en}</p> : <p className="muted">خلاصه مستقیمی ثبت نشده است.</p>}
                  <div className="search-v6-card-meta">
                    <ReviewStatus status={item.review_status} compact />
                    <small>{item.psychologist_count.toLocaleString("fa-IR")} شخص · {item.concept_count.toLocaleString("fa-IR")} مفهوم</small>
                  </div>
                </Link>
              ))}
              {!data.theories.length && <div className="card muted">نتیجه‌ای در نظریه‌ها نیست.</div>}
            </div>
          </section>

          <section className="search-section">
            <div className="search-section-head"><div><div className="meta">Timeline</div><h2>رویدادهای تاریخی</h2></div><span>{data.timeline_events.length.toLocaleString("fa-IR")}</span></div>
            <div className="grid">
              {data.timeline_events.map(item => (
                <Link className="card" href={`/timeline/${item.slug}`} key={item.slug}>
                  <div className="meta">{item.date_text || (item.year_start ? item.year_start.toLocaleString("fa-IR") : "تاریخ نامشخص")}</div>
                  <h3>{item.title_fa || item.title_en}</h3>
                  {item.title_fa && <div className="latin-label">{item.title_en}</div>}
                  <div className="search-v6-card-meta">
                    <ReviewStatus status={item.review_status} compact />
                    <small>{humanizeCode(item.event_type)} · {item.psychologist_count + item.theory_count + item.therapy_count + item.technique_count + item.concept_count} اتصال</small>
                  </div>
                </Link>
              ))}
              {!data.timeline_events.length && <div className="card muted">نتیجه‌ای در Timeline نیست.</div>}
            </div>
          </section>

          <section className="search-section">
            <div className="search-section-head"><div><div className="meta">Therapies</div><h2>رویکردهای درمانی</h2></div><span>{data.therapies.length.toLocaleString("fa-IR")}</span></div>
            <div className="grid">
              {data.therapies.map(item => (
                <Link className="card" href={`/therapies/${item.slug}`} key={item.slug}>
                  <div className="meta">{item.family.name_fa || item.family.name_en}</div>
                  <h3>{item.name_fa || item.name_en}</h3>
                  <div className="latin-label">{item.name_en}</div>
                  <p>{item.summary}</p>
                  <small className="muted">{item.technique_count.toLocaleString("fa-IR")} تکنیک · {item.disorder_count.toLocaleString("fa-IR")} زمینه بالینی</small>
                </Link>
              ))}
              {!data.therapies.length && <div className="card muted">نتیجه‌ای در درمان‌ها نیست.</div>}
            </div>
          </section>

          <section className="search-section">
            <div className="search-section-head"><div><div className="meta">Techniques</div><h2>تکنیک‌های درمانی</h2></div><span>{data.techniques.length.toLocaleString("fa-IR")}</span></div>
            <div className="grid">
              {data.techniques.map(item => (
                <Link className="card" href={`/techniques/${item.slug}`} key={item.slug}>
                  <div className="meta">Technique</div>
                  <h3>{item.name_fa || item.name_en}</h3>
                  <div className="latin-label">{item.name_en}</div>
                  <p>{item.summary}</p>
                  <small className="muted">{item.therapy_count.toLocaleString("fa-IR")} درمان · {item.concept_count.toLocaleString("fa-IR")} مفهوم</small>
                </Link>
              ))}
              {!data.techniques.length && <div className="card muted">نتیجه‌ای در تکنیک‌ها نیست.</div>}
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
