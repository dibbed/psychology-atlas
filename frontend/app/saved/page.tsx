"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { api } from "@/lib/api";
import { clearTokens, hasToken } from "@/lib/auth";
import type { Concept, Disorder, TherapyBookmark } from "@/lib/types";

type DisorderBookmark = { id: number; disorder: Disorder; created_at: string };
type ConceptBookmark = { id: number; concept: Concept; created_at: string };
type SavedData = {
  disorders: DisorderBookmark[];
  concepts: ConceptBookmark[];
  therapies: TherapyBookmark[];
};

export default function SavedPage() {
  const [data, setData] = useState<SavedData | null>(null);
  const [error, setError] = useState("");
  const [query, setQuery] = useState("");

  useEffect(() => {
    if (!hasToken()) { location.href = "/login"; return; }
    const controller = new AbortController();
    setError("");
    Promise.all([
      api<DisorderBookmark[]>("/bookmarks/", { signal: controller.signal }, true),
      api<ConceptBookmark[]>("/concept-bookmarks/", { signal: controller.signal }, true),
      api<TherapyBookmark[]>("/therapy-bookmarks/", { signal: controller.signal }, true),
    ])
      .then(([disorders, concepts, therapies]) => {
        if (!controller.signal.aborted) setData({ disorders, concepts, therapies });
      })
      .catch((reason: any) => {
        if (reason?.name !== "AbortError") setError(reason?.message || "دریافت ذخیره‌شده‌ها انجام نشد.");
      });
    return () => controller.abort();
  }, []);

  if (error) {
    return (
      <main className="shell page"><div className="card error-state"><h2>ذخیره‌شده‌ها بارگذاری نشد</h2><p>{error}</p><div className="actions" style={{ marginTop: 16 }}><button className="button primary" onClick={() => location.reload()}>تلاش دوباره</button><button className="button" onClick={() => { clearTokens(); location.href = "/login"; }}>ورود دوباره</button></div></div></main>
    );
  }

  if (!data) return <main className="shell page"><p className="muted">در حال بارگذاری کتابخانه خصوصی...</p></main>;
  const match = (name: string) => name.toLocaleLowerCase("fa").includes(query.trim().toLocaleLowerCase("fa"));
  const visible = {
    disorders: data.disorders.filter(item => match(`${item.disorder.name_fa} ${item.disorder.name_en}`)),
    concepts: data.concepts.filter(item => match(`${item.concept.name_fa} ${item.concept.name_en}`)),
    therapies: data.therapies.filter(item => match(`${item.therapy.name_fa} ${item.therapy.name_en}`)),
  };
  const empty = !data.disorders.length && !data.concepts.length && !data.therapies.length;
  const noMatch = !empty && !visible.disorders.length && !visible.concepts.length && !visible.therapies.length;

  return (
    <main className="shell page stack">
      <div>
        <div className="eyebrow">کتابخانهٔ من</div>
        <h1 className="section-title">ذخیره‌شده‌ها</h1>
        <p className="section-copy">ذخیره‌کردن درمان فقط برای مطالعهٔ شخصی است و به معنی توصیه یا انتخاب درمان برای فردی خاص نیست.</p>
      </div>
      {!empty && <div className="library-filter"><label htmlFor="saved-query">جست‌وجو در ذخیره‌شده‌ها</label><input id="saved-query" className="search" type="search" value={query} onChange={event => setQuery(event.target.value)} placeholder="نام اختلال، مفهوم یا درمان…" /></div>}
      {noMatch && <div className="card"><h2>موردی پیدا نشد</h2><p>عبارت جست‌وجو را تغییر بده.</p><button className="button" onClick={() => setQuery("")}>پاک‌کردن جست‌وجو</button></div>}
      {empty ? <div className="card"><h3>هنوز چیزی ذخیره نکرده‌ای</h3><p>در صفحهٔ یک اختلال، مفهوم یا درمان گزینهٔ ذخیره را بزن.</p></div> : (
        <>
          <section className="stack">
            <div className="search-section-head"><h2>درمان‌ها</h2><span>{visible.therapies.length.toLocaleString("fa-IR")}</span></div>
            <div className="grid">
              {visible.therapies.map(item => <Link className="card" href={`/therapies/${item.therapy.slug}`} key={`t-${item.id}`}><div className="meta">{item.therapy.family.name_fa || item.therapy.family.name_en}</div><h3>{item.therapy.name_fa || item.therapy.name_en}</h3><div className="latin-label">{item.therapy.name_en}</div><p>{item.therapy.summary}</p></Link>)}
            </div>
            {!visible.therapies.length && !query && <p className="muted">درمان ذخیره‌شده‌ای نداری.</p>}
          </section>
          <section className="stack">
            <div className="search-section-head"><h2>اختلالات</h2><span>{visible.disorders.length.toLocaleString("fa-IR")}</span></div>
            <div className="grid">{visible.disorders.map(item => <Link className="card" href={`/disorders/${item.disorder.slug}`} key={`d-${item.id}`}><div className="meta">{item.disorder.category}</div><h3>{item.disorder.name_fa || item.disorder.name_en}</h3><p>{item.disorder.short_description}</p></Link>)}</div>
            {!visible.disorders.length && !query && <p className="muted">اختلال ذخیره‌شده‌ای نداری.</p>}
          </section>
          <section className="stack">
            <div className="search-section-head"><h2>مفاهیم</h2><span>{visible.concepts.length.toLocaleString("fa-IR")}</span></div>
            <div className="grid">{visible.concepts.map(item => <Link className="card" href={`/concepts/${item.concept.slug}`} key={`c-${item.id}`}><div className="meta">مفهوم</div><h3>{item.concept.name_fa || item.concept.name_en}</h3><p>{item.concept.simple_definition}</p></Link>)}</div>
            {!visible.concepts.length && !query && <p className="muted">مفهوم ذخیره‌شده‌ای نداری.</p>}
          </section>
        </>
      )}
    </main>
  );
}
