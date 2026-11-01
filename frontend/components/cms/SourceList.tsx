"use client";

import { useEffect, useState } from "react";
import { cms, CmsError, CmsPage } from "@/lib/cms";
import { SourceSummary } from "@/lib/cmsGovernance";
import { faNumber } from "@/lib/fa";
import { normalizePersianSearch } from "@/lib/text";
import { CmsState, useCms } from "./CmsShell";

export default function SourceList() {
  const { can } = useCms();
  const [query, setQuery] = useState<URLSearchParams>();
  const [data, setData] = useState<CmsPage<SourceSummary>>();
  const [error, setError] = useState<unknown>();
  const [retry, setRetry] = useState(0);
  const [searchMode, setSearchMode] = useState("q");
  const allowed = can("cms_source_view");
  useEffect(() => { const safe = new URLSearchParams(); const incoming = new URLSearchParams(location.search); for (const key of ["q", "doi", "pmid", "page", "page_size", "archived"]) if (incoming.has(key)) safe.set(key, incoming.get(key)!); setQuery(safe); setSearchMode(safe.get("doi") ? "doi" : safe.get("pmid") ? "pmid" : "q"); }, []);
  useEffect(() => {
    if (!allowed || !query) return;
    let active = true; setData(undefined); setError(undefined);
    const params = new URLSearchParams(query);
    if (params.has("q")) params.set("q", normalizePersianSearch(params.get("q") || ""));
    cms<CmsPage<SourceSummary>>(`/sources/?${params}`).then(result => { if (active) setData(result.data); }).catch(failure => { if (active) setError(failure); });
    return () => { active = false; };
  }, [query, allowed, retry]);
  function pagination(page: number) { const params = new URLSearchParams(query); params.set("page", String(page)); return `?${params}`; }
  if (!allowed) return <CmsState error={new CmsError(403, "PERMISSION_DENIED", "")} />;
  return <div className="stack" dir="rtl">
    <header className="cms-title cms-section-head"><div><p className="eyebrow">کتاب‌شناسی / مدیریت منابع</p><h1>منابع و وابستگی‌ها</h1><p className="muted">عنوان اصلی و هویت منبع، مصرف‌کنندگان و حفاظت‌های ثبت‌شده در سرور.</p></div>
      <div className="cms-actions">{can("cms_source_create") && <a className="button primary" href="/admin-console/sources/new">ثبت منبع</a>}{can("cms_source_export") && <a className="button secondary" href={`/admin-console/sources/export?${query || ""}`}>خروجی کتاب‌شناسی</a>}</div>
    </header>
    {query && <form className="cms-filters card" method="get">
      <label>روش جست‌وجو<select value={searchMode} onChange={event => setSearchMode(event.target.value)}><option value="q">عنوان</option><option value="doi">DOI دقیق</option><option value="pmid">PMID دقیق</option></select></label>
      <label>{searchMode === "q" ? "جست‌وجوی عنوان" : `${searchMode.toUpperCase()} دقیق`}<input key={searchMode} name={searchMode} type="search" dir={searchMode === "q" ? "auto" : "ltr"} maxLength={searchMode === "doi" ? 255 : searchMode === "pmid" ? 64 : 200} defaultValue={query.get(searchMode) || ""} /></label>
      <label>بایگانی<select name="archived" defaultValue={query.get("archived") || "0"}><option value="0">فعال</option><option value="1">بایگانی‌شده</option></select></label>
      <button className="button secondary">جست‌وجو</button><a className="cms-link" href="/admin-console/sources">پاک کردن فیلتر</a>
    </form>}
    {error ? <CmsState error={error} retry={() => setRetry(n => n + 1)} /> : !data ? <CmsState loading /> : !data.results.length ? <CmsState empty="منبعی با این فیلترها یافت نشد؛ جست‌وجو را تغییر دهید." /> :
      <div className="cms-table-wrap" role="region" tabIndex={0} aria-label="فهرست منابع؛ قابل پیمایش افقی"><table className="cms-table"><caption>{faNumber(data.count)} منبع</caption>
        <thead><tr><th scope="col">عنوان و جزئیات</th><th scope="col">نویسنده / سازمان / سال</th><th scope="col">هویت دقیق</th><th scope="col">راستی‌آزمایی</th><th scope="col">مصرف‌کنندگان</th></tr></thead>
        <tbody>{data.results.map(source => <tr key={source.id}><th scope="row"><a className="cms-record-link" href={`/admin-console/sources/${source.id}?list=${encodeURIComponent(query?.toString() || "")}`}><strong dir="auto">{source.title}</strong><span className="cms-link">جزئیات و اثر تغییر ←</span></a>{source.archived && <span className="cms-badge">بایگانی‌شده</span>}</th>
          <td><p dir="auto">{source.authors.join("، ") || source.organization || "ثبت نشده"}</p><p>{source.publication_year == null ? "سال ثبت نشده" : faNumber(source.publication_year)}</p></td>
          <td><p dir="ltr">DOI: {source.doi || "—"}</p><p dir="ltr">PMID: {source.pmid || "—"}</p></td><td><bdi>{source.verification_status || "نامشخص"}</bdi></td><td>{source.usage_count === null ? "نمایش در جزئیات" : faNumber(source.usage_count)}</td>
        </tr>)}</tbody>
      </table></div>}
    {data && <nav className="cms-pagination" aria-label="صفحه‌بندی منابع">{data.page > 1 && <a className="button secondary" href={pagination(data.page - 1)}>صفحهٔ قبلی</a>}<span>صفحهٔ {faNumber(data.page)} · {faNumber(data.count)} منبع</span>{data.page * data.page_size < data.count && <a className="button secondary" href={pagination(data.page + 1)}>صفحهٔ بعدی</a>}</nav>}
  </div>;
}
