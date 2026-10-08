"use client";

import Link from "next/link";
import { useSearchParams } from "next/navigation";
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
  const [retry, setRetry] = useState(0);
  const urlQuery = useSearchParams().get("q") || "";

  useEffect(() => setQuery(urlQuery), [urlQuery]);

  useEffect(() => {
    const q = query.trim();
    setData(null);
    setDsmData(null);
    setError("");
    if (q.length < 2) {
      setLoading(false);
      return;
    }
    setLoading(true);
    const controller = new AbortController();
    const timer = setTimeout(() => {
      Promise.all([
        api<SearchResults>(`/search/?q=${encodeURIComponent(q)}`, { signal: controller.signal }),
        api<DSMPaginatedRecords>(`/dsm/records/?q=${encodeURIComponent(q)}&page_size=6`, { signal: controller.signal }),
      ])
        .then(([atlas, dsm]) => {
          if (controller.signal.aborted) return;
          setData(atlas);
          setDsmData(dsm);
        })
        .catch((e: any) => {
          if (!controller.signal.aborted && e?.name !== "AbortError") {
            setData(null);
            setDsmData(null);
            setError(e.message || "جست‌وجو انجام نشد.");
          }
        })
        .finally(() => {
          if (!controller.signal.aborted) setLoading(false);
        });
    }, 220);
    return () => {
      clearTimeout(timer);
      controller.abort();
    };
  }, [query, retry]);

  function changeQuery(value: string) {
    setQuery(value);
    const url = new URL(window.location.href);
    if (value) url.searchParams.set("q", value);
    else url.searchParams.delete("q");
    window.history.replaceState(window.history.state, "", url.pathname + url.search);
  }

  const atlasTotal = data
    ? data.disorders.length
      + data.concepts.length
      + data.symptoms.length
      + data.therapies.length
      + data.techniques.length
      + data.psychologists.length
      + data.theories.length
      + data.timeline_events.length
      + data.brain_entities.length
      + data.assessments.length
    : 0;
  const total = atlasTotal + (dsmData?.count || 0);

  return (
    <div className="stack">
      <input
        autoFocus
        className="search global-search-input"
        value={query}
        maxLength={255}
        dir="auto"
        onChange={event => changeQuery(event.target.value)}
        placeholder="ساختار مغز، ابزار ارزیابی، مفهوم، اختلال یا مرجع DSM..."
        aria-label="جست‌وجوی سراسری اطلس"
      />
      {query.trim().length < 2 && <div className="card"><p>برای جست‌وجو در اطلس و مرجع DSM دست‌کم دو حرف بنویس.</p></div>}
      {loading && <p className="muted" role="status">در حال جست‌وجو…</p>}
      {error && <div className="card error-state" role="alert"><p>{error}</p><button type="button" className="button" onClick={() => setRetry(value => value + 1)}>تلاش دوباره</button></div>}
      {data && dsmData && !loading && (
        <>
          <div className="results-count" role="status">{total.toLocaleString("fa-IR")} نتیجه پیدا شد.</div>
          {total === 0 && <p className="card muted">نتیجه‌ای مطابق این عبارت پیدا نشد. نام یا اختصار دیگری را امتحان کنید.</p>}
          <p className="muted">نتایج، هویت‌های ثبت‌شدهٔ اطلس هستند؛ جست‌وجو رابطهٔ علمی، محل عملکرد مغز یا تشخیص ایجاد نمی‌کند.</p>
          {total > 0 && <nav className="search-domain-jumps" aria-label="رفتن به دستهٔ نتایج">
            {data.brain_entities.length > 0 && <a href="#search-brain">اطلس مغز <span>{data.brain_entities.length.toLocaleString("fa-IR")}</span></a>}
            {data.assessments.length > 0 && <a href="#search-assessments">ابزارهای ارزیابی <span>{data.assessments.length.toLocaleString("fa-IR")}</span></a>}
            {([["search-dsm", "مرجع DSM", dsmData.count], ["search-disorders", "اختلالات", data.disorders.length], ["search-concepts", "مفاهیم", data.concepts.length], ["search-therapies", "درمان‌ها", data.therapies.length], ["search-techniques", "تکنیک‌ها", data.techniques.length], ["search-symptoms", "نشانه‌ها", data.symptoms.length], ["search-psychologists", "روان‌شناسان", data.psychologists.length], ["search-theories", "نظریه‌ها", data.theories.length], ["search-timeline", "تاریخ", data.timeline_events.length]] as const).filter(([, , count]) => count > 0).map(([id, label, count]) => <a href={`#${id}`} key={id}>{label} <span>{count.toLocaleString("fa-IR")}</span></a>)}
          </nav>}

          <section className="search-section" id="search-brain">
            <div className="search-section-head"><h2>ساختارهای مغز</h2><span>{data.brain_entities.length.toLocaleString("fa-IR")}</span></div>
            <div className="grid">
              {data.brain_entities.map(item => <Link className="card" href={`/brain/${item.slug}`} key={item.slug}>
                <div className="meta">ساختار آناتومی · اطلس مغز</div>
                <h3>{item.name_fa || <bdi lang="en">{item.name_en}</bdi>}</h3>
                {item.name_fa && <div className="latin-label"><bdi lang="en">{item.name_en}</bdi></div>}
                <ReviewStatus status={item.review_status} compact />
              </Link>)}
              {!data.brain_entities.length && <div className="card muted">ساختاری مطابق این عبارت پیدا نشد.</div>}
            </div>
          </section>
          <section className="search-section" id="search-assessments">
            <div className="search-section-head"><h2>ابزارهای ارزیابی</h2><span>{data.assessments.length.toLocaleString("fa-IR")}</span></div>
            <div className="grid">
              {data.assessments.map(item => <Link className="card" href={`/assessments/${item.slug}`} key={item.slug}>
                <div className="meta">خانوادهٔ ابزار · اطلس ارزیابی</div>
                <h3>{item.name_fa || <bdi lang="en">{item.name_en}</bdi>}</h3>
                {item.name_fa && <div className="latin-label"><bdi lang="en">{item.name_en}</bdi></div>}
                <p dir="auto">{item.description}</p>
                <ReviewStatus status={item.review_status} compact />
              </Link>)}
              {!data.assessments.length && <div className="card muted">ابزاری مطابق این عبارت پیدا نشد.</div>}
            </div>
          </section>

          <section className="search-section dsm-search-results" id="search-dsm">
            <div className="search-section-head">
              <div><div className="meta">مرجع آموزشی DSM</div><h2>مرجع DSM-5-TR فارسی</h2></div>
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
              {!dsmData.results.length && <div className="card muted">نتیجه‌ای در مرجع DSM نیست.</div>}
            </div>
            {dsmData.count > dsmData.results.length && <Link className="button ghost" href={`/dsm?q=${encodeURIComponent(query.trim())}`}>دیدن همه {dsmData.count.toLocaleString("fa-IR")} نتیجه DSM</Link>}
          </section>

          <section className="search-section" id="search-disorders">
            <div className="search-section-head"><div><div className="meta">اختلالات</div><h2>اختلالات اطلس</h2></div><span>{data.disorders.length.toLocaleString("fa-IR")}</span></div>
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

          <section className="search-section" id="search-concepts">
            <div className="search-section-head"><div><div className="meta">اطلس مفاهیم</div><h2>مفاهیم</h2></div><span>{data.concepts.length.toLocaleString("fa-IR")}</span></div>
            <div className="grid">
              {data.concepts.map(item => <ConceptCard concept={item} key={item.slug} />)}
              {!data.concepts.length && <div className="card muted">نتیجه‌ای در مفاهیم نیست.</div>}
            </div>
          </section>

          <section className="search-section" id="search-psychologists">
            <div className="search-section-head"><div><div className="meta">افراد</div><h2>روان‌شناسان و پژوهشگران</h2></div><span>{data.psychologists.length.toLocaleString("fa-IR")}</span></div>
            <div className="grid">
              {data.psychologists.map(item => (
                <Link className="card" href={`/psychologists/${item.slug}`} key={item.slug}>
                  <div className="meta">{item.role_fa || item.role_en || "روان‌شناس"}</div>
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

          <section className="search-section" id="search-theories">
            <div className="search-section-head"><div><div className="meta">اندیشه‌ها</div><h2>نظریه‌ها و مدل‌ها</h2></div><span>{data.theories.length.toLocaleString("fa-IR")}</span></div>
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

          <section className="search-section" id="search-timeline">
            <div className="search-section-head"><div><div className="meta">خط زمانی</div><h2>رویدادهای تاریخی</h2></div><span>{data.timeline_events.length.toLocaleString("fa-IR")}</span></div>
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
              {!data.timeline_events.length && <div className="card muted">نتیجه‌ای در رویدادها نیست.</div>}
            </div>
          </section>

          <section className="search-section" id="search-therapies">
            <div className="search-section-head"><div><div className="meta">اطلس درمان</div><h2>رویکردهای درمانی</h2></div><span>{data.therapies.length.toLocaleString("fa-IR")}</span></div>
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

          <section className="search-section" id="search-techniques">
            <div className="search-section-head"><div><div className="meta">روش‌ها</div><h2>تکنیک‌های درمانی</h2></div><span>{data.techniques.length.toLocaleString("fa-IR")}</span></div>
            <div className="grid">
              {data.techniques.map(item => (
                <Link className="card" href={`/techniques/${item.slug}`} key={item.slug}>
                  <div className="meta">تکنیک</div>
                  <h3>{item.name_fa || item.name_en}</h3>
                  <div className="latin-label">{item.name_en}</div>
                  <p>{item.summary}</p>
                  <small className="muted">{item.therapy_count.toLocaleString("fa-IR")} درمان · {item.concept_count.toLocaleString("fa-IR")} مفهوم</small>
                </Link>
              ))}
              {!data.techniques.length && <div className="card muted">نتیجه‌ای در تکنیک‌ها نیست.</div>}
            </div>
          </section>

          <section className="search-section" id="search-symptoms">
            <div className="search-section-head"><div><div className="meta">نشانه‌ها</div><h2>نشانه‌ها</h2></div><span>{data.symptoms.length.toLocaleString("fa-IR")}</span></div>
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
