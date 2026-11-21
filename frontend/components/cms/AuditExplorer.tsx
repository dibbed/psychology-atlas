"use client";
import { useEffect, useState } from "react";
import { CmsState, useCms } from "./CmsShell";
import { cms, CmsAudit, CmsError, CmsPage, cmsDate } from "@/lib/cms";
import { faNumber } from "@/lib/fa";

export default function AuditExplorer({ id }: { id?: string }) {
  const { can } = useCms();
  const [page, setPage] = useState(1);
  const [data, setData] = useState<CmsPage<CmsAudit>>();
  const [event, setEvent] = useState<CmsAudit>();
  const [error, setError] = useState<unknown>();
  const [retry, setRetry] = useState(0);
  const allowed = can("cms_audit_view");
  useEffect(() => {
    if (!allowed) return;
    let active = true; setData(undefined); setEvent(undefined); setError(undefined);
    const load = async () => {
      if (id) { const result = await cms<CmsAudit>(`/audit/${id}/`); if (active) setEvent(result.data); }
      else { const result = await cms<CmsPage<CmsAudit>>(`/audit/?page=${page}`); if (active) setData(result.data); }
    };
    load().catch(failure => { if (active) setError(failure); });
    return () => { active = false; };
  }, [id, page, retry, allowed]);
  if (!allowed) return <CmsState error={new CmsError(403, "PERMISSION_DENIED", "")} />;
  return <div className="stack"><div className="cms-title"><p className="eyebrow">ردِ عملیات</p><h1>{id ? `رویداد ${faNumber(id)}` : "تاریخچهٔ عملیات"}</h1><p className="muted">اطلاعات ثبت‌شده فقط خواندنی‌اند؛ مقادیر متن محتوا در audit ذخیره نمی‌شوند.</p></div>
    {error ? <CmsState error={error} retry={() => setRetry(value => value + 1)} /> : event ? <section className="card stack"><a className="cms-link" href="/admin-console/audit">→ بازگشت به تاریخچه</a><dl className="cms-audit-detail">{[["عملیات", event.action], ["نتیجه", event.outcome], ["زمان", cmsDate(event.created_at)], ["نوع هدف", event.target_kind || "—"], ["شناسهٔ هدف", event.target_key || "—"], ["دلیل ثبت‌شده", event.reason || "—"], ["فیلدهای تغییرکرده", event.diff.join("، ") || "—"], ["نسخهٔ قبل / بعد", `${event.base_revision ?? "—"} / ${event.new_revision ?? "—"}`], ["شناسهٔ درخواست", event.request_id], ["ارجاع ثبت‌کننده", event.actor_ref || "—"], ["کد خطا", event.error_code || "—"]].map(([label, value]) => <div key={label}><dt>{label}</dt><dd><bdi>{value}</bdi></dd></div>)}</dl>{event.target_kind === "category" && event.target_key && can("cms_core_view") && <a className="button secondary" href={`/admin-console/content/category/${event.target_key}`}>مشاهدهٔ دسته‌بندی مرتبط</a>}</section> : !data ? <CmsState loading /> : !data.results.length ? <CmsState empty="هنوز رویدادی ثبت نشده است." /> : <><div className="cms-table-wrap" tabIndex={0} role="region" aria-label="تاریخچه؛ قابل پیمایش افقی"><table className="cms-table"><caption>{faNumber(data.count)} رویداد</caption><thead><tr><th scope="col">عملیات و جزئیات</th><th scope="col">نتیجه</th><th scope="col">هدف</th><th scope="col">زمان</th></tr></thead><tbody>{data.results.map(row => <tr key={row.id}><th scope="row"><a className="cms-record-link" href={`/admin-console/audit/${row.id}`}><bdi>{row.action}</bdi><span className="cms-link">جزئیات ←</span></a></th><td>{row.outcome === "success" ? "انجام‌شده" : row.outcome === "denied" ? "ردشده" : "ناموفق"}</td><td><bdi>{row.target_kind || "—"}</bdi></td><td><time dateTime={row.created_at}>{cmsDate(row.created_at)}</time></td></tr>)}</tbody></table></div><nav className="cms-pagination" aria-label="صفحه‌بندی تاریخچه">{page > 1 && <button className="button secondary" onClick={() => setPage(value => value - 1)}>صفحهٔ قبل</button>}<span>صفحهٔ {faNumber(page)}</span>{page * data.page_size < data.count && <button className="button secondary" onClick={() => setPage(value => value + 1)}>صفحهٔ بعد</button>}</nav></>}
  </div>;
}
