"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import { hasToken } from "@/lib/auth";

export default function NotesPage() {
  const [data, setData] = useState<{ disorders: any[]; concepts: any[] } | null>(null);
  const [error, setError] = useState("");

  useEffect(() => {
    if (!hasToken()) { location.href = "/login"; return; }
    Promise.all([
      api<any[]>("/notes/", {}, true),
      api<any[]>("/concept-notes/", {}, true),
    ])
      .then(([disorders, concepts]) => setData({ disorders, concepts }))
      .catch((e: any) => setError(e.message || "دریافت یادداشت‌ها انجام نشد."));
  }, []);

  return (
    <main className="shell page stack">
      <div><div className="meta">یادداشت‌های من · Universal Base</div><h1 className="section-title" style={{ fontSize: 44 }}>یادداشت‌های Disorder و Concept را کنار هم نگه دار.</h1></div>
      {error && <div className="card error-state"><p>{error}</p></div>}
      {!data && !error && <p className="muted">در حال بارگذاری یادداشت‌ها...</p>}
      {data && !data.disorders.length && !data.concepts.length && <div className="card"><h3>هنوز یادداشتی نداری</h3><p>از صفحه هر اختلال یا مفهوم، بخش «یادداشت من» را باز کن.</p></div>}
      {data && data.disorders.length > 0 && (
        <section className="stack">
          <div className="search-section-head"><h2>یادداشت اختلالات</h2><span>{data.disorders.length.toLocaleString("fa-IR")}</span></div>
          <div className="grid">{data.disorders.map(note => <Link className="card" href={`/disorders/${note.disorder.slug}`} key={`d-${note.id}`}><div className="meta">{note.disorder.category}</div><h3>{note.disorder.name_fa || note.disorder.name_en}</h3><p>{note.body}</p></Link>)}</div>
        </section>
      )}
      {data && data.concepts.length > 0 && (
        <section className="stack">
          <div className="search-section-head"><h2>یادداشت مفاهیم</h2><span>{data.concepts.length.toLocaleString("fa-IR")}</span></div>
          <div className="grid">{data.concepts.map(note => <Link className="card" href={`/concepts/${note.concept.slug}`} key={`c-${note.id}`}><div className="meta">مفهوم</div><h3>{note.concept.name_fa || note.concept.name_en}</h3><p>{note.body}</p></Link>)}</div>
        </section>
      )}
    </main>
  );
}
