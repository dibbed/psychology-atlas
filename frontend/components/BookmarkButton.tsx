"use client";

import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import { hasToken } from "@/lib/auth";

export default function BookmarkButton({ slug }: { slug: string }) {
  const [saved, setSaved] = useState(false);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    if (!hasToken()) return;
    api<any[]>("/bookmarks/", {}, true)
      .then(items => setSaved(items.some(x => x.disorder.slug === slug)))
      .catch(() => {});
  }, [slug]);

  async function toggle() {
    if (!hasToken()) {
      location.href = "/login";
      return;
    }
    setBusy(true);
    try {
      if (saved) {
        await api(`/bookmarks/${slug}/`, { method: "DELETE" }, true);
        setSaved(false);
      } else {
        await api("/bookmarks/", { method: "POST", body: JSON.stringify({ slug }) }, true);
        setSaved(true);
      }
    } finally {
      setBusy(false);
    }
  }

  return (
    <button className="button" onClick={toggle} disabled={busy}>
      {busy ? "در حال ذخیره..." : saved ? "ذخیره شده ✓" : "ذخیره موضوع"}
    </button>
  );
}
