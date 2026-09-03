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
  const empty = !data.disorders.length && !data.concepts.length && !data.therapies.length;

  return (
    <main className="shell page stack">
      <div>
        <div className="meta">ذخیره‌شده‌ها · Private Library</div>
        <h1 className="section-title" style={{ fontSize: 44 }}>اختلال، مفهوم و درمان را در یک کتابخانه خصوصی نگه دار.</h1>
        <p className="section-copy">ذخیره‌کردن Therapy فقط یک ابزار مطالعه شخصی است و به معنی توصیه یا انتخاب درمان برای یک فرد نیست.</p>
      </div>
      {empty ? <div className="card"><h3>هنوز چیزی ذخیره نکرده‌ای</h3><p>در صفحه Disorder، Concept یا Therapy گزینه ذخیره را بزن.</p></div> : (
        <>
          <section className="stack">
            <div className="search-section-head"><h2>درمان‌ها</h2><span>{data.therapies.length.toLocaleString("fa-IR")}</span></div>
            <div className="grid">
              {data.therapies.map(item => <Link className="card" href={`/therapies/${item.therapy.slug}`} key={`t-${item.id}`}><div className="meta">{item.therapy.family.name_fa || item.therapy.family.name_en}</div><h3>{item.therapy.name_fa || item.therapy.name_en}</h3><div className="latin-label">{item.therapy.name_en}</div><p>{item.therapy.summary}</p></Link>)}
            </div>
            {!data.therapies.length && <p className="muted">درمان ذخیره‌شده‌ای نداری.</p>}
          </section>
          <section className="stack">
            <div className="search-section-head"><h2>اختلالات</h2><span>{data.disorders.length.toLocaleString("fa-IR")}</span></div>
            <div className="grid">{data.disorders.map(item => <Link className="card" href={`/disorders/${item.disorder.slug}`} key={`d-${item.id}`}><div className="meta">{item.disorder.category}</div><h3>{item.disorder.name_fa || item.disorder.name_en}</h3><p>{item.disorder.short_description}</p></Link>)}</div>
            {!data.disorders.length && <p className="muted">اختلال ذخیره‌شده‌ای نداری.</p>}
          </section>
          <section className="stack">
            <div className="search-section-head"><h2>مفاهیم</h2><span>{data.concepts.length.toLocaleString("fa-IR")}</span></div>
            <div className="grid">{data.concepts.map(item => <Link className="card" href={`/concepts/${item.concept.slug}`} key={`c-${item.id}`}><div className="meta">مفهوم</div><h3>{item.concept.name_fa || item.concept.name_en}</h3><p>{item.concept.simple_definition}</p></Link>)}</div>
            {!data.concepts.length && <p className="muted">مفهوم ذخیره‌شده‌ای نداری.</p>}
          </section>
        </>
      )}
    </main>
  );
}
