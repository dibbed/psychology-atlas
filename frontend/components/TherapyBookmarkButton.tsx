"use client";

import { useEffect, useRef, useState } from "react";
import { api } from "@/lib/api";
import { hasToken } from "@/lib/auth";
import type { TherapyBookmark } from "@/lib/types";

export default function TherapyBookmarkButton({ slug }: { slug: string }) {
  const [saved, setSaved] = useState(false);
  const [loading, setLoading] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const requestRef = useRef<AbortController | null>(null);

  useEffect(() => {
    requestRef.current?.abort();
    if (!hasToken()) {
      setSaved(false);
      setLoading(false);
      setError("");
      return;
    }
    const controller = new AbortController();
    requestRef.current = controller;
    setLoading(true);
    setError("");
    api<TherapyBookmark[]>("/therapy-bookmarks/", { signal: controller.signal }, true)
      .then(items => {
        if (!controller.signal.aborted) setSaved(items.some(item => item.therapy.slug === slug));
      })
      .catch((reason: any) => {
        if (reason?.name !== "AbortError") setError(reason?.message || "وضعیت ذخیره درمان دریافت نشد.");
      })
      .finally(() => {
        if (!controller.signal.aborted) setLoading(false);
      });
    return () => controller.abort();
  }, [slug]);

  async function toggle() {
    if (!hasToken()) {
      location.href = "/login";
      return;
    }
    if (busy || loading) return;
    setBusy(true);
    setError("");
    try {
      if (saved) {
        await api(`/therapy-bookmarks/${slug}/`, { method: "DELETE" }, true);
        setSaved(false);
      } else {
        await api<TherapyBookmark>(
          "/therapy-bookmarks/",
          { method: "POST", body: JSON.stringify({ slug }) },
          true,
        );
        setSaved(true);
      }
    } catch (reason: any) {
      setError(reason?.message || "تغییر وضعیت ذخیره درمان انجام نشد.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="therapy-personal-action">
      <button className="button" onClick={toggle} disabled={busy || loading}>
        {loading ? "در حال بررسی..." : busy ? "در حال ذخیره..." : saved ? "درمان ذخیره شده ✓" : "ذخیره درمان"}
      </button>
      {error && <div className="error small" style={{ marginTop: 8 }}>{error}</div>}
    </div>
  );
}
