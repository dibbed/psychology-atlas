"use client";
import { useEffect, useState } from "react";
import { cms, CmsError, CmsPage } from "@/lib/cms";
import { GovernanceKind, GovernanceRecordData, RightsPayload, TerminologyPayload, governanceComputedStatuses, governanceLabels, governanceResources } from "@/lib/cmsGovernance";
import { CmsState, useCms } from "./CmsShell";
import { faNumber } from "@/lib/fa";

export default function GovernanceQueue({ kind }: { kind: GovernanceKind }) {
  const { can } = useCms();
  const resources = Object.entries(governanceResources).filter(([, resource]) => can(`cms_${resource.domain}_view`));
  const allowed = resources.length > 0; const create = resources.some(([, resource]) => can(`cms_${resource.domain}_edit`));
  const [query, setQuery] = useState<URLSearchParams>(); const [data, setData] = useState<CmsPage<GovernanceRecordData>>(); const [error, setError] = useState<unknown>(); const [retry, setRetry] = useState(0);
  useEffect(() => { const params = new URLSearchParams(location.search); const safe = new URLSearchParams(); for (const key of ["q", "resource_type", "resource_id", "status", "computed_status", "mine", "page", "page_size"]) if (params.get(key)) safe.set(key, params.get(key)!); setQuery(safe); }, []);
  useEffect(() => { if (!query || !allowed) return; let active = true; setData(undefined); setError(undefined); cms<CmsPage<GovernanceRecordData>>(`/governance/${kind}/?${query}`).then(result => { if (active) setData(result.data); }).catch(failure => { if (active) setError(failure); }); return () => { active = false; }; }, [query, allowed, retry, kind]);
  const pageLink = (page: number) => { const params = new URLSearchParams(query); params.set("page", String(page)); return `?${params}`; };
  const title = kind === "rights" ? "حقوق محتوا" : "اصطلاحات فارسی";
  if (!allowed) return <CmsState error={new CmsError(403, "PERMISSION_DENIED", "")} />;
  return <div className="stack" dir="rtl"><header className="cms-section-head cms-title"><div><p className="eyebrow">حاکمیت محتوا / صف بررسی</p><h1>{title}</h1><p className="muted">{kind === "rights" ? "اجازهٔ استفاده برای هدف، نسخه، ماده و کاربرد مشخص؛ وضعیت حقوق از وضعیت گردش بررسی جداست." : "پیشنهاد display و alias با منبع، دلیل و تصمیم نسخهٔ مشخص؛ مستقل از بررسی علمی و حقوق."}</p></div>{create && <a className="button primary" href={`/admin-console/${kind}/new`}>پیشنهاد تازه</a>}</header>
    {kind === "rights" && <div className="cms-actions"><a className="button secondary" href="?computed_status=review_overdue">صف موعد بازبینی گذشته</a><a className="button secondary" href="?computed_status=expired">حقوق منقضی</a></div>}
    {query && <form className="cms-filters card" method="get"><label>جست‌وجو<input name="q" type="search" dir="auto" maxLength={200} defaultValue={query.get("q") || ""} /></label>
      <label>نوع هدف<select name="resource_type" defaultValue={query.get("resource_type") || ""}><option value="">همهٔ هدف‌های مجاز</option>{resources.map(([key, resource]) => <option value={key} key={key}>{resource.label}</option>)}</select></label>
      <label>شناسهٔ هدف<input type="number" name="resource_id" dir="ltr" min={1} defaultValue={query.get("resource_id") || ""} /></label>
      <label>وضعیت گردش بررسی<select name="status" defaultValue={query.get("status") || ""}><option value="">همه</option>{["submitted", "in_review", "approved", "rejected", ...(kind === "rights" ? ["revoked"] : [])].map(status => <option key={status} value={status}>{governanceLabels[status]}</option>)}</select></label>
      <label>وضعیت محاسبه‌شدهٔ سرور<select name="computed_status" defaultValue={query.get("computed_status") || ""}><option value="">همه</option>{(kind === "rights" ? governanceComputedStatuses : ["stale", "submitted", "in_review", "approved", "rejected"]).map(status => <option key={status} value={status}>{governanceLabels[status]}</option>)}</select></label>
      <label>تخصیص به من<select name="mine" defaultValue={query.get("mine") || ""}><option value="">همهٔ موارد مجاز</option><option value="1">وظیفه‌های من</option></select></label><button className="button secondary">اعمال فیلتر</button><a className="cms-link" href={`/admin-console/${kind}`}>پاک کردن</a>
    </form>}
    {error ? <CmsState error={error} retry={() => setRetry(n => n + 1)} /> : !data ? <CmsState loading /> : !data.results.length ? <CmsState empty="مورد مجازی با این فیلترها یافت نشد." /> : <div className="cms-table-wrap" role="region" tabIndex={0} aria-label={`${title}؛ قابل پیمایش افقی`}><table className="cms-table"><caption>{faNumber(data.count)} پیشنهاد در محدودهٔ دسترسی شما</caption><thead><tr><th scope="col">هدف و نسخهٔ دقیق</th><th scope="col">پیشنهاد</th><th scope="col">گردش بررسی</th><th scope="col">وضعیت فعلی سرور</th><th scope="col">موانع</th></tr></thead><tbody>{data.results.map(record => <tr key={record.id}>
      <th scope="row"><a className="cms-record-link" href={`/admin-console/${kind}/${record.id}?list=${encodeURIComponent(query?.toString() || "")}`}><strong>{governanceResources[record.resource_type]?.label || record.resource_type} {faNumber(record.resource_id)}</strong><span className="cms-id"><bdi>{record.resource_version}</bdi></span><span className="cms-link">جزئیات و بررسی ←</span></a></th>
      <td>{kind === "rights" ? <><p>{governanceLabels[(record.payload as RightsPayload).material]} / {governanceLabels[(record.payload as RightsPayload).intended_use]}</p><p>پیشنهاد: {governanceLabels[(record.payload as RightsPayload).status]}</p><p>انقضا: <bdi>{(record.payload as RightsPayload).expires_on || "ثبت نشده"}</bdi></p><p>بازبینی: <bdi>{(record.payload as RightsPayload).review_on || "ثبت نشده"}</bdi></p></> : <><p dir="rtl">{(record.payload as TerminologyPayload).name_fa}</p><p dir="ltr">{(record.payload as TerminologyPayload).name_en}</p><p>{governanceLabels[(record.payload as TerminologyPayload).term_kind]}</p></>}</td>
      <td>{governanceLabels[record.status] || record.status}<p>نسخهٔ {faNumber(record.version)}</p></td><td>{governanceLabels[record.computed_status] || record.computed_status}<p>{record.eligible ? "واجد شرایط همین دامنه در سرور" : "واجد شرایط نیست"}</p></td><td>{record.blockers.length ? record.blockers.map((blocker, index) => <p key={index}><bdi>{governanceLabels[blocker] || blocker}</bdi></p>) : "بدون مانع ثبت‌شده"}</td>
    </tr>)}</tbody></table></div>}
    {data && <nav className="cms-pagination" aria-label={`صفحه‌بندی ${title}`}>{data.page > 1 && <a className="button secondary" href={pageLink(data.page - 1)}>صفحهٔ قبلی</a>}<span>صفحهٔ {faNumber(data.page)} · {faNumber(data.count)} نتیجه</span>{data.page * data.page_size < data.count && <a className="button secondary" href={pageLink(data.page + 1)}>صفحهٔ بعدی</a>}</nav>}
  </div>;
}
