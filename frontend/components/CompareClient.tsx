"use client";

import { useEffect, useMemo, useState } from "react";
import { api } from "@/lib/api";
import type { Disorder, DisorderDetail } from "@/lib/types";

export default function CompareClient({ initialSlug }: { initialSlug?: string }) {
  const [all, setAll] = useState<Disorder[]>([]);
  const [selected, setSelected] = useState<string[]>(initialSlug ? [initialSlug] : []);
  const [items, setItems] = useState<DisorderDetail[]>([]);
  const [query, setQuery] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    api<{ results: Disorder[] }>("/disorders/")
      .then(x => setAll(x.results))
      .catch((e: any) => setError(e.message || "دریافت اختلالات انجام نشد."))
      .finally(() => setLoading(false));
  }, []);

  useEffect(() => {
    if (initialSlug) setSelected(s => s.includes(initialSlug) ? s : [initialSlug, ...s].slice(0, 4));
  }, [initialSlug]);

  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase();
    if (!q) return all;
    return all.filter(d => `${d.name_fa} ${d.name_en} ${d.category}`.toLowerCase().includes(q));
  }, [all, query]);

  function toggle(slug: string) {
    setSelected(s => s.includes(slug) ? s.filter(x => x !== slug) : s.length < 4 ? [...s, slug] : s);
  }

  async function compare() {
    if (selected.length < 2) return;
    try {
      setError("");
      setItems(await api<DisorderDetail[]>(`/disorders/compare/?slugs=${selected.join(",")}`));
    } catch (e: any) {
      setError(e.message || "مقایسه انجام نشد.");
    }
  }

  return (
    <div className="stack">
      <div className="card stack" style={{ gap: 14 }}>
        <div>
          <h3>۲ تا ۴ اختلال انتخاب کن</h3>
          <p className="muted small">{selected.length} اختلال انتخاب شده است.</p>
        </div>
        <input className="search" value={query} onChange={e => setQuery(e.target.value)} placeholder="جست‌وجو برای افزودن به مقایسه..." />
        {loading ? <p className="muted">در حال دریافت اختلالات...</p> : (
          <div className="compare-picker">
            {filtered.map(d => (
              <button
                key={d.slug}
                className={`compare-option ${selected.includes(d.slug) ? "selected" : ""}`}
                onClick={() => toggle(d.slug)}
              >
                <span>{d.name_fa || d.name_en}</span>
                <small>{d.category}</small>
              </button>
            ))}
          </div>
        )}
        <div className="actions">
          <button className="button primary" disabled={selected.length < 2} onClick={compare}>ساخت جدول مقایسه</button>
          {selected.length > 0 && <button className="button" onClick={() => { setSelected([]); setItems([]); }}>پاک‌کردن انتخاب‌ها</button>}
        </div>
        {error && <p className="error">{error}</p>}
      </div>

      {items.length > 0 && (
        <div className="compare-table">
          <table>
            <thead>
              <tr>
                <th>بعد مقایسه</th>
                {items.map(x => <th key={x.slug}>{x.name_fa || x.name_en}</th>)}
              </tr>
            </thead>
            <tbody>
              <tr><td>دسته</td>{items.map(x => <td key={x.slug}>{x.category}</td>)}</tr>
              <tr><td>خلاصه</td>{items.map(x => <td key={x.slug}>{x.short_description}</td>)}</tr>
              <tr><td>شروع معمول</td>{items.map(x => <td key={x.slug}>{x.typical_onset || "متغیر"}</td>)}</tr>
              <tr><td>ویژگی‌های بالینی</td>{items.map(x => <td key={x.slug}>{x.clinical_features}</td>)}</tr>
              <tr><td>تمرکز ارزیابی</td>{items.map(x => <td key={x.slug}>{x.assessment_overview}</td>)}</tr>
              <tr><td>نشانه‌های ثبت‌شده</td>{items.map(x => <td key={x.slug}>{x.symptoms.map(s => s.name_fa || s.name_en).join("، ") || "ثبت نشده"}</td>)}</tr>
              <tr><td>سیر</td>{items.map(x => <td key={x.slug}>{x.course_note}</td>)}</tr>
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
