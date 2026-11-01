"use client";

import { useEffect, useState } from "react";
import { Search } from "lucide-react";
import { CmsState, useCms } from "./CmsShell";
import { cms, CmsError, ReviewQueuePage, ReviewSummary, reviewPolicyLabels, reviewReasonLabels, reviewStatusLabels, revisionLabels } from "@/lib/cms";
import { faNumber } from "@/lib/fa";
import { normalizePersianSearch } from "@/lib/text";
import { useDomainSchemas } from './DomainFields';
import { domainTitle } from '@/lib/cmsDomains';

const taskTypeLabels = { source: "بررسی منابع", scientific: "بررسی علمی" };
const taskStatusLabels: Record<ReviewSummary["tasks"][number]["status"], string> = {
  queued: "در صف", assigned: "تخصیص‌یافته", approved: "تأییدشده", rejected: "ردشده", cancelled: "لغوشده",
};

export default function ReviewQueue() {
  const { can, leave } = useCms();
  const {schemas, error: schemaError, retry: retrySchemas} = useDomainSchemas();
  const [query, setQuery] = useState<URLSearchParams>();
  const [data, setData] = useState<ReviewQueuePage>();
  const [error, setError] = useState<unknown>();
  const [retry, setRetry] = useState(0);
  const allowed = can("cms_core_view") || can("cms_dsm_view");

  useEffect(() => { setQuery(new URLSearchParams(location.search)); }, []);
  useEffect(() => {
    if (!query || !allowed) return;
    let active = true; setError(undefined); setData(undefined);
    const params = new URLSearchParams(query);
    if (params.has("q")) params.set("q", normalizePersianSearch(params.get("q") || ""));
    cms<ReviewQueuePage>(`/reviews/?${params}`).then(result => { if (active) setData(result.data); }).catch(failure => { if (active) setError(failure); });
    return () => { active = false; };
  }, [query, retry, allowed]);

  const pagination = (page: number) => { const params = new URLSearchParams(query); params.set("page", String(page)); return `?${params}`; };
  if (!allowed) return <CmsState error={new CmsError(403, "PERMISSION_DENIED", "")} />;
  if (schemaError) return <CmsState error={schemaError} retry={retrySchemas}/>;
  if (!schemas) return <CmsState loading/>;

  return <div className="stack" dir="rtl" data-testid="review-queue">
    <div className="cms-section-head cms-title">
      <div><p className="eyebrow">محتوای مرجع / بررسی علمی</p><h1>صف بررسی محتوای مرجع</h1><p className="muted">صف شامل پیش‌نویس‌ها و محتوای میراث هم هست؛ میراث بدون تصمیم علمی است.</p></div>
      <a className="button secondary" href="/admin-console/reviews/policy">سیاست بررسی</a>
    </div>
    {query && <form className="cms-filters card" method="get" action="/admin-console/reviews" onSubmit={event => {
      event.preventDefault();
      const params = new URLSearchParams();
      new FormData(event.currentTarget).forEach((value, key) => { if (typeof value === "string" && value) params.set(key, value); });
      leave(() => location.assign(`/admin-console/reviews?${params}`));
    }}>
      <label>جست‌وجوی نام<span className="cms-search-input"><Search size={16} aria-hidden="true" /><input type="search" name="q" defaultValue={query.get("q") || ""} maxLength={200} /></span></label>
      <label>نوع محتوا<select name="kind" defaultValue={query.get("kind") || ""}><option value="">همهٔ انواع مجاز</option>{schemas.map(schema => <option key={schema.kind} value={schema.kind}>{schema.label}</option>)}</select></label>
      <label>وضعیت نسخه<select name="status" defaultValue={query.get("status") || ""}><option value="">همهٔ وضعیت‌ها</option>{Object.entries(revisionLabels).map(([status, label]) => <option key={status} value={status}>{label}</option>)}</select></label>
      <label>وظیفه‌های بررسی<select name="mine" defaultValue={query.get("mine") || ""}><option value="">همهٔ رکوردها</option><option value="1">وظیفه‌های تخصیص‌یافته به من</option></select></label>
      {query.has("page_size") && <input type="hidden" name="page_size" value={query.get("page_size") || ""} />}
      <button className="button secondary" type="submit">اعمال فیلتر</button><a className="cms-link" href="/admin-console/reviews">پاک کردن</a>
    </form>}
    {data && <div className="cms-notice"><p>سیاست فعلی: {reviewPolicyLabels[data.policy.mode]} · نسخهٔ {faNumber(data.policy.version)}</p><p>اعتبار بازبینی علمی پیشنهاد و صلاحیت نمایش عمومی محتوای اصلی، دو ارزیابی مستقل سرورند.</p></div>}
    {error ? <CmsState error={error} retry={() => setRetry(value => value + 1)} /> : !data ? <CmsState loading /> : !data.results.length ? <CmsState empty={data.count ? "در این صفحه نتیجه‌ای نیست؛ به صفحهٔ قبل برگردید." : "هیچ محتوای مجازی با این فیلتر یافت نشد. فیلتر را پاک کنید."} /> : <div className="cms-table-wrap" tabIndex={0} role="region" aria-label="صف بررسی محتوای مرجع؛ قابل پیمایش افقی">
      <table className="cms-table">
        <caption>صف بررسی؛ {faNumber(data.count)} رکورد</caption>
        <thead><tr><th scope="col">نام و نوع محتوا</th><th scope="col">نسخه</th><th scope="col">وضعیت نسخه</th><th scope="col">وضعیت علمی پیشنهاد</th><th scope="col">وظیفه‌های منابع و علمی</th><th scope="col">اعتبار بازبینی علمی پیشنهاد</th><th scope="col">صلاحیت نمایش عمومی محتوای اصلی</th></tr></thead>
        <tbody>{data.results.map((row: ReviewSummary) => <tr key={`${row.record.kind}:${row.record.id}`}>
          <th scope="row"><a className="cms-record-link" data-testid="review-detail-link" href={`/admin-console/reviews/${row.record.kind}/${row.record.id}?list=${encodeURIComponent(query?.toString() || "")}`}><strong>{domainTitle(row.record.payload)}</strong><span>{schemas.find(schema => schema.kind === row.record.kind)?.label || row.record.kind}</span>{row.record.intent === 'archive' && <span className="cms-badge">درخواست بایگانی آینده؛ اصل بدون تغییر</span>}<span className="cms-link">جزئیات بررسی ←</span></a></th>
          <td>{faNumber(row.record.version)}</td>
          <td><span className="cms-badge">{row.record.revision_status ? revisionLabels[row.record.revision_status] || row.record.revision_status : "بدون نسخهٔ جاری"}</span></td>
          <td>{reviewStatusLabels[row.scientific_status]}</td>
          <td>{row.tasks.length ? <ul>{row.tasks.map(task => <li key={task.id}><strong>{taskTypeLabels[task.review_type]}</strong><p>{taskStatusLabels[task.status]} · نسخهٔ وظیفه {faNumber(task.version)}</p><p>بازبین: {task.assignee ? <bdi dir="ltr">{task.assignee}</bdi> : "تخصیص‌نیافته"}</p></li>)}</ul> : <span className="muted">وظیفهٔ بررسی ثبت نشده است.</span>}</td>
          <td><p>{row.approval.eligible ? "بازبینی علمی معتبر و به‌روز" : "فاقد بازبینی علمی معتبر و به‌روز"}</p>{row.approval.blockers.length > 0 && <ul aria-label="موانع اعتبار بازبینی پیشنهاد">{row.approval.blockers.map(blocker => <li key={blocker}>{reviewReasonLabels[blocker] || <bdi dir="ltr">{blocker}</bdi>}</li>)}</ul>}</td>
          <td><p>{row.canonical_public_eligible ? "واجد شرایط نمایش عمومی" : "فاقد شرایط نمایش عمومی"}</p><p className="muted">شرط سرور: <bdi dir="ltr">{row.public_gate}</bdi></p></td>
        </tr>)}</tbody>
      </table>
    </div>}
    {data && <nav className="cms-pagination" aria-label="صفحه‌بندی صف بررسی">{data.page > 1 && <a className="button secondary" href={pagination(data.page - 1)}>صفحهٔ قبل</a>}<span>صفحهٔ {faNumber(data.page)} · {faNumber(data.count)} نتیجه</span>{data.page * data.page_size < data.count && <a className="button secondary" href={pagination(data.page + 1)}>صفحهٔ بعد</a>}</nav>}
  </div>;
}
