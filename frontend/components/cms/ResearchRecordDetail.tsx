"use client";

import { useEffect, useRef, useState } from "react";
import { CmsError, CmsPage, cmsDate } from "@/lib/cms";
import { ResearchAction, ResearchDecision, ResearchMapping, ResearchRaw, ResearchRecord, Snapshot, mutationBlocked, researchActionLabels, researchReasons, researchSourceIds, versionHeaders } from "@/lib/cmsJobs";
import { faNumber } from "@/lib/fa";
import { CmsState } from "./CmsShell";
import { GovernancePagination } from "./GovernanceForms";
import { PrivateMutationError, ResearchBoundary, usePrivateCms } from "./CmsJobsShared";
import ResearchExport from "./ResearchExport";

const capabilities: Record<ResearchAction, string> = { map: "cms_research_map", reject: "cms_research_reject", defer: "cms_research_defer", stage: "cms_research_derive" };
const blank = { canonical_key: "", name_en: "", name_fa: "", source_ids: "" };
function mappingForm(mapping: ResearchMapping = {}) {
  return { canonical_key: mapping.canonical_key || "", name_en: mapping.name_en || "", name_fa: mapping.name_fa || "", source_ids: (mapping.source_ids || []).join(", ") };
}
function MappingView({ mapping }: { mapping: ResearchMapping }) {
  return <dl className="cms-audit-detail">
    <div><dt>کلید معنایی پیشنهادی</dt><dd dir="ltr">{mapping.canonical_key || "ثبت نشده"}</dd></div>
    <div><dt>نام انگلیسی مشتق</dt><dd dir="ltr">{mapping.name_en || "ثبت نشده"}</dd></div>
    <div><dt>نام فارسی مشتق</dt><dd>{mapping.name_fa || "ثبت نشده"}</dd></div>
    <div><dt>شناسه‌های منابع</dt><dd>{mapping.source_ids?.length ? mapping.source_ids.map(id => <bdi key={id}>{faNumber(id)} </bdi>) : "ثبت نشده"}</dd></div>
  </dl>;
}

