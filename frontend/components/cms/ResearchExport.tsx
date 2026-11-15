"use client";

import { useRef, useState } from "react";
import { CmsError } from "@/lib/cms";
import { AdminJob } from "@/lib/cmsJobs";
import { PrivateMutationError, usePrivateCms } from "./CmsJobsShared";

const fields = [
  ["id", "شناسهٔ رکورد"],
  ["dataset_id", "شناسهٔ مجموعه"],
  ["section", "نوع/بخش"],
  ["external_id", "شناسهٔ ورودی"],
  ["staging_state", "وضعیت بررسی مشتق"],
  ["review_status", "وضعیت مرور ثبت‌شده"],
  ["verification_status", "وضعیت راستی‌آزمایی"],
  ["name_en", "نام انگلیسی"],
  ["name_fa", "نام فارسی"],
] as const;
const initial = ["id", "section", "external_id", "staging_state"];

export default function ResearchExport({ targetKind, targetId }: {
  targetKind: "dataset" | "record"; targetId: number;
}) {
  const { can, request, current } = usePrivateCms();
  const [projection, setProjection] = useState<string[]>(initial);
  const [confirmation, setConfirmation] = useState(false);
  const [job, setJob] = useState<AdminJob>();
  const [error, setError] = useState<unknown>();
  const [busy, setBusy] = useState(false);
  const [unknown, setUnknown] = useState(false);
  const key = useRef<string | null>(null);
  const lock = useRef(false);
  if (!can("cms_research_view") || !can("cms_research_export")) return null;

  function setField(field: string, checked: boolean) {
    if (busy || unknown || job) return;
    setProjection(list => checked ? [...list, field] : list.filter(item => item !== field));
    setConfirmation(false);
    key.current = null;
  }

  async function submit() {
    if (!projection.length || busy || lock.current || job || (!confirmation && !unknown)) return;
    lock.current = true; setBusy(true); setError(undefined);
    try {
      key.current ??= crypto.randomUUID();
      const response = await request<{ job: AdminJob }>("/research/exports/", {
        method: "POST",
        body: JSON.stringify({ target_kind: targetKind, target_id: targetId,
          projection, request_key: key.current }),
      });
      if (current()) { setJob(response.data.job); setUnknown(false); setConfirmation(false); }
    } catch (failure) {
      if (current()) {
        setError(failure);
        if (failure instanceof CmsError && failure.code === "UNKNOWN_OUTCOME") setUnknown(true);
      }
    } finally { lock.current = false; if (current()) setBusy(false); }
  }

  return <section className="card stack" aria-label="درخواست خروجی خصوصی پژوهش" dir="rtl">
    <h2>خروجی کنترل‌شدهٔ پژوهشی</h2>
    <p className="muted">انتخاب رکوردهای {targetKind === "dataset" ? "این مجموعه" : "این رکورد"} و ستون‌های مجاز،
      یک Snapshot خصوصی JSON می‌سازد؛ متن خام، محتوای محدود، منبع محرمانه و نگاشت‌های پژوهشی خارج‌اند.
      مجوز هنگام ثبت، پردازش و دانلود دوباره بررسی می‌شود.</p>
    <fieldset className="cms-fieldset" disabled={busy || !!job || unknown}>
      <legend>فیلدهای مجاز خروجی</legend>
      {fields.filter(([field]) => !["name_en", "name_fa"].includes(field) || can("cms_research_raw_read"))
        .map(([field, label]) => <label key={field} className="cms-check-row">
          <input type="checkbox" checked={projection.includes(field)}
            onChange={event => setField(field, event.target.checked)} />
          <span>{label}</span>
        </label>)}
    </fieldset>
    {error != null && !unknown && <PrivateMutationError error={error} busy={busy} reload={() => { setError(undefined); setConfirmation(false); }} />}
    {unknown && <p role="alert" className="cms-notice">پاسخ سرور نامعلوم است. فقط همان درخواست با همان کلید پیگیری دوباره ارسال می‌شود؛
      از ساخت درخواست تازه جلوگیری شده است.</p>}
    {!job && <div className="cms-actions">
      {!unknown && !confirmation && <button className="button secondary" disabled={busy || !projection.length}
        onClick={() => setConfirmation(true)}>بررسی درخواست خروجی</button>}
      {(confirmation || unknown) && <button className="button primary" disabled={busy || !projection.length}
        onClick={submit}>{busy ? "در حال ثبت…" : unknown ? "تطبیق همان درخواست" : "تأیید و ایجاد کار خروجی"}</button>}
      {confirmation && !unknown && <button className="button secondary" disabled={busy}
        onClick={() => setConfirmation(false)}>لغو</button>}
    </div>}
    {job && <p role="status">درخواست ثبت شد. خروجی تا پایان پردازش قابل دانلود نیست.
      <a className="cms-link" href={`/admin-console/jobs/${job.id}`}>پیگیری کار و دریافت فایل</a>
    </p>}
  </section>;
}
