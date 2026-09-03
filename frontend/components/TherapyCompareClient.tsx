"use client";

import Link from "next/link";
import { useEffect, useMemo, useRef, useState } from "react";
import { api } from "@/lib/api";
import { normalizePersianSearch } from "@/lib/text";
import type { Paginated, Therapy, TherapyCompareResponse, TherapyDetail } from "@/lib/types";

function label(value: string) {
  const labels: Record<string, string> = {
    guideline_recommended: "توصیه‌شده در راهنما",
    commonly_used: "کاربرد رایج",
    adjunctive: "مکمل",
    alternative: "جایگزین",
    context_dependent: "وابسته به زمینه",
    not_first_line: "غیرخط اول",
    research_context: "زمینه پژوهشی",
    guideline: "راهنمای بالینی",
    systematic_review: "مرور نظام‌مند / فراتحلیل",
    controlled_trials: "کارآزمایی کنترل‌شده",
    observational: "شواهد مشاهده‌ای",
    mixed: "شواهد مختلط",
    emerging: "شواهد در حال شکل‌گیری",
    insufficient: "شواهد ناکافی",
    core: "محوری",
    common: "رایج",
    optional: "اختیاری",
    adapted: "انطباق‌یافته",
    component: "مؤلفه",
  };
  return labels[value] || value.replaceAll("_", " ");
}

function joined(values: string[], fallback = "ثبت نشده") {
  const rows = values.filter(Boolean);
  return rows.length ? rows.join("، ") : fallback;
}

