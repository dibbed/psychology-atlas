"use client";

import { useEffect, useState } from "react";
import { CmsError, CmsPage, cmsDate } from "@/lib/cms";
import { ResearchDataset } from "@/lib/cmsJobs";
import { faNumber } from "@/lib/fa";
import { CmsState } from "./CmsShell";
import { GovernancePagination } from "./GovernanceForms";
import { ResearchBoundary, usePrivateCms } from "./CmsJobsShared";

export default function ResearchList() {
  const { can, request, current } = usePrivateCms(); const allowed = can("cms_research_view");
  const [data, setData] = useState<CmsPage<ResearchDataset>>(); const [error, setError] = useState<unknown>();
  const [page, setPage] = useState(1); const [reload, setReload] = useState(0);
  useEffect(() => {
    if (!allowed) return;
    let active = true; const abort = new AbortController(); setData(undefined); setError(undefined);
    request<CmsPage<ResearchDataset>>(`/research/datasets/?page=${page}`, { signal: AbortSignal.any([abort.signal, AbortSignal.timeout(15000)]) })
      .then(result => { if (active && current()) setData(result.data); }).catch(failure => { if (active && current()) setError(failure); });
    return () => { active = false; abort.abort(); };
  }, [allowed, request, current, page, reload]);
  if (!allowed) return <CmsState error={new CmsError(403, "PERMISSION_DENIED", "")} />;
  return <div className="stack" dir="rtl"><header className="cms-title cms-section-head"><div><p className="eyebrow">پژوهش / دادهٔ حفظ‌شده</p><h1>مجموعه‌های پژوهشی</h1><p className="muted">فرادادهٔ امن و وضعیت ورود مجموعه‌ها؛ متن خام فقط با مجوز و ثبت رویداد جداگانه در دسترس است.</p></div><div className="cms-actions">
    {(can("cms_artifact_upload") || can("cms_artifact_download")) && <a className="button primary" href="/admin-console/research/intake">ورود و فایل‌های خصوصی</a>}{can("cms_research_intake") && <a className="button secondary" href="/admin-console/jobs">پیگیری کارها</a>}</div></header><ResearchBoundary />
    <button className="button secondary" onClick={() => setReload(n => n + 1)}>بازخوانی مجموعه‌ها</button>
    {error ? <CmsState error={error} retry={() => setReload(n => n + 1)} /> : !data ? <CmsState loading /> : <>
      {!data.results.length ? <CmsState empty="مجموعهٔ پژوهشی قابل‌دسترسی وجود ندارد؛ ورود فایل نیازمند مجوز جداگانه است." /> : <div className="cms-table-wrap" role="region" tabIndex={0} aria-label="مجموعه‌های پژوهشی؛ قابل پیمایش افقی"><table className="cms-table"><caption>{faNumber(data.count)} مجموعه</caption><thead><tr><th scope="col">نام و نسخه</th><th scope="col">رکورد / وضعیت ورود</th><th scope="col">فایل حفظ‌شده</th><th scope="col">زمان ایجاد</th></tr></thead><tbody>{data.results.map(dataset => <tr key={dataset.id}><th scope="row"><a className="cms-record-link cms-link" href={`/admin-console/research/${dataset.id}`}><strong dir="auto">{dataset.dataset_name || dataset.source_filename}</strong><bdi>{dataset.dataset_version || "نسخه ثبت نشده"}</bdi></a></th><td>{faNumber(dataset.records)} رکورد<p>{dataset.intake_complete ? "ورود کامل" : "ورود هنوز کامل نشده"}</p></td><td><bdi>{dataset.source_filename}</bdi><p className="cms-id" dir="ltr">{dataset.sha256}</p></td><td>{cmsDate(dataset.created_at)}</td></tr>)}</tbody></table></div>}
      <GovernancePagination data={data} onPage={setPage} /></>}
  </div>;
}
