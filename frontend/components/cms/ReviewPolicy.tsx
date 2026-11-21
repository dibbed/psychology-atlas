"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { CmsState, useCms } from "./CmsShell";
import {
  cms, CmsError, CmsPage, ReviewPolicy as Policy, ReviewPolicyDetail, ReviewPolicyHistory,
  cmsDate, reviewPolicyLabels, reviewReasonLabels,
} from "@/lib/cms";
import { faNumber } from "@/lib/fa";

type Snapshot = { data: ReviewPolicyDetail; etag: string | null };

export default function ReviewPolicy() {
  const { me, can, setDirty, leave } = useCms();
  const allowed = can("cms_core_view");
  const editable = allowed && can("cms_owner") && can("cms_settings_edit");
  const [base, setBase] = useState<Snapshot>();
  const [mode, setMode] = useState<Policy["mode"]>("solo_owner");
  const [reason, setReason] = useState("");
  const [method, setMethod] = useState<"totp" | "recovery">("totp");
  const [token, setToken] = useState("");
  const [dirty, setFormDirty] = useState(false);
  const [busy, setBusy] = useState(false);
  const busyRef = useRef(false);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState<unknown>();
  const [reload, setReload] = useState(0);
  const [saveError, setSaveError] = useState<unknown>();
  const [lockMessage, setLockMessage] = useState<string>();
  const [saved, setSaved] = useState(false);
  const [history, setHistory] = useState<CmsPage<ReviewPolicyHistory>>();
  const [historyQuery, setHistoryQuery] = useState<{ page: number }>();
  const [historyLoading, setHistoryLoading] = useState(false);
  const [historyError, setHistoryError] = useState<unknown>();
  const historySequence = useRef(0);
  const failure = saveError instanceof CmsError ? saveError : undefined;
  const fieldErrors = failure?.details.field_errors;

  useEffect(() => { setDirty(dirty || busy); return () => setDirty(false); }, [dirty, busy, setDirty]);

  const acceptSnapshot = useCallback((snapshot: Snapshot) => {
    historySequence.current += 1;
    setHistoryQuery(undefined); setHistoryLoading(false); setHistoryError(undefined);
    setHistory(snapshot.data.history); setBase(snapshot);
    setMode(snapshot.data.mode); setReason(""); setToken(""); setMethod("totp");
    setFormDirty(false); setDirty(false); setLockMessage(undefined); setSaveError(undefined);
  }, [setDirty]);

  useEffect(() => {
    if (!allowed) return;
    let active = true;
    setLoading(true); setLoadError(undefined);
    cms<ReviewPolicyDetail>("/reviews/policy/?page=1")
      .then(snapshot => { if (active) acceptSnapshot(snapshot); })
      .catch(error => { if (active) setLoadError(error); })
      .finally(() => { if (active) setLoading(false); });
    return () => { active = false; };
  }, [allowed, reload, acceptSnapshot]);

  useEffect(() => {
    if (!allowed || !historyQuery) return;
    let active = true;
    const sequence = ++historySequence.current;
    setHistoryLoading(true); setHistoryError(undefined);
    cms<ReviewPolicyDetail>(`/reviews/policy/?page=${historyQuery.page}`)
      .then(({ data }) => { if (active && sequence === historySequence.current) setHistory(data.history); })
      .catch(error => { if (active && sequence === historySequence.current) setHistoryError(error); })
      .finally(() => { if (active && sequence === historySequence.current) setHistoryLoading(false); });
    return () => { active = false; };
  }, [allowed, historyQuery]);

  function edited() {
    setFormDirty(true); setDirty(true); setSaved(false);
  }

  function reloadPolicy() {
    if (busyRef.current || loading) return;
    leave(() => {
      if (busyRef.current) return;
      setDirty(dirty); setSaved(false); setLoading(true);
      setReload(value => value + 1);
    });
  }

  function resetForm() {
    if (!base || busyRef.current || loading) return;
    leave(() => {
      if (busyRef.current) return;
      setMode(base.data.mode); setReason(""); setToken(""); setMethod("totp");
      setFormDirty(false); setDirty(false); setSaved(false); setSaveError(undefined);
    });
  }

  async function save(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (busyRef.current || loading || loadError || lockMessage || !editable || !base?.etag
        || mode === base.data.mode || !base.data.reason_codes.includes(reason) || !token.trim()) return;
    const policyBody = { mode, reason };
    const etag = base.etag;
    const expectedUserId = me.user.id;
    busyRef.current = true; setBusy(true); setSaveError(undefined); edited();
    let posted = false;
    try {
      await cms("/auth/step-up/", {
        method: "POST", headers: { "If-Match": etag },
        body: JSON.stringify({ token, method, action: "review_policy", target_id: 1, payload: policyBody }),
      }, expectedUserId);
      await cms<Policy>("/reviews/policy/", {
        method: "POST", headers: { "If-Match": etag }, body: JSON.stringify(policyBody),
      }, expectedUserId);
      posted = true;
      const snapshot = await cms<ReviewPolicyDetail>("/reviews/policy/?page=1");
      acceptSnapshot(snapshot); setSaved(true);
    } catch (error) {
      setSaveError(error);
      if (posted) {
        setLockMessage("تغییر سیاست ثبت شد، اما دریافت وضعیت تازه ناموفق بود. پیش از هر تغییر بعدی، نسخهٔ سرور و تاریخچه را با دکمهٔ دریافت دوباره بررسی کنید.");
      } else if (error instanceof CmsError && (error.code === "UNKNOWN_OUTCOME" || error.status === 409 || error.status === 412 || error.status >= 500)) {
        setLockMessage("نتیجهٔ عملیات نامعلوم است یا نسخهٔ پایه تغییر کرده است. ذخیره تا دریافت صریح و موفق نسخهٔ سرور قفل می‌ماند؛ بازنشانی فرم یا صفحه‌بندی تاریخچه این قفل را باز نمی‌کند.");
      }
    } finally {
      busyRef.current = false; setBusy(false);
    }
  }

  if (!allowed) return <CmsState error={new CmsError(403, "PERMISSION_DENIED", "")} />;

  return <div className="stack">
    <a className="cms-link" href="/admin-console/reviews">بازگشت به صف بازبینی</a>
    <div className="cms-title">
      <h1>سیاست بازبینی محتوای مرجع</h1>
      <p className="muted">این سیاست فقط بررسی پیشنهادهای محتوای مرجع (core) را کنترل می‌کند.</p>
    </div>
    <p className="cms-notice">مجوز تنظیمات در این بخش فقط برای تغییر سیاست بازبینی محتوای مرجع فعال است. تغییر به مالک دارای هر دو مجوز مالک و ویرایش تنظیمات، همراه با تأیید دومرحله‌ای متصل به همین تغییر، محدود است.</p>
    <p className="cms-notice">تصمیم‌های قبلی تغییر یا حذف نمی‌شوند. با تغییر سیاست، تصمیم‌های وابسته به سیاست قبلی با علت «{reviewReasonLabels.POLICY_CHANGED}» دیگر معتبر نیستند. واجد شرایط بودن برای تأیید، به معنای انتشار نیست؛ تغییر سیاست محتوای عمومی را منتشر نمی‌کند.</p>

    <div className="cms-actions">
      <button type="button" className="button secondary" disabled={busy || loading} onClick={reloadPolicy}>دریافت دوبارهٔ سیاست و تاریخچه از سرور</button>
    </div>
    {loading && <CmsState loading />}
    {loadError != null && <CmsState error={loadError} retry={reloadPolicy} />}

    {base && <>
      <section className="card stack" aria-labelledby="review-policy-current-title">
        <h2 id="review-policy-current-title">سیاست ذخیره‌شدهٔ سرور</h2>
        <dl className="cms-audit-detail">
          <div><dt>محدوده</dt><dd>محتوای مرجع (core)</dd></div>
          <div><dt>سیاست فعلی</dt><dd>{reviewPolicyLabels[base.data.mode]}</dd></div>
          <div><dt>نسخهٔ سیاست</dt><dd>{faNumber(base.data.version)}</dd></div>
        </dl>
        {!editable && <p className="cms-notice">دسترسی شما در این صفحه فقط خواندنی است. ویرایش به هر دو مجوز مالک و ویرایش تنظیمات نیاز دارد.</p>}
      </section>

      {editable && <form className="card stack" onSubmit={save} aria-labelledby="review-policy-form-title" aria-busy={busy || loading} data-testid="review-policy-form">
        <div className="cms-section-head">
          <h2 id="review-policy-form-title">تغییر سیاست بازبینی</h2>
          <span className="muted" role="status">{dirty ? "ذخیره نشده" : "بدون تغییر ذخیره‌نشده"}</span>
        </div>
        <p id="review-policy-form-hint" className="muted">حالت تازه و دلیل مجاز را انتخاب کنید. تأیید دومرحله‌ای فقط برای همین حالت و دلیل انجام می‌شود؛ سپس تغییر روی نسخهٔ ذخیره‌شدهٔ بالا ارسال می‌شود.</p>
        {saveError != null && <CmsState error={saveError} />}
        {lockMessage && <p className="cms-notice" role="status">{lockMessage}</p>}
        {!base.etag && <p className="cms-notice" role="status">شناسهٔ نسخهٔ سرور (ETag) دریافت نشده است. ذخیره غیرفعال است؛ سیاست را دوباره از سرور دریافت کنید.</p>}
        <fieldset className="cms-fieldset" disabled={busy || loading} aria-describedby="review-policy-form-hint">
          <legend className="muted">سیاست و تأیید دومرحله‌ای</legend>
          <div className="cms-form-field">
            <label htmlFor="review-policy-mode">حالت بازبینی</label>
            <select id="review-policy-mode" name="mode" required value={mode} aria-invalid={!!fieldErrors?.mode} aria-describedby="review-policy-mode-hint" onChange={event => { setMode(event.target.value as Policy["mode"]); edited(); }}>
              {Object.entries(reviewPolicyLabels).map(([value, label]) => <option key={value} value={value}>{label}</option>)}
            </select>
            <small id="review-policy-mode-hint">حالت باید با سیاست فعلی متفاوت باشد. {fieldErrors?.mode?.join(" · ")}</small>
          </div>
          <div className="cms-form-field">
            <label htmlFor="review-policy-reason">دلیل تغییر سیاست (الزامی)</label>
            <select id="review-policy-reason" name="reason" required value={reason} aria-invalid={!!fieldErrors?.reason} aria-describedby="review-policy-reason-hint" onChange={event => { setReason(event.target.value); edited(); }}>
              <option value="" disabled>دلیل را انتخاب کنید</option>
              {base.data.reason_codes.map(code => <option key={code} value={code}>{reviewReasonLabels[code] || code}</option>)}
            </select>
            <small id="review-policy-reason-hint">فقط دلیل‌های مجاز همین نسخهٔ سرور قابل انتخاب‌اند. {fieldErrors?.reason?.join(" · ")}</small>
          </div>
          <div className="cms-form-field">
            <label htmlFor="review-policy-method">روش تأیید دومرحله‌ای</label>
            <select id="review-policy-method" name="method" value={method} aria-invalid={!!fieldErrors?.method} aria-describedby="review-policy-method-hint" onChange={event => { setMethod(event.target.value as "totp" | "recovery"); setToken(""); edited(); }}>
              <option value="totp">برنامهٔ رمزساز</option><option value="recovery">کد بازیابی</option>
            </select>
            <small id="review-policy-method-hint">کد بازیابی یک‌بار مصرف است. {fieldErrors?.method?.join(" · ")}</small>
          </div>
          <div className="cms-form-field">
            <label htmlFor="review-policy-token">{method === "totp" ? "کد برنامهٔ رمزساز" : "کد بازیابی"} (الزامی)</label>
            <input id="review-policy-token" name="token" type="password" dir="ltr" required maxLength={128} autoComplete="one-time-code" inputMode={method === "totp" ? "numeric" : "text"} value={token} aria-invalid={!!fieldErrors?.token} aria-describedby="review-policy-token-hint" onChange={event => { setToken(event.target.value); edited(); }} />
            <small id="review-policy-token-hint">کد تازه برای تأیید همین تغییر وارد کنید. {fieldErrors?.token?.join(" · ")}</small>
          </div>
        </fieldset>
        <div className="cms-actions">
          <button type="submit" className="button primary" data-testid="review-policy-save" disabled={busy || loading || !!loadError || !!lockMessage || !base.etag || mode === base.data.mode || !base.data.reason_codes.includes(reason) || !token.trim()}>{busy ? "در حال تأیید و ذخیره…" : "تأیید دومرحله‌ای و ذخیرهٔ سیاست"}</button>
          <button type="button" className="button secondary" disabled={busy || loading || !dirty} onClick={resetForm}>بازنشانی فرم به سیاست ذخیره‌شده</button>
        </div>
        {saved && <p className="cms-success" role="status">سیاست ذخیره شد و وضعیت تازهٔ سرور دریافت شد. انتشار عمومی انجام نشده است.</p>}
      </form>}

      <section className="card stack" aria-labelledby="review-policy-history-title" aria-busy={historyLoading}>
        <h2 id="review-policy-history-title">تاریخچهٔ تغییر سیاست</h2>
        <p className="muted">صفحه‌بندی فقط تاریخچه را دریافت می‌کند؛ فرم و نسخهٔ پایهٔ ذخیره تغییر نمی‌کنند.</p>
        {historyLoading ? <CmsState loading /> : historyError != null ? <CmsState error={historyError} retry={() => setHistoryQuery({ page: historyQuery?.page || history?.page || 1 })} /> : history && <>
          {!history.results.length ? <CmsState empty="هنوز تغییری در سیاست بازبینی ثبت نشده است." /> : <div className="cms-table-wrap" tabIndex={0} role="region" aria-label="تاریخچهٔ سیاست؛ قابل پیمایش افقی">
            <table className="cms-table">
              <caption>{faNumber(history.count)} تغییر ثبت‌شده</caption>
              <thead><tr><th scope="col">نسخه</th><th scope="col">سیاست قبلی</th><th scope="col">سیاست تازه</th><th scope="col">دلیل</th><th scope="col">زمان</th></tr></thead>
              <tbody>{history.results.map(row => <tr key={row.version}>
                <th scope="row">{faNumber(row.version)}</th><td>{reviewPolicyLabels[row.previous_mode]}</td><td>{reviewPolicyLabels[row.mode]}</td>
                <td>{reviewReasonLabels[row.reason] || row.reason}</td><td><time dateTime={row.created_at}>{cmsDate(row.created_at)}</time></td>
              </tr>)}</tbody>
            </table>
          </div>}
          <nav className="cms-pagination" aria-label="صفحه‌بندی تاریخچهٔ سیاست">
            <button type="button" className="button secondary" disabled={busy || loading || history.page <= 1} onClick={() => setHistoryQuery({ page: history.page - 1 })}>صفحهٔ قبل</button>
            <span>صفحهٔ {faNumber(history.page)}</span>
            <button type="button" className="button secondary" disabled={busy || loading || history.page * history.page_size >= history.count} onClick={() => setHistoryQuery({ page: history.page + 1 })}>صفحهٔ بعد</button>
          </nav>
        </>}
      </section>
    </>}
  </div>;
}