export default function TherapyCompareClient({ initialSlug }: { initialSlug?: string }) {
  const [all, setAll] = useState<Therapy[]>([]);
  const [selected, setSelected] = useState<string[]>([]);
  const [items, setItems] = useState<TherapyDetail[]>([]);
  const [note, setNote] = useState("");
  const [query, setQuery] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);
  const [comparing, setComparing] = useState(false);
  const loadRef = useRef<AbortController | null>(null);
  const compareRef = useRef<AbortController | null>(null);

  useEffect(() => {
    const controller = new AbortController();
    loadRef.current = controller;
    setLoading(true);
    api<Paginated<Therapy>>("/therapies/?page_size=100", { signal: controller.signal })
      .then(data => {
        if (!controller.signal.aborted) setAll(data.results);
      })
      .catch((reason: any) => {
        if (reason?.name !== "AbortError") setError(reason?.message || "دریافت درمان‌ها انجام نشد.");
      })
      .finally(() => {
        if (!controller.signal.aborted) setLoading(false);
      });
    return () => controller.abort();
  }, []);

  useEffect(() => {
    if (initialSlug && all.some(item => item.slug === initialSlug)) {
      setSelected(current => current.includes(initialSlug) ? current : [initialSlug, ...current].slice(0, 4));
    }
  }, [initialSlug, all]);

  useEffect(() => () => compareRef.current?.abort(), []);

  const filtered = useMemo(() => {
    const q = normalizePersianSearch(query.trim());
    if (!q) return all;
    return all.filter(item => normalizePersianSearch([
      item.name_fa,
      item.name_en,
      item.slug,
      item.family.name_fa,
      item.family.name_en,
      item.summary,
      ...item.aliases.map(alias => alias.text),
      ...item.classifications.flatMap(row => [row.name_fa, row.name_en]),
    ].filter(Boolean).join(" ")).includes(q));
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
        setNote("");
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
    setComparing(true);
    setError("");
    setItems([]);
    setNote("");
    try {
      const data = await api<TherapyCompareResponse>(
        `/therapies/compare/?slugs=${selected.map(encodeURIComponent).join(",")}`,
        { signal: controller.signal },
      );
      if (!controller.signal.aborted) {
        setItems(data.items);
        setNote(data.note);
      }
    } catch (reason: any) {
      if (reason?.name !== "AbortError") setError(reason?.message || "مقایسه درمان‌ها انجام نشد.");
    } finally {
      if (!controller.signal.aborted) setComparing(false);
    }
  }

  return (
    <div className="stack therapy-compare-client">
      <section className="card stack therapy-compare-picker" style={{ gap: 14 }}>
        <div>
          <div className="meta">Therapy Compare · structured only</div>
          <h3>۲ تا ۴ رویکرد درمانی انتخاب کن</h3>
          <p className="muted small">این ابزار ساختار، تکنیک‌ها، زمینه‌های بالینی، مفاهیم، محدودیت‌ها و provenance را مقایسه می‌کند؛ نه «بهترین درمان» را.</p>
        </div>
        <input
          className="search"
          value={query}
          onChange={event => setQuery(event.target.value)}
          placeholder="نام فارسی/انگلیسی، CBT، خانواده یا classification..."
          aria-label="جست‌وجوی درمان برای مقایسه"
        />
        {loading ? <p className="muted">در حال دریافت Therapy Atlas...</p> : (
          <div className="compare-picker therapy-compare-options">
            {filtered.map(item => (
              <button
                className={`compare-option ${selected.includes(item.slug) ? "selected" : ""}`}
                onClick={() => toggle(item.slug)}
                key={item.slug}
                aria-pressed={selected.includes(item.slug)}
              >
                <span>{item.name_fa || item.name_en}</span>
                <small className="latin-label">{item.name_en}</small>
                <small>{item.family.name_fa || item.family.name_en}</small>
              </button>
            ))}
          </div>
        )}
        <div className="therapy-compare-selection-summary">
          <span>{selected.length.toLocaleString("fa-IR")} درمان انتخاب شده</span>
          {selected.length >= 4 && <small>سقف مقایسه ۴ درمان است.</small>}
        </div>
        <div className="actions">
          <button className="button primary" disabled={selected.length < 2 || comparing} onClick={compare}>
            {comparing ? "در حال ساخت مقایسه..." : "ساخت جدول Therapy Compare"}
          </button>
          {!!selected.length && <button className="button" onClick={() => { compareRef.current?.abort(); setComparing(false); setSelected([]); setItems([]); setNote(""); setError(""); }}>پاک‌کردن انتخاب‌ها</button>}
        </div>
        {error && <div className="error-state"><p>{error}</p></div>}
      </section>

      {!!items.length && (
        <>
          <div className="study-hint therapy-compare-note">{note}</div>
          <div className="compare-table therapy-compare-table">
            <table>
              <thead>
                <tr>
                  <th>بعد مقایسه</th>
                  {items.map(item => (
                    <th key={item.slug}>
                      <Link href={`/therapies/${item.slug}`}>{item.name_fa || item.name_en}</Link>
                      <small className="latin-label compare-head-en">{item.name_en}</small>
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                <tr><td>خانواده اصلی</td>{items.map(item => <td key={item.slug}>{item.family.name_fa || item.family.name_en}<small className="compare-cell-sub">{item.family.name_en}</small></td>)}</tr>
                <tr><td>وضعیت بررسی علمی</td>{items.map(item => <td key={item.slug}>{item.review_status === "source_checked" ? "Source checked" : item.review_status}</td>)}</tr>
                <tr><td>طبقه‌بندی‌ها</td>{items.map(item => <td key={item.slug}>{joined(item.classifications.map(row => row.name_fa || row.name_en))}</td>)}</tr>
                <tr><td>خلاصه</td>{items.map(item => <td key={item.slug}>{item.summary}</td>)}</tr>
                <tr><td>تعریف دانشگاهی</td>{items.map(item => <td key={item.slug}>{item.academic_definition || "ثبت نشده"}</td>)}</tr>
                <tr><td>اصول محوری</td>{items.map(item => <td key={item.slug}>{item.core_principles || "ثبت نشده"}</td>)}</tr>
                <tr><td>ساختار معمول</td>{items.map(item => <td key={item.slug}>{item.typical_structure || "ثبت نشده"}</td>)}</tr>
                <tr><td>تکنیک‌های ثبت‌شده</td>{items.map(item => <td key={item.slug}>{joined(item.techniques.map(row => `${row.technique.name_fa || row.technique.name_en} (${label(row.role)})`))}</td>)}</tr>
                <tr><td>منابع روابط تکنیکی</td>{items.map(item => <td key={item.slug}>{joined([...new Set(item.techniques.flatMap(row => row.sources.map(source => source.organization || source.title)))])}</td>)}</tr>
                <tr><td>زمینه‌های بالینی</td>{items.map(item => <td key={item.slug}>{joined(item.disorders.map(row => `${row.disorder.name_fa || row.disorder.name_en} · ${label(row.clinical_role)} · ${label(row.evidence_basis)}`))}</td>)}</tr>
                <tr><td>منابع روابط بالینی</td>{items.map(item => <td key={item.slug}>{joined([...new Set(item.disorders.flatMap(row => row.sources.map(source => source.organization || source.title)))])}</td>)}</tr>
                <tr><td>مفاهیم متصل</td>{items.map(item => <td key={item.slug}>{joined(item.concepts.map(row => row.concept.name_fa || row.concept.name_en))}</td>)}</tr>
                <tr><td>منابع روابط مفهومی</td>{items.map(item => <td key={item.slug}>{joined([...new Set(item.concepts.flatMap(row => row.sources.map(source => source.organization || source.title)))])}</td>)}</tr>
                <tr><td>زمینه‌های مناسب آموزشی</td>{items.map(item => <td key={item.slug}>{item.appropriate_contexts || "ثبت نشده"}</td>)}</tr>
                <tr><td>محدودیت‌ها</td>{items.map(item => <td key={item.slug}>{item.limitations || "ثبت نشده"}</td>)}</tr>
                <tr><td>Safety Notes</td>{items.map(item => <td key={item.slug}>{item.safety_notes || "ثبت نشده"}</td>)}</tr>
                <tr><td>یادداشت شواهد</td>{items.map(item => <td key={item.slug}>{item.evidence_note || "ثبت نشده"}</td>)}</tr>
                <tr><td>منابع مستقیم</td>{items.map(item => <td key={item.slug}>{joined(item.sources.map(source => source.organization || source.title))}</td>)}</tr>
              </tbody>
            </table>
          </div>
        </>
      )}
    </div>
  );
}
