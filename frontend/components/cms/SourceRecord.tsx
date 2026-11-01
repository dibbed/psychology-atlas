"use client";

import { useEffect, useRef, useState } from "react";
import { cms, CmsError, CmsPage, cmsDate } from "@/lib/cms";
import { SourceDetail, SourceHistoryEntry, SourceMapping, SourceOperation, SourcePayload, SourcePlan, SourceRequest, sourceBlank, sourceLabels, sourceOperationLabels, sourcePayload, governanceBlocked } from "@/lib/cmsGovernance";
import { faNumber } from "@/lib/fa";
import { CmsState, useCms } from "./CmsShell";
import { GovernanceError, GovernancePagination } from "./GovernanceForms";
import SourceFields from "./SourceFields";
import SourceImpact, { sourceUsages } from "./SourceImpact";
import SourceComparison, { sourceValue } from "./SourceComparison";
import SourcePlanPanel, { sourceAuthority } from "./SourcePlanPanel";

export default function SourceRecord({ id }: { id?: string }) {
  const { me, can, setDirty, leave } = useCms();
  const [base, setBase] = useState<SourceDetail>(); const [form, setForm] = useState<SourcePayload>(sourceBlank);
  const [operation, setOperation] = useState<SourceOperation>(id ? "update" : "create");
  const [tab, setTab] = useState(id ? "detail" : "edit"); const [retry, setRetry] = useState(0);
  const [loading, setLoading] = useState(!!id); const [error, setError] = useState<unknown>(); const [writeError, setWriteError] = useState<unknown>();
  const [busy, setBusy] = useState(false); const lock = useRef(false);
  const [candidateText, setCandidateText] = useState(""); const [candidates, setCandidates] = useState<SourceDetail[]>([]); const [candidateError, setCandidateError] = useState<unknown>();
  const [choices, setChoices] = useState<Partial<Record<keyof SourcePayload, number>>>({}); const [mapping, setMapping] = useState<SourceMapping[]>([]);
  const [plan, setPlan] = useState<{ data: SourcePlan; etag: string | null }>(); const [planInput, setPlanInput] = useState("");
  const [history, setHistory] = useState<CmsPage<SourceHistoryEntry>>(); const [historyError, setHistoryError] = useState<unknown>(); const [historyPage, setHistoryPage] = useState(1);
  const [back, setBack] = useState("/admin-console/sources");
  const allowed = can("cms_source_view");
  const normalizedForm = { ...form, authors: form.authors.map(author => author.trim()).filter(Boolean) };
  const changes = operation === "create" ? normalizedForm : Object.fromEntries(Object.keys(sourceBlank).filter(key => JSON.stringify(normalizedForm[key as keyof SourcePayload]) !== JSON.stringify(base?.source[key as keyof SourcePayload])).map(key => [key, normalizedForm[key as keyof SourcePayload]]));
  const mappingOperation = operation === "merge" || operation === "split";
  const targetOperation = mappingOperation || operation === "successor";
  const request: SourceRequest = { operation, ...(id ? { source_id: Number(id) } : {}), ...(["create", "update"].includes(operation) ? { changes } : {}), ...(targetOperation ? { candidates: candidates.map(item => item.source.id) } : {}), ...(operation === "merge" ? { field_choices: choices } : {}), ...(mappingOperation ? { mapping } : {}) };
  const input = JSON.stringify(request);
  const dirty = JSON.stringify(form) !== JSON.stringify(base ? sourcePayload(base.source) : sourceBlank) || !!candidateText || Object.keys(choices).length > 0 || mapping.length > 0;
  const incomplete = [base, ...candidates].filter(Boolean).some(item => item && Object.entries(item.impact.counts).some(([key, count]) => item.impact[key as keyof Pick<typeof item.impact, "canonical" | "review" | "archives" | "successors">].length < count));
  const editable = sourceAuthority(operation, can);
  const blocked = governanceBlocked(writeError);
  useEffect(() => { setDirty(dirty || busy); return () => setDirty(false); }, [dirty, busy, setDirty]);
  useEffect(() => { const params = new URLSearchParams(new URLSearchParams(location.search).get("list") || ""); const safe = new URLSearchParams(); for (const key of ["q", "doi", "pmid", "archived", "page", "page_size"]) if (params.has(key)) safe.set(key, params.get(key)!); setBack(`/admin-console/sources?${safe}`); }, []);
  useEffect(() => {
    if (!id || !allowed) return;
    let active = true; setLoading(true); setError(undefined);
    cms<SourceDetail>(`/sources/${id}/`).then(result => { if (active) { setBase(result.data); setForm(sourcePayload(result.data.source)); } }).catch(failure => { if (active) setError(failure); }).finally(() => { if (active) setLoading(false); });
    return () => { active = false; };
  }, [id, allowed, retry]);
  useEffect(() => {
    if (!id || !allowed || tab !== "history") return;
    let active = true; setHistory(undefined); setHistoryError(undefined);
    cms<CmsPage<SourceHistoryEntry>>(`/sources/${id}/history/?page=${historyPage}`).then(result => { if (active) setHistory(result.data); }).catch(failure => { if (active) setHistoryError(failure); });
    return () => { active = false; };
  }, [id, allowed, tab, historyPage, retry, plan?.data.version]);
  async function loadCandidates() {
    if (lock.current) return;
    const ids = candidateText.split(/[,،\s]+/).filter(Boolean).map(Number);
    if (!ids.length || ids.some(value => !Number.isSafeInteger(value) || value <= 0) || new Set(ids).size !== ids.length || ids.includes(Number(id))) { setCandidateError(new CmsError(400, "INVALID_INPUT", "شناسه‌های مثبت و متمایز منابع دیگر را وارد کنید.")); return; }
    lock.current = true; setBusy(true); setCandidateError(undefined); setCandidates([]); setChoices({}); setMapping([]);
    try { setCandidates(await Promise.all(ids.map(async candidate => (await cms<SourceDetail>(`/sources/${candidate}/`)).data))); }
    catch (failure) { setCandidateError(failure); }
    finally { lock.current = false; setBusy(false); }
  }
  async function preview() {
    if (lock.current || !editable || blocked || (mappingOperation && incomplete)) return;
    lock.current = true; setBusy(true); setWriteError(undefined);
    try { const result = await cms<SourcePlan>("/sources/preview/", { method: "POST", body: input }, me.user.id); setPlan(result); setPlanInput(input); }
    catch (failure) { setWriteError(failure); }
    finally { lock.current = false; setBusy(false); }
  }
  function changeOperation(next: SourceOperation) { setOperation(next); setChoices({}); setMapping([]); setCandidates([]); setCandidateText(""); setPlan(undefined); setWriteError(undefined); }
  if (!allowed || (!id && !can("cms_source_create"))) return <CmsState error={new CmsError(403, "PERMISSION_DENIED", "")} />;
  if (loading) return <CmsState loading />;
  if (error) return <div className="stack"><CmsState error={error} retry={() => setRetry(n => n + 1)} />{id && <a className="cms-link" href={`/admin-console/sources/${id}/history`}>تاریخچهٔ حفظ‌شدهٔ منبع</a>}</div>;
  return <div className="stack" dir="rtl"><a className="cms-link" href={back}>→ بازگشت به فهرست با فیلتر قبلی</a>
    <header className="cms-title"><p className="eyebrow">منابع / {id ? "جزئیات و عملیات" : "ثبت منبع"}</p><h1 dir="auto">{base?.source.title || "منبع تازه"}</h1>{base && <p>نسخهٔ {faNumber(base.source.version)} · {base.source.archived ? "بایگانی‌شده" : "فعال"}</p>}</header>
    <nav className="cms-tabs" aria-label="نماهای منبع">{[...(id ? [["detail", "مشخصات و اثر"]] : []), ["edit", "عملیات و پیش‌نمایش"], ...(id ? [["history", "تاریخچه"]] : [])].map(([value, label]) => <button type="button" className="button secondary" key={value} aria-pressed={tab === value} onClick={() => setTab(value)}>{label}</button>)}</nav>
    {tab === "detail" && base && <><section className="card stack"><h2>کتاب‌شناسی و هویت ثبت‌شده</h2>{Object.entries(sourceLabels).map(([key, label]) => <div key={key}><h3>{label}</h3><p className="cms-prose" dir={["doi", "pmid", "url", "resource_version"].includes(key) ? "ltr" : "auto"}>{sourceValue(base.source[key as keyof SourcePayload])}</p></div>)}<h3>نسخه‌های provenance حفظ‌شده</h3><pre className="cms-prose" dir="ltr">{sourceValue(base.source.provenance_versions)}</pre><p className="muted">فرادادهٔ خام تاریخی حفظ شده و از این فرم قابل جایگزینی نیست.</p></section><SourceImpact impact={base.impact} />{base.successors.length > 0 && <section className="card stack"><h2>پیشینهٔ جانشینی</h2>{base.successors.map((item, index) => <pre className="cms-prose" key={index} dir="auto">{sourceValue(item)}</pre>)}</section>}</>}
    {tab === "edit" && <form className="stack" onSubmit={event => { event.preventDefault(); preview(); }}>
      <section className="card stack"><h2>انتخاب عملیات</h2><label>عملیات منبع<select value={operation} disabled={busy || blocked} onChange={event => leave(() => changeOperation(event.target.value as SourceOperation))}>{(id ? ["update", "archive", "delete", "merge", "split", "successor"] as SourceOperation[] : ["create"] as SourceOperation[]).filter(value => sourceAuthority(value, can)).map(value => <option value={value} key={value}>{sourceOperationLabels[value]}</option>)}</select></label>
        {!editable && <p className="cms-notice">مجوز عملیات، پیش‌نمایش و اعتبارسنجی منابع لازم است.</p>}
        <p className="muted">ذخیرهٔ مستقیم وجود ندارد. ابتدا طرح نسخه‌دار سرور را بررسی و سپس همان طرح را اعمال کنید.</p>
        {base?.source.archived && <p className="cms-notice">منبع بایگانی‌شده، قابل‌ویرایش و مقصد انتقال نیست.</p>}
        {!!base?.impact.protection.length && <p className="cms-notice">این منبع ادعاهای محافظت‌شده دارد. ویرایش یا انتقال آن فقط در صورت اجازهٔ اعتبارسنجی سرور ممکن است؛ مسیر جانشینی provenance قبلی را حفظ می‌کند.</p>}
        <GovernanceError error={writeError} prefix="source" labels={sourceLabels}>{blocked && <button type="button" className="button secondary" disabled={busy} onClick={() => leave(() => { setWriteError(undefined); setPlan(undefined); setCandidates([]); setChoices({}); setMapping([]); setCandidateText(""); setRetry(n => n + 1); })}>بازخوانی منبع و اثر؛ ساخت طرح تازه</button>}{writeError instanceof CmsError && writeError.code === "UNKNOWN_OUTCOME" && <p>پیش از تکرار پیش‌نمایش، <a className="cms-link" href="/admin-console/audit">تاریخچهٔ عملیات</a> را بررسی کنید.</p>}</GovernanceError>
        {(["create", "update"].includes(operation)) && <SourceFields value={form} onChange={setForm} disabled={busy || !editable || blocked} error={writeError} />}
        {targetOperation && <><label>شناسهٔ منابع {operation === "merge" ? "نامزد ادغام؛ منبع فعلی باقی می‌ماند" : operation === "split" ? "مقصد تفکیک؛ حداقل دو منبع" : "جانشین؛ دقیقاً یک منبع"}<input dir="ltr" value={candidateText} disabled={busy || blocked || !editable} onChange={event => { setCandidateText(event.target.value); setCandidates([]); setChoices({}); setMapping([]); }} placeholder="12, 34" /></label><button type="button" className="button secondary" disabled={busy || !candidateText || blocked || !editable} onClick={loadCandidates}>دریافت مشخصات و اثر منابع انتخاب‌شده</button>{candidateError != null && <CmsState error={candidateError} />}
          {candidates.map(candidate => <div key={candidate.source.id} className="cms-history-entry"><h3 dir="auto">{candidate.source.title}</h3><p dir="ltr">DOI: {candidate.source.doi || "—"} · PMID: {candidate.source.pmid || "—"} · version: {candidate.source.resource_version || "—"}</p>{candidate.source.archived && <p className="cms-notice">این منبع بایگانی شده و مقصد انتقال مجاز نیست.</p>}</div>)}
        </>}
        {operation === "merge" && base && candidates.length > 0 && <SourceComparison sources={[base, ...candidates].map(item => ({ id: item.source.id, payload: sourcePayload(item.source) }))} choices={choices} onChange={setChoices} disabled={busy || !editable || blocked} />}
        {(operation === "archive" || operation === "delete") && <p className="cms-notice">{operation === "delete" ? "فقط منبع بدون هیچ مصرف‌کننده قابل‌حذف است؛ تاریخچه باقی می‌ماند." : "بایگانی، وضعیت بررسی علمی ادعاها را تغییر نمی‌دهد."}</p>}
      </section>
      {mappingOperation && (operation === "merge" ? candidates : base ? [base] : []).map(item => <SourceImpact key={item.source.id} impact={item.impact} mapping={mapping} onMapping={setMapping} disabled={busy || blocked || !editable} targets={(operation === "merge" ? base ? [base] : [] : candidates).map(target => ({ id: target.source.id, title: target.source.title }))} />)}
      {mappingOperation && <button type="button" className="button secondary" disabled={busy || blocked || incomplete || !editable} onClick={() => setMapping((operation === "merge" ? candidates : base ? [base] : []).flatMap(item => sourceUsages(item.impact).map(usage => ({ key: usage.key, action: "retain" as const }))))}>انتخاب صریح حفظ همهٔ مراجع؛ سپس اصلاح نگاشت‌های لازم</button>}
      <div className="cms-actions"><button className="button primary" disabled={busy || blocked || !editable || (targetOperation && !candidates.length) || (mappingOperation && incomplete)}>{busy ? "در حال دریافت…" : "ساخت پیش‌نمایش و اعتبارسنجی سرور"}</button><button type="button" className="button secondary" disabled={busy} onClick={() => leave(() => { setForm(base ? sourcePayload(base.source) : sourceBlank); setCandidates([]); setCandidateText(""); setChoices({}); setMapping([]); setPlan(undefined); setWriteError(undefined); })}>کنارگذاشتن تغییرات فرم</button></div>
    </form>}
    {plan && <SourcePlanPanel key={plan.data.id} snapshot={plan} current={input === planInput} onResult={result => { setPlan(result); if (result.data.status === "applied") { setDirty(false); setCandidates([]); setCandidateText(""); setChoices({}); setMapping([]); if (!id && result.data.receipt?.source_ids[0]) location.assign(`/admin-console/sources/${result.data.receipt.source_ids[0]}`); else if (result.data.operation === "delete") { if (base) setForm(sourcePayload(base.source)); } else setRetry(n => n + 1); } }} onBusy={setBusy} repreview={preview} />}
    {tab === "history" && (historyError ? <CmsState error={historyError} retry={() => setRetry(n => n + 1)} /> : !history ? <CmsState loading /> : <section className="card stack"><h2>تاریخچهٔ منبع</h2>{!history.results.length && <CmsState empty="عملیاتی ثبت نشده است." />}{history.results.map(item => <details className="cms-history-entry" key={item.id}><summary>{sourceOperationLabels[item.operation]} · نسخهٔ {faNumber(item.version)} · {cmsDate(item.created_at)}</summary><p><bdi>{item.actor_ref}</bdi></p><a className="cms-link" href={`/admin-console/sources/plans/${item.plan_id}`}>طرح این عملیات</a><div className="cms-compare"><div><h3>پیش از تغییر</h3><pre className="cms-prose" dir="auto">{sourceValue(item.before)}</pre></div><div><h3>پس از تغییر</h3><pre className="cms-prose" dir="auto">{sourceValue(item.after)}</pre></div></div></details>)}<GovernancePagination data={history} onPage={setHistoryPage} /></section>)}
  </div>;
}
