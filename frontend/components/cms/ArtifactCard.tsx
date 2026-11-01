"use client";

import { useEffect, useRef, useState } from "react";
import { CmsError, cmsDate } from "@/lib/cms";
import { AdminArtifact, AdminJob, Snapshot, artifactKindLabels, artifactStateLabels, artifactUsable, mutationBlocked, p06ErrorMessages, versionHeaders } from "@/lib/cmsJobs";
import { faNumber } from "@/lib/fa";
import { CmsState } from "./CmsShell";
import { PrivateMutationError, usePrivateCms } from "./CmsJobsShared";

export default function ArtifactCard({ id, allowImport = true, onChange, onBusy }: { id: string; allowImport?: boolean; onChange?: () => void; onBusy?: (busy: boolean) => void }) {
  const { can, request, current } = usePrivateCms();
  const [snapshot, setSnapshot] = useState<Snapshot<{ artifact: AdminArtifact }>>();
  const [error, setError] = useState<unknown>(); const [writeError, setWriteError] = useState<unknown>();
  const [reload, setReload] = useState(0); const [busy, setBusy] = useState(false);
  const [confirmation, setConfirmation] = useState<"revoke" | "import" | "cleanup">();
  const [jobId, setJobId] = useState<string>(); const [uncertainImport, setUncertainImport] = useState(false);
  const [cleanupJobId, setCleanupJobId] = useState<string>();
  const key = useRef<string | undefined>(undefined); const lock = useRef(false);
  const artifact = snapshot?.data.artifact; const blocked = mutationBlocked(writeError);
  const editable = !!artifact && can("cms_artifact_upload") && can(`cms_${artifact.domain}_view`) && can(artifact.domain === "research" ? "cms_research_intake" : `cms_${artifact.domain}_edit`);
  const cleanupAllowed = editable && artifact?.state === "expired" && artifact.cleanup_supported !== false && !artifact.purged_at && !cleanupJobId;
  useEffect(() => { onBusy?.(busy); return () => onBusy?.(false); }, [busy, onBusy]);
  useEffect(() => {
    let active = true; const abort = new AbortController(); setSnapshot(undefined); setError(undefined);
    request<{ artifact: AdminArtifact }>(`/artifacts/${encodeURIComponent(id)}/`, { signal: AbortSignal.any([abort.signal, AbortSignal.timeout(15000)]) })
      .then(result => { if (active && current()) setSnapshot(result); })
      .catch(failure => { if (active && current()) setError(failure); });
    return () => { active = false; abort.abort(); };
  }, [id, reload, current, request]);
  async function action(chosen: "validate" | "revoke" | "import" | "cleanup") {
    if (!snapshot || !artifact || lock.current || blocked || (chosen !== "import" && !editable) || (chosen === "import" && uncertainImport)) return;
    if (chosen === "cleanup" && !cleanupAllowed) return;
    lock.current = true; setBusy(true); setWriteError(undefined); setConfirmation(undefined);
    try {
      if (chosen === "import") {
        key.current ??= crypto.randomUUID();
        const result = await request<{ job: AdminJob }>("/research/imports/", { method: "POST", body: JSON.stringify({ artifact_id: artifact.id, request_key: key.current }) });
        if (current()) setJobId(result.data.job.id);
      } else if (chosen === "cleanup") {
        const result = await request<{ job: AdminJob }>(`/artifacts/${artifact.id}/cleanup/`, { method: "POST", headers: versionHeaders(snapshot.etag), body: "{}" });
        if (current()) { setCleanupJobId(result.data.job.id); setReload(n => n + 1); onChange?.(); }
      } else {
        const result = await request<{ artifact: AdminArtifact }>(`/artifacts/${artifact.id}/${chosen}/`, { method: "POST", headers: versionHeaders(snapshot.etag), body: "{}" });
        if (current()) { setSnapshot(result); onChange?.(); }
      }
    } catch (failure) {
      if (current()) { setWriteError(failure); if (chosen === "import" && failure instanceof CmsError && failure.code === "UNKNOWN_OUTCOME") setUncertainImport(true); }
    } finally { lock.current = false; if (current()) setBusy(false); }
  }
  return <section className="card stack" aria-label="جزئیات فایل خصوصی"><h2>فراداده و چرخهٔ فایل خصوصی</h2>
    <PrivateMutationError error={writeError} prefix="artifact" busy={busy} reload={() => { setWriteError(undefined); setConfirmation(undefined); setReload(n => n + 1); }} />
    {error ? <CmsState error={error} retry={() => setReload(n => n + 1)} /> : !artifact ? <CmsState loading /> : <>
      <h3 dir="auto">{artifact.filename}</h3><p className="cms-id"><bdi>{artifact.id}</bdi></p>
      <dl className="cms-audit-detail"><div><dt>نوع و دامنه</dt><dd>{artifactKindLabels[artifact.kind]} · <bdi>{artifact.domain}</bdi></dd></div>
        <div><dt>وضعیت فعلی</dt><dd>{artifactStateLabels[artifact.state]}{!artifactUsable(artifact) && artifact.state === "ready" && "؛ زمان دسترسی پایان یافته"}</dd></div>
        <div><dt>حجم ثبت‌شده و نسخه</dt><dd>{faNumber(artifact.size)} بایت · نسخهٔ {faNumber(artifact.version)}</dd></div>
        <div><dt>اثر انگشت SHA-256</dt><dd dir="ltr">{artifact.sha256}</dd></div>
        <div><dt>ایجاد / انقضا</dt><dd>{cmsDate(artifact.created_at)} / {cmsDate(artifact.expires_at)}</dd></div>
        {artifact.purged_at && <div><dt>پاکسازی بایت‌های فایل</dt><dd>{cmsDate(artifact.purged_at)}؛ فراداده و تاریخچه حفظ شده‌اند.</dd></div>}
        <div><dt>اتصال نسخهٔ دقیق</dt><dd>{artifact.resource_type ? <><bdi>{artifact.resource_type}</bdi> · {faNumber(artifact.resource_id ?? "")} · <bdi>{artifact.resource_version}</bdi></> : "بدون هدف محتوایی؛ فایل ورود پژوهش"}</dd></div>
        <div><dt>نتیجهٔ اعتبارسنجی</dt><dd><bdi>{artifact.validation_code || "هنوز ثبت نشده"}</bdi></dd></div></dl>
      <p className="muted">فایل در فضای خصوصی نگهداری می‌شود. اعتبارسنجی فقط قالب، حدود و یکپارچگی را می‌سنجد؛ شاهد علمی یا اجازهٔ استفاده ایجاد نمی‌کند.</p>
      <p className="muted">پاکسازی فقط با درخواست و تأیید صریح شما انجام می‌شود؛ بایت‌های فایل را از فضای خصوصی حذف می‌کند و فراداده و تاریخچه را نگه می‌دارد. سرور مجوز بارگذاری، مالکیت و دامنهٔ جاری را بررسی می‌کند؛ ارجاع حاکمیت محتوا، بایگانی یا الزام نگهداری مانع حذف است.</p>
      {artifact.cleanup_supported === false && artifact.state === "expired" && !artifact.purged_at && <p className="cms-notice">{p06ErrorMessages.CLEANUP_PLATFORM_UNAVAILABLE}</p>}
      <div className="cms-actions"><button className="button secondary" disabled={busy || blocked} onClick={() => { setConfirmation(undefined); setReload(n => n + 1); }}>بازخوانی فراداده</button>
        {editable && artifact.state === "quarantine" && <button className="button primary" disabled={busy || blocked || !snapshot?.etag} onClick={() => action("validate")}>اعتبارسنجی جداگانهٔ فایل</button>}
        {can("cms_artifact_download") && can(`cms_${artifact.domain}_view`) && artifactUsable(artifact) && <a className="button secondary" href={`/api/admin/artifacts/${artifact.id}/download/?purpose=research_review`} download>دریافت خصوصی با مجوز جاری</a>}
        {editable && !["revoked", "expired"].includes(artifact.state) && <button className="button secondary" disabled={busy || blocked || !snapshot?.etag} onClick={() => setConfirmation("revoke")}>بررسی لغو دسترسی فایل</button>}
        <button className="button secondary" disabled={busy || blocked || !snapshot?.etag || !cleanupAllowed} onClick={() => setConfirmation("cleanup")}>پاکسازی فایل منقضی بدون وابستگی</button>
        {allowImport && can("cms_research_view") && can("cms_research_intake") && artifact.kind !== "evidence_json" && artifactUsable(artifact) && !jobId && <button className="button primary" disabled={busy || blocked || uncertainImport} onClick={() => setConfirmation("import")}>بررسی ایجاد کار ورود</button>}
      </div>
      {confirmation && <section className="cms-conflict stack" aria-labelledby={`artifact-confirm-${artifact.id}`}><h3 id={`artifact-confirm-${artifact.id}`}>{confirmation === "cleanup" ? "تأیید پاکسازی فایل منقضی بدون وابستگی" : confirmation === "revoke" ? "تأیید لغو دسترسی فایل" : "تأیید ایجاد کار ورود"}</h3><p>{confirmation === "cleanup" ? "یک کار پاکسازی ایجاد می‌شود. حذف بایت‌های فایل برگشت‌پذیر نیست؛ فراداده و تاریخچه حفظ می‌شوند. فقط فایل منقضی بدون وابستگی یا الزام نگهداری، پس از بررسی دوبارهٔ سرور قابل حذف است." : confirmation === "revoke" ? "دریافت و پردازش بعدی این فایل متوقف می‌شود. دادهٔ تاریخی واردشده حذف نمی‌شود." : "یک کار برای ورود به فضای پژوهش ایجاد می‌شود؛ متن خام حفظ می‌شود و ارتقا یا انتشار خودکار انجام نمی‌شود."}</p><div className="cms-actions"><button className="button primary" disabled={busy || blocked || (confirmation === "cleanup" && !cleanupAllowed)} onClick={() => action(confirmation)}>تأیید {confirmation === "cleanup" ? "ایجاد کار پاکسازی" : confirmation === "revoke" ? "لغو دسترسی" : "ایجاد کار"}</button><button className="button secondary" disabled={busy} onClick={() => setConfirmation(undefined)}>انصراف</button></div></section>}
      {jobId && <a className="cms-link" href={`/admin-console/jobs/${jobId}`}>پیگیری کار ایجادشده ←</a>}
      {cleanupJobId && <a className="cms-link" href={`/admin-console/jobs/${cleanupJobId}`}>پیگیری کار پاکسازی ←</a>}
      {uncertainImport && <p className="cms-notice">ایجاد دوبارهٔ کار در این فرم بسته است؛ نتیجه را در <a className="cms-link" href="/admin-console/jobs">فهرست کارها</a> بررسی کنید. کلید پیگیری درخواست: <bdi>{key.current}</bdi></p>}
    </>}
  </section>;
}
