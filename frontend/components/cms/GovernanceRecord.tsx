"use client";
import { useEffect, useRef, useState } from "react";
import { cms, CmsError, CmsPage } from "@/lib/cms";
import { GovernanceDetail, GovernanceKind, ResourceBinding, RightsPayload, TerminologyPayload, governanceBlocked, governanceLabels, governanceResources, rightsBlank, terminologyBlank } from "@/lib/cmsGovernance";
import { faNumber } from "@/lib/fa";
import { CmsState, useCms } from "./CmsShell";
import { GovernanceError } from "./GovernanceForms";
import GovernanceResourcePicker from "./GovernanceResourcePicker";
import GovernanceReview from "./GovernanceReview";
import GovernanceHistory, { GovernanceEvent } from "./GovernanceHistory";
import RightsFields, { rightsFieldLabels } from "./RightsFields";
import TerminologyFields, { terminologyFieldLabels } from "./TerminologyFields";
import { sourceValue } from "./SourceComparison";

function proposal(detail: GovernanceDetail): RightsPayload | TerminologyPayload {
  const record = detail.record;
  return { ...(record.kind === "rights" ? rightsBlank : terminologyBlank), ...record.payload, resource_type: record.resource_type, resource_id: record.resource_id, resource_version: record.resource_version };
}
function binding(detail: GovernanceDetail): ResourceBinding {
  const record = detail.record;
  return { resource_type: record.resource_type, resource_id: record.resource_id, domain: record.domain, resource_version: record.resource_version, resource_digest: record.resource_digest, name_en: "", name_fa: "" };
}
const validEvidence = (evidence: { source_id?: number; artifact_id?: string; locator: string }[], required: boolean) => (!required || evidence.length > 0) && evidence.length <= 20 && evidence.every(item => {
  const source = Number.isSafeInteger(item.source_id) && (item.source_id ?? 0) > 0;
  const artifact = !!item.artifact_id && /^[0-9a-f]{8}(-[0-9a-f]{4}){3}-[0-9a-f]{12}$/i.test(item.artifact_id);
  return source !== artifact && !!item.locator.trim() && item.locator.trim().length <= 1000;
});

