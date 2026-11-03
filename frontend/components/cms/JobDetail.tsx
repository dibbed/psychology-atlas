"use client";

import { useEffect, useRef, useState } from "react";
import { CmsError, cmsDate } from "@/lib/cms";
import { AdminJob, Snapshot, jobActive, jobKindLabels, jobStatusLabels, learningKindLabels, learningEditorPaths, mutationBlocked, p06ErrorMessages, versionHeaders } from "@/lib/cmsJobs";
import { faNumber } from "@/lib/fa";
import { CmsState } from "./CmsShell";
import { JobProgress, PrivateMutationError, usePrivateCms } from "./CmsJobsShared";
import ArtifactCard from "./ArtifactCard";

export default function JobDetail({ id }: { id: string }) {
  const { can, request, current, setDirty } = usePrivateCms();
  const allowed = can("cms_enter");
  const [snapshot, setSnapshot] = useState<Snapshot<{ job: AdminJob }>>();
  const [error, setError] = useState<unknown>(); const [writeError, setWriteError] = useState<unknown>();
  const [reload, setReload] = useState(0); const [busy, setBusy] = useState(false);
  const [cardBusy, setCardBusy] = useState(false);
  const [outputBusy, setOutputBusy] = useState(false);
  const [confirmation, setConfirmation] = useState<"retry" | "cancel">();
  const [pollStopped, setPollStopped] = useState(false); const lock = useRef(false);
  const blocked = mutationBlocked(writeError); const job = snapshot?.data.job;
  useEffect(() => { setDirty(busy || cardBusy || outputBusy); return () => setDirty(false); }, [busy, cardBusy, outputBusy, setDirty]);
  useEffect(() => {
    if (!allowed || blocked) return;
    let active = true, pending = false, failures = 0, stopped = false;
    let timer: ReturnType<typeof setTimeout> | undefined;
    const abort = new AbortController();
    setSnapshot(undefined); setError(undefined); setPollStopped(false);
    async function read() {
      if (!active || !current() || pending || stopped || lock.current || document.visibilityState !== "visible") return;
      pending = true;
      try {
        const result = await request<{ job: AdminJob }>(`/jobs/${encodeURIComponent(id)}/`, { signal: AbortSignal.any([abort.signal, AbortSignal.timeout(15000)]) });
        if (!active || !current() || lock.current) return;
        setSnapshot(result); setError(undefined); failures = 0;
        if (jobActive(result.data.job) && !lock.current && !blocked) timer = setTimeout(read, 4000);
      } catch (failure) {
        if (!active || !current()) return;
        setError(failure); failures += 1;
        const transient = failure instanceof CmsError && (failure.status === 0 || failure.status >= 500);
        if (transient && failures <= 3 && !blocked) timer = setTimeout(read, 2000 * failures);
        else { stopped = true; setPollStopped(true); }
      } finally { pending = false; }
    }
    const visibility = () => { if (timer) clearTimeout(timer); if (document.visibilityState === "visible") void read(); };
    document.addEventListener("visibilitychange", visibility); void read();
    return () => { active = false; abort.abort(); if (timer) clearTimeout(timer); document.removeEventListener("visibilitychange", visibility); };
  }, [allowed, id, request, current, reload, blocked]);
  async function action() {
    if (!snapshot || !confirmation || lock.current || blocked || !allowed) return;
    const chosen = confirmation; lock.current = true; setBusy(true); setWriteError(undefined); setConfirmation(undefined);
    try {
      const result = await request<{ job: AdminJob }>(`/jobs/${encodeURIComponent(id)}/${chosen}/`, { method: "POST", headers: versionHeaders(snapshot.etag), body: "{}" });
      if (current()) { setSnapshot(result); setReload(n => n + 1); }
    } catch (failure) { if (current()) setWriteError(failure); }
    finally { lock.current = false; if (current()) setBusy(false); }
  }
  if (!allowed) return <CmsState error={new CmsError(403, "PERMISSION_DENIED", "")} />;
  return <div className="stack" dir="rtl"><a className="cms-link" href="/admin-console/jobs">→ همهٔ کارها</a><header className="cms-title"><p className="eyebrow">پردازش خصوصی</p><h1>جزئیات کار{job && ` ${jobKindLabels[job.kind] || job.kind}`}</h1><p className="cms-id"><bdi>{id}</bdi></p></header>
    <p className="muted">وضعیت کار فعال فقط وقتی این صفحه دیده می‌شود بازخوانی می‌شود. پس از سه تلاش دوبارهٔ ناموفق، بازخوانی خودکار متوقف می‌شود.</p>
    <PrivateMutationError error={writeError} busy={busy} reload={() => { setWriteError(undefined); setConfirmation(undefined); setReload(n => n + 1); }} />
    {error != null && <CmsState error={error} retry={() => setReload(n => n + 1)} />}
    {pollStopped && <p className="cms-notice">بازخوانی خودکار متوقف است؛ اطلاعات زیر ممکن است قدیمی باشد.</p>}
    {!snapshot && !error ? <CmsState loading /> : job && <>
      <section className="card stack"><h2>{jobStatusLabels[job.status] || job.status}</h2><JobProgress job={job} /><p>نسخهٔ سرور: {faNumber(job.version)} · آخرین تغییر: {cmsDate(job.updated_at)}</p>
        {job.cancel_requested && <p className="cms-notice">لغو درخواست شده است؛ نتیجه تا رسیدن به نقطهٔ امن پردازش قطعی نیست.</p>}
        {job.error_code && <p>کد خطا: <bdi>{job.error_code}</bdi></p>}
        {job.error_code === "CLEANUP_PLATFORM_UNAVAILABLE" && <p className="cms-notice">{p06ErrorMessages.CLEANUP_PLATFORM_UNAVAILABLE}</p>}
        {job.result.dataset_id != null && <a className="cms-link" href={`/admin-console/research/${job.result.dataset_id}`}>مشاهدهٔ رکوردهای مجموعهٔ واردشده</a>}
        {job.result.records != null && <p>تعداد رکورد گزارش‌شده: {faNumber(job.result.records)}</p>}
        {job.result.items != null && <p>تعداد آیتم‌های آموزشی پردازش‌شده: {faNumber(job.result.items)}</p>}
        {job.result.created&&<ul>{job.result.created.map(row=><li key={row.kind+"-"+row.resource_id}>
          {learningKindLabels[row.kind]} · شناسهٔ محتوای تازه: <bdi>{faNumber(row.resource_id)}</bdi>{" "}
          <a className="cms-link" href={"/admin-console/content/"+learningEditorPaths[row.kind]}>فهرست خصوصی</a>
        </li>)}</ul>}
        {job.result.duplicate === true && <p className="cms-notice">این فایل قبلاً وارد شده است؛ سرور مجموعهٔ موجود را برگردانده است.</p>}
        {job.kind === "artifact_cleanup" && job.result.cleaned === true && <p className="cms-notice">سرور حذف بایت‌های فایل را تأیید کرده است؛ فراداده و تاریخچه حفظ شده‌اند.</p>}
        {job.kind === "artifact_cleanup" && job.result.cleaned === false && <p className="cms-notice">سرور حذف بایت‌های فایل را تأیید نکرده است؛ وضعیت و خطای کار را بررسی کنید.</p>}
        <div className="cms-actions"><button className="button secondary" disabled={busy || blocked} onClick={() => { setConfirmation(undefined); setReload(n => n + 1); }}>بازخوانی وضعیت</button>
          {job.retry_available && <button className="button secondary" disabled={busy || blocked || !snapshot?.etag || job.attempt >= 3} onClick={() => setConfirmation("retry")}>بررسی تلاش دوباره</button>}
          {jobActive(job) && !job.cancel_requested && <button className="button secondary" disabled={busy || blocked || !snapshot?.etag} onClick={() => setConfirmation("cancel")}>بررسی لغو کار</button>}</div>
        <p className="muted">نمایش دکمه مجوز ایجاد نمی‌کند. اقدام فقط برای عامل کار یا مالک واجد مجوز اصلی و با بررسی دوبارهٔ سرور انجام می‌شود.</p>
        {confirmation && <section className="cms-conflict stack" aria-labelledby="job-confirm"><h3 id="job-confirm">{confirmation === "retry" ? "تأیید تلاش تازه برای همین کار" : "تأیید درخواست لغو"}</h3><p>{confirmation === "retry" ? "فقط خطای قابل بازیابی و کمتر از سه تلاش قابل ادامه است؛ دادهٔ خام دوباره ساخته یا جایگزین نمی‌شود." : "اثر ثبت‌شدهٔ قبلی برگردانده نمی‌شود؛ پردازش در نقطهٔ امن متوقف می‌شود."}</p><div className="cms-actions"><button className="button primary" disabled={busy || blocked} onClick={action}>تأیید {confirmation === "retry" ? "تلاش دوباره" : "درخواست لغو"}</button><button className="button secondary" onClick={() => setConfirmation(undefined)}>انصراف</button></div></section>}
      </section>
      <ArtifactCard key={job.artifact_id} id={job.artifact_id} allowImport={false} onBusy={setCardBusy} />
      {job.output_artifact_id&&!jobActive(job)&&<section className="stack"><h2>بستهٔ خروجی آموزشی</h2>
        <ArtifactCard key={job.output_artifact_id} id={job.output_artifact_id} allowImport={false} onBusy={setOutputBusy}/>
      </section>}
      {job.output_artifact_id&&jobActive(job)&&<p role="status">بسته در حال آماده‌سازی است؛ دریافت تا ثبت موفق نتیجه بسته می‌ماند.</p>}
    </>}
  </div>;
}
