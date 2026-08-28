"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { api } from "@/lib/api";
import { clearTokens, hasToken } from "@/lib/auth";

export default function SavedPage() {
  const [data, setData] = useState<{ disorders: any[]; concepts: any[] } | null>(null);
  const [error, setError] = useState("");

  useEffect(() => {
    if (!hasToken()) { location.href = "/login"; return; }
    Promise.all([
      api<any[]>("/bookmarks/", {}, true),
      api<any[]>("/concept-bookmarks/", {}, true),
    ])
      .then(([disorders, concepts]) => setData({ disorders, concepts }))
      .catch((e: any) => setError(e.message || "دریافت ذخیره‌شده‌ها انجام نشد."));
  }, []);

  if (error) {
    return (
      <main className="shell page"><div className="card error-state"><h2>ذخیره‌شده‌ها بارگذاری نشد</h2><p>{error}</p><div className="actions" style={{ marginTop: 16 }}><button className="button primary" onClick={() => location.reload()}>تلاش دوباره</button><button className="button" onClick={() => { clearTokens(); location.href = "/login"; }}>ورود دوباره</button></div></div></main>
    );
  }

  if (!data) return <main className="shell page"><p className="muted">در حال بارگذاری موضوعات ذخیره‌شده...</p></main>;
  const empty = !data.disorders.length && !data.concepts.length;

  return (
    <main className="shell page stack">
      <div><div className="meta">ذخیره‌شده‌ها · Universal Base</div><h1 className="section-title" style={{ fontSize: 44 }}>اختلال و مفهوم را در یک کتابخانه خصوصی نگه دار.</h1></div>
      {empty ? <div className="card"><h3>هنوز چیزی ذخیره نکرده‌ای</h3><p>در صفحه Disorder یا Concept گزینه ذخیره را بزن.</p></div> : (
        <>
          <section className="stack"><div className="search-section-head"><h2>اختلالات</h2><span>{data.disorders.length.toLocaleString("fa-IR")}</span></div><div className="grid">{data.disorders.map(item => <Link className="card" href={`/disorders/${item.disorder.slug}`} key={`d-${item.id}`}><div className="meta">{item.disorder.category}</div><h3>{item.disorder.name_fa || item.disorder.name_en}</h3><p>{item.disorder.short_description}</p></Link>)}</div>{!data.disorders.length && <p className="muted">اختلال ذخیره‌شده‌ای نداری.</p>}</section>
          <section className="stack"><div className="search-section-head"><h2>مفاهیم</h2><span>{data.concepts.length.toLocaleString("fa-IR")}</span></div><div className="grid">{data.concepts.map(item => <Link className="card" href={`/concepts/${item.concept.slug}`} key={`c-${item.id}`}><div className="meta">مفهوم</div><h3>{item.concept.name_fa || item.concept.name_en}</h3><p>{item.concept.simple_definition}</p></Link>)}</div>{!data.concepts.length && <p className="muted">مفهوم ذخیره‌شده‌ای نداری.</p>}</section>
        </>
      )}
    </main>
  );
}
