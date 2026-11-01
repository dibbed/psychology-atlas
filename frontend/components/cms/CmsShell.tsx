"use client";

import { createContext, useCallback, useContext, useEffect, useRef, useState } from "react";
import { usePathname } from "next/navigation";
import { BookOpenText, History, LayoutDashboard, ListChecks, LogOut, ShieldCheck } from "lucide-react";
import { cms, CmsCatalog, CmsError, CmsMe } from "@/lib/cms";

type ConsoleContext = { me: CmsMe; can: (capability: string) => boolean; setDirty: (dirty: boolean) => void; leave: (action: () => void) => void };
const Context = createContext<ConsoleContext | null>(null);
export function useCms() {
  const value = useContext(Context);
  if (!value) throw new Error("CMS context required");
  return value;
}

export function CmsState({ error, loading, empty, retry }: { error?: unknown; loading?: boolean; empty?: string; retry?: () => void }) {
  const focus = useRef<HTMLDivElement>(null);
  useEffect(() => { if (error) focus.current?.focus(); }, [error]);
  if (loading) return <div className="cms-state" role="status" aria-live="polite"><span className="cms-loading" aria-hidden="true" />در حال دریافت داده از سرور…</div>;
  if (empty) return <div className="cms-state"><h2>موردی یافت نشد</h2><p>{empty}</p></div>;
  const failure = error instanceof CmsError ? error : null;
  const forbidden = failure?.code === "PERMISSION_DENIED" || failure?.code === "NOT_FOUND";
  return <div className="cms-state cms-error" role="alert" tabIndex={-1} ref={focus}>
    <h2>{forbidden ? "این بخش در دسترس شما نیست" : "درخواست انجام نشد"}</h2>
    <p>{forbidden ? "مجوز کافی ندارید یا رکورد در محدودهٔ دسترسی شما وجود ندارد." : failure?.message || "دریافت اطلاعات ناموفق بود."}</p>
    {failure?.details.request_id && <p>شناسهٔ پیگیری: <bdi>{failure.details.request_id}</bdi></p>}
    {retry && !forbidden && <button className="button secondary" onClick={retry}>تلاش دوباره</button>}
  </div>;
}

function Login({ expired, onSuccess }: { expired: boolean; onSuccess: () => void }) {
  const [stage, setStage] = useState<"password" | "mfa">("password");
  const [method, setMethod] = useState("totp");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<unknown>();
  async function submit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (busy) return;
    const formElement = event.currentTarget;
    const fields = new FormData(formElement);
    setBusy(true); setError(undefined);
    try {
      if (stage === "password") {
        await cms("/auth/login/", { method: "POST", body: JSON.stringify({ username: fields.get("username"), password: fields.get("password") }) });
        formElement.reset(); setStage("mfa");
      } else {
        await cms("/auth/verify/", { method: "POST", body: JSON.stringify({ method, token: fields.get("token") }) });
        onSuccess();
      }
    } catch (failure) { setError(failure); } finally { setBusy(false); }
  }
  async function complete() {
    if (busy) return;
    setBusy(true); setError(undefined);
    try { await cms("/auth/complete/", { method: "POST", body: "{}" }); onSuccess(); }
    catch (failure) { setError(failure); } finally { setBusy(false); }
  }
  return <main id="cms-main" className="cms-login shell">
    <a href="/" className="eyebrow">اطلس روان‌شناسی</a>
    <section className="card stack">
      <ShieldCheck size={28} aria-hidden="true" />
      <div><p className="eyebrow">کنسول مدیریت · دسترسی محدود</p><h1>{expired ? "نشست مدیریت پایان یافته است" : "ورود به کنسول"}</h1></div>
      {expired && <p role="status">نشست پایان یافته یا در پنجرهٔ دیگری تغییر کرده است. برای ادامه دوباره وارد شوید. تغییرات ذخیره‌نشده از حافظهٔ این صفحه پاک شده‌اند؛ تغییری خودکار تکرار نمی‌شود.</p>}
      <p>ورود مدیریت به گذرواژه و احراز هویت دومرحله‌ای نیاز دارد.</p>
      <form key={stage} onSubmit={submit} className="stack">
        {stage === "password" ? <>
          <label>نام کاربری<input name="username" dir="ltr" autoComplete="username" required maxLength={254} autoFocus /></label>
          <label>گذرواژه<input name="password" type="password" dir="ltr" autoComplete="current-password" required maxLength={1024} /></label>
        </> : <>
          <label>روش تأیید<select value={method} onChange={event => setMethod(event.target.value)}><option value="totp">کد برنامهٔ احراز هویت</option><option value="recovery">کد بازیابی یک‌بارمصرف</option></select></label>
          <label>کد تأیید<input name="token" dir="ltr" autoComplete="one-time-code" required maxLength={128} autoFocus /></label>
          <p className="muted">اگر هنوز MFA تنظیم نشده، <a className="cms-link" href="/account/two_factor/setup/" target="_blank" rel="noopener">تنظیم دومرحله‌ای را در پنجرهٔ جدید انجام دهید</a> و سپس ورود را تکمیل کنید.</p>
          <button type="button" className="button secondary" disabled={busy} onClick={complete}>تکمیل ورود پس از تنظیم MFA</button>
        </>}
        <button className="button primary" disabled={busy}>{busy ? "در حال بررسی…" : stage === "password" ? "ادامه با گذرواژه" : "تأیید و ورود"}</button>
      </form>
      {error != null && <CmsState error={error} />}
    </section>
  </main>;
}

