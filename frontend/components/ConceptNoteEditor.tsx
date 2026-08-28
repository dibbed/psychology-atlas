"use client";

import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import { hasToken } from "@/lib/auth";
import type { ConceptNote } from "@/lib/types";

export default function ConceptNoteEditor({ slug }: { slug: string }) {
  const [body, setBody] = useState("");
  const [status, setStatus] = useState("");
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [authenticated, setAuthenticated] = useState<boolean | null>(null);

  useEffect(() => {
    const signedIn = hasToken();
    setAuthenticated(signedIn);
    if (!signedIn) {
      setLoading(false);
      return;
    }
    api<ConceptNote>(`/concept-notes/${slug}/`, {}, true)
      .then(note => setBody(note.body || ""))
      .catch(() => setStatus("بارگذاری یادداشت مفهوم انجام نشد."))
      .finally(() => setLoading(false));
  }, [slug]);

  async function save() {
    if (busy) return;
    setBusy(true);
    setStatus("در حال ذخیره...");
    try {
      await api<ConceptNote>(`/concept-notes/${slug}/`, {
        method: "PUT",
        body: JSON.stringify({ body }),
      }, true);
      setStatus(body.trim() ? "یادداشت ذخیره شد." : "یادداشت خالی حذف شد.");
    } catch (e: any) {
      setStatus(e.message || "ذخیره یادداشت انجام نشد.");
    } finally {
      setBusy(false);
    }
  }

  async function remove() {
    if (busy) return;
    setBusy(true);
    try {
      await api(`/concept-notes/${slug}/`, { method: "DELETE" }, true);
      setBody("");
      setStatus("یادداشت حذف شد.");
    } catch (e: any) {
      setStatus(e.message || "حذف یادداشت انجام نشد.");
    } finally {
      setBusy(false);
    }
  }

  if (authenticated === null || loading) return <p className="muted">در حال بارگذاری یادداشت...</p>;
  if (!authenticated) return <div className="card"><p>برای نوشتن یادداشت شخصی، وارد حساب کاربری شو.</p></div>;

  return (
    <div className="card stack" style={{ gap: 12 }}>
      <textarea
        className="note-input"
        value={body}
        maxLength={12000}
        onChange={event => setBody(event.target.value)}
        placeholder="برداشت یا نکته شخصی درباره این مفهوم..."
        disabled={busy}
      />
      <div className="actions">
        <button className="button primary" onClick={save} disabled={busy}>{busy ? "در حال ذخیره..." : "ذخیره یادداشت"}</button>
        {body && <button className="button" onClick={remove} disabled={busy}>حذف</button>}
        {status && <span className="muted small">{status}</span>}
      </div>
    </div>
  );
}
