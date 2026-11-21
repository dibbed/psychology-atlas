"use client";
import { useEffect, useState } from "react";
import { Plus, Search } from "lucide-react";
import { CmsState, useCms } from "./CmsShell";
import { cms, CmsError, CmsPage, CmsRecord, publicationLabels, revisionLabels } from "@/lib/cms";
import { faNumber } from "@/lib/fa";
import { normalizePersianSearch } from "@/lib/text";

export default function CategoryList() {
  const { can } = useCms();
  const [query, setQuery] = useState<URLSearchParams>();
  const [data, setData] = useState<CmsPage<CmsRecord>>();
  const [error, setError] = useState<unknown>();
  const [retry, setRetry] = useState(0);
  const allowed = can("cms_core_view");
  useEffect(() => { setQuery(new URLSearchParams(location.search)); }, []);
  useEffect(() => {
    if (!query || !allowed) return;
    let active = true; setError(undefined); setData(undefined);
    const params = new URLSearchParams(query);
    if (params.has("q")) params.set("q", normalizePersianSearch(params.get("q") || ""));
    cms<CmsPage<CmsRecord>>(`/content/category/?${params}`).then(result => { if (active) setData(result.data); }).catch(failure => { if (active) setError(failure); });
    return () => { active = false; };
  }, [query, retry, allowed]);
  const pagination = (page: number) => { const params = new URLSearchParams(query); params.set("page", String(page)); return `?${params}`; };
  if (!allowed) return <CmsState error={new CmsError(403, "PERMISSION_DENIED", "")} />;
  return <div className="stack">
    <div className="cms-section-head cms-title"><div><p className="eyebrow">محتوای مرجع / دسته‌بندی‌ها</p><h1>دسته‌بندی‌ها</h1><p className="muted">پیشنهادها و محتوای میراث؛ ذخیره به معنی انتشار نیست.</p></div>{can("cms_core_create") && <a className="button primary" href="/admin-console/content/category/new"><Plus size={17} aria-hidden="true" />پیش‌نویس جدید</a>}</div>
    {query && <form className="cms-filters card" method="get">
      <label>جست‌وجوی نام<span className="cms-search-input"><Search size={16} aria-hidden="true" /><input type="search" name="q" defaultValue={query.get("q") || ""} maxLength={200} /></span></label>
      <label>وضعیت نسخه<select name="status" defaultValue={query.get("status") || ""}><option value="">همهٔ وضعیت‌ها</option>{["legacy", "draft", "discarded"].map(status => <option key={status} value={status}>{revisionLabels[status]}</option>)}</select></label>
      <label>ترتیب<select name="sort" defaultValue={query.get("sort") || "newest"}><option value="newest">جدیدترین anchor</option><option value="oldest">قدیمی‌ترین anchor</option></select></label>
      <button className="button secondary">اعمال فیلتر</button><a className="cms-link" href="/admin-console/content/category">پاک کردن</a>
    </form>}
    {error ? <CmsState error={error} retry={() => setRetry(value => value + 1)} /> : !data ? <CmsState loading /> : !data.results.length ? <CmsState empty={data.count ? "در این صفحه نتیجه‌ای نیست؛ به صفحهٔ قبل برگردید." : "هیچ دسته‌بندی با این فیلتر یافت نشد. فیلتر را پاک کنید یا پیش‌نویس بسازید."} /> : <div className="cms-table-wrap" tabIndex={0} role="region" aria-label="فهرست دسته‌بندی‌ها؛ قابل پیمایش افقی">
      <table className="cms-table"><caption>نتایج دسته‌بندی‌ها؛ {faNumber(data.count)} رکورد</caption><thead><tr><th scope="col">نام و جزئیات</th><th scope="col">نسخه</th><th scope="col">وضعیت پیشنهاد</th><th scope="col">محتوای اصلی</th></tr></thead>
        <tbody>{data.results.map(row => <tr key={row.id}><th scope="row"><a className="cms-record-link" href={`/admin-console/content/category/${row.id}?list=${encodeURIComponent(query?.toString() || "")}`}><strong>{row.payload.name_fa || row.payload.name_en}</strong><bdi className="muted">{row.payload.name_en}</bdi><span className="cms-link">جزئیات ←</span></a></th><td>{faNumber(row.version)}</td><td><span className="cms-badge">{revisionLabels[row.revision_status] || row.revision_status}</span></td><td>{publicationLabels[row.publication] || row.publication}</td></tr>)}</tbody>
      </table></div>}
    {data && <nav className="cms-pagination" aria-label="صفحه‌بندی دسته‌بندی‌ها">{data.page > 1 && <a className="button secondary" href={pagination(data.page - 1)}>صفحهٔ قبل</a>}<span>صفحهٔ {faNumber(data.page)} · {faNumber(data.count)} نتیجه</span>{data.page * data.page_size < data.count && <a className="button secondary" href={pagination(data.page + 1)}>صفحهٔ بعد</a>}</nav>}
  </div>;
}
