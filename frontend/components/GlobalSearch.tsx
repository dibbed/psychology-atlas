"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import type { SearchResults } from "@/lib/types";
import { conceptKindLabel } from "./ConceptCard";

export default function GlobalSearch({ initialQuery = "" }: { initialQuery?: string }) {
  const [query, setQuery] = useState(initialQuery);
  const [data, setData] = useState<SearchResults | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    const q = query.trim();
    if (q.length < 2) {
      setData(null);
      setLoading(false);
      return;
    }
    const controller = new AbortController();
    const timer = setTimeout(() => {
      setLoading(true);
      setError("");
      api<SearchResults>(`/search/?q=${encodeURIComponent(q)}`, { signal: controller.signal })
        .then(setData)
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

  const total = data ? data.disorders.length + data.concepts.length + data.symptoms.length : 0;

  return (
    <div className="stack">
      <input
        autoFocus
        className="search global-search-input"
        value={query}
        onChange={event => setQuery(event.target.value)}
        placeholder="اختلال، مفهوم یا نشانه را جست‌وجو کن..."
        aria-label="جست‌وجوی سراسری اطلس"
      />
      {query.trim().length < 2 && <div className="card"><p>حداقل دو حرف بنویس. Search V3 همزمان Disorder، Concept و Symptom را بررسی می‌کند.</p></div>}
      {loading && <p className="muted">در حال جست‌وجوی اطلس...</p>}
      {error && <div className="card error-state"><p>{error}</p></div>}
      {data && !loading && (
        <>
          <div className="results-count">{total.toLocaleString("fa-IR")} نتیجه در سه نوع داده پیدا شد.</div>

          <section className="search-section">
            <div className="search-section-head"><div><div className="meta">Disorders</div><h2>اختلالات</h2></div><span>{data.disorders.length.toLocaleString("fa-IR")}</span></div>
            <div className="grid">
              {data.disorders.map(item => (
                <Link className="card" href={`/disorders/${item.slug}`} key={item.slug}>
                  <div className="meta">{item.category}</div><h3>{item.name_fa || item.name_en}</h3><p>{item.short_description}</p>
                </Link>
              ))}
              {!data.disorders.length && <div className="card muted">نتیجه‌ای در اختلالات نیست.</div>}
            </div>
          </section>

          <section className="search-section">
            <div className="search-section-head"><div><div className="meta">Concepts</div><h2>مفاهیم</h2></div><span>{data.concepts.length.toLocaleString("fa-IR")}</span></div>
            <div className="grid">
              {data.concepts.map(item => (
                <Link className="card" href={`/concepts/${item.slug}`} key={item.slug}>
                  <div className="meta">{conceptKindLabel(item.kind)}</div><h3>{item.name_fa || item.name_en}</h3><p>{item.simple_definition}</p>
                </Link>
              ))}
              {!data.concepts.length && <div className="card muted">نتیجه‌ای در مفاهیم نیست.</div>}
            </div>
          </section>

          <section className="search-section">
            <div className="search-section-head"><div><div className="meta">Symptoms</div><h2>نشانه‌ها</h2></div><span>{data.symptoms.length.toLocaleString("fa-IR")}</span></div>
            <div className="grid">
              {data.symptoms.map(item => (
                <div className="card" key={item.slug}><div className="meta">نشانه · {item.domain}</div><h3>{item.name_fa || item.name_en}</h3>{item.description && <p>{item.description}</p>}</div>
              ))}
              {!data.symptoms.length && <div className="card muted">نتیجه‌ای در نشانه‌ها نیست.</div>}
            </div>
          </section>
        </>
      )}
    </div>
  );
}
