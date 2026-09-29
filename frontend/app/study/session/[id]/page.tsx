"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useCallback, useEffect, useState } from "react";
import { ApiError, api } from "@/lib/api";
import { hasToken } from "@/lib/auth";
import { faNumber } from "@/lib/fa";
import type { StudyBlock, StudySession } from "@/lib/types";

const statusLabels = { in_progress: "در جریان", completed: "پایان‌یافته", abandoned: "رهاشده" };

function elapsedLabel(seconds: number) {
  const hours = Math.floor(seconds / 3600);
  const minutes = Math.floor((seconds % 3600) / 60);
  const remaining = seconds % 60;
  return [hours, minutes, remaining].map((part) => faNumber(part).padStart(2, "۰")).join(":");
}

function timestampLabel(value: string) {
  return new Intl.DateTimeFormat("fa-IR", { dateStyle: "medium", timeStyle: "short" }).format(new Date(value));
}

export default function StudySessionPage() {
  const params = useParams<{ id: string }>();
  const sessionId = Number(params.id);
  const [session, setSession] = useState<StudySession | null>(null);
  const [loading, setLoading] = useState(true);
  const [authExpired, setAuthExpired] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [busy, setBusy] = useState(false);
  const [clock, setClock] = useState(Date.now());
  const [loadedAt, setLoadedAt] = useState(Date.now());

  const load = useCallback(async () => {
    if (!Number.isInteger(sessionId) || sessionId <= 0) { setError("شناسه جلسه معتبر نیست."); setLoading(false); return; }
    if (!hasToken()) { setAuthExpired(true); setLoading(false); return; }
    try {
      const result = await api<{ session: StudySession }>(`/study/sessions/${sessionId}/`, {}, true);
      setSession(result.session);
      setError("");
      const receivedAt = Date.now();
      setLoadedAt(receivedAt);
      setClock(receivedAt);
    } catch (reason: unknown) {
      if (reason instanceof ApiError && reason.status === 401) { setAuthExpired(true); return; }
      setError(reason instanceof ApiError && reason.status === 404
        ? "این جلسه پیدا نشد یا به این حساب تعلق ندارد."
        : reason instanceof Error ? reason.message : "جلسه دریافت نشد.");
    } finally { setLoading(false); }
  }, [sessionId]);

  useEffect(() => { void load(); }, [load]);
  useEffect(() => {
    if (session?.status !== "in_progress") return;
    const timer = window.setInterval(() => setClock(Date.now()), 1000);
    const refresh = () => { if (document.visibilityState === "visible") void load(); };
    document.addEventListener("visibilitychange", refresh);
    return () => { window.clearInterval(timer); document.removeEventListener("visibilitychange", refresh); };
  }, [session?.status, load]);

  async function transition(action: "complete" | "abandon") {
    if (!session || busy) return;
    if (action === "abandon" && !window.confirm("این جلسه مطالعه رها شود؟ این کار وضعیت بلوک را تغییر نمی‌دهد.")) return;
    setBusy(true); setError(""); setNotice("");
    try {
      const response = await api<{ session: StudySession }>(`/study/sessions/${session.id}/${action}/`, { method: "POST", body: "{}" }, true);
      setSession(response.session);
      setNotice(action === "complete" ? "دوره مطالعه پایان یافت. تکمیل بلوک جداگانه بررسی می‌شود." : "جلسه رها شد. بلوک مطالعه تغییر نکرد.");
    } catch (reason: unknown) {
      if (reason instanceof ApiError && reason.status === 401) { setAuthExpired(true); return; }
      if (reason instanceof ApiError && reason.code === "study_session_transition_conflict") {
        await load();
        setError("وضعیت جلسه در جای دیگری تغییر کرده است. وضعیت تازه نمایش داده شد.");
      } else setError(reason instanceof Error ? reason.message : "تغییر وضعیت جلسه انجام نشد.");
    } finally { setBusy(false); }
  }

  async function completeBlock() {
    if (!session?.primary_block || busy) return;
    const block = session.primary_block;
    if (!block.evidence_required && !window.confirm("انجام این بلوک را تأیید می‌کنی؟ این تأیید فقط پایبندی به برنامه است و به معنی تسلط نیست.")) return;
    setBusy(true); setError(""); setNotice("");
    try {
      await api<StudyBlock>(`/study/blocks/${block.id}/complete/`, { method: "POST", body: "{}" }, true);
      await load();
      setNotice(block.evidence_required ? "شواهد فعالیت بررسی و بلوک تکمیل شد." : "انجام بلوک با تأیید تو ثبت شد.");
    } catch (reason: unknown) {
      if (reason instanceof ApiError && reason.status === 401) { setAuthExpired(true); return; }
      setError(reason instanceof ApiError && reason.code === "study_block_evidence_missing"
        ? "هنوز شواهد لازم برای تکمیل این بلوک پیدا نشده است. فعالیت اصلی را انجام بده و دوباره بررسی کن."
        : reason instanceof Error ? reason.message : "تکمیل بلوک انجام نشد.");
      if (reason instanceof ApiError && reason.status === 409 && reason.code !== "study_block_evidence_missing") {
        void load();
      }
    } finally { setBusy(false); }
  }

  if (loading) return <main className="shell page"><div className="card" role="status">در حال بارگذاری جلسه...</div></main>;
  if (authExpired) return <main className="shell page"><div className="card error-state"><h1>برای ادامه وارد شو</h1><p>برای دیدن جلسهٔ شخصی باید دوباره وارد حساب شوی.</p><Link className="button primary" href="/login">ورود به حساب</Link></div></main>;
  if (!session) return <main className="shell page"><div className="card error-state" role="alert"><h1>جلسه در دسترس نیست</h1><p>{error}</p><div className="actions"><button className="button" onClick={() => void load()}>تلاش دوباره</button><Link className="button primary" href="/study">بازگشت به مرکز مطالعه</Link></div></div></main>;

  const block = session.primary_block;
  const elapsed = session.status === "in_progress"
    ? Math.min(86400, Math.max(0, session.elapsed_seconds + Math.floor((clock - loadedAt) / 1000)))
    : session.actual_seconds;

  return <main className="shell page stack focused-session" dir="rtl">
    <header><Link href="/study" className="study-plan-back">بازگشت به مرکز مطالعه</Link><div className="meta">جلسه مطالعه · {statusLabels[session.status]}</div><h1 className="section-title">{block?.snapshot_title || "جلسه مطالعه"}</h1><p className="section-copy">پایان جلسه فقط پایان یک دورهٔ مطالعه است؛ به‌تنهایی بلوک یا محتوای آموزشی را تکمیل نمی‌کند.</p></header>
    {error && <div className="study-plan-inline-error" role="alert">{error}</div>}
    {notice && <div className="study-plan-notice" role="status">{notice}</div>}
    <section className="card session-summary" aria-label="وضعیت جلسه">
      <div className="today-capacity-grid"><div><span>وضعیت</span><strong>{statusLabels[session.status]}</strong></div><div><span>زمان برنامه‌ریزی‌شده</span><strong>{faNumber(session.planned_minutes)} <small>دقیقه</small></strong></div><div><span>شروع به وقت دستگاه</span><strong className="session-timestamp">{timestampLabel(session.started_at)}</strong></div><div><span>زمان سپری‌شده</span><strong dir="ltr">{elapsedLabel(elapsed)}</strong></div></div>
      <p className="muted small">زمان سپری‌شده فقط نمایش فاصلهٔ زمانی است، نه تأیید تمرکز یا یادگیری. زمان و پایان ثبت‌شده از سرور می‌آید.{session.elapsed_capped || elapsed === 86400 ? " نمایش زمان در ۲۴ ساعت محدود شده است." : ""}</p>
      {session.status === "completed" && session.completed_at && <p>پایان: {timestampLabel(session.completed_at)}</p>}
      {session.status === "abandoned" && session.abandoned_at && <p>رهاشده در: {timestampLabel(session.abandoned_at)}</p>}
    </section>
    <section className="card session-block"><div className="today-section-head"><h2>بلوک اصلی</h2><Link href={`/study/plans/${session.plan_id}`}>باز کردن برنامه</Link></div>
      {block ? <><h3>{block.snapshot_title}</h3><p>وضعیت بلوک: {block.status === "completed" ? "تکمیل‌شده" : block.status === "in_progress" ? "در جریان" : block.status === "pending" ? "در انتظار" : "دیگر قابل انجام نیست"} · {faNumber(block.estimated_minutes)} دقیقه</p>
        <p className="muted small">{block.evidence_required ? "تکمیل بلوک نیازمند شواهد فعالیت در مسیر اصلی یادگیری است." : "تکمیل بلوک با تأیید صریح تو فقط پایبندی به برنامه را ثبت می‌کند."}</p>
        <div className="actions">{block.action_href ? <Link className="button primary" href={block.action_href}>باز کردن فعالیت اصلی</Link> : <p className="muted">محتوای این بلوک فعلاً در دسترس نیست.</p>}
          {block.status !== "completed" && block.action_href && <button type="button" className="button" disabled={busy} onClick={() => void completeBlock()}>{block.evidence_required ? "بررسی تکمیل بلوک" : "تأیید انجام بلوک"}</button>}</div>
      </> : <p className="muted">بلوک اصلی حذف شده یا دیگر در دسترس نیست. می‌توانی جلسه را پایان بدهی یا به برنامه برگردی.</p>}
    </section>
    {session.status === "in_progress" && <section className="card session-finish"><h2>پایان دوره مطالعه</h2><p className="muted">پایان دادن یا رها کردن جلسه، وضعیت بلوک و شواهد یادگیری را تغییر نمی‌دهد.</p><div className="actions"><button type="button" className="button primary" disabled={busy} onClick={() => void transition("complete")}>پایان جلسه</button><button type="button" className="button danger-ghost" disabled={busy} onClick={() => void transition("abandon")}>رها کردن جلسه</button></div></section>}
    <Link className="button session-return" href="/study">بازگشت به مرکز مطالعه</Link>
  </main>;
}
