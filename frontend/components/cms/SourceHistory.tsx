"use client";
import { useEffect, useState } from "react";
import { cms, CmsError, CmsPage, cmsDate } from "@/lib/cms";
import { SourceHistoryEntry, sourceOperationLabels } from "@/lib/cmsGovernance";
import { CmsState, useCms } from "./CmsShell";
import { GovernancePagination } from "./GovernanceForms";
import { sourceValue } from "./SourceComparison";
import { faNumber } from "@/lib/fa";

export default function SourceHistory({ id }: { id: string }) {
  const { can } = useCms(); const allowed = can("cms_source_view");
  const [data, setData] = useState<CmsPage<SourceHistoryEntry>>(); const [error, setError] = useState<unknown>(); const [page, setPage] = useState(1); const [retry, setRetry] = useState(0);
  useEffect(() => { if (!allowed) return; let active = true; setData(undefined); setError(undefined); cms<CmsPage<SourceHistoryEntry>>(`/sources/${id}/history/?page=${page}`).then(result => { if (active) setData(result.data); }).catch(failure => { if (active) setError(failure); }); return () => { active = false; }; }, [id, page, retry, allowed]);
  if (!allowed) return <CmsState error={new CmsError(403, "PERMISSION_DENIED", "")} />;
  return <div className="stack" dir="rtl"><a className="cms-link" href="/admin-console/sources">→ منابع</a><h1>تاریخچهٔ حفظ‌شدهٔ منبع {faNumber(id)}</h1><p className="muted">تاریخچه پس از حذف منبع بدون مصرف هم باقی می‌ماند.</p>
    {error ? <CmsState error={error} retry={() => setRetry(n => n + 1)} /> : !data ? <CmsState loading /> : <>{!data.results.length && <CmsState empty="تاریخچه‌ای ثبت نشده است." />}{data.results.map(item => <details key={item.id} className="cms-history-entry"><summary>{sourceOperationLabels[item.operation]} · نسخهٔ {faNumber(item.version)} · {cmsDate(item.created_at)}</summary><p><bdi>{item.actor_ref}</bdi></p><a className="cms-link" href={`/admin-console/sources/plans/${item.plan_id}`}>طرح عملیات</a><div className="cms-compare"><pre className="cms-prose" dir="auto">پیش از تغییر: {sourceValue(item.before)}</pre><pre className="cms-prose" dir="auto">پس از تغییر: {sourceValue(item.after)}</pre></div></details>)}<GovernancePagination data={data} onPage={setPage} /></>}
  </div>;
}
