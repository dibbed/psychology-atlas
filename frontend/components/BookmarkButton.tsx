"use client";

import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import { hasToken } from "@/lib/auth";

export default function BookmarkButton({ slug }: { slug: string }) {
  const [saved, setSaved] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    if (!hasToken()) return;
    api<any[]>("/bookmarks/", {}, true)
      .then(items => setSaved(items.some(x => x.disorder.slug === slug)))
      .catch(() => setError("وضعیت ذخیره‌شدن موضوع دریافت نشد."));
  }, [slug]);

  async function toggle() {
    if (!hasToken()) {
      location.href = "/login";
      return;
    }
    if (busy) return;
    setBusy(true);
    setError("");
    try {
      if (saved) {
        await api(`/bookmarks/${slug}/`, { method: "DELETE" }, true);
        setSaved(false);
      } else {
        await api("/bookmarks/", { method: "POST", body: JSON.stringify({ slug }) }, true);
        setSaved(true);
      }
    } catch (e: any) {
      setError(e.message || "تغییر وضعیت ذخیره موضوع انجام نشد.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div>
      <button className="button" onClick={toggle} disabled={busy}>
        {busy ? "در حال ذخیره..." : saved ? "ذخیره شده ✓" : "ذخیره موضوع"}
      </button>
      {error && <div className="error small" style={{ marginTop: 8 }}>{error}</div>}
    </div>
  );
}