export default function CmsShell({ children }: { children: React.ReactNode }) {
  const path = usePathname();
  const [me, setMe] = useState<CmsMe>();
  const [catalog, setCatalog] = useState<CmsCatalog>();
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<unknown>();
  const [expired, setExpired] = useState(false);
  const [dirty, setDirty] = useState(false);
  const dirtyRef = useRef(false);
  const leaving = useRef(false);
  const pending = useRef<(() => void) | null>(null);
  const dialog = useRef<HTMLDialogElement>(null);
  const logoutBusy = useRef(false);
  const hasSession = useRef(false);
  const can = (cap: string) => !!me?.ready_capabilities.includes(cap);
  const markDirty = useCallback((value: boolean) => { dirtyRef.current = value; setDirty(value); }, []);
  const load = useCallback(async () => {
    setLoading(true); setError(undefined);
    try {
      const current = (await cms<CmsMe>("/me/")).data;
      const capabilities = current.ready_capabilities.includes("cms_catalog") ? (await cms<CmsCatalog>("/catalog/")).data : undefined;
      hasSession.current = true;
      setMe(current); setCatalog(capabilities); setExpired(false);
    } catch (failure) {
      setMe(undefined); setCatalog(undefined);
      if (!(failure instanceof CmsError && failure.code === "UNAUTHENTICATED")) setError(failure);
    } finally { setLoading(false); }
  }, []);
  useEffect(() => { void load(); }, [load]);
  useEffect(() => { if (me) document.getElementById("cms-main")?.focus(); }, [me]);
  useEffect(() => {
    const end = () => { setMe(undefined); setCatalog(undefined); markDirty(false); if (hasSession.current) setExpired(true); hasSession.current = false; pending.current = null; dialog.current?.close(); };
    const unload = (event: BeforeUnloadEvent) => { if (dirtyRef.current && !leaving.current) { event.preventDefault(); event.returnValue = ""; } };
    window.addEventListener("cms-session-expired", end); window.addEventListener("beforeunload", unload);
    const channel = typeof BroadcastChannel !== "undefined" ? new BroadcastChannel("atlas-cms-session") : null;
    if (channel) channel.onmessage = end;
    return () => { window.removeEventListener("cms-session-expired", end); window.removeEventListener("beforeunload", unload); channel?.close(); };
  }, [markDirty]);
  const leave = (action: () => void) => {
    if (!dirtyRef.current) { action(); return; }
    pending.current = action; dialog.current?.showModal();
  };
  async function logout() {
    if (logoutBusy.current) return;
    logoutBusy.current = true;
    try { await cms("/auth/logout/", { method: "POST", body: "{}" }); markDirty(false); hasSession.current = false; setMe(undefined); setCatalog(undefined); setExpired(false); }
    catch (failure) { setError(failure); } finally { logoutBusy.current = false; }
  }
  if (loading) return <div className="cms-root shell page"><CmsState loading /></div>;
  if (!me) return <div className="cms-root">{error ? <div className="shell page"><CmsState error={error} retry={load} /></div> : <Login expired={expired} onSuccess={load} />}</div>;
  const contentReady = (can('cms_core_view') || can('cms_dsm_view') || can('cms_therapy_view') || can('cms_history_view') || can('cms_brain_view') || can('cms_assessment_view')) && me.ready_content_kinds.some(kind => !catalog || catalog.ready_content_kinds.includes(kind));
  const governanceReady = ["core", "dsm", "therapy", "history", "cases", "learning", "brain", "assessment", "source"].some(domain => can(`cms_${domain}_view`));
  const items = [
    { href: "/admin-console", label: "خانهٔ مدیریت", icon: LayoutDashboard, ready: can("cms_dashboard") },
    { href: "/admin-console/content", label: "محتوای مرجع", icon: BookOpenText, ready: contentReady },
    { href: "/admin-console/reviews", label: "بررسی پیشنهادها", icon: ShieldCheck, ready: can("cms_core_view") || can('cms_dsm_view') || can('cms_therapy_view') || can('cms_history_view') || can('cms_brain_view') || can('cms_assessment_view') },
    { href: "/admin-console/sources", label: "منابع", icon: BookOpenText, ready: can("cms_source_view") },
    { href: "/admin-console/rights", label: "حقوق محتوا", icon: ShieldCheck, ready: governanceReady },
    { href: "/admin-console/terminology", label: "اصطلاحات فارسی", icon: BookOpenText, ready: governanceReady },
    { href: "/admin-console/research", label: "داده‌های پژوهشی", icon: BookOpenText, ready: can("cms_research_view") },
    { href: "/admin-console/research/intake", label: "ورود و فایل‌های خصوصی", icon: BookOpenText, ready: can("cms_enter") && (can("cms_artifact_upload") || can("cms_artifact_download")) },
    { href: "/admin-console/jobs", label: "کارهای پردازش", icon: ListChecks, ready: can("cms_enter") && (can("cms_artifact_upload") || (can("cms_research_view") && can("cms_research_intake"))) },
    { href: "/admin-console/audit", label: "تاریخچهٔ عملیات", icon: History, ready: can("cms_audit_view") },
  ].filter(item => item.ready);
  const future = [
    ["cms_brain_view", "اطلس مغز"], ["cms_assessment_view", "ارزیابی‌ها"], ["cms_cases_view", "کیس‌ها"],
    ["cms_publication_view", "انتشار"], ["cms_roles_view", "نقش‌ها و دسترسی"],
  ].filter(([cap]) => catalog?.capabilities.some(item => item.codename === cap));
  return <Context.Provider value={{ me, can, setDirty: markDirty, leave }}>
    <div className="cms-root" onClickCapture={event => {
      const link = (event.target as HTMLElement).closest<HTMLAnchorElement>("a[href]");
      if (!link || !dirtyRef.current || event.ctrlKey || event.metaKey || event.shiftKey || event.altKey || link.target === "_blank" || link.href === location.href || link.hash) return;
      event.preventDefault(); leave(() => location.assign(link.href));
    }}>
      <a href="#cms-main" className="skip-link">رفتن به محتوای مدیریت</a>
      <header className="cms-header"><a href="/" className="brand">اطلس روان‌شناسی</a><span className="cms-badge">کنسول مدیریت</span><span className="cms-account"><bdi>{me.user.username}</bdi><button className="button secondary" onClick={() => leave(logout)}><LogOut size={16} aria-hidden="true" />خروج</button></span></header>
      <div className="cms-workspace">
        <aside className="cms-sidebar"><p className="eyebrow">مدیریت اطلس</p><nav aria-label="بخش‌های مدیریت">{items.map(({ href, label, icon: Icon }) => <a key={href} href={href} aria-current={(href === "/admin-console" ? path === href : path.startsWith(href)) ? "page" : undefined}><Icon size={18} aria-hidden="true" />{label}</a>)}</nav>
          {future.length > 0 && <details className="cms-future"><summary>بخش‌های بعدی</summary><ul>{future.map(([cap, label]) => <li key={cap}>{label}<small>رابط آماده نشده</small></li>)}</ul></details>}
          <p className="cms-sidebar-note">ذخیرهٔ پیشنهاد، محتوای عمومی را منتشر نمی‌کند.</p>
        </aside>
        <main id="cms-main" tabIndex={-1} className="cms-main">
          <div className="cms-context"><span>اطلس / مدیریت</span><span role="status">{dirty ? "تغییرات ذخیره نشده" : "نشست دومرحله‌ای"}</span></div>
          {error != null && <CmsState error={error} retry={() => setError(undefined)} />}
          {children}
        </main>
      </div>
      <dialog ref={dialog} className="cms-dialog" aria-labelledby="cms-leave-title" onCancel={() => { pending.current = null; }}>
        <h2 id="cms-leave-title">تغییرات ذخیره نشده‌اند</h2><p>با ترک صفحه، تغییرات این فرم از دست می‌روند.</p>
        <div className="cms-actions"><button className="button primary" autoFocus onClick={() => { pending.current = null; dialog.current?.close(); }}>ادامهٔ ویرایش</button>
          <button className="button secondary" onClick={() => { const action = pending.current; pending.current = null; leaving.current = true; markDirty(false); dialog.current?.close(); action?.(); leaving.current = false; }}>ترک بدون ذخیره</button></div>
      </dialog>
    </div>
  </Context.Provider>;
}
