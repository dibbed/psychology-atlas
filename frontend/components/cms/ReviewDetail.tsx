"use client";
import { useCallback, useEffect, useRef, useState } from "react";
import { cms, CmsError, ReviewDetail as Detail, ReviewEvidence, ReviewSummary, publicationLabels, revisionLabels,
  reviewFieldLabels, reviewPolicyLabels, reviewReasonLabels, reviewStatusLabels } from "@/lib/cms";
import { faNumber } from "@/lib/fa";
import { CmsState, useCms } from "./CmsShell";
import ReviewEvidenceForm from "./ReviewEvidenceForm";
import ReviewHistory from "./ReviewHistory";
import ReviewTaskPanel from "./ReviewTaskPanel";
import { DomainValueView, fieldLabel, useDomainSchemas } from './DomainFields';
import { domainHeaders, domainTitle } from '@/lib/cmsDomains';

type Snapshot = { data: Detail; etag: string | null };
export default function ReviewDetail({ kind, id }: { kind: string; id: string }) {
  const { me, can, setDirty, leave } = useCms();
  const {schemas, error: schemaError, retry: retrySchema} = useDomainSchemas();
  const schema = schemas?.find(item => item.kind === kind);
  const allowed = !!schema && can(`cms_${schema.domain}_view`);
  const path = `/reviews/${encodeURIComponent(kind)}/${encodeURIComponent(id)}/`;
  const [base, setBase] = useState<Snapshot>();
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<unknown>();
  const [writeError, setWriteError] = useState<unknown>();
  const [readError, setReadError] = useState<unknown>();
  const [busy, setBusy] = useState(false);
  const busyRef = useRef(false);
  const [locked, setLocked] = useState(false);
  const [saved, setSaved] = useState(false);
  const [retry, setRetry] = useState(0);
  const [evidence, setEvidence] = useState<ReviewEvidence[]>([]);
  const [evidenceDirty, setEvidenceDirty] = useState(false);
  const [formDirty, setFormDirty] = useState<Record<string, boolean>>({});
  const [generation, setGeneration] = useState(0);
  const [back, setBack] = useState("/admin-console/reviews");
  const markForm = useCallback((key: string, dirty: boolean) => setFormDirty(current => current[key] === dirty ? current : { ...current, [key]: dirty }), []);
  useEffect(() => {
    const previous = new URLSearchParams(new URLSearchParams(location.search).get("list") || "");
    const safe = new URLSearchParams();
    for (const key of ["kind", "status", "q", "mine", "page", "page_size"]) if (previous.has(key)) safe.set(key, previous.get(key)!);
    setBack(`/admin-console/reviews${safe.size ? `?${safe}` : ""}`);
  }, [path]);
  useEffect(() => { setDirty(evidenceDirty || Object.values(formDirty).some(Boolean) || busy); return () => setDirty(false); }, [evidenceDirty, formDirty, busy, setDirty]);
  useEffect(() => {
    if (!allowed) return;
    let active = true; setLoading(true); setError(undefined);
    cms<Detail>(path).then(snapshot => { if (active) { setBase(snapshot); setEvidence(snapshot.data.evidence); } })
      .catch(failure => { if (active) setError(failure); }).finally(() => { if (active) setLoading(false); });
    return () => { active = false; };
  }, [path, allowed, retry]);
  async function reload() {
    if (busyRef.current) return;
    busyRef.current = true; setBusy(true); setReadError(undefined);
    try {
      const snapshot = await cms<Detail>(path);
      setBase(snapshot); setEvidence(snapshot.data.evidence); setEvidenceDirty(false); setFormDirty({}); setGeneration(n => n + 1);
      setWriteError(undefined); setLocked(false); setSaved(false); setDirty(false);
    } catch (failure) { setReadError(failure); }
    finally { busyRef.current = false; setBusy(false); }
  }
  async function action(name: "submit" | "assign" | "decide" | "reopen", body: Record<string, unknown>) {
    if (busyRef.current || locked || !base?.etag) return false;
    busyRef.current = true; setBusy(true); setWriteError(undefined); setReadError(undefined); setSaved(false);
    let committed = false;
    try {
      await cms<ReviewSummary>(`${path}${name}/`, { method: "POST", headers: domainHeaders(base.etag), body: JSON.stringify(body) }, me.user.id);
      committed = true;
      const snapshot = await cms<Detail>(path);
      setBase(snapshot); setSaved(true);
      if (name === "submit" || name === "reopen") { setEvidence(snapshot.data.evidence); setEvidenceDirty(false); }
      return true;
    } catch (failure) {
      if (committed) { setLocked(true); setReadError(failure); }
      else {
        setWriteError(failure);
        if (failure instanceof CmsError && (failure.code === "UNKNOWN_OUTCOME" || failure.status === 409 || failure.status === 412 || failure.status >= 500)) setLocked(true);
      }
      return false;
    } finally { busyRef.current = false; setBusy(false); }
  }
  if (schemaError) return <CmsState error={schemaError} retry={retrySchema}/>;
  if (!schemas) return <CmsState loading/>;
  if (!allowed || !schema) return <CmsState error={new CmsError(403, "PERMISSION_DENIED", "")} />;
  if (loading) return <CmsState loading />;
  if (error) return <CmsState error={error} retry={() => setRetry(n => n + 1)} />;
  if (!base) return <CmsState loading />;
  const detail = base.data;
  const record = detail.record;
  const status = record.revision_status || "";
  const disabled = busy || locked || !base.etag;
  const labels = Object.fromEntries(schema.fields.map(field => [field.name, fieldLabel(field)]));
  const populated = Object.entries(record.payload).filter(([field, value]) => detail.evidence_fields.includes(field) && value !== null && value !== '' && value !== undefined && (!Array.isArray(value) || value.length > 0) && (typeof value !== 'object' || Array.isArray(value) || Object.keys(value).length > 0)).map(([field]) => field);
  const serverBlockers = writeError instanceof CmsError ? writeError.details.blockers || [] : [];
  return <div className="stack" data-testid="review-detail">
    <div className="cms-actions"><a className="cms-link" href={back}>→ بازگشت به صف بررسی</a><a className="cms-link" href="/admin-console/reviews/policy">سیاست بررسی مرجع</a>
      <a className="cms-link" href={`/admin-console/content/${kind}/${record.id}`}>جزئیات و ویرایش پیشنهاد</a>
    </div>
    <div className="cms-title"><p className="eyebrow">بررسی پیشنهاد / {schema.label}</p><h1><bdi>{domainTitle(record.payload)}</bdi></h1>
      <div className="cms-actions"><span className="cms-badge">نسخهٔ {faNumber(record.version)}</span><span className="cms-badge">{revisionLabels[status] || status}</span><span className="cms-badge">{reviewStatusLabels[detail.scientific_status]}</span></div>
    </div>
    <p className="cms-notice">تأیید بررسی فقط اعتبار علمی همین پیشنهاد و شواهد آن را مشخص می‌کند؛ انتشار یا اعمال روی محتوای اصلی نیست.</p>
    <section className="card stack"><h2>اعتبار بررسی پیشنهاد</h2>
      <p>واجد تأیید معتبر پیشنهاد: {detail.approval.eligible ? "بله؛ بررسی علمی تازه و معتبر است" : "خیر"}</p>
      {detail.approval.blockers.length > 0 && <ul className="cms-review-blockers">{detail.approval.blockers.map(blocker => <li key={blocker}><bdi>{reviewReasonLabels[blocker] || blocker}</bdi></li>)}</ul>}
      <p>سیاست فعلی: {reviewPolicyLabels[detail.policy.mode]} · نسخهٔ {faNumber(detail.policy.version)}</p>
      <p>محتوای اصلی: {publicationLabels[record.publication] || record.publication}</p>
      <p>شرط عمومی محتوای اصلی موجود: <bdi>{detail.public_gate}</bdi> · {detail.canonical_public_eligible ? "در شرط فعلی واجد است" : "در شرط فعلی واجد نیست"}</p>
      <p className="muted">این شرط وضعیت اصل موجود است و انتشار پیشنهاد را ثابت نمی‌کند. میراث بدون تصمیم علمی معتبر، بازبینی‌شده محسوب نمی‌شود.</p>
      {status === "legacy" && <p className="cms-notice">ابتدا پیشنهاد پیش‌نویس را در ویرایشگر موجود ذخیره کنید؛ محتوای میراث مستقیم برای بررسی ارسال نمی‌شود.</p>}
      {record.intent === 'archive' && <p className="cms-notice">موضوع این بررسی درخواست بایگانی برای برداشت آینده در P16 است؛ اصل فعلی اکنون برداشته نمی‌شود.</p>}
    </section>
    <section className="card stack"><h2>پیشنهاد ذخیره‌شده</h2>{Object.entries(record.payload).map(([field, value]) => <div key={field}><h3>{labels[field] || field}</h3><DomainValueView value={value}/></div>)}</section>
    {writeError != null && <CmsState error={writeError} />}
    {serverBlockers.length > 0 && <ul className="cms-review-blockers">{serverBlockers.map(blocker => <li key={blocker}>{reviewReasonLabels[blocker] || blocker}</li>)}</ul>}
    {readError != null && <CmsState error={readError} />}
    {locked && <p role="alert" className="cms-notice">اقدام تازه قفل است. نتیجه، نسخه و تاریخچه را با دریافت صریح نسخهٔ سرور بررسی کنید؛ عملیات قبلی خودکار تکرار نمی‌شود. دریافت نسخهٔ سرور فرم‌ها را بازنشانی می‌کند.</p>}
    {!base.etag && <p role="alert" className="cms-notice">نسخهٔ امنیتی پاسخ موجود نیست؛ تا دریافت آن هیچ تغییری ارسال نمی‌شود.</p>}
    <div className="cms-actions"><button data-testid="review-reload" className="button secondary" disabled={busy} onClick={() => leave(() => { void reload(); })}>دریافت نسخهٔ سرور و بازنشانی فرم‌ها</button>
      {can(`cms_${schema.domain}_edit`) && can(`cms_${schema.domain}_submit`) && ["submitted", "in_review", "approved"].includes(status) && <button data-testid="review-reopen" className="button secondary" disabled={disabled} onClick={() => leave(() => { void action("reopen", {}); })}>بازگشایی بررسی به پیش‌نویس</button>}
    </div>
    {busy && <p role="status">در حال بررسی درخواست…</p>}
    {saved && <p role="status" className="cms-success">عملیات ثبت و جزئیات تازه دریافت شد؛ پیشنهاد منتشر نشده است.</p>}
    {status === "draft" && can(`cms_${schema.domain}_submit`) && <ReviewEvidenceForm labels={labels} value={evidence} fields={detail.evidence_fields} populated={populated} disabled={disabled}
      onChange={value => { setEvidence(value); setEvidenceDirty(true); setSaved(false); }} onSubmit={() => { void action("submit", { evidence }); }} />}
    {status === "draft" && !can(`cms_${schema.domain}_submit`) && <p className="cms-notice">مجوز ارسال این پیش‌نویس برای بررسی را ندارید.</p>}
    {status !== "draft" && <section className="card stack"><h2>شواهد ثبت‌شدهٔ بررسی</h2>{detail.evidence.length ? <ul className="cms-review-blockers">{detail.evidence.map((item, index) => <li key={index}>منبع {faNumber(item.source_id)} · <bdi>{item.locator}</bdi> · {item.fields.map(field => reviewFieldLabels[field] || field).join("، ")}</li>)}</ul> : <p className="muted">شاهد بررسی ثبت نشده است.</p>}</section>}
    {detail.tasks.length ? <div className="cms-review-tasks">{[...detail.tasks].sort((a, b) => Number(a.review_type === "scientific") - Number(b.review_type === "scientific")).map(task =>
      <ReviewTaskPanel labels={labels} domain={schema.domain} key={`${generation}-${task.id}`} task={task} detail={detail} path={path} disabled={disabled} onDirty={markForm} action={action} />)}</div> : <p className="cms-notice">وظیفهٔ بررسی وجود ندارد؛ بازبینی از ارسال پیش‌نویس همراه با شواهد آغاز می‌شود.</p>}
    <ReviewHistory labels={labels} path={path} version={record.version} />
  </div>;
}
