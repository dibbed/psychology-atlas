"use client";

import { useEffect, useState } from "react";
import { CmsError, CmsPage, cmsDate } from "@/lib/cms";
import { AdminJob, jobKindLabels, jobStatusLabels } from "@/lib/cmsJobs";
import { faNumber } from "@/lib/fa";
import { CmsState } from "./CmsShell";
import { GovernancePagination } from "./GovernanceForms";
import { JobProgress, usePrivateCms } from "./CmsJobsShared";

export default function JobList() {
  const { can, request, current } = usePrivateCms();
  const allowed = can("cms_enter");
  const [data, setData] = useState<CmsPage<AdminJob>>();
  const [error, setError] = useState<unknown>();
  const [page, setPage] = useState(1); const [status, setStatus] = useState(""); const [reload, setReload] = useState(0);
  useEffect(() => {
    if (!allowed) return;
    let active = true; const abort = new AbortController(); setData(undefined); setError(undefined);
    const params = new URLSearchParams({ page: String(page) }); if (status) params.set("status", status);
    request<CmsPage<AdminJob>>(`/jobs/?${params}`, { signal: AbortSignal.any([abort.signal, AbortSignal.timeout(15000)]) })
      .then(result => { if (active && current()) setData(result.data); })
      .catch(failure => { if (active && current()) setError(failure); });
    return () => { active = false; abort.abort(); };
  }, [allowed, current, request, page, status, reload]);
  if (!allowed) return <CmsState error={new CmsError(403, "PERMISSION_DENIED", "")} />;
  return <div className="stack" dir="rtl"><header className="cms-title"><p className="eyebrow">ورود پژوهش / پاکسازی فایل خصوصی</p><h1>کارهای پردازش</h1><p className="muted">کارهای قابل‌دسترسی حساب فعلی. مجوز هر نوع کار، دامنهٔ جاری و مالکیت در سرور دوباره بررسی می‌شود.</p></header>
    <div className="cms-filters card"><label>وضعیت کار<select value={status} onChange={event => { setStatus(event.target.value); setPage(1); }}><option value="">همهٔ وضعیت‌ها</option>{(["queued", "running", "succeeded", "failed", "cancelled"] as const).map(value => <option key={value} value={value}>{jobStatusLabels[value]}</option>)}</select></label>
      <button className="button secondary" onClick={() => setReload(n => n + 1)}>بازخوانی فهرست</button>{(can("cms_artifact_upload") || can("cms_artifact_download")) && <a className="cms-link" href="/admin-console/research/intake">ورود و فایل‌های خصوصی</a>}</div>
    {error ? <CmsState error={error} retry={() => setReload(n => n + 1)} /> : !data ? <CmsState loading /> : <>
      {!data.results.length ? <CmsState empty="کار قابل‌دسترسی با این وضعیت پیدا نشد." /> : <div className="cms-table-wrap" role="region" tabIndex={0} aria-label="کارهای پردازش؛ قابل پیمایش افقی"><table className="cms-table"><caption>{faNumber(data.count)} کار</caption><thead><tr><th scope="col">کار</th><th scope="col">وضعیت</th><th scope="col">پیشرفت واقعی</th><th scope="col">آخرین تغییر</th></tr></thead>
        <tbody>{data.results.map(job => <tr key={job.id}><th scope="row"><a className="cms-record-link cms-link" href={`/admin-console/jobs/${job.id}`}>جزئیات {jobKindLabels[job.kind] || job.kind}<bdi className="cms-id">{job.id}</bdi></a></th><td>{jobStatusLabels[job.status] || job.status}{job.cancel_requested && <p>لغو درخواست شده؛ هنوز پایان نیافته</p>}</td><td><JobProgress job={job} /></td><td>{cmsDate(job.updated_at)}{job.error_code && <p className="cms-id" dir="ltr">{job.error_code}</p>}</td></tr>)}</tbody></table></div>}
      <GovernancePagination data={data} onPage={setPage} /></>}
  </div>;
}
