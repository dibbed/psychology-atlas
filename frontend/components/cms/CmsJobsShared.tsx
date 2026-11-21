"use client";

import { useCallback, useEffect, useMemo } from "react";
import { CmsError } from "@/lib/cms";
import { AdminJob, cmsJobs, mutationBlocked } from "@/lib/cmsJobs";
import { faNumber } from "@/lib/fa";
import { useCms } from "./CmsShell";
import { GovernanceError } from "./GovernanceForms";

export function usePrivateCms() {
  const context = useCms();
  const { me } = context;
  const scope = useMemo(() => ({ active: true, abort: new AbortController() }), [me.session.id, me.user.id]);
  useEffect(() => {
    // Strict Mode remounts effects; each lifetime owns its own controller.
    scope.active = true; scope.abort = new AbortController();
    const end = () => { scope.active = false; scope.abort.abort(); };
    window.addEventListener("cms-session-expired", end);
    const channel = typeof BroadcastChannel === "undefined" ? null : new BroadcastChannel("atlas-cms-session");
    if (channel) channel.onmessage = end;
    return () => { end(); window.removeEventListener("cms-session-expired", end); channel?.close(); };
  }, [scope]);
  const current = useCallback(() => scope.active, [scope]);
  const request = useCallback(<T,>(path: string, options: RequestInit = {}) => {
    if (!scope.active) return Promise.reject(new CmsError(403, "UNAUTHENTICATED", "نشست پایان یافته است."));
    return cmsJobs<T>(path, { ...options, signal: AbortSignal.any([scope.abort.signal, options.signal ?? AbortSignal.timeout(15000)]) }, me);
  }, [me, scope]);
  return { ...context, request, current };
}

export function ResearchBoundary() {
  return <p className="cms-notice">ورود فایل، نشانی منبع و اعتبارسنجی قالب، شاهد علمی یا مجوز حقوقی نیستند. نگاشت و آماده‌سازی فقط تصمیم مشتق ثبت می‌کنند؛ دادهٔ خام حفظ می‌شود و چیزی در محتوای مرجع منتشر نمی‌شود.</p>;
}

export function JobProgress({ job }: { job: AdminJob }) {
  return <div className="stack" aria-live="polite"><p>پردازش‌شده: {faNumber(job.progress_done)} از {job.progress_total == null ? "تعداد کل نامعلوم" : faNumber(job.progress_total)}</p>
    <p className="muted">تلاش انجام‌شده: {faNumber(job.attempt)} از حداکثر {faNumber(3)}</p></div>;
}

export function PrivateMutationError({ error, reload, busy, prefix = "research" }: {
  error: unknown; reload: () => void; busy: boolean; prefix?: string;
}) {
  return <GovernanceError error={error} prefix={prefix}>
    {mutationBlocked(error) && <><p>اقدام دوباره قفل است. نسخهٔ جاری و تاریخچه را بررسی کنید و سپس یک اقدام تازه انتخاب کنید.</p>
      <button type="button" className="button secondary" disabled={busy} onClick={reload}>بازخوانی صریح وضعیت سرور</button>
      <a className="cms-link" href="/admin-console/jobs">بررسی کارهای ثبت‌شده</a>
      <a className="cms-link" href="/admin-console/audit">بررسی تاریخچهٔ عملیات</a></>}
  </GovernanceError>;
}
