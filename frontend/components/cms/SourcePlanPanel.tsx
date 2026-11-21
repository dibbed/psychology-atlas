"use client";

import { useRef, useState } from "react";
import { cms } from "@/lib/cms";
import { SourcePlan, governanceBlocked, sourceOperationLabels } from "@/lib/cmsGovernance";
import { faNumber } from "@/lib/fa";
import { GovernanceError } from "./GovernanceForms";
import { useCms } from "./CmsShell";
import { sourceValue } from "./SourceComparison";

export function sourceAuthority(operation: SourcePlan["operation"], can: (capability: string) => boolean) {
  return can("cms_source_view") && can("cms_source_preview") && can("cms_source_validate") &&
    (operation === "delete" ? can("cms_source_delete_preview") && can("cms_source_delete_unused") : can(`cms_source_${operation === "create" ? "create" : operation === "archive" ? "archive" : "edit"}`));
}

export default function SourcePlanPanel({ snapshot, current, onResult, onBusy, repreview }: {
  snapshot: { data: SourcePlan; etag: string | null }; current: boolean;
  onResult: (snapshot: { data: SourcePlan; etag: string | null }) => void; onBusy: (busy: boolean) => void; repreview?: () => void;
}) {
  const { me, can } = useCms();
  const [busy, setBusy] = useState(false); const lock = useRef(false);
  const [error, setError] = useState<unknown>(); const [ack, setAck] = useState(false);
  const [resolved, setResolved] = useState(false);
  const plan = snapshot.data;
  const blocked = governanceBlocked(error);
  async function action(apply: boolean) {
    if (lock.current || (apply && (!current || !plan.preview.can_apply || !snapshot.etag || !ack || blocked || !sourceAuthority(plan.operation, can) || plan.status !== "preview"))) return;
    lock.current = true; setBusy(true); onBusy(true);
    try {
      const result = await cms<SourcePlan>(`/sources/plans/${plan.id}/${apply ? "apply/" : ""}`, apply ? { method: "POST", headers: { "If-Match": snapshot.etag! }, body: "{}" } : {}, apply ? me.user.id : undefined);
      onResult(result); setAck(false); setResolved(!apply);
      if (!apply && result.data.status === "applied") setError(undefined);
    } catch (failure) { setError(failure); setResolved(false); }
    finally { lock.current = false; setBusy(false); onBusy(false); }
  }
  return <section className="card stack" aria-label="پیش‌نمایش نسخه‌دار و اعتبارسنجی منبع">
    <h2>{sourceOperationLabels[plan.operation]}؛ طرح نسخهٔ {faNumber(plan.version)}</h2><p className="cms-id">شناسهٔ طرح: <bdi>{plan.id}</bdi> · اثرانگشت: <bdi>{plan.fingerprint}</bdi></p>
    <a className="cms-link" href={`/admin-console/sources/plans/${plan.id}`}>بازکردن همین طرح ذخیره‌شده</a>
    <p>انتقال: {faNumber(plan.preview.counts.moved)} · بدون تغییر: {faNumber(plan.preview.counts.unchanged)} · مسدود: {faNumber(plan.preview.counts.blocked)}</p>
    {!current && <p className="cms-notice">ورودی فرم پس از این پیش‌نمایش تغییر کرده است؛ پیش‌نمایش تازه لازم است.</p>}
    {plan.preview.blockers.length > 0 && <div className="cms-error"><h3>موانع سرور</h3><ul>{plan.preview.blockers.map((item, index) => <li key={index}><bdi>{item.code} · {item.key}</bdi><p dir="auto">{item.message}</p></li>)}</ul></div>}
    {([["normalization", "هویت و فراداده پس از نرمال‌سازی"], ["comparisons", "مقایسهٔ هویت و فیلدها"], ["identity_conflicts", "تعارض‌های هویتی"], ["mapping", "نگاشت اعتبارسنجی‌شده"], ["manual_plan", "مراجع تاریخی؛ رسیدگی دستی"], ["rereview", "بازبینی دوبارهٔ لازم"]] as const).map(([key, title]) => <details className="cms-history-entry" key={key}><summary>{title}</summary><pre className="cms-prose" dir="auto">{sourceValue(plan.preview[key])}</pre></details>)}
    <GovernanceError error={error} prefix="source"><button type="button" className="button secondary" disabled={busy} onClick={() => action(false)}>بررسی وضعیت همین طرح در سرور</button>{repreview && resolved && plan.status !== "applied" && <button type="button" className="button secondary" disabled={busy} onClick={repreview}>پیش‌نمایش تازه با دادهٔ فعلی</button>}</GovernanceError>
    {plan.status === "applied" ? <div className="cms-success stack" role="status"><h3>طرح در سرور اعمال شده است</h3><p>منابع: {plan.receipt?.source_ids.map(id => faNumber(id)).join("، ")}</p><p>انتقال: {faNumber(plan.receipt?.counts.moved || 0)} · بدون تغییر: {faNumber(plan.receipt?.counts.unchanged || 0)} · مسدود: {faNumber(plan.receipt?.counts.blocked || 0)}</p>{plan.receipt?.source_ids.map(id => <a className="cms-link" href={`/admin-console/sources/${id}`} key={id}>جزئیات منبع {faNumber(id)}</a>)}</div> : <>
      <label className="cms-review-check"><input type="checkbox" checked={ack} disabled={busy || !current || blocked} onChange={event => setAck(event.target.checked)} />اثر و نگاشت همین طرح را بررسی کرده‌ام و اعمال آن را می‌پذیرم.</label>
      <button type="button" className="button primary" disabled={busy || !ack || !current || !plan.preview.can_apply || !snapshot.etag || blocked || !sourceAuthority(plan.operation, can)} onClick={() => action(true)}>اعمال طرح اعتبارسنجی‌شده</button>
    </>}
  </section>;
}
