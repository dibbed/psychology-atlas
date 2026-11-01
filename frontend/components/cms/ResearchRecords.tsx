"use client";

import { useEffect, useState } from "react";
import { CmsError, CmsPage } from "@/lib/cms";
import { ResearchRecord, researchActionLabels } from "@/lib/cmsJobs";
import { faNumber } from "@/lib/fa";
import { CmsState } from "./CmsShell";
import { GovernancePagination } from "./GovernanceForms";
import { ResearchBoundary, usePrivateCms } from "./CmsJobsShared";

export default function ResearchRecords({ id }: { id: string }) {
  const { can, request, current } = usePrivateCms(); const allowed = can("cms_research_view");
  const [data, setData] = useState<CmsPage<ResearchRecord>>();
  const [error, setError] = useState<unknown>(); const [page, setPage] = useState(1); const [reload, setReload] = useState(0);
  useEffect(() => {
    if (!allowed) return;
    let active = true; const abort = new AbortController(); setData(undefined); setError(undefined);
    request<CmsPage<ResearchRecord>>(`/research/datasets/${encodeURIComponent(id)}/records/?page=${page}`, { signal: AbortSignal.any([abort.signal, AbortSignal.timeout(15000)]) })
      .then(result => { if (active && current()) setData(result.data); }).catch(failure => { if (active && current()) setError(failure); });
    return () => { active = false; abort.abort(); };
  }, [allowed, id, page, reload, request, current]);
  if (!allowed) return <CmsState error={new CmsError(403, "PERMISSION_DENIED", "")} />;
  return <div className="stack" dir="rtl"><a className="cms-link" href="/admin-console/research">→ مجموعه‌های پژوهشی</a><header className="cms-title"><p className="eyebrow">پژوهش / مجموعهٔ {faNumber(id)}</p><h1>رکوردهای مجموعهٔ پژوهشی</h1><p className="muted">شمار رکوردها هنگام ورود فعال ممکن است نهایی نباشد؛ وضعیت کامل شدن در فهرست مجموعه‌ها ثبت می‌شود.</p></header><ResearchBoundary />
    <button className="button secondary" onClick={() => setReload(n => n + 1)}>بازخوانی رکوردها</button>
    {error ? <CmsState error={error} retry={() => setReload(n => n + 1)} /> : !data ? <CmsState loading /> : <>{!data.results.length ? <CmsState empty="رکوردی در این صفحه ثبت نشده است؛ در صورت ورود فعال، وضعیت کار را بررسی کنید." /> : <div className="cms-table-wrap" role="region" tabIndex={0} aria-label="رکوردهای پژوهشی؛ قابل پیمایش افقی"><table className="cms-table"><caption>{faNumber(data.count)} رکورد ثبت‌شده</caption><thead><tr><th scope="col">نام / جزئیات</th><th scope="col">بخش / شناسهٔ ورودی</th><th scope="col">آخرین تصمیم مشتق</th><th scope="col">نسخهٔ تصمیم</th></tr></thead><tbody>{data.results.map(record => <tr key={record.id}><th scope="row"><a className="cms-record-link cms-link" href={`/admin-console/research/records/${record.id}`}><strong dir="auto">{record.name_fa || record.name_en || `رکورد ${faNumber(record.id)}`}</strong><bdi dir="ltr">{record.name_en}</bdi></a></th><td><bdi>{record.section}</bdi><p className="cms-id"><bdi>{record.external_id}</bdi></p></td><td>{record.decision ? researchActionLabels[record.decision.action] : "بدون تصمیم مشتق"}<p className="muted">بدون تأیید علمی یا انتشار</p></td><td>{faNumber(record.version)}</td></tr>)}</tbody></table></div>}<GovernancePagination data={data} onPage={setPage} /></>}
  </div>;
}
