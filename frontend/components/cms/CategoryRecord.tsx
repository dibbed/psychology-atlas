"use client";
import { useEffect, useRef, useState } from "react";
import { CmsState, useCms } from "./CmsShell";
import { cms, CategoryPayload, CmsError, CmsPage, CmsRecord, CmsRevision, cmsDate, publicationLabels, revisionLabels } from "@/lib/cms";
import { faNumber } from "@/lib/fa";

const fields = ["name_en", "name_fa", "description"] as const;
const labels = { name_en: "نام علمی انگلیسی", name_fa: "نام فارسی", description: "توضیح" };
const blank: CategoryPayload = { name_en: "", name_fa: "", description: "" };
const values = (payload: CategoryPayload): CategoryPayload => ({ ...blank, ...payload });
const equal = (a: CategoryPayload, b: CategoryPayload) => fields.every(field => a[field] === b[field]);
type Snapshot = { data: CmsRecord; etag: string | null };

export default function CategoryRecord({ id }: { id?: string }) {
  const { me, can, setDirty, leave } = useCms();
  const [base, setBase] = useState<Snapshot>();
  const [form, setForm] = useState<CategoryPayload>(blank);
  const [loading, setLoading] = useState(!!id);
  const [error, setError] = useState<unknown>();
  const [saveError, setSaveError] = useState<unknown>();
  const [tab, setTab] = useState(id ? "detail" : "edit");
  const [busy, setBusy] = useState(false);
  const busyRef = useRef(false);
  const [saved, setSaved] = useState(false);
  const [conflict, setConflict] = useState<Snapshot>();
  const [choices, setChoices] = useState<Partial<Record<keyof CategoryPayload, "mine" | "current">>>({});
  const [history, setHistory] = useState<CmsPage<CmsRevision>>();
  const [historyError, setHistoryError] = useState<unknown>();
  const [historyPage, setHistoryPage] = useState(1);
  const [historyRetry, setHistoryRetry] = useState(0);
  const [back, setBack] = useState("/admin-console/content/category");
  const [retry, setRetry] = useState(0);
  const summary = useRef<HTMLDivElement>(null);
  const editable = can(id ? "cms_core_edit" : "cms_core_create") && (!base || ["legacy", "draft", "changes_requested"].includes(base.data.revision_status));
  const allowed = can("cms_core_view") && (!!id || editable);
  const dirty = !equal(form, values(base?.data.payload || blank));
  const failure = saveError instanceof CmsError ? saveError : undefined;
  const blocked = failure?.code === "UNKNOWN_OUTCOME" || failure?.status === 412 || failure?.status === 409 || !!conflict;
  useEffect(() => { setDirty(dirty || busy); return () => setDirty(false); }, [dirty, busy, setDirty]);
  useEffect(() => { if (saveError) summary.current?.focus(); }, [saveError]);
  useEffect(() => {
    const params = new URLSearchParams(new URLSearchParams(location.search).get("list") || "");
    const safe = new URLSearchParams();
    for (const key of ["q", "status", "sort", "page", "page_size"]) if (params.has(key)) safe.set(key, params.get(key)!);
    setBack(`/admin-console/content/category?${safe}`);
  }, []);
  useEffect(() => {
    if (!id || !allowed) return;
    let active = true; setLoading(true); setError(undefined);
    cms<CmsRecord>(`/content/category/${id}/`).then(snapshot => { if (active) { setBase(snapshot); setForm(values(snapshot.data.payload)); } }).catch(failure => { if (active) setError(failure); }).finally(() => { if (active) setLoading(false); });
    return () => { active = false; };
  }, [id, allowed, retry]);
  useEffect(() => {
    if (tab !== "history" || !id || !allowed) return;
    let active = true; setHistory(undefined); setHistoryError(undefined);
    cms<CmsPage<CmsRevision>>(`/content/category/${id}/revisions/?page=${historyPage}`).then(result => { if (active) setHistory(result.data); }).catch(failure => { if (active) setHistoryError(failure); });
    return () => { active = false; };
  }, [tab, id, allowed, historyPage, historyRetry, base?.data.version]);
  async function save(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (busyRef.current || blocked || !editable) return;
    busyRef.current = true; setBusy(true); setSaveError(undefined); setSaved(false);
    try {
      const snapshot = await cms<CmsRecord>(id ? `/content/category/${id}/revisions/` : "/content/category/", {
        method: "POST", headers: base?.etag ? { "If-Match": base.etag } : {},
        body: JSON.stringify({ payload: form, ...(id ? { base_digest: base?.data.canonical_digest, reason: "CONTENT_UPDATE" } : { reason: "DRAFT_CREATION" }) }),
      }, me.user.id);
      setBase(snapshot); setForm(values(snapshot.data.payload)); setDirty(false); setSaved(true);
      if (!id) { location.assign(`/admin-console/content/category/${snapshot.data.id}`); }
    } catch (failure) { setSaveError(failure); } finally { busyRef.current = false; setBusy(false); }
  }
  async function compareCurrent() {
    if (!id || busyRef.current) return;
    busyRef.current = true; setBusy(true);
    try {
      const current = await cms<CmsRecord>(`/content/category/${id}/`);
      const selections: typeof choices = {};
      fields.forEach(field => {
        if (form[field] === values(base?.data.payload || blank)[field]) selections[field] = "current";
        else if (values(current.data.payload)[field] === values(base?.data.payload || blank)[field] || form[field] === values(current.data.payload)[field]) selections[field] = "mine";
      });
      setChoices(selections); setConflict(current);
    } catch (failure) { setSaveError(failure); } finally { busyRef.current = false; setBusy(false); }
  }
  function merge() {
    if (!conflict || fields.some(field => !choices[field])) return;
    const current = values(conflict.data.payload);
    const merged = { ...form };
    fields.forEach(field => { if (choices[field] === "current") merged[field] = current[field]; });
    setBase(conflict); setForm(merged); setConflict(undefined); setSaveError(undefined); setSaved(equal(current, merged));
  }
  if (!allowed) return <CmsState error={new CmsError(403, "PERMISSION_DENIED", "")} />;
  if (loading) return <CmsState loading />;
  if (error) return <CmsState error={error} retry={() => setRetry(value => value + 1)} />;
  return <div className="stack">
    <div className="cms-actions"><a className="cms-link" href={back}>→ بازگشت به فهرست با فیلتر قبلی</a>{base && can("cms_core_view") && <a className="button secondary" data-testid="category-review-link" href={`/admin-console/reviews/category/${base.data.id}`}>بررسی پیشنهاد و شواهد</a>}</div>
    <div className="cms-title"><p className="eyebrow">دسته‌بندی / {id ? "جزئیات و نسخه‌ها" : "پیشنهاد جدید"}</p><h1><bdi>{base?.data.payload.name_fa || base?.data.payload.name_en || "پیش‌نویس دسته‌بندی"}</bdi></h1>
      {base && <div className="cms-actions"><span className="cms-badge">نسخهٔ {faNumber(base.data.version)}</span><span className="cms-badge">{revisionLabels[base.data.revision_status]}</span><span className="muted">{publicationLabels[base.data.publication]}</span></div>}
    </div>
    <nav className="cms-tabs" aria-label="نماهای دسته‌بندی">{[...(id ? [["detail", "نمای کلی"]] : []), ...(editable ? [["edit", "ویرایش پیشنهاد"]] : []), ["preview", "پیش‌نمایش و اختلاف"], ...(id ? [["history", "تاریخچهٔ نسخه‌ها"]] : [])].map(([value, label]) => <button key={value} className="button secondary" aria-pressed={tab === value} onClick={() => setTab(value)}>{label}</button>)}</nav>
    {tab === "detail" && base && <section className="card stack"><h2>آخرین پیشنهاد ذخیره‌شده</h2>{fields.map(field => <div key={field}><h3>{labels[field]}</h3><p className="cms-prose" dir={field === "name_en" ? "ltr" : "auto"}>{base.data.payload[field] || "ثبت نشده"}</p></div>)}<p className="muted">این snapshot پیشنهاد CMS است. میراث بدون تصمیم علمی ثبت شده و پیشنهاد جدید هنوز منتشر نشده است.</p><p className="cms-id">شناسهٔ محتوا: <bdi>{base.data.id}</bdi></p></section>}
    <form hidden={tab !== "edit"} onSubmit={save} className="card stack" aria-label="ویرایش دسته‌بندی">
      <div className="cms-section-head"><h2>{id ? "ویرایش پیشنهاد" : "پیش‌نویس جدید"}</h2><span className="muted">{dirty ? "ذخیره نشده" : "بدون تغییر"}</span></div>
      <p className="cms-notice">فقط نام‌ها و توضیح قابل‌ویرایش‌اند. ذخیرهٔ این فرم، محتوای اصلی را تغییر نمی‌دهد.</p>
      {saveError != null && <div ref={summary} tabIndex={-1} className="cms-error" role="alert"><h3>{failure?.status === 412 ? "نسخه تغییر کرده است" : failure?.status === 403 ? "مجوز ذخیره ندارید" : "ذخیره تأیید نشد"}</h3><p>{failure?.message || "ذخیره انجام نشد."}</p>
        {failure?.details.field_errors && <ul>{Object.entries(failure.details.field_errors).map(([field, errors]) => <li key={field}><a className="cms-link" href={`#cms-${field}`}>{labels[field as keyof CategoryPayload] || field}: {Array.isArray(errors) ? errors.join(" · ") : String(errors)}</a></li>)}</ul>}
        {failure?.details.request_id && <p className="cms-id">شناسهٔ پیگیری: <bdi>{failure.details.request_id}</bdi></p>}
        {failure?.details.blockers?.includes("CANONICAL_RECONCILIATION_REQUIRED") ? <p>محتوای اصلی خارج از این مسیر تغییر کرده است؛ ذخیره تا تطبیق آن مسدود می‌ماند.</p> : id && (failure?.status === 412 || failure?.status === 409 || failure?.code === "UNKNOWN_OUTCOME") && <button type="button" className="button secondary" disabled={busy} onClick={compareCurrent}>دریافت نسخهٔ سرور و مقایسه</button>}
        {!id && failure?.code === "UNKNOWN_OUTCOME" && <p>پیش از ساخت دوباره، <a className="cms-link" href="/admin-console/audit">تاریخچهٔ عملیات</a> و فهرست را بررسی کنید.</p>}
      </div>}
      <fieldset className="cms-fieldset" disabled={busy || !!conflict || !editable}>
        {fields.map(field => <div className="cms-form-field" key={field}><label htmlFor={`cms-${field}`}>{labels[field]}{field === "name_en" ? " (الزامی)" : ""}</label>
          {field === "description" ? <textarea id={`cms-${field}`} name={field} rows={7} dir="auto" maxLength={20000} value={form[field]} aria-invalid={!!failure?.details.field_errors?.[field]} aria-describedby={`cms-${field}-hint`} onChange={event => { setForm({ ...form, [field]: event.target.value }); setSaved(false); }} />
            : <input id={`cms-${field}`} name={field} dir={field === "name_en" ? "ltr" : "rtl"} maxLength={200} required={field === "name_en"} value={form[field]} aria-invalid={!!failure?.details.field_errors?.[field]} aria-describedby={`cms-${field}-hint`} onChange={event => { setForm({ ...form, [field]: event.target.value }); setSaved(false); }} />}
          <small id={`cms-${field}-hint`}>{field === "description" ? "متن ساده؛ حداکثر ۲۰٬۰۰۰ نویسه. محتوای علمی نیازمند review مستقل است." : "حداکثر ۲۰۰ نویسه؛ نام اصلی منبع را حفظ کنید."}{failure?.details.field_errors?.[field]?.join(" · ")}</small>
        </div>)}
      </fieldset>
      {conflict && <section className="cms-conflict"><h3>بازبینی اختلاف با نسخهٔ {faNumber(conflict.data.version)}</h3><p>انتخاب کنید کدام مقدار در پیشنهاد بعدی بماند. تغییرهای هم‌زمان روی یک فیلد، انتخاب پیش‌فرض ندارند.</p>
        {fields.map(field => <fieldset key={field} className="cms-merge-field"><legend>{labels[field]}</legend><div className="cms-compare"><div><strong>تغییر شما</strong><p dir={field === "name_en" ? "ltr" : "auto"}>{form[field] || "خالی"}</p></div><div><strong>نسخهٔ فعلی سرور</strong><p dir={field === "name_en" ? "ltr" : "auto"}>{conflict.data.payload[field] || "خالی"}</p></div></div><label>مقدار پیشنهاد بعدی<select aria-label={`انتخاب ${labels[field]}`} value={choices[field] || ""} onChange={event => setChoices({ ...choices, [field]: event.target.value as "mine" | "current" })}><option value="" disabled>انتخاب کنید</option><option value="mine">تغییر من</option><option value="current">نسخهٔ سرور</option></select></label></fieldset>)}
        <button type="button" className="button secondary" disabled={fields.some(field => !choices[field])} onClick={merge}>پذیرش مقایسه و ادامهٔ ویرایش</button>
      </section>}
      <div className="cms-actions"><button className="button primary" disabled={busy || blocked || !dirty || !editable}>{busy ? "در حال ذخیره…" : "ذخیرهٔ پیشنهاد"}</button>{id && <button type="button" className="button secondary" disabled={busy} onClick={() => leave(() => { setForm(values(base!.data.payload)); setSaveError(undefined); setConflict(undefined); setDirty(false); })}>بازگرداندن فرم به نسخهٔ ذخیره‌شده</button>}</div>
      {saved && <p role="status" className="cms-success">پیشنهاد ذخیره شد. محتوای عمومی بدون تغییر است.</p>}
    </form>
    {tab === "preview" && <section className="card stack"><h2>پیش‌نمایش پیشنهاد{dirty ? " ذخیره‌نشده" : " ذخیره‌شده"}</h2><p className="muted">نمای متن پیشنهاد؛ این نما تأیید علمی یا پیش‌نمایش انتشار عمومی نیست.</p><article className="cms-preview"><h3>{form.name_fa || form.name_en}</h3><p dir="ltr">{form.name_en}</p><p className="cms-prose" dir="auto">{form.description || "توضیح ثبت نشده"}</p></article><h3>اختلاف با پیشنهاد ذخیره‌شده</h3>{fields.filter(field => form[field] !== values(base?.data.payload || blank)[field]).map(field => <div key={field} className="cms-merge-field"><strong>{labels[field]}</strong><div className="cms-compare"><div><small>ذخیره‌شده</small><p dir={field === "name_en" ? "ltr" : "auto"}>{base?.data.payload[field] || "خالی"}</p></div><div><small>فرم فعلی</small><p dir={field === "name_en" ? "ltr" : "auto"}>{form[field] || "خالی"}</p></div></div></div>)}{!dirty && <p className="muted">اختلافی با آخرین پیشنهاد ذخیره‌شده ندارد.</p>}</section>}
    {tab === "history" && <section className="card stack"><h2>تاریخچهٔ نسخه‌های مستقل</h2>{historyError ? <CmsState error={historyError} retry={() => setHistoryRetry(value => value + 1)} /> : !history ? <CmsState loading /> : <><p className="muted">{faNumber(history.count)} نسخه؛ هیچ نسخهٔ قبلی بازنویسی نمی‌شود.</p>{history.results.map((revision, index) => <details className="cms-history-entry" key={revision.id}><summary>نسخهٔ {faNumber(revision.sequence)} · {revisionLabels[revision.status]} · <time dateTime={revision.created_at}>{cmsDate(revision.created_at)}</time></summary>{fields.map(field => <div key={field}><h3>{labels[field]}</h3><p className="cms-prose" dir={field === "name_en" ? "ltr" : "auto"}>{revision.payload[field] || "ثبت نشده"}</p>{history.results[index + 1] && revision.payload[field] !== history.results[index + 1].payload[field] && <p className="muted">مقدار نسخهٔ قبل: <bdi>{history.results[index + 1].payload[field] || "خالی"}</bdi></p>}</div>)}</details>)}<div className="cms-pagination">{historyPage > 1 && <button className="button secondary" onClick={() => setHistoryPage(value => value - 1)}>نسخه‌های جدیدتر</button>}{historyPage * history.page_size < history.count && <button className="button secondary" onClick={() => setHistoryPage(value => value + 1)}>نسخه‌های قدیمی‌تر</button>}</div></>}</section>}
  </div>;
}
