"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import { clearTokens, hasToken } from "@/lib/auth";
import type { Concept, ConceptNote, Disorder, Therapy, TherapyNote, UserNote } from "@/lib/types";

type DisorderNote = UserNote & { id: number; disorder: Disorder };
type SavedConceptNote = ConceptNote & { id: number; concept: Concept };
type SavedTherapyNote = TherapyNote & { id: number; therapy: Therapy };
type NotesData = { disorders: DisorderNote[]; concepts: SavedConceptNote[]; therapies: SavedTherapyNote[] };

export default function NotesPage() {
  const [data, setData] = useState<NotesData | null>(null);
  const [error, setError] = useState("");

  useEffect(() => {
    if (!hasToken()) { location.href = "/login"; return; }
    const controller = new AbortController();
    setError("");
    Promise.all([
      api<DisorderNote[]>("/notes/", { signal: controller.signal }, true),
      api<SavedConceptNote[]>("/concept-notes/", { signal: controller.signal }, true),
      api<SavedTherapyNote[]>("/therapy-notes/", { signal: controller.signal }, true),
    ])
      .then(([disorders, concepts, therapies]) => {
        if (!controller.signal.aborted) setData({ disorders, concepts, therapies });
      })
      .catch((reason: any) => {
        if (reason?.name !== "AbortError") setError(reason?.message || "دریافت یادداشت‌ها انجام نشد.");
      });
    return () => controller.abort();
  }, []);

  const empty = data && !data.disorders.length && !data.concepts.length && !data.therapies.length;

  return (
    <main className="shell page stack">
      <div>
        <div className="meta">یادداشت‌های من · Private Library</div>
        <h1 className="section-title" style={{ fontSize: 44 }}>یادداشت‌های Disorder، Concept و Therapy را کنار هم نگه دار.</h1>
        <p className="section-copy">یادداشت Therapy خصوصی است و محتوای علمی، Graph یا recommendation سیستم را تغییر نمی‌دهد.</p>
      </div>
      {error && <div className="card error-state"><h3>یادداشت‌ها بارگذاری نشد</h3><p>{error}</p><div className="actions"><button className="button primary" onClick={() => location.reload()}>تلاش دوباره</button><button className="button" onClick={() => { clearTokens(); location.href = "/login"; }}>ورود دوباره</button></div></div>}
      {!data && !error && <p className="muted">در حال بارگذاری یادداشت‌ها...</p>}
      {empty && <div className="card"><h3>هنوز یادداشتی نداری</h3><p>از صفحه هر اختلال، مفهوم یا درمان، بخش «یادداشت من» را باز کن.</p></div>}
      {data && data.therapies.length > 0 && (
        <section className="stack">
          <div className="search-section-head"><h2>یادداشت درمان‌ها</h2><span>{data.therapies.length.toLocaleString("fa-IR")}</span></div>
          <div className="grid">{data.therapies.map(note => <Link className="card" href={`/therapies/${note.therapy.slug}`} key={`t-${note.id}`}><div className="meta">{note.therapy.family.name_fa || note.therapy.family.name_en}</div><h3>{note.therapy.name_fa || note.therapy.name_en}</h3><div className="latin-label">{note.therapy.name_en}</div><p className="note-preview">{note.body}</p></Link>)}</div>
        </section>
      )}
      {data && data.disorders.length > 0 && (
        <section className="stack">
          <div className="search-section-head"><h2>یادداشت اختلالات</h2><span>{data.disorders.length.toLocaleString("fa-IR")}</span></div>
          <div className="grid">{data.disorders.map(note => <Link className="card" href={`/disorders/${note.disorder.slug}`} key={`d-${note.id}`}><div className="meta">{note.disorder.category}</div><h3>{note.disorder.name_fa || note.disorder.name_en}</h3><p className="note-preview">{note.body}</p></Link>)}</div>
        </section>
      )}
      {data && data.concepts.length > 0 && (
        <section className="stack">
          <div className="search-section-head"><h2>یادداشت مفاهیم</h2><span>{data.concepts.length.toLocaleString("fa-IR")}</span></div>
          <div className="grid">{data.concepts.map(note => <Link className="card" href={`/concepts/${note.concept.slug}`} key={`c-${note.id}`}><div className="meta">مفهوم</div><h3>{note.concept.name_fa || note.concept.name_en}</h3><p className="note-preview">{note.body}</p></Link>)}</div>
        </section>
      )}
    </main>
  );
}