export default function ResearchRecordDetail({ id }: { id: string }) {
  const { can, request, current, setDirty, leave } = usePrivateCms(); const allowed = can("cms_research_view");
  const [snapshot, setSnapshot] = useState<Snapshot<{ record: ResearchRecord }>>();
  const [history, setHistory] = useState<CmsPage<ResearchDecision>>(); const [historyError, setHistoryError] = useState<unknown>();
  const [historyBusy, setHistoryBusy] = useState(false);
  const [form, setForm] = useState(blank); const [action, setAction] = useState<ResearchAction | "">(""); const [confirmation, setConfirmation] = useState(false);
  const [raw, setRaw] = useState<ResearchRaw>(); const [error, setError] = useState<unknown>(); const [writeError, setWriteError] = useState<unknown>();
  const [busy, setBusy] = useState(false); const lock = useRef(false); const [reload, setReload] = useState(0);
  const record = snapshot?.data.record; const blocked = mutationBlocked(writeError);
  const dirty = JSON.stringify(form) !== JSON.stringify(mappingForm(record?.decision?.mapping)) || action !== "";
  const actionAllowed = !!action && can(capabilities[action]);
  useEffect(() => { setDirty(dirty || busy); return () => setDirty(false); }, [dirty, busy, setDirty]);
  useEffect(() => {
    if (!allowed) return;
    let active = true; const abort = new AbortController(); setSnapshot(undefined); setHistory(undefined); setRaw(undefined); setError(undefined); setHistoryError(undefined); setConfirmation(false);
    const options = { signal: AbortSignal.any([abort.signal, AbortSignal.timeout(15000)]) };
    Promise.all([request<{ record: ResearchRecord }>(`/research/records/${encodeURIComponent(id)}/`, options), request<CmsPage<ResearchDecision>>(`/research/records/${encodeURIComponent(id)}/history/?page=1`, options)])
      .then(([result, decisions]) => { if (active && current()) { setSnapshot(result); setHistory(decisions.data); setForm(mappingForm(result.data.record.decision?.mapping)); setAction(""); setWriteError(undefined); } })
      .catch(failure => { if (active && current()) setError(failure); });
    return () => { active = false; abort.abort(); };
  }, [allowed, id, request, current, reload]);
  function refresh() { leave(() => { setRaw(undefined); setConfirmation(false); setReload(n => n + 1); }); }
  async function historyPage(page: number) {
    if (historyBusy || !allowed) return;
    setHistoryBusy(true); setHistoryError(undefined);
    try { const result = await request<CmsPage<ResearchDecision>>(`/research/records/${encodeURIComponent(id)}/history/?page=${page}`); if (current()) setHistory(result.data); }
    catch (failure) { if (current()) setHistoryError(failure); }
    finally { if (current()) setHistoryBusy(false); }
  }
  function mapping(): ResearchMapping {
    if (action !== "map") return {};
    const source_ids = researchSourceIds(form.source_ids);
    const value: ResearchMapping = { ...(form.canonical_key.trim() ? { canonical_key: form.canonical_key.trim() } : {}), ...(form.name_en.trim() ? { name_en: form.name_en.trim() } : {}), ...(form.name_fa.trim() ? { name_fa: form.name_fa.trim() } : {}), ...(source_ids.length ? { source_ids } : {}) };
    if (!Object.keys(value).length) throw new CmsError(400, "INVALID_MAPPING", "حداقل یک مقدار برای نگاشت مشتق وارد کنید.");
    return value;
  }
  function review(event: React.FormEvent) {
    event.preventDefault(); if (busy || blocked || !actionAllowed) return;
    try { mapping(); setWriteError(undefined); setConfirmation(true); }
    catch (failure) { setWriteError(failure); }
  }
  async function decide() {
    if (!action || !snapshot || !confirmation || !actionAllowed || blocked || lock.current) return;
    lock.current = true; setBusy(true); setRaw(undefined); setWriteError(undefined);
    try {
      const result = await request<{ record: ResearchRecord }>(`/research/records/${encodeURIComponent(id)}/decisions/`, { method: "POST", headers: versionHeaders(snapshot.etag), body: JSON.stringify({ action, mapping: mapping(), reason: researchReasons[action] }) });
      if (current()) { setSnapshot(result); setForm(mappingForm(result.data.record.decision?.mapping)); setAction(""); setConfirmation(false); setReload(n => n + 1); }
    } catch (failure) { if (current()) { setWriteError(failure); setConfirmation(false); } }
    finally { lock.current = false; if (current()) setBusy(false); }
  }
  async function previewRaw() {
    if (!snapshot || !can("cms_research_raw_read") || lock.current || blocked) return;
    lock.current = true; setBusy(true); setRaw(undefined); setWriteError(undefined);
    try {
      const result = await request<{ record: ResearchRaw }>(`/research/records/${encodeURIComponent(id)}/raw-preview/`, { method: "POST", headers: versionHeaders(snapshot.etag), body: JSON.stringify({ purpose: "research_review", reason: "RESEARCH_RAW" }) });
      if (current()) setRaw(result.data.record);
    } catch (failure) { if (current()) setWriteError(failure); }
    finally { lock.current = false; if (current()) setBusy(false); }
  }
  if (!allowed) return <CmsState error={new CmsError(403, "PERMISSION_DENIED", "")} />;
  return <div className="stack" dir="rtl"><a className="cms-link" href={record ? `/admin-console/research/${record.dataset_id}` : "/admin-console/research"}>→ بازگشت به مجموعهٔ پژوهشی</a><header className="cms-title"><p className="eyebrow">پژوهش / رکورد {faNumber(id)}</p><h1 dir="auto">{record?.name_fa || record?.name_en || "جزئیات رکورد پژوهشی"}</h1></header><ResearchBoundary />
    <PrivateMutationError error={writeError} busy={busy} reload={refresh} />
    {error ? <CmsState error={error} retry={refresh} /> : !record ? <CmsState loading /> : <>
      <section className="card stack"><h2>فرادادهٔ ورودی حفظ‌شده</h2><p dir="ltr">{record.name_en || "نام انگلیسی ثبت نشده"}</p><p>{record.name_fa || "نام فارسی ثبت نشده"}</p><p>بخش: <bdi>{record.section}</bdi> · شناسهٔ ورودی: <bdi>{record.external_id}</bdi></p><p>نسخهٔ تصمیم: {faNumber(record.version)} · وضعیت مشتق: {record.decision ? researchActionLabels[record.decision.action] : "بدون تصمیم"}</p>
        {record.decision && <><h3>آخرین نگاشت مشتق</h3><MappingView mapping={record.decision.mapping} /><p>دلیل: <bdi>{record.decision.reason}</bdi> · {cmsDate(record.decision.created_at)}</p></>}
        <div className="cms-actions"><button className="button secondary" disabled={busy} onClick={refresh}>بازخوانی رکورد و تاریخچه</button>{can("cms_research_raw_read") && <button className="button secondary" disabled={busy || blocked} onClick={previewRaw}>دریافت متن خام؛ با ثبت رویداد دسترسی</button>}</div>
        {raw && <section className="cms-preview stack" aria-label="پیش‌نمایش خام خصوصی"><h3>پیش‌نمایش خام با مجوز جاری</h3><p className="muted">هدف ثبت‌شده: بررسی پژوهش. این نمایش، راستی‌آزمایی علمی نیست.</p><button className="button secondary" onClick={() => setRaw(undefined)}>بستن و پاک کردن پیش‌نمایش خام</button><pre className="cms-prose" dir="auto">{JSON.stringify(raw.payload, null, 2)}</pre></section>}
      </section>
      <ResearchExport targetKind="record" targetId={record.id} />
      {Object.values(capabilities).some(cap => can(cap)) && <form className="card stack" onSubmit={review}><h2>تصمیم تازهٔ مشتق</h2><fieldset className="cms-fieldset" disabled={busy || blocked || !snapshot?.etag}>
        <label>اقدام صریح<select value={action} onChange={event => { setAction(event.target.value as ResearchAction | ""); setConfirmation(false); }}><option value="">یک اقدام را انتخاب کنید</option>{(Object.keys(capabilities) as ResearchAction[]).filter(value => can(capabilities[value])).map(value => <option key={value} value={value}>{researchActionLabels[value]}</option>)}</select></label>
        {action === "map" && <><label>کلید معنایی مشتق<input id="research-canonical_key" dir="ltr" maxLength={400} value={form.canonical_key} onChange={event => { setForm({ ...form, canonical_key: event.target.value }); setConfirmation(false); }} /></label><label>نام انگلیسی مشتق<input id="research-name_en" dir="ltr" maxLength={500} value={form.name_en} onChange={event => { setForm({ ...form, name_en: event.target.value }); setConfirmation(false); }} /></label><label>نام فارسی مشتق<input id="research-name_fa" dir="rtl" maxLength={500} value={form.name_fa} onChange={event => { setForm({ ...form, name_fa: event.target.value }); setConfirmation(false); }} /></label><label>شناسهٔ عددی منابع؛ جداشده با ویرگول<input id="research-source_ids" dir="ltr" maxLength={2000} value={form.source_ids} disabled={!can("cms_source_view")} onChange={event => { setForm({ ...form, source_ids: event.target.value }); setConfirmation(false); }} /><small>منبع و نشانی به‌تنهایی شاهد علمی یا حقوقی نیستند.</small></label></>}
        {action === "stage" && <p className="cms-notice">آخرین نگاشت معتبر برای بررسی علمی آینده آماده می‌شود. این اقدام تأیید علمی، ارتقا به مرجع یا انتشار نیست؛ نسخه و منابع در سرور دوباره بررسی می‌شوند.</p>}
        {action === "reject" && <p className="cms-notice">رد، یک تصمیم تازه ثبت می‌کند؛ ورودی خام و تاریخچه حذف نمی‌شوند.</p>}
        {action === "defer" && <p className="cms-notice">بررسی به تعویق می‌افتد؛ دادهٔ خام و تصمیم‌های قبلی حفظ می‌شوند.</p>}
        {action && <p>دلیل ثابت این اقدام: <bdi>{researchReasons[action]}</bdi></p>}
        <div className="cms-actions"><button className="button primary" disabled={!actionAllowed}>بررسی تصمیم پیش از ثبت</button><button type="button" className="button secondary" onClick={() => leave(() => { setForm(mappingForm(record.decision?.mapping)); setAction(""); setConfirmation(false); })}>کنار گذاشتن فرم</button></div>
        {confirmation && action && <section className="cms-conflict stack" aria-labelledby="research-confirm"><h3 id="research-confirm">تأیید {researchActionLabels[action]}</h3><p>این تصمیم برای نسخهٔ {faNumber(record.version)} ثبت می‌شود. محتوای مرجع و دادهٔ خام تغییر نمی‌کنند.</p><div className="cms-actions"><button type="button" className="button primary" onClick={decide}>ثبت نهایی تصمیم</button><button type="button" className="button secondary" onClick={() => setConfirmation(false)}>بازگشت به فرم</button></div></section>}
      </fieldset></form>}
      <section className="card stack" aria-label="تاریخچهٔ تصمیم‌های مشتق"><h2>تاریخچهٔ تغییرناپذیر تصمیم‌ها</h2>{historyError != null && <CmsState error={historyError} retry={() => historyPage(history?.page || 1)} />}
        {!history ? <CmsState loading /> : <>{!history.results.length && <CmsState empty="تصمیم مشتقی برای این رکورد ثبت نشده است." />}{history.results.map(decision => <details className="cms-history-entry" key={decision.id}><summary>{researchActionLabels[decision.action]} · نسخهٔ {faNumber(decision.sequence)} · {cmsDate(decision.created_at)}</summary><p>عامل: <bdi>{decision.actor_ref}</bdi> · دلیل: <bdi>{decision.reason}</bdi></p><MappingView mapping={decision.mapping} /></details>)}<GovernancePagination data={history} onPage={historyPage} disabled={historyBusy || busy} /></>}
      </section>
    </>}
  </div>;
}
