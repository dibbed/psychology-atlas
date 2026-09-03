"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import { api } from "@/lib/api";
import { faNumber } from "@/lib/fa";
import { normalizePersianSearch } from "@/lib/text";
import type { DSMRecordDetail, Disorder, DisorderDetail } from "@/lib/types";

export default function CompareClient({ initialSlug }: { initialSlug?: string }) {
  const [all, setAll] = useState<Disorder[]>([]);
  const [selected, setSelected] = useState<string[]>([]);
  const [items, setItems] = useState<DisorderDetail[]>([]);
  const [dsmItems, setDsmItems] = useState<Record<string, DSMRecordDetail | null>>({});
  const [query, setQuery] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);
  const [comparing, setComparing] = useState(false);
  const compareRef = useRef<AbortController | null>(null);

  useEffect(() => {
    const controller = new AbortController();
    api<{ results: Disorder[] }>("/disorders/?page_size=300", { signal: controller.signal })
      .then(x => { if (!controller.signal.aborted) setAll(x.results); })
      .catch((e: any) => { if (e?.name !== "AbortError") setError(e.message || "دریافت اختلالات انجام نشد."); })
      .finally(() => { if (!controller.signal.aborted) setLoading(false); });
    return () => controller.abort();
  }, []);

  useEffect(() => () => compareRef.current?.abort(), []);

  useEffect(() => {
    if (initialSlug && all.some(d => d.slug === initialSlug)) {
      setSelected(s => s.includes(initialSlug) ? s : [initialSlug, ...s].slice(0, 4));
    }
  }, [initialSlug, all]);

  const filtered = useMemo(() => {
    const q = normalizePersianSearch(query.trim());
    if (!q) return all;
    return all.filter(d => normalizePersianSearch(`${d.name_fa} ${d.name_en} ${d.category}`).includes(q));
  }, [all, query]);

  function toggle(slug: string) {
    setSelected(current => {
      const next = current.includes(slug)
        ? current.filter(value => value !== slug)
        : current.length < 4 ? [...current, slug] : current;
      if (next !== current) {
        compareRef.current?.abort();
        setComparing(false);
        setItems([]);
        setDsmItems({});
        setError("");
      }
      return next;
    });
  }

  async function compare() {
    if (selected.length < 2 || comparing) return;
    compareRef.current?.abort();
    const controller = new AbortController();
    compareRef.current = controller;
    try {
      setComparing(true);
      setError("");
      const [comparison, dsmRows] = await Promise.all([
        api<DisorderDetail[]>(`/disorders/compare/?slugs=${selected.join(",")}`, { signal: controller.signal }),
        Promise.all(selected.map(async slug => {
          try {
            const record = await api<DSMRecordDetail>(`/dsm/records/by-disorder/${slug}/?detail=true`, { signal: controller.signal });
            return [slug, record] as const;
          } catch (reason: any) {
            if (reason?.name === "AbortError") throw reason;
            return [slug, null] as const;
          }
        })),
      ]);
      if (!controller.signal.aborted) {
        setItems(comparison);
        setDsmItems(Object.fromEntries(dsmRows));
      }
    } catch (e: any) {
      if (e?.name !== "AbortError") {
        setItems([]);
        setDsmItems({});
        setError(e.message || "مقایسه انجام نشد.");
      }
    } finally {
      if (!controller.signal.aborted) setComparing(false);
    }
  }

  return (
    <div className="stack">
      <div className="card stack" style={{ gap: 14 }}>
        <div>
          <h3>۲ تا ۴ اختلال انتخاب کن</h3>
          <p className="muted small">{faNumber(selected.length)} اختلال انتخاب شده است.</p>
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
                {d.name_en && d.name_en !== d.name_fa && <small className="latin-label">{d.name_en}</small>}
                <small>{d.category}</small>
              </button>
            ))}
          </div>
        )}
        <div className="actions">
          <button className="button primary" disabled={selected.length < 2 || comparing} onClick={compare}>{comparing ? "در حال مقایسه..." : "ساخت جدول مقایسه"}</button>
          {selected.length > 0 && <button className="button" onClick={() => { compareRef.current?.abort(); setSelected([]); setItems([]); setDsmItems({}); setError(""); setComparing(false); }}>پاک‌کردن انتخاب‌ها</button>}
        </div>
        {error && <p className="error">{error}</p>}
      </div>

      {items.length > 0 && (
        <div className="compare-table">
          <table>
            <thead>
              <tr>
                <th>بعد مقایسه</th>
                {items.map(x => <th key={x.slug}><span>{x.name_fa || x.name_en}</span>{x.name_en && x.name_en !== x.name_fa && <small className="latin-label compare-head-en">{x.name_en}</small>}</th>)}
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
              <tr className="compare-dsm-row"><td>وضعیت DSM MASTER</td>{items.map(x => <td key={x.slug}>{dsmItems[x.slug]?.classification_status || "رکورد متصل ندارد"}</td>)}</tr>
              <tr className="compare-dsm-row"><td>خلاصه MASTER</td>{items.map(x => <td key={x.slug}>{dsmItems[x.slug]?.summary || "ثبت نشده"}</td>)}</tr>
              <tr className="compare-dsm-row"><td>ارزیابی هدفمند MASTER</td>{items.map(x => <td key={x.slug}>{dsmItems[x.slug]?.assessment.filter(item => typeof item === "string").slice(0, 6).join("، ") || "ثبت نشده"}</td>)}</tr>
              <tr className="compare-dsm-row"><td>افتراق‌های MASTER</td>{items.map(x => <td key={x.slug}>{dsmItems[x.slug]?.differential.slice(0, 6).map(item => typeof item === "string" ? item : typeof item === "object" && item && "عنوان" in item ? String((item as Record<string, unknown>)["عنوان"]) : "").filter(Boolean).join("، ") || "ثبت نشده"}</td>)}</tr>
              <tr className="compare-dsm-row"><td>زمینه فرهنگی/رشدی</td>{items.map(x => <td key={x.slug}>{dsmItems[x.slug]?.context_considerations || "ثبت نشده"}</td>)}</tr>
              <tr className="compare-dsm-row"><td>نکته امتحانی MASTER</td>{items.map(x => <td key={x.slug}>{dsmItems[x.slug]?.exam_tip || "ثبت نشده"}</td>)}</tr>
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