export default function GovernanceRecord({ kind, id }: { kind: GovernanceKind; id?: string }) {
  const { me, can, setDirty, leave } = useCms();
  const [base, setBase] = useState<{ data: GovernanceDetail; etag: string | null }>();
  const [form, setForm] = useState<RightsPayload | TerminologyPayload>(kind === "rights" ? rightsBlank : terminologyBlank);
  const [resource, setResource] = useState<ResourceBinding>();
  const [tab, setTab] = useState(id ? "detail" : "edit"); const [retry, setRetry] = useState(0); const [loading, setLoading] = useState(!!id);
  const [error, setError] = useState<unknown>(); const [writeError, setWriteError] = useState<unknown>(); const [busy, setBusy] = useState(false); const lock = useRef(false);
  const [saved, setSaved] = useState(false); const [reviewDirty, setReviewDirty] = useState(false); const [revokeReason, setRevokeReason] = useState("");
  const [history, setHistory] = useState<CmsPage<GovernanceEvent>>(); const [historyError, setHistoryError] = useState<unknown>(); const [historyPage, setHistoryPage] = useState(1);
  const [back, setBack] = useState(`/admin-console/${kind}`);
  const record = base?.data.record;
  const domain = resource?.domain || record?.domain || governanceResources[form.resource_type]?.domain;
  const domainReader = Object.values(governanceResources).some(item => can(`cms_${item.domain}_view`));
  const readable = id ? domainReader && (!record || can(`cms_${record.domain}_view`)) : Object.values(governanceResources).some(item => can(`cms_${item.domain}_view`) && can(`cms_${item.domain}_edit`));
  const editable = !!domain && can(`cms_${domain}_view`) && can(`cms_${domain}_edit`) && (!record || !["approved", "revoked"].includes(record.status));
  const formDirty = JSON.stringify(form) !== JSON.stringify(base ? proposal(base.data) : kind === "rights" ? rightsBlank : terminologyBlank);
  const dirty = formDirty || reviewDirty || !!revokeReason;
  const blocked = governanceBlocked(writeError);
  const evidenceRequired = kind === "terminology" || (form as RightsPayload).status === "allowed";
  const valid = !!resource && !!form.resource_version && validEvidence(form.evidence, evidenceRequired) && (kind !== "rights" || validEvidence((form as RightsPayload).holder_evidence, (form as RightsPayload).status === "allowed"));
  const labels = kind === "rights" ? rightsFieldLabels : terminologyFieldLabels;
  useEffect(() => { setDirty(dirty || busy); return () => setDirty(false); }, [dirty, busy, setDirty]);
  useEffect(() => { const params = new URLSearchParams(new URLSearchParams(location.search).get("list") || ""); const safe = new URLSearchParams(); for (const key of ["q", "resource_type", "resource_id", "status", "computed_status", "mine", "page", "page_size"]) if (params.get(key)) safe.set(key, params.get(key)!); setBack(`/admin-console/${kind}?${safe}`); }, [kind]);
  useEffect(() => {
    if (!id || !readable) return; let active = true; setLoading(true); setError(undefined);
    cms<GovernanceDetail>(`/governance/${kind}/${id}/`).then(result => { if (active) { setBase(result); setForm(proposal(result.data)); setResource(binding(result.data)); setWriteError(undefined); setReviewDirty(false); setRevokeReason(""); } }).catch(failure => { if (active) setError(failure); }).finally(() => { if (active) setLoading(false); });
    return () => { active = false; };
  }, [id, kind, retry, readable]);
  useEffect(() => {
    if (!id || tab !== "history" || !readable) return; let active = true; setHistory(undefined); setHistoryError(undefined);
    cms<CmsPage<GovernanceEvent>>(`/governance/${kind}/${id}/history/?page=${historyPage}`).then(result => { if (active) setHistory(result.data); }).catch(failure => { if (active) setHistoryError(failure); });
    return () => { active = false; };
  }, [id, kind, tab, historyPage, retry, readable, record?.version]);
  function accept(result: { data: GovernanceDetail; etag: string | null }) { setBase(result); setForm(proposal(result.data)); setResource(binding(result.data)); setSaved(true); setWriteError(undefined); setReviewDirty(false); setRevokeReason(""); }
  async function save(event: React.FormEvent) {
    event.preventDefault(); if (lock.current || blocked || !editable || !valid || (id && !base?.etag)) return;
    lock.current = true; setBusy(true); setWriteError(undefined); setSaved(false);
    const payload = { ...form, evidence: form.evidence.map(item => ({ ...item, locator: item.locator.trim() })), reason: "CORRECTION_REQUIRED" };
    if (kind === "terminology") (payload as TerminologyPayload).alternatives = (payload as TerminologyPayload).alternatives.map(value => value.trim()).filter(Boolean);
    if (id) { for (const field of ["resource_type", "resource_id", ...(kind === "rights" ? ["material", "intended_use"] : ["term_kind"])]) delete (payload as unknown as Record<string, unknown>)[field]; }
    try {
      const result = await cms<GovernanceDetail>(`/governance/${kind}/${id ? `${id}/` : ""}`, { method: id ? "PATCH" : "POST", ...(id ? { headers: { "If-Match": base!.etag! } } : {}), body: JSON.stringify(payload) }, me.user.id);
      accept(result); setDirty(false); if (!id) location.assign(`/admin-console/${kind}/${result.data.record.id}`);
    } catch (failure) { setWriteError(failure); }
    finally { lock.current = false; setBusy(false); }
  }
  async function action(name: string, payload: Record<string, unknown>): Promise<boolean> {
    if (!id || !base?.etag || !domain || lock.current || blocked || formDirty) return false;
    const reviewScope = can(`cms_review_decide_${domain}_${kind}`) && can(`cms_${domain}_view`);
    const allowed = name === "reopen" ? can(`cms_${domain}_edit`) && can(`cms_${domain}_view`) : name === "revoke" ? kind === "rights" && can("cms_rights_revoke") && reviewScope : can(`cms_${kind}_decide`) && reviewScope;
    if (!allowed) return false;
    lock.current = true; setBusy(true); setWriteError(undefined); setSaved(false);
    try { accept(await cms<GovernanceDetail>(`/governance/${kind}/${id}/${name}/`, { method: "POST", headers: { "If-Match": base.etag }, body: JSON.stringify(payload) }, me.user.id)); return true; }
    catch (failure) { setWriteError(failure); return false; }
    finally { lock.current = false; setBusy(false); }
  }
  if (!readable) return <CmsState error={new CmsError(403, "PERMISSION_DENIED", "")} />;
  if (loading) return <CmsState loading />;
  if (error) return <CmsState error={error} retry={() => setRetry(n => n + 1)} />;
  return <div className="stack" dir="rtl"><a className="cms-link" href={back}>→ بازگشت به صف با فیلتر قبلی</a>
    <header className="cms-title"><p className="eyebrow">حاکمیت محتوا / {kind === "rights" ? "حقوق محتوا" : "اصطلاحات فارسی"}</p><h1>{id ? "پیشنهاد و تصمیم نسخهٔ دقیق" : "پیشنهاد تازه"}</h1>{record && <div className="cms-actions"><span className="cms-badge">نسخهٔ {faNumber(record.version)}</span><span>{governanceLabels[record.status] || record.status}</span><span>{governanceLabels[record.computed_status] || record.computed_status}</span></div>}</header>
    <nav className="cms-tabs" aria-label="نماهای پیشنهاد">{[...(id ? [["detail", "نمای کلی و موانع"]] : []), ["edit", "پیشنهاد و شواهد"], ...(id ? [["review", "بررسی و تصمیم"], ["history", "تاریخچه"]] : [])].map(([value, label]) => <button type="button" className="button secondary" key={value} aria-pressed={tab === value} onClick={() => setTab(value)}>{label}</button>)}</nav>
    <GovernanceError error={writeError} prefix={kind} labels={{ ...labels, ...governanceLabels }}>{id && blocked && <button type="button" className="button secondary" disabled={busy} onClick={() => leave(() => { setRetry(n => n + 1); setSaved(false); })}>دریافت صریح نسخه و وضعیت سرور؛ کنارگذاشتن فرم محلی</button>}{!id && blocked && <p>پیش از ثبت دوباره، <a className="cms-link" href={`/admin-console/${kind}`}>صف پیشنهادها</a> و <a className="cms-link" href="/admin-console/audit">تاریخچهٔ عملیات</a> را بررسی کنید.</p>}</GovernanceError>
    {saved && <p className="cms-success" role="status">پاسخ نسخهٔ تازه از سرور دریافت شد.</p>}
    {tab === "detail" && record && <section className="card stack"><h2>دامنه و وضعیت معتبر سرور</h2><p>{governanceResources[record.resource_type]?.label} {faNumber(record.resource_id)}</p><p className="cms-id">نسخهٔ هدف: <bdi>{record.resource_version}</bdi> · سیاست: {faNumber(record.policy_version)}</p><p>{record.eligible ? "واجد شرایط همین دامنه در سرور" : "واجد شرایط نیست"}</p><ul>{record.blockers.map((blocker, index) => <li key={index}><bdi>{governanceLabels[blocker] || blocker}</bdi></li>)}</ul>
      {Object.entries(record.payload).filter(([key]) => !["resource_type", "resource_id", "resource_version"].includes(key)).map(([key, value]) => <div key={key}><h3>{labels[key] || key}</h3><p className="cms-prose" dir={key === "name_en" || key.endsWith("_on") ? "ltr" : "auto"}>{typeof value === "string" ? governanceLabels[value] || value || "ثبت نشده" : sourceValue(value)}</p></div>)}
      {record.preview && <section className="cms-preview stack" dir={record.preview.dir}><h3>{record.preview.name_fa}</h3><p dir={record.preview.name_en_dir}>{record.preview.name_en}</p><p>{governanceLabels[record.preview.term_kind]}</p><p>{record.preview.alternatives.join("، ")}</p><p className="cms-badge">پیش‌نمایش پیشنهاد نسخهٔ {faNumber(record.version)}؛ منتشر نشده</p></section>}
      {!!record.candidate_conflicts?.length && <div className="cms-notice stack"><h3>اصطلاحات مشابه؛ تصمیم خودکار انجام نمی‌شود</h3>{record.candidate_conflicts.map((candidate, index) => <p key={index} dir="auto">{sourceValue(candidate)}</p>)}{record.candidate_conflicts_more && <p>نمایش نامزدها محدود است؛ برای بررسی بیشتر، صف همین دامنه را جست‌وجو کنید.</p>}</div>}
    </section>}
    {tab === "edit" && <form className="stack" onSubmit={save}>
      {editable || !id ? <GovernanceResourcePicker value={resource} disabled={busy || blocked} immutable={!!id} onChange={value => { setResource(value); setForm(current => ({ ...current, resource_type: value.resource_type, resource_id: value.resource_id, resource_version: value.resource_version })); setSaved(false); }} /> : <p className="cms-notice">{record && ["approved", "revoked"].includes(record.status) ? "پیش از اصلاح، بررسی را بازگشایی کنید؛ تأیید قبلی برای نسخهٔ تازه معتبر نیست." : "برای ویرایش این دامنه مجوز ندارید."}</p>}
      <section className="card stack">{kind === "rights" ? <RightsFields value={form as RightsPayload} onChange={value => { setForm(value); setSaved(false); }} disabled={busy || blocked || !editable} immutable={!!id} error={writeError} /> : <TerminologyFields value={form as TerminologyPayload} onChange={value => { setForm(value); setSaved(false); }} disabled={busy || blocked || !editable} immutable={!!id} error={writeError} />}
        <p className="muted">دلیل ثبت پیشنهاد: {governanceLabels.CORRECTION_REQUIRED}. ذخیره، نسخهٔ تازهٔ پیشنهاد می‌سازد و تخصیص قبلی را پاک می‌کند.</p><div className="cms-actions"><button className="button primary" disabled={busy || blocked || !editable || !valid || (!!id && !base?.etag)}>{id ? "ثبت نسخهٔ تازه برای بررسی" : "ارسال پیشنهاد برای بررسی"}</button><button type="button" className="button secondary" disabled={busy} onClick={() => leave(() => { setForm(base ? proposal(base.data) : kind === "rights" ? rightsBlank : terminologyBlank); setResource(base ? binding(base.data) : undefined); setWriteError(undefined); setSaved(false); })}>کنارگذاشتن تغییرات فرم</button></div>
      </section>
    </form>}
    {tab === "review" && base && <><GovernanceReview key={record?.version} detail={base.data} disabled={busy || blocked || formDirty} action={action} onDirty={setReviewDirty} />
      <section className="card stack"><h2>بازگشایی و لغو</h2>{formDirty && <p className="cms-notice">پیش از تصمیم، تغییرات محلی را ذخیره یا کنار بگذارید.</p>}
        {kind === "rights" && <p className="muted">بازگشایی و اصلاح، پیشنهاد تازه‌ای برای بررسی می‌سازند. تصمیم حقوقی مؤثر قبلی تا تصمیم صریح تازه، با شرایط فعلی منبع، هدف، سیاست، بازبین و تاریخ‌ها ارزیابی می‌شود.</p>}
        {domain && can(`cms_${domain}_edit`) && <button type="button" className="button secondary" disabled={busy || blocked || formDirty} onClick={() => action("reopen", {})}>{kind === "rights" ? "بازگشایی بررسی حقوق" : "بازگشایی؛ تأیید اصطلاح قبلی معتبر نخواهد شد"}</button>}
        {kind === "rights" && domain && can("cms_rights_revoke") && can(`cms_review_decide_${domain}_rights`) && <form onSubmit={event => { event.preventDefault(); if (revokeReason) action("revoke", { reason: revokeReason }); }}><fieldset className="cms-fieldset" disabled={busy || blocked || formDirty || record?.status === "revoked"}><legend>لغو دامنهٔ حقوق با حفظ تاریخچه</legend><label>دلیل لغو<select required value={revokeReason} onChange={event => setRevokeReason(event.target.value)}><option value="">انتخاب کنید</option>{base.data.reason_codes.revoke.map(code => <option key={code} value={code}>{governanceLabels[code] || code}</option>)}</select></label><button className="button secondary" disabled={!revokeReason}>لغو اجازهٔ همین دامنه</button></fieldset></form>}
      </section>
    </>}
    {tab === "history" && <GovernanceHistory data={history} error={historyError} retry={() => setRetry(n => n + 1)} onPage={setHistoryPage}>{event => <pre className="cms-prose" dir="auto">{sourceValue(event)}</pre>}</GovernanceHistory>}
  </div>;
}
