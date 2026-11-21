"use client";
import { useEffect, useState } from "react";
import { cms, CmsError } from "@/lib/cms";
import { SourcePlan } from "@/lib/cmsGovernance";
import { CmsState, useCms } from "./CmsShell";
import SourcePlanPanel from "./SourcePlanPanel";

export default function SourcePlanRecord({ id }: { id: string }) {
  const { can, setDirty } = useCms();
  const [snapshot, setSnapshot] = useState<{ data: SourcePlan; etag: string | null }>();
  const [error, setError] = useState<unknown>(); const [retry, setRetry] = useState(0); const [busy, setBusy] = useState(false);
  const allowed = can("cms_source_view");
  useEffect(() => { setDirty(busy); return () => setDirty(false); }, [busy, setDirty]);
  useEffect(() => {
    if (!allowed) return; let active = true; setError(undefined); setSnapshot(undefined);
    cms<SourcePlan>(`/sources/plans/${id}/`).then(result => { if (active) setSnapshot(result); }).catch(failure => { if (active) setError(failure); });
    return () => { active = false; };
  }, [id, allowed, retry]);
  if (!allowed) return <CmsState error={new CmsError(403, "PERMISSION_DENIED", "")} />;
  return <div className="stack" dir="rtl"><a className="cms-link" href="/admin-console/sources">→ منابع</a><h1>طرح ذخیره‌شدهٔ منبع</h1>
    {error ? <CmsState error={error} retry={() => setRetry(n => n + 1)} /> : !snapshot ? <CmsState loading /> : <><SourcePlanPanel snapshot={snapshot} current onResult={setSnapshot} onBusy={setBusy} />{snapshot.data.source_id && <a className="cms-link" href={`/admin-console/sources/${snapshot.data.source_id}`}>بازگشت به منبع و ساخت پیش‌نمایش تازه</a>}</>}
  </div>;
}
