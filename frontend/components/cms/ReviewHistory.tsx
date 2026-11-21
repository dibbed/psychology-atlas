"use client";
import { useEffect, useState } from "react";
import { cms, CmsPage, ReviewDecision, cmsDate, reviewFieldLabels, reviewPolicyLabels, reviewReasonLabels } from "@/lib/cms";
import { faNumber } from "@/lib/fa";
import { CmsState } from "./CmsShell";

export default function ReviewHistory({ path, version, labels = reviewFieldLabels }: { path: string; version: number; labels?: Record<string, string> }) {
  const [page, setPage] = useState(1);
  const [data, setData] = useState<CmsPage<ReviewDecision>>();
  const [error, setError] = useState<unknown>();
  const [retry, setRetry] = useState(0);
  useEffect(() => {
    let active = true; setData(undefined); setError(undefined);
    cms<CmsPage<ReviewDecision>>(`${path}history/?page=${page}`).then(result => { if (active) setData(result.data); })
      .catch(failure => { if (active) setError(failure); });
    return () => { active = false; };
  }, [path, version, page, retry]);
  const outcomes: Record<string, string> = { assigned: "تخصیص بازبین", approve: "تأیید پیشنهاد", reject: "درخواست اصلاح", reopened: "بازگشایی", invalidated: "عدم اعتبار برای اقدام تازه" };
  return <section className="card stack"><h2>تاریخچهٔ تصمیم‌های بررسی</h2>
    <p className="muted">تصمیم‌ها تغییرناپذیرند و نسخه، شواهد و سیاست زمان تصمیم را نگه می‌دارند؛ تاریخچه مجوز انتشار یا اعتبار فعلی نیست.</p>
    {error ? <CmsState error={error} retry={() => setRetry(n => n + 1)} /> : !data ? <CmsState loading /> : <>
      {!data.results.length && <CmsState empty="در این صفحه تصمیمی ثبت نشده است." />}
      {data.results.map(decision => <details key={decision.id} className="cms-history-entry">
        <summary>{decision.review_type === "source" ? "منابع" : "علمی"} · {outcomes[decision.outcome] || decision.outcome} · <time dateTime={decision.created_at}>{cmsDate(decision.created_at)}</time></summary>
        <div className="stack"><p>دلیل: <bdi>{reviewReasonLabels[decision.reason] || decision.reason}</bdi></p>
          <p>نسخهٔ موضوع: {faNumber(decision.subject_revision)} · نسخهٔ تصمیم: {faNumber(decision.revision)} · سیاست {faNumber(decision.policy_version)}: {reviewPolicyLabels[decision.policy_mode]}</p>
          <p>خودبازبینی: {decision.self_review ? "بله؛ با پذیرش صریح مالک" : "خیر"}</p>
          <p>فیلدها: {decision.fields.map(field => labels[field] || field).join("، ") || "بدون فیلد؛ تصمیم تأیید یا گردش وظیفه"}</p>
          {decision.supersedes != null && <p>جایگزین تصمیم شمارهٔ {faNumber(decision.supersedes)}</p>}
          <ul>{decision.evidence.map((evidence, index) => <li key={index}>منبع {faNumber(evidence.source_id)} · <bdi>{evidence.locator}</bdi> · {evidence.fields.map(field => labels[field] || field).join("، ")}</li>)}</ul>
          <dl className="cms-audit-detail">{[["ارجاع تصمیم‌گیرنده", decision.actor_ref], ["ارجاع بازبین", decision.assignee_ref], ["اثر انگشت موضوع", decision.revision_hash], ["اثر انگشت وابستگی‌ها", decision.dependency_digest]].map(([label, value]) => <div key={label}><dt>{label}</dt><dd><bdi>{value || "—"}</bdi></dd></div>)}</dl>
        </div>
      </details>)}
      <nav className="cms-pagination" aria-label="صفحه‌بندی تصمیم‌های بررسی">
        <button className="button secondary" disabled={page <= 1} onClick={() => setPage(n => n - 1)}>تصمیم‌های جدیدتر</button><span>صفحهٔ {faNumber(data.page)} · {faNumber(data.count)} تصمیم</span>
        <button className="button secondary" disabled={page * data.page_size >= data.count} onClick={() => setPage(n => n + 1)}>تصمیم‌های قدیمی‌تر</button>
      </nav>
    </>}
  </section>;
}
