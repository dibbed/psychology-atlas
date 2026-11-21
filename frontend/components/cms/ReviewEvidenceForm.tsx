"use client";
import { useEffect, useState } from "react";
import { cms, CmsPage, ReviewEvidence, ReviewSource, reviewFieldLabels } from "@/lib/cms";
import { faNumber } from "@/lib/fa";
import { CmsState } from "./CmsShell";

export default function ReviewEvidenceForm({ value, fields, populated, disabled, onChange, onSubmit, labels = reviewFieldLabels }: {
  value: ReviewEvidence[]; fields: string[]; populated: string[]; disabled: boolean;
  onChange: (value: ReviewEvidence[]) => void; onSubmit: () => void;
  labels?: Record<string, string>;
}) {
  const [search, setSearch] = useState("");
  const [query, setQuery] = useState("");
  const [page, setPage] = useState(1);
  const [sources, setSources] = useState<CmsPage<ReviewSource>>();
  const [error, setError] = useState<unknown>();
  const [retry, setRetry] = useState(0);
  const [target, setTarget] = useState(0);
  const [selected, setSelected] = useState<Record<number, ReviewSource>>({});
  useEffect(() => {
    let active = true; setSources(undefined); setError(undefined);
    const params = new URLSearchParams({ q: query, page: String(page) });
    cms<CmsPage<ReviewSource>>(`/reviews/sources/?${params}`).then(result => { if (active) setSources(result.data); })
      .catch(failure => { if (active) setError(failure); });
    return () => { active = false; };
  }, [query, page, retry]);
  const uncovered = populated.filter(field => !value.some(item => item.fields.includes(field)));
  const valid = value.length >= 1 && value.length <= 20 && !uncovered.length && value.every(item =>
    Number.isSafeInteger(item.source_id) && item.source_id > 0 && !!item.locator.trim() && item.locator.trim().length <= 1000 &&
    item.fields.length > 0 && item.fields.every(field => fields.includes(field)));
  const update = (index: number, patch: Partial<ReviewEvidence>) => onChange(value.map((item, i) => i === index ? { ...item, ...patch } : item));
  return <section className="card stack" aria-labelledby="review-evidence-title">
    <h2 id="review-evidence-title">شواهد پیشنهاد</h2>
    <p className="muted">برای همهٔ فیلدهای پُر شاهد ثبت کنید؛ هر شاهد یک منبع، نشانی دقیق و فیلدهای پشتیبانی‌شده دارد. حداکثر ۲۰ شاهد. منابع در این صفحه ویرایش نمی‌شوند.</p>
    <form className="cms-filters" onSubmit={event => { event.preventDefault(); setPage(1); setQuery(search.trim()); }}>
      <label>جست‌وجوی منبع با عنوان، DOI یا PMID<input type="search" value={search} maxLength={200} dir="auto" onChange={event => setSearch(event.target.value)} /></label>
      <button className="button secondary">جست‌وجوی منابع</button>
    </form>
    <label>انتخاب منبع برای شاهد<select value={target} disabled={disabled || !value.length} onChange={event => setTarget(Number(event.target.value))}>
      {value.map((_, index) => <option key={index} value={index}>شاهد {faNumber(index + 1)}</option>)}
    </select></label>
    {error ? <CmsState error={error} retry={() => setRetry(n => n + 1)} /> : !sources ? <CmsState loading /> : <>
      {!sources.results.length && <CmsState empty="منبعی یافت نشد؛ جست‌وجو را تغییر دهید." />}
      <ul className="cms-review-sources">{sources.results.map(source => <li key={source.id}>
        <div><strong dir="auto">{source.title}</strong><p className="cms-id"><bdi>DOI: {source.doi || "—"} · PMID: {source.pmid || "—"}</bdi></p><p className="muted">وضعیت منبع: <bdi>{source.verification_status}</bdi></p></div>
        <button type="button" className="button secondary" disabled={disabled || !value[target]} onClick={() => { setSelected(current => ({ ...current, [source.id]: source })); update(target, { source_id: source.id }); }}>انتخاب منبع {faNumber(source.id)}</button>
      </li>)}</ul>
      <nav className="cms-pagination" aria-label="صفحه‌بندی منابع">
        <button type="button" className="button secondary" disabled={sources.page <= 1} onClick={() => setPage(n => n - 1)}>منابع قبلی</button>
        <span>صفحهٔ {faNumber(sources.page)} · {faNumber(sources.count)} منبع</span>
        <button type="button" className="button secondary" disabled={sources.page * sources.page_size >= sources.count} onClick={() => setPage(n => n + 1)}>منابع بعدی</button>
      </nav>
    </>}
    <form data-testid="review-evidence-form" className="stack" onSubmit={event => { event.preventDefault(); if (valid && !disabled) onSubmit(); }}>
      <fieldset disabled={disabled} className="cms-fieldset"><legend>شواهد و فیلدهای پشتیبانی‌شده</legend>
        {value.map((item, index) => <fieldset className="cms-merge-field stack" key={index}><legend>شاهد {faNumber(index + 1)}</legend>
          <p>منبع انتخاب‌شده: <bdi>{selected[item.source_id]?.title || (item.source_id ? `شناسهٔ ${faNumber(item.source_id)}` : "انتخاب نشده")}</bdi></p>
          <label>نشانی دقیق شاهد {faNumber(index + 1)}<input value={item.locator} dir="auto" required maxLength={1000} placeholder="صفحه، بخش، جدول یا نشانی دقیق" onChange={event => update(index, { locator: event.target.value })} /></label>
          <fieldset className="cms-review-fields"><legend>فیلدهای پشتیبانی‌شدهٔ شاهد {faNumber(index + 1)}</legend>{fields.map(field => <label key={field} className="cms-review-check">
            <input type="checkbox" checked={item.fields.includes(field)} onChange={event => update(index, { fields: event.target.checked ? [...item.fields, field] : item.fields.filter(key => key !== field) })} />{labels[field] || field}
          </label>)}</fieldset>
          <button type="button" className="button secondary" onClick={() => { onChange(value.filter((_, i) => i !== index)); setTarget(0); }}>حذف شاهد {faNumber(index + 1)}</button>
        </fieldset>)}
        <button type="button" className="button secondary" disabled={value.length >= 20} onClick={() => { setTarget(value.length); onChange([...value, { source_id: 0, locator: "", fields: [] }]); }}>افزودن شاهد</button>
        {uncovered.length > 0 && <p className="cms-notice" role="status">فیلدهای بدون شاهد: {uncovered.map(field => labels[field] || field).join("، ")}</p>}
        <button data-testid="review-submit" className="button primary" disabled={!valid}>ارسال پیشنهاد برای بررسی</button>
      </fieldset>
    </form>
  </section>;
}
