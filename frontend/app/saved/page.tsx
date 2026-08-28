"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { api } from "@/lib/api";
import { clearTokens, hasToken } from "@/lib/auth";

export default function SavedPage() {
  const [items, setItems] = useState<any[] | null>(null);
  const [error, setError] = useState("");

  useEffect(() => {
    if (!hasToken()) { location.href = "/login"; return; }
    api<any[]>("/bookmarks/", {}, true)
      .then(setItems)
      .catch((e: any) => setError(e.message || "دریافت ذخیره‌شده‌ها انجام نشد."));
  }, []);

  if (error) {
    return (
      <main className="shell page">
        <div className="card error-state">
          <h2>ذخیره‌شده‌ها بارگذاری نشد</h2>
          <p>{error}</p>
          <div className="actions" style={{ marginTop: 16 }}>
            <button className="button primary" onClick={() => location.reload()}>تلاش دوباره</button>
            <button className="button" onClick={() => { clearTokens(); location.href = "/login"; }}>ورود دوباره</button>
          </div>
        </div>
      </main>
    );
  }

  if (!items) return <main className="shell page"><p className="muted">در حال بارگذاری موضوعات ذخیره‌شده...</p></main>;

  return (
    <main className="shell page stack">
      <div>
        <div className="meta">ذخیره‌شده‌ها</div>
        <h1 className="section-title" style={{ fontSize: 44 }}>فهرست خصوصی تو برای مرور دوباره.</h1>
      </div>
      {items.length ? (
        <div className="grid">
          {items.map(x => (
            <Link className="card" href={`/disorders/${x.disorder.slug}`} key={x.id}>
              <div className="meta">{x.disorder.category}</div>
              <h3>{x.disorder.name_fa || x.disorder.name_en}</h3>
              <p>{x.disorder.short_description}</p>
            </Link>
          ))}
        </div>
      ) : (
        <div className="card"><h3>هنوز چیزی ذخیره نکرده‌ای</h3><p>صفحه یک اختلال را باز کن و گزینه «ذخیره موضوع» را بزن.</p></div>
      )}
    </main>
  );
}
