"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import { hasToken } from "@/lib/auth";
import type { UserNote } from "@/lib/types";

export default function NotesPage() {
  const [notes, setNotes] = useState<UserNote[] | null>(null);
  const [error, setError] = useState("");

  useEffect(() => {
    if (!hasToken()) { location.href = "/login"; return; }
    api<UserNote[]>("/notes/", {}, true)
      .then(setNotes)
      .catch((e: any) => setError(e.message || "دریافت یادداشت‌ها انجام نشد."));
  }, []);

  return (
    <main className="shell page stack">
      <div>
        <div className="meta">یادداشت‌های من</div>
        <h1 className="section-title" style={{ fontSize: 44 }}>نکته‌های شخصی برای مرور بعدی.</h1>
      </div>
      {error && <div className="card error-state"><p>{error}</p></div>}
      {!notes && !error && <p className="muted">در حال بارگذاری یادداشت‌ها...</p>}
      {notes && notes.length === 0 && <div className="card"><h3>هنوز یادداشتی نداری</h3><p>از صفحه هر اختلال، تب «یادداشت من» را باز کن.</p></div>}
      {notes && notes.length > 0 && (
        <div className="grid">
          {notes.map(note => (
            <Link className="card" href={`/disorders/${note.disorder?.slug}`} key={note.id}>
              <div className="meta">{note.disorder?.category}</div>
              <h3>{note.disorder?.name_fa || note.disorder?.name_en}</h3>
              <p>{note.body}</p>
            </Link>
          ))}
        </div>
      )}
    </main>
  );
}
