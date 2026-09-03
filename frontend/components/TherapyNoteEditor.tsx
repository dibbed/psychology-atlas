"use client";

import { useEffect, useRef, useState } from "react";
import { api } from "@/lib/api";
import { hasToken } from "@/lib/auth";
import type { TherapyNote } from "@/lib/types";

export default function TherapyNoteEditor({ slug }: { slug: string }) {
  const [body, setBody] = useState("");
  const [status, setStatus] = useState("");
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [authenticated, setAuthenticated] = useState<boolean | null>(null);
  const loadRef = useRef<AbortController | null>(null);

  useEffect(() => {
    loadRef.current?.abort();
    const signedIn = hasToken();
    setAuthenticated(signedIn);
    setStatus("");
    if (!signedIn) {
      setBody("");
      setLoading(false);
      return;
    }
    const controller = new AbortController();
    loadRef.current = controller;
    setLoading(true);
    api<TherapyNote>(`/therapy-notes/${slug}/`, { signal: controller.signal }, true)
      .then(note => {
        if (!controller.signal.aborted) setBody(note.body || "");
      })
      .catch((reason: any) => {
        if (reason?.name !== "AbortError") setStatus(reason?.message || "بارگذاری یادداشت درمان انجام نشد.");
      })
      .finally(() => {
        if (!controller.signal.aborted) setLoading(false);
      });
    return () => controller.abort();
  }, [slug]);

  async function save() {
    if (busy) return;
    setBusy(true);
    setStatus("در حال ذخیره...");
    try {
      const note = await api<TherapyNote>(
        `/therapy-notes/${slug}/`,
        { method: "PUT", body: JSON.stringify({ body }) },
        true,
      );
      setBody(note.body || "");
      setStatus(note.exists === false ? "یادداشت خالی حذف شد." : "یادداشت درمان ذخیره شد.");
    } catch (reason: any) {
      setStatus(reason?.message || "ذخیره یادداشت درمان انجام نشد.");
    } finally {
      setBusy(false);
    }
  }

  async function remove() {
    if (busy) return;
    setBusy(true);
    setStatus("");
    try {
      await api(`/therapy-notes/${slug}/`, { method: "DELETE" }, true);
      setBody("");
      setStatus("یادداشت درمان حذف شد.");
    } catch (reason: any) {
      setStatus(reason?.message || "حذف یادداشت درمان انجام نشد.");
    } finally {
      setBusy(false);
    }
  }

  if (authenticated === null || loading) return <p className="muted">در حال بارگذاری یادداشت درمان...</p>;
  if (!authenticated) return <div className="card"><p>برای نوشتن یادداشت خصوصی روی این درمان، وارد حساب کاربری شو.</p></div>;

  return (
    <div className="card stack therapy-note-editor" style={{ gap: 12 }}>
      <div>
        <div className="meta">Private study note</div>
        <p className="muted small">این یادداشت فقط برای حساب خودت ذخیره می‌شود و وارد محتوای علمی یا Graph نمی‌شود.</p>
      </div>
      <textarea
        className="note-input"
        value={body}
        maxLength={12000}
        onChange={event => setBody(event.target.value)}
        placeholder="نکته‌ای درباره ساختار، تفاوت‌ها یا منابع این درمان برای مرور بعدی بنویس..."
        disabled={busy}
      />
      <div className="therapy-note-meta">
        <span>{body.length.toLocaleString("fa-IR")} / ۱۲٬۰۰۰</span>
      </div>
      <div className="actions">
        <button className="button primary" onClick={save} disabled={busy}>{busy ? "در حال ذخیره..." : "ذخیره یادداشت"}</button>
        {body && <button className="button" onClick={remove} disabled={busy}>حذف</button>}
        {status && <span className="muted small">{status}</span>}
      </div>
    </div>
  );
}
