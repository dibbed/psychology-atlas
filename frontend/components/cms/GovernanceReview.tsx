"use client";
import { useEffect, useState } from "react";
import { cms, CmsPage } from "@/lib/cms";
import { GovernanceDetail, GovernanceReviewer, governanceLabels } from "@/lib/cmsGovernance";
import { CmsState, useCms } from "./CmsShell";
import { GovernancePagination } from "./GovernanceForms";
import { faNumber } from "@/lib/fa";

export default function GovernanceReview({ detail, disabled, action, onDirty }: {
  detail: GovernanceDetail; disabled: boolean; action: (action: string, payload: Record<string, unknown>) => Promise<boolean>; onDirty: (dirty: boolean) => void;
}) {
  const { me, can } = useCms(); const record = detail.record;
  const allowed = can(`cms_${record.kind}_decide`) && can(`cms_review_decide_${record.domain}_${record.kind}`) && can(`cms_${record.domain}_view`);
  const active = ["submitted", "in_review"].includes(record.status);
  const stale = record.computed_status === "stale";
  const [reviewers, setReviewers] = useState<CmsPage<GovernanceReviewer>>(); const [error, setError] = useState<unknown>(); const [page, setPage] = useState(1); const [retry, setRetry] = useState(0);
  const [reviewerId, setReviewerId] = useState(""); const [outcome, setOutcome] = useState("approve"); const [reason, setReason] = useState(""); const [ack, setAck] = useState(false);
  const reviewer = reviewers?.results.find(item => String(item.id) === reviewerId);
  const ownerAck = detail.policy.mode === "solo_owner" && can("cms_owner");
  const approvalReason = detail.reason_codes.approve[0];
  const dirty = !!reviewerId || outcome !== "approve" || !!reason || ack;
  useEffect(() => { onDirty(dirty); return () => onDirty(false); }, [dirty, onDirty]);
  useEffect(() => {
    if (!allowed || !active) return; let mounted = true; setReviewers(undefined); setError(undefined); setReviewerId("");
    cms<CmsPage<GovernanceReviewer>>(`/governance/${record.kind}/${record.id}/reviewers/?page=${page}`).then(result => { if (mounted) setReviewers(result.data); }).catch(failure => { if (mounted) setError(failure); });
    return () => { mounted = false; };
  }, [record.id, record.kind, record.version, active, allowed, page, retry]);
  return <section className="card stack"><h2>تخصیص و تصمیم نسخهٔ دقیق</h2><p className="cms-notice">نسخهٔ پیشنهاد {faNumber(record.version)} · سیاست {faNumber(detail.policy.version)}: {detail.policy.mode === "two_person" ? "دو نفره؛ مشارکت‌کننده حتی مالک نمی‌تواند بازبین باشد" : "مالک تنها؛ خودبازبینی با پذیرش صریح"}</p>
    <p className="cms-id">نسخهٔ هدف: <bdi>{record.resource_version}</bdi> · اثرانگشت شواهد: <bdi>{record.dependency_digest}</bdi></p>
    {stale && <div className="cms-notice stack"><p>نسخه یا شرایط پیشنهاد تغییر کرده است؛ پیش از تخصیص و تصمیم، پیشنهاد باید به‌روزرسانی یا بررسی بازگشایی شود.</p><ul>{record.blockers.map((code, index) => <li key={index}>{governanceLabels[code] || code}</li>)}</ul></div>}
    {!allowed ? <p className="muted">برای تخصیص و تصمیم، مجوز عمومی و مجوز بررسی همین دامنه لازم است.</p> : !active ? <p className="muted">این پیشنهاد در وضعیت بررسی فعال نیست؛ برای بررسی تازه، بازگشایی لازم است.</p> : <>
        <form onSubmit={async event => { event.preventDefault(); if (!disabled && !stale && reviewer && !reviewer.conflicts.length && await action("assign", { reviewer_id: reviewer.id })) setReviewerId(""); }}>
        <fieldset className="cms-fieldset" disabled={disabled || stale}><legend>انتخاب بازبین مجاز</legend>
          {error ? <CmsState error={error} retry={() => setRetry(n => n + 1)} /> : !reviewers ? <CmsState loading /> : <><label>بازبین<select value={reviewerId} onChange={event => setReviewerId(event.target.value)}><option value="">انتخاب کنید</option>{reviewers.results.map(item => <option key={item.id} value={item.id} disabled={item.conflicts.length > 0}>{item.username}{item.conflicts.length ? ` — ${item.conflicts.map(code => governanceLabels[code] || code).join("، ")}` : ""}</option>)}</select></label><GovernancePagination data={reviewers} disabled={disabled} onPage={setPage} /></>}
          <button className="button secondary" disabled={!reviewer || !!reviewer.conflicts.length || !!error}>تخصیص بازبین همین نسخه</button>
        </fieldset>
      </form>
      {record.assignee_id != null && record.assignee_id !== me.user.id && <p className="cms-notice">فقط بازبین تخصیص‌یافته می‌تواند تصمیم بگیرد.</p>}
      {record.assignee_id === me.user.id && <form onSubmit={async event => { event.preventDefault(); if (!disabled && !stale && (outcome === "approve" || reason) && (!ownerAck || ack) && await action("decide", { outcome, reason: outcome === "approve" ? approvalReason : reason, self_review_ack: ack })) { setReason(""); setAck(false); setOutcome("approve"); } }}>
        <fieldset className="cms-fieldset" disabled={disabled || stale}><legend>تصمیم فقط برای نسخهٔ نمایش‌داده‌شده</legend>
          <label>نتیجه<select value={outcome} onChange={event => setOutcome(event.target.value)}><option value="approve">تأیید همین پیشنهاد</option><option value="reject">درخواست اصلاح</option></select></label>
          {outcome === "approve" ? <p>دلیل ثبت‌شده: {governanceLabels[approvalReason]}</p> : <label>دلیل مستند تصمیم<select required value={reason} onChange={event => setReason(event.target.value)}><option value="">انتخاب کنید</option>{detail.reason_codes.reject.map(code => <option key={code} value={code}>{governanceLabels[code] || code}</option>)}</select></label>}
          {ownerAck && <label className="cms-review-check"><input type="checkbox" checked={ack} onChange={event => setAck(event.target.checked)} />اگر مشارکت‌کنندهٔ این پیشنهاد هستم، به‌عنوان مالک خودبازبینی همین نسخه را صریحاً می‌پذیرم.</label>}
          <p className="muted">عنوان دلیل، اجازهٔ حقوقی یا تأیید علمی نمی‌سازد؛ وضعیت دقیق پیشنهاد و تصمیم سرور ملاک است.</p>
          <button className="button primary" disabled={(outcome !== "approve" && !reason) || (ownerAck && !ack)}>ثبت تصمیم نسخهٔ {faNumber(record.version)}</button>
        </fieldset>
      </form>}
    </>}
  </section>;
}
