"use client";
import { useEffect, useState } from "react";
import { cms, CmsError, CmsPage } from "@/lib/cms";
import { SourcePayload } from "@/lib/cmsGovernance";
import { CmsState, useCms } from "./CmsShell";
import { GovernancePagination } from "./GovernanceForms";
import { faNumber } from "@/lib/fa";

type Bibliography = Omit<SourcePayload, "verification_status"> & { id: number };
export default function SourceExport() {
  const { can } = useCms(); const allowed = can("cms_source_view") && can("cms_source_export");
  const [query, setQuery] = useState<URLSearchParams>(); const [data, setData] = useState<CmsPage<Bibliography>>(); const [error, setError] = useState<unknown>(); const [retry, setRetry] = useState(0);
  useEffect(() => { const safe = new URLSearchParams(); const incoming = new URLSearchParams(location.search); for (const key of ["q", "doi", "pmid", "archived", "page", "page_size"]) if (incoming.has(key)) safe.set(key, incoming.get(key)!); setQuery(safe); }, []);
  useEffect(() => { if (!allowed || !query) return; let active = true; setData(undefined); setError(undefined); cms<CmsPage<Bibliography>>(`/sources/export/?${query}`).then(result => { if (active) setData(result.data); }).catch(failure => { if (active) setError(failure); }); return () => { active = false; }; }, [query, allowed, retry]);
  function download() { if (!data) return; const url = URL.createObjectURL(new Blob([JSON.stringify(data, null, 2)], { type: "application/json" })); const anchor = document.createElement("a"); anchor.href = url; anchor.download = `bibliography-page-${data.page}.json`; anchor.click(); URL.revokeObjectURL(url); }
  if (!allowed) return <CmsState error={new CmsError(403, "PERMISSION_DENIED", "")} />;
  return <div className="stack" dir="rtl"><a className="cms-link" href="/admin-console/sources">→ منابع</a><h1>خروجی کتاب‌شناسی</h1><p className="muted">فقط فیلدهای مجاز کتاب‌شناسی؛ خروجی هر صفحه جداست.</p>
    {error ? <CmsState error={error} retry={() => setRetry(n => n + 1)} /> : !data ? <CmsState loading /> : <section className="card stack"><p>کل نتیجه: {faNumber(data.count)} · این فایل: {faNumber(data.results.length)} رکورد · صفحهٔ {faNumber(data.page)}</p><button type="button" className="button primary" onClick={download}>دریافت JSON همین صفحه</button><GovernancePagination data={data} onPage={page => { const params = new URLSearchParams(query); params.set("page", String(page)); setQuery(params); }} /></section>}
  </div>;
}
