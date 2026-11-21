"use client";
import { useEffect, useState } from "react";
import { cms, CmsPage, ReviewDetail, ReviewReviewer, ReviewTask, reviewFieldLabels, reviewReasonLabels } from "@/lib/cms";
import { faNumber } from "@/lib/fa";
import { CmsState, useCms } from "./CmsShell";

export default function ReviewTaskPanel({ task, detail, path, disabled, onDirty, action, domain = 'core', labels = reviewFieldLabels }: {
  task: ReviewTask; detail: ReviewDetail; path: string; disabled: boolean;
  onDirty: (key: string, dirty: boolean) => void;
  action: (name: "assign" | "decide", body: Record<string, unknown>) => Promise<boolean>;
  domain?: string; labels?: Record<string, string>;
}) {
  const { me, can, leave } = useCms();
  const [page, setPage] = useState(1);
  const [reviewers, setReviewers] = useState<CmsPage<ReviewReviewer>>();
  const [error, setError] = useState<unknown>();
  const [retry, setRetry] = useState(0);
  const [reviewer, setReviewer] = useState<ReviewReviewer>();
  const [outcome, setOutcome] = useState<"approve" | "reject">("approve");
  const [reason, setReason] = useState("");
  const [fields, setFields] = useState<string[]>([]);
  const [ack, setAck] = useState(false);
  const permitted = can(`cms_review_decide_${domain}_${task.review_type}`);
  const active = ["submitted", "in_review"].includes(detail.record.revision_status || "") && ["queued", "assigned"].includes(task.status);
  const stale = detail.approval.blockers.some(blocker => blocker !== "APPROVAL_REQUIRED");
  const sourceDone = detail.tasks.some(item => item.review_type === "source" && item.status === "approved");
  const scienceBlocked = task.review_type === "scientific" && !sourceDone;
  const decide = permitted && active && task.status === "assigned" && task.assignee_id === me.user.id;
  const ownerAck = can("cms_owner") && detail.policy.mode === "solo_owner";
  const dirty = !!reviewer || outcome !== "approve" || !!reason || fields.length > 0 || ack;
  useEffect(() => { onDirty(String(task.id), dirty); return () => onDirty(String(task.id), false); }, [task.id, dirty, onDirty]);
  useEffect(() => {
    if (!permitted || !active) return;
    let current = true; setReviewers(undefined); setError(undefined);
    cms<CmsPage<ReviewReviewer>>(`${path}reviewers/?review_type=${task.review_type}&page=${page}`).then(result => { if (current) setReviewers(result.data); })
      .catch(failure => { if (current) setError(failure); });
    return () => { current = false; };
  }, [path, permitted, active, task.review_type, task.version, detail.policy.version, page, retry]);
  const validDecision = outcome === "approve" || (!!reason && detail.rejection_reasons.includes(reason) && fields.length > 0);
  const statusLabels: Record<ReviewTask["status"], string> = { queued: "در صف", assigned: "تخصیص‌یافته", approved: "تأییدشده", rejected: "ردشده", cancelled: "لغوشده" };
  const reset = () => { setReviewer(undefined); setOutcome("approve"); setReason(""); setFields([]); setAck(false); };
  return <section className="card stack" aria-labelledby={`review-task-${task.id}`}>
    <h2 id={`review-task-${task.id}`}>{task.review_type === "source" ? "۱. بررسی منابع" : "۲. بررسی علمی"}</h2>
    <p>وظیفهٔ {faNumber(task.id)} · نسخهٔ {faNumber(task.version)} · {statusLabels[task.status]}</p>
    <p>بازبین تخصیص‌یافته: <bdi>{task.assignee || "هنوز تخصیص داده نشده"}</bdi></p>
    <p className="cms-id">نسخهٔ موضوع: {faNumber(task.subject_revision)} · سیاست ثبت‌شده: {faNumber(task.policy_version)}</p>
    {scienceBlocked && <p className="cms-notice">ابتدا منابع در وظیفهٔ جداگانه تأیید شوند؛ سپس تصمیم علمی ثبت شود.</p>}
    {permitted && active && <>
      <form className="stack" onSubmit={async event => {
        event.preventDefault();
        if (!reviewer || reviewer.conflict || disabled || stale) return;
        if (await action("assign", { task_id: task.id, task_version: task.version, reviewer_id: reviewer.id })) setReviewer(undefined);
      }}>
        <fieldset disabled={disabled || stale} className="cms-fieldset"><legend>تخصیص بازبین {task.review_type === "source" ? "منابع" : "علمی"}</legend>
          {error ? <CmsState error={error} retry={() => setRetry(n => n + 1)} /> : !reviewers ? <CmsState loading /> : <>
            <label>بازبین {task.review_type === "source" ? "منابع" : "علمی"}<select value={reviewer?.id || ""} onChange={event => setReviewer(reviewers.results.find(item => item.id === Number(event.target.value)))}>
              <option value="">بازبین را انتخاب کنید</option>
              {reviewer && !reviewers.results.some(item => item.id === reviewer.id) && <option value={reviewer.id}>{reviewer.username}</option>}
              {reviewers.results.map(item => <option key={item.id} value={item.id} disabled={!!item.conflict}>{item.username}{item.conflict ? ` — ${reviewReasonLabels[item.conflict] || item.conflict}` : ""}</option>)}
            </select></label>
            {!reviewers.count && <p className="muted">بازبین واجد مجوزی یافت نشد.</p>}
            <nav className="cms-pagination" aria-label={`صفحه‌بندی بازبین‌های ${task.review_type === "source" ? "منابع" : "علمی"}`}>
              <button type="button" className="button secondary" disabled={page <= 1} onClick={() => setPage(n => n - 1)}>بازبین‌های قبلی</button>
              <span>صفحهٔ {faNumber(page)} · {faNumber(reviewers.count)} بازبین</span>
              <button type="button" className="button secondary" disabled={page * reviewers.page_size >= reviewers.count} onClick={() => setPage(n => n + 1)}>بازبین‌های بعدی</button>
            </nav>
          </>}
          {reviewer?.conflict && <p className="cms-notice">{reviewReasonLabels[reviewer.conflict] || reviewer.conflict}</p>}
          <button className="button secondary" data-testid={`review-assign-${task.review_type}`} disabled={!reviewer || !!reviewer.conflict || !reviewers || !!error}>تخصیص بازبین {task.review_type === "source" ? "منابع" : "علمی"}</button>
        </fieldset>
      </form>
      {task.status === "assigned" && task.assignee_id !== me.user.id && <p className="muted">فقط بازبین تخصیص‌یافته می‌تواند تصمیم این وظیفه را ثبت کند.</p>}
      {decide && <form className="stack" onSubmit={async event => {
        event.preventDefault();
        if (disabled || stale || scienceBlocked || !validDecision || (ownerAck && !ack)) return;
        const body = { task_id: task.id, task_version: task.version, outcome,
          reason: outcome === "approve" ? task.review_type === "source" ? "SOURCE_VERIFIED" : "SCIENCE_VERIFIED" : reason,
          fields: outcome === "approve" ? [] : fields, self_review_ack: ack };
        if (await action("decide", body)) { setOutcome("approve"); setReason(""); setFields([]); setAck(false); }
      }}>
        <fieldset disabled={disabled || stale || scienceBlocked} className="cms-fieldset"><legend>تصمیم بازبین تخصیص‌یافته</legend>
          <label>نتیجهٔ بررسی {task.review_type === "source" ? "منابع" : "علمی"}<select value={outcome} onChange={event => setOutcome(event.target.value as "approve" | "reject")}><option value="approve">تأیید پیشنهاد</option><option value="reject">درخواست اصلاح</option></select></label>
          {outcome === "reject" && <>
            <label>دلیل رد {task.review_type === "source" ? "منابع" : "علمی"}<select required value={reason} onChange={event => setReason(event.target.value)}><option value="">دلیل را انتخاب کنید</option>{detail.rejection_reasons.map(code => <option key={code} value={code}>{reviewReasonLabels[code] || code}</option>)}</select></label>
            <fieldset className="cms-review-fields"><legend>فیلدهای نیازمند اصلاح؛ حداقل یک فیلد</legend>{detail.evidence_fields.map(field => <label key={field} className="cms-review-check"><input type="checkbox" checked={fields.includes(field)} onChange={event => setFields(current => event.target.checked ? [...current, field] : current.filter(key => key !== field))} />{labels[field] || field}</label>)}</fieldset>
          </>}
          {ownerAck && <label className="cms-review-check"><input type="checkbox" checked={ack} onChange={event => setAck(event.target.checked)} />به‌عنوان مالک، اگر نویسندهٔ این پیشنهاد هستم، خودبازبینی آن را صریحاً می‌پذیرم.</label>}
          {detail.policy.mode === "two_person" && <p className="cms-notice">در سیاست دو نفره، نویسنده اجازهٔ تصمیم روی پیشنهاد خود را ندارد؛ تعارض در سرور دوباره کنترل می‌شود.</p>}
          <button className="button primary" data-testid={`review-${outcome === "approve" ? "approve" : "reject"}-${task.review_type}`} disabled={!validDecision || (ownerAck && !ack)}>{outcome === "approve" ? task.review_type === "source" ? "تأیید منابع" : "تأیید بررسی علمی" : "ثبت درخواست اصلاح"}</button>
        </fieldset>
      </form>}
      {dirty && <button type="button" className="button secondary" disabled={disabled} onClick={() => leave(reset)}>پاک کردن فرم این وظیفه</button>}
    </>}
    {!permitted && active && <p className="muted">مجوز تصمیم و تخصیص این نوع بررسی را ندارید.</p>}
  </section>;
}
