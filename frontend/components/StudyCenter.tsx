"use client";

import Link from "next/link";
import { useCallback, useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { ApiError, api } from "@/lib/api";
import { hasToken } from "@/lib/auth";
import { faNumber } from "@/lib/fa";
import type { StudySession, StudyToday, TodayBlock } from "@/lib/types";
import DailyChallengeCard from "./DailyChallengeCard";
import DSMStudyPanel from "./DSMStudyPanel";
import StudyHeatmap from "./StudyHeatmap";
import StudyRecommendationsV2 from "./StudyRecommendationsV2";

type Overview = { streak: number; concepts: { studied: number; mastered: number }; heatmap: { date: string; count: number }[]; distortion_practice: { attempts: number; accuracy: number } };
type PendingStart = { blockId: number; eventId: string };
const pendingKey = "study-session-pending-start";

const kindLabels: Record<string, string> = {
  flashcard_review: "مرور فلش‌کارت", concept_review: "مرور مفهوم", disorder_review: "مرور اختلال",
  therapy_reading: "مطالعه درمان", theory_reading: "مطالعه نظریه", psychologist_reading: "مطالعه روان‌شناس",
  timeline_review: "مرور خط زمان", quiz_practice: "آزمون", case_practice: "مورد بالینی",
  distortion_practice: "تمرین تحریف شناختی", notes_review: "مرور یادداشت‌ها", daily_challenge_optional: "چالش روزانه",
};
const reasons: Record<string, string> = {
  session_in_progress: "یک جلسه مطالعه در جریان داری.", session_focus_unavailable: "جلسه‌ات هنوز فعال است؛ محتوای بلوک فعلاً در دسترس نیست.",
  case_in_progress: "تمرین موردی ناتمام داری.", block_overdue: "این بلوک از تاریخ برنامه‌ریزی‌شده گذشته است.",
  block_due_today: "این بلوک برای امروز برنامه‌ریزی شده است.", srs_overdue: "مرور فلش‌کارت‌های عقب‌افتاده در صف است.",
  srs_due: "فلش‌کارت موعدرسیده داری.", challenge_available: "چالش امروز در دسترس است و ظرفیت برنامه‌ریزی‌نشده داری.",
  recommendation_v2: "این پیشنهاد بر پایهٔ محتوای در دسترس و وضعیت فعلی مطالعه‌ات نمایش داده می‌شود.", create_plan: "برای زمان‌بندی مطالعه، ابتدا یک برنامه بساز.",
  review_plans: "برنامه‌های موجود را بازبینی کن.", prepare_schedule: "برنامه فعال است و زمان‌بندی آن نیاز به آماده‌سازی دارد.",
  srs_new: "فلش‌کارت‌های جدید برای شروع در دسترس‌اند.",
};

function dateLabel(value: string) {
  const [year, month, day] = value.split("-").map(Number);
  if (!year || !month || !day) return value;
  return new Intl.DateTimeFormat("fa-IR", { year: "numeric", month: "short", day: "numeric", timeZone: "UTC" })
    .format(new Date(Date.UTC(year, month - 1, day)));
}

function pendingStart(): PendingStart | null {
  try {
    const raw = sessionStorage.getItem(pendingKey);
    if (!raw) return null;
    const value: unknown = JSON.parse(raw);
    if (value && typeof value === "object" && "blockId" in value && "eventId" in value &&
        typeof value.blockId === "number" && typeof value.eventId === "string") return value as PendingStart;
  } catch { /* Ignore a corrupt local draft. */ }
  return null;
}

function BlockList({ title, blocks, total, truncated, onStart, busy, active }: {
  title: string; blocks: TodayBlock[]; total: number; truncated: boolean;
  onStart: (id: number) => void; busy: boolean; active: boolean;
}) {
  return <section className="card today-blocks" aria-label={title}>
    <div className="today-section-head"><h2>{title} <span className="muted">{faNumber(total)}</span></h2><Link href="/study/plans">برنامه‌ها</Link></div>
    {blocks.length === 0 ? <p className="muted">بلوک قابل انجامی در این بخش نیست.</p> :
      <div className="today-block-list">{blocks.map((block) => <article className="today-block-row" key={block.id}>
        <div className="today-block-copy">
          <div className="meta">{kindLabels[block.block_kind] ?? block.block_kind} · {faNumber(block.estimated_minutes)} دقیقه · {block.status === "in_progress" ? "در جریان" : "در انتظار"}</div>
          <h3>{block.snapshot_title}</h3>
          <p><Link href={`/study/plans/${block.plan_id}`}>برنامه {faNumber(block.plan_id)}</Link> · {dateLabel(block.scheduled_date)} · {block.evidence_required ? "تکمیل با بررسی شواهد فعالیت" : "تکمیل با تأیید در برنامه"}</p>
        </div>
        <div className="actions"><Link className="button" href={block.action_href}>باز کردن فعالیت</Link>
          {!active && <button className="button primary" type="button" disabled={busy} onClick={() => onStart(block.id)}>شروع جلسه</button>}
        </div>
      </article>)}</div>}
    {truncated && <p className="muted small">{faNumber(total)} بلوک وجود دارد؛ بخشی از فهرست نمایش داده شده است.</p>}
  </section>;
}

export default function StudyCenter() {
  const router = useRouter();
  const [today, setToday] = useState<StudyToday | null>(null);
  const [overview, setOverview] = useState<Overview | null>(null);
  const [authenticated, setAuthenticated] = useState<boolean | null>(null);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [pending, setPending] = useState<PendingStart | null>(null);
  const inFlight = useRef(false);

  const loadToday = useCallback(async () => {
    const response = await api<StudyToday>("/study/today/", {}, true);
    setToday(response);
    if (response.active_session) {
      sessionStorage.removeItem(pendingKey);
      setPending(null);
    }
    return response;
  }, []);
  const refreshRecommendations = useCallback(async () => (await loadToday()).recommendations, [loadToday]);

  useEffect(() => {
    const signedIn = hasToken();
    setAuthenticated(signedIn);
    setPending(pendingStart());
    if (!signedIn) { setLoading(false); return; }
    void loadToday().catch((reason: unknown) => {
      if (reason instanceof ApiError && reason.status === 401) { setAuthenticated(false); return; }
      setError(reason instanceof Error ? reason.message : "اطلاعات امروز دریافت نشد.");
    }).finally(() => setLoading(false));
    void api<Overview>("/study/overview/", {}, true).then(setOverview).catch(() => {});
  }, [loadToday]);

  async function start(blockId: number) {
    if (inFlight.current) return;
    const existing = pendingStart();
    if (existing && existing.blockId !== blockId) {
      setPending(existing);
      setError("درخواست جلسه قبلی هنوز تعیین تکلیف نشده است. ابتدا همان درخواست را بازیابی کن.");
      return;
    }
    const request = existing ?? { blockId, eventId: crypto.randomUUID() };
    sessionStorage.setItem(pendingKey, JSON.stringify(request));
    setPending(request);
    inFlight.current = true;
    setBusy(true);
    setError("");
    try {
      const result = await api<{ session: StudySession; created: boolean }>("/study/sessions/", {
        method: "POST", body: JSON.stringify({ primary_block_id: request.blockId, client_event_id: request.eventId }),
      }, true);
      sessionStorage.removeItem(pendingKey);
      setPending(null);
      router.push(`/study/session/${result.session.id}`);
    } catch (reason: unknown) {
      if (reason instanceof ApiError && reason.status === 401) { setAuthenticated(false); return; }
      if (reason instanceof ApiError && reason.status === 409 && reason.code === "study_session_active") {
        try {
          const current = await api<{ session: StudySession | null }>("/study/sessions/current/", {}, true);
          if (current.session) {
            sessionStorage.removeItem(pendingKey);
            setPending(null);
            router.push(`/study/session/${current.session.id}`);
            return;
          }
        } catch { /* Retain the same token for recovery. */ }
      }
      if (reason instanceof ApiError && ["study_session_block_unavailable", "study_block_not_found", "study_session_event_conflict", "study_session_invalid"].includes(reason.code ?? "")) {
        sessionStorage.removeItem(pendingKey);
        setPending(null);
        void loadToday().catch(() => {});
      }
      setError(reason instanceof ApiError && reason.code === "study_session_block_unavailable"
        ? "این بلوک یا محتوایش دیگر برای شروع جلسه در دسترس نیست. فهرست امروز را تازه کن."
        : reason instanceof Error ? `${reason.message} اگر پاسخ شروع را دریافت نکردی، با همان درخواست دوباره تلاش کن.` : "شروع جلسه نامشخص است؛ درخواست قبلی را بازیابی کن.");
    } finally { inFlight.current = false; setBusy(false); }
  }

  if (authenticated === null || loading) return <div className="card" role="status">در حال آماده‌کردن مرکز مطالعه...</div>;
  if (!authenticated) return <div className="stack"><div className="card"><h2>برای دیدن برنامه امروز وارد شو</h2><p>جلسه‌ها و برنامهٔ شخصی پس از ورود نمایش داده می‌شوند.</p><Link href="/login" className="button primary">ورود به حساب</Link></div><DailyChallengeCard /><DSMStudyPanel /></div>;
  if (!today) return <div className="card error-state" role="alert"><p>{error || "اطلاعات امروز آماده نیست."}</p><button className="button" onClick={() => void loadToday().catch((reason: unknown) => setError(reason instanceof Error ? reason.message : "بارگذاری انجام نشد."))}>تلاش دوباره</button></div>;

  const next = today.next_action;
  const active = today.active_session;
  const nextBlock = [...today.overdue_blocks.items, ...today.today_blocks.items].find((block) => block.id === next.block_id);
  const nextPlan = today.active_plans.items.find((plan) => plan.id === next.plan_id);
  const recommendation = today.recommendations.items.find((item) => item.key === next.recommendation_key);
  const heroTitle = active?.primary_block?.snapshot_title || nextBlock?.snapshot_title || recommendation?.title ||
    (next.kind === "resume_case" ? "ادامه تمرین مورد بالینی" : next.kind === "srs_review" ? "مرور فلش‌کارت‌ها" : next.action.label);

  return <div className="stack today-center">
    {error && <div className="study-plan-inline-error" role="alert">{error}</div>}
    {pending && !active && <div className="card today-recovery" role="status"><p>درخواست شروع جلسه قبلی هنوز پاسخ قطعی ندارد. بازیابی با همان شناسه انجام می‌شود.</p><button className="button primary" disabled={busy} onClick={() => void start(pending.blockId)}>بازیابی شروع جلسه</button></div>}
    <section className="card today-hero" aria-labelledby="today-next-title">
      <div><div className="meta">قدم بعدی · {dateLabel(today.local_date)} · {today.timezone}</div><h2 id="today-next-title">{heroTitle}</h2>
        <p>{reasons[next.reason_code] ?? "پیشنهاد بعدی بر پایهٔ وضعیت فعلی مطالعه است."}</p>
        {nextPlan && <p className="muted small">برنامه: <Link href={`/study/plans/${nextPlan.id}`}>{nextPlan.name}</Link>{nextBlock ? ` · ${kindLabels[nextBlock.block_kind] ?? nextBlock.block_kind}` : ""}</p>}
      </div>
      <div className="actions">{active ? <Link className="button primary" href={`/study/session/${active.id}`}>ادامه جلسه مطالعه</Link> : <>
        {next.can_start_session && next.block_id && !pending ? <button className="button primary" type="button" disabled={busy} onClick={() => void start(next.block_id!)}>شروع جلسه متمرکز</button> : null}
        <Link className={next.can_start_session ? "button" : "button primary"} href={next.action.href}>{next.action.label}</Link>
      </>}</div>
    </section>

    <section className="card today-capacity" aria-label="ظرفیت امروز"><div className="today-section-head"><h2>ظرفیت امروز</h2><span className="muted">{dateLabel(today.local_date)}</span></div>
      <div className="today-capacity-grid">{([
        ["ظرفیت در دسترس", today.capacity.available_minutes], ["زمان‌بندی‌شده", today.capacity.scheduled_minutes],
        ["بلوک تکمیل‌شده", today.capacity.completed_minutes], ["باقی‌مانده", today.capacity.remaining_minutes],
        ["بیش از ظرفیت", today.capacity.over_capacity_minutes],
      ] as const).map(([label, value]) => <div key={label}><span>{label}</span><strong>{faNumber(value)} <small>دقیقه</small></strong></div>)}</div>
      {today.capacity.available_minutes === 0 && <p className="muted small">برای امروز ظرفیت ثبت نشده است. ظرفیت برنامه‌ها را بررسی کن.</p>}
      {today.capacity.over_capacity_minutes > 0 && <p className="muted small">زمان‌بندی امروز از ظرفیت ثبت‌شده بیشتر است؛ در صورت نیاز برنامه‌ها را بازبینی کن.</p>}
    </section>

    <div className="today-work-grid">
      <BlockList title="بلوک‌های امروز" blocks={today.today_blocks.items} total={today.today_blocks.total} truncated={today.today_blocks.truncated} onStart={(id) => void start(id)} busy={busy || !!pending} active={!!active} />
      <BlockList title="عقب‌افتاده‌ها" blocks={today.overdue_blocks.items} total={today.overdue_blocks.total} truncated={today.overdue_blocks.truncated} onStart={(id) => void start(id)} busy={busy || !!pending} active={!!active} />
    </div>

    <section className="card today-plans"><div className="today-section-head"><h2>برنامه‌های فعال</h2><Link href="/study/plans">همه برنامه‌ها</Link></div>
      {today.active_plans.total === 0 ? <p className="muted">برنامهٔ فعالی نداری. اگر برنامه‌ای پیش‌نویس است، آن را در بخش برنامه‌ها بازبینی و فعال کن.</p> :
        <div className="today-plan-list">{today.active_plans.items.map((plan) => <div key={plan.id}><Link href={`/study/plans/${plan.id}`}><strong>{plan.name}</strong></Link><span>{plan.plan_kind === "exam" ? "برنامه امتحان" : "مطالعه عمومی"} · ظرفیت امروز {faNumber(plan.today_available_minutes)} دقیقه</span>
          {plan.plan_kind === "exam" && plan.target_date && <span>تاریخ هدف: {dateLabel(plan.target_date)} · {plan.days_remaining === 0 ? "امروز" : plan.days_remaining! > 0 ? `${faNumber(plan.days_remaining!)} روز مانده` : `${faNumber(-plan.days_remaining!)} روز گذشته`}</span>}
          {plan.schedule_stale && <span>زمان‌بندی نیاز به بازبینی دارد.</span>}{plan.generation_version === 0 && <span>هنوز زمان‌بندی ساخته نشده است.</span>}</div>)}</div>}
      {today.active_plans.truncated && <p className="muted small">{faNumber(today.active_plans.total)} برنامه فعال وجود دارد؛ بخشی نمایش داده شده است.</p>}
      <div className="actions"><Link className="button" href="/study/plans/new">برنامه جدید</Link></div>
    </section>

    <section className="card today-review"><h2>مرور فلش‌کارت</h2><p>{faNumber(today.review.due)} موعدرسیده · {faNumber(today.review.overdue)} عقب‌افتاده · {faNumber(today.review.new)} کارت جدید</p><Link className="button" href="/flashcards">رفتن به مرور</Link></section>
    <StudyRecommendationsV2 dueCards={today.review.due} initialData={today.recommendations} onRefresh={refreshRecommendations} />
    {overview && <div className="study-stats"><div className="study-stat"><strong>{faNumber(overview.streak)}</strong><small>روز زنجیرهٔ مطالعه</small></div><div className="study-stat"><strong>{faNumber(today.review.due)}</strong><small>فلش‌کارت موعدرسیده</small></div><div className="study-stat"><strong>{faNumber(overview.concepts.studied)}</strong><small>مفهوم مطالعه‌شده</small></div></div>}
    {overview && <div className="grid-2"><section className="card"><h2>فعالیت ۴۲ روز اخیر</h2><StudyHeatmap days={overview.heatmap} /></section><section className="card"><h2>تمرین تحریف‌های شناختی</h2><p className="muted">{faNumber(overview.distortion_practice.attempts)} پاسخ ثبت‌شده · دقت {faNumber(overview.distortion_practice.accuracy)}٪</p><Link className="button" href="/cognitive-distortions#practice">ادامه تمرین</Link></section></div>}
    <div id="daily-challenge"><DailyChallengeCard /></div>
    <DSMStudyPanel />
  </div>;
}
