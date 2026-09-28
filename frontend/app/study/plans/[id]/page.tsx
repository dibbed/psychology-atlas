"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useCallback, useEffect, useMemo, useState } from "react";
import { ApiError, api } from "@/lib/api";
import { hasToken } from "@/lib/auth";
import { faNumber } from "@/lib/fa";
import type {
  StudyBlock,
  StudyBlockKind,
  StudyBlockStatus,
  StudyGenerationResponse,
  StudyGenerationSummary,
  StudyPlan,
  StudyPlanAvailability,
  StudyPlanScope,
  StudyScheduleResponse,
  StudyScopeCatalogItem,
  StudyScopeCatalogResponse,
  StudyScopeTargetType,
} from "@/lib/types";

const weekdayLabels = ["دوشنبه", "سه‌شنبه", "چهارشنبه", "پنج‌شنبه", "جمعه", "شنبه", "یکشنبه"];

const statusLabel: Record<StudyPlan["status"], string> = {
  draft: "پیش‌نویس",
  active: "فعال",
  paused: "متوقف",
  completed: "تکمیل‌شده",
  archived: "بایگانی",
};

const blockKindLabel: Record<StudyBlockKind, string> = {
  flashcard_review: "مرور فلش‌کارت",
  concept_review: "مرور مفهوم",
  disorder_review: "مرور اختلال",
  therapy_reading: "مطالعه درمان",
  theory_reading: "مطالعه نظریه",
  psychologist_reading: "مطالعه روان‌شناس",
  timeline_review: "مرور خط زمانی",
  quiz_practice: "تمرین آزمون",
  case_practice: "تمرین کیس",
  distortion_practice: "تمرین تحریف شناختی",
  notes_review: "مرور یادداشت",
  daily_challenge_optional: "چالش روزانه اختیاری",
};

const blockStatusLabel: Record<StudyBlockStatus, string> = {
  pending: "در انتظار",
  in_progress: "در حال انجام",
  completed: "تکمیل‌شده",
  skipped: "ردشده",
  superseded: "جایگزین‌شده",
};

const targetTypeOptions: { value: StudyScopeTargetType; label: string }[] = [
  { value: "disorder", label: "اختلال" },
  { value: "concept", label: "مفهوم" },
  { value: "therapy", label: "درمان" },
  { value: "theory", label: "نظریه" },
  { value: "psychologist", label: "روان‌شناس" },
  { value: "timeline_event", label: "رویداد تاریخی" },
  { value: "quiz", label: "آزمون" },
  { value: "clinical_case", label: "کیس آموزشی" },
];

const catalogCategoryLabels: Record<string, string> = {
  Behavioral: "رفتاری",
  Clinical: "بالینی",
  Cognitive: "شناختی",
  Emotional: "هیجانی",
  General: "عمومی",
  Interpersonal: "بین‌فردی",
  Treatment: "درمان",
};

function redirectToLogin(path: string) {
  location.href = `/login?next=${encodeURIComponent(path)}`;
}

function normalizeAvailability(rows: StudyPlanAvailability[]) {
  const byDay = new Map(rows.map((row) => [row.weekday, row.available_minutes]));
  return Array.from({ length: 7 }, (_, weekday) => ({
    weekday,
    available_minutes: byDay.get(weekday) ?? 0,
  }));
}

function planError(reason: unknown, fallback: string) {
  return reason instanceof Error ? reason.message : fallback;
}

function targetTypeLabel(type: StudyScopeTargetType) {
  return targetTypeOptions.find((item) => item.value === type)?.label ?? type;
}

function displayDate(value: string) {
  const parts = value.split("-").map(Number);
  if (parts.length !== 3 || parts.some(Number.isNaN)) return value;
  return new Intl.DateTimeFormat("fa-IR", {
    year: "numeric",
    month: "short",
    day: "numeric",
    weekday: "short",
    timeZone: "UTC",
  }).format(new Date(Date.UTC(parts[0], parts[1] - 1, parts[2])));
}

function generationSummary(value: StudyPlan["last_generation_summary"]) {
  return "scheduler_version" in value ? value as StudyGenerationSummary : null;
}

export default function StudyPlanDetailPage() {
  const params = useParams<{ id: string }>();
  const planId = Number(params.id);
  const pagePath = `/study/plans/${params.id}`;

  const [plan, setPlan] = useState<StudyPlan | null>(null);
  const [core, setCore] = useState({
    name: "",
    plan_kind: "general" as StudyPlan["plan_kind"],
    start_date: "",
    target_date: "",
    notes: "",
  });
  const [availability, setAvailability] = useState<StudyPlanAvailability[]>([]);
  const [scopes, setScopes] = useState<StudyPlanScope[]>([]);
  const [targetType, setTargetType] = useState<StudyScopeTargetType>("concept");
  const [scopeQuery, setScopeQuery] = useState("");
  const [catalog, setCatalog] = useState<StudyScopeCatalogItem[]>([]);
  const [catalogLoading, setCatalogLoading] = useState(false);
  const [schedule, setSchedule] = useState<StudyScheduleResponse | null>(null);
  const [scheduleLoading, setScheduleLoading] = useState(false);
  const [rescheduleDates, setRescheduleDates] = useState<Record<number, string>>({});
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState("");
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");

  const configurationEditable = plan?.status === "draft" || plan?.status === "paused";
  const coreEditable = plan != null && !["archived", "completed"].includes(plan.status);

  const syncPlan = useCallback((next: StudyPlan) => {
    setPlan(next);
    setCore({
      name: next.name,
      plan_kind: next.plan_kind,
      start_date: next.start_date,
      target_date: next.target_date ?? "",
      notes: next.notes,
    });
    setAvailability(normalizeAvailability(next.availability));
    setScopes(next.scopes);
  }, []);

  const loadPlan = useCallback(async () => {
    if (!Number.isInteger(planId) || planId <= 0) {
      setError("شناسه برنامه معتبر نیست.");
      setLoading(false);
      return;
    }
    if (!hasToken()) {
      redirectToLogin(pagePath);
      return;
    }
    setLoading(true);
    setError("");
    try {
      const [planResponse, scheduleResponse] = await Promise.all([
        api<StudyPlan>(`/study/plans/${planId}/`, {}, true),
        api<StudyScheduleResponse>(`/study/plans/${planId}/schedule/`, {}, true),
      ]);
      syncPlan(planResponse);
      setSchedule(scheduleResponse);
      setRescheduleDates(
        Object.fromEntries(
          scheduleResponse.days.flatMap((day) =>
            day.blocks.map((block) => [block.id, block.scheduled_date]),
          ),
        ),
      );
    } catch (reason: unknown) {
      if (reason instanceof ApiError && reason.status === 401) {
        redirectToLogin(pagePath);
        return;
      }
      setError(planError(reason, "برنامه مطالعه دریافت نشد."));
    } finally {
      setLoading(false);
    }
  }, [pagePath, planId, syncPlan]);

  useEffect(() => {
    void loadPlan();
  }, [loadPlan]);

  const loadSchedule = useCallback(async () => {
    if (!Number.isInteger(planId) || planId <= 0 || !hasToken()) return;
    setScheduleLoading(true);
    try {
      const response = await api<StudyScheduleResponse>(
        `/study/plans/${planId}/schedule/`,
        {},
        true,
      );
      setSchedule(response);
      setRescheduleDates(
        Object.fromEntries(
          response.days.flatMap((day) =>
            day.blocks.map((block) => [block.id, block.scheduled_date]),
          ),
        ),
      );
    } catch (reason: unknown) {
      if (reason instanceof ApiError && reason.status === 401) {
        redirectToLogin(pagePath);
        return;
      }
      setError(planError(reason, "برنامه زمان‌بندی دریافت نشد."));
    } finally {
      setScheduleLoading(false);
    }
  }, [pagePath, planId]);

  useEffect(() => {
    if (!hasToken() || !configurationEditable) {
      setCatalog([]);
      return;
    }
    const controller = new AbortController();
    const timeout = window.setTimeout(async () => {
      setCatalogLoading(true);
      try {
        const query = new URLSearchParams({
          target_type: targetType,
          q: scopeQuery.trim(),
          limit: "20",
        });
        const response = await api<StudyScopeCatalogResponse>(
          `/study/scope-catalog/?${query.toString()}`,
          { signal: controller.signal },
          true,
        );
        setCatalog(response.items);
      } catch (reason: unknown) {
        if (reason instanceof DOMException && reason.name === "AbortError") return;
        if (reason instanceof ApiError && reason.status === 401) {
          redirectToLogin(pagePath);
          return;
        }
        setCatalog([]);
      } finally {
        if (!controller.signal.aborted) setCatalogLoading(false);
      }
    }, 220);

    return () => {
      window.clearTimeout(timeout);
      controller.abort();
    };
  }, [configurationEditable, pagePath, scopeQuery, targetType]);

  const weeklyMinutes = useMemo(
    () => availability.reduce((sum, row) => sum + (Number.isFinite(row.available_minutes) ? row.available_minutes : 0), 0),
    [availability],
  );

  const selectedKeys = useMemo(
    () => new Set(scopes.map((scope) => `${scope.target_type}:${scope.target_slug}`)),
    [scopes],
  );

  const latestGeneration = useMemo(
    () => plan ? generationSummary(plan.last_generation_summary) : null,
    [plan],
  );

  const scheduleBlocks = useMemo(
    () => schedule?.days.flatMap((day) => day.blocks) ?? [],
    [schedule],
  );

  async function saveCore() {
    if (!plan || !coreEditable) return;
    setBusy("core");
    setError("");
    setNotice("");
    try {
      const response = await api<StudyPlan>(
        `/study/plans/${plan.id}/`,
        {
          method: "PATCH",
          body: JSON.stringify({
            name: core.name,
            plan_kind: core.plan_kind,
            start_date: core.start_date,
            target_date: core.plan_kind === "exam" ? core.target_date || null : null,
            notes: core.notes,
          }),
        },
        true,
      );
      syncPlan(response);
      setNotice("مشخصات برنامه ذخیره شد.");
    } catch (reason: unknown) {
      setError(planError(reason, "ذخیره مشخصات برنامه انجام نشد."));
    } finally {
      setBusy("");
    }
  }

  async function saveAvailability() {
    if (!plan || !configurationEditable) return;
    setBusy("availability");
    setError("");
    setNotice("");
    try {
      const response = await api<StudyPlan>(
        `/study/plans/${plan.id}/availability/`,
        {
          method: "PUT",
          body: JSON.stringify({ availability }),
        },
        true,
      );
      syncPlan(response);
      setNotice("ظرفیت هفتگی ذخیره شد.");
    } catch (reason: unknown) {
      setError(planError(reason, "ذخیره ظرفیت هفتگی انجام نشد."));
    } finally {
      setBusy("");
    }
  }

  async function saveScopes() {
    if (!plan || !configurationEditable) return;
    setBusy("scopes");
    setError("");
    setNotice("");
    try {
      const response = await api<StudyPlan>(
        `/study/plans/${plan.id}/scopes/`,
        {
          method: "PUT",
          body: JSON.stringify({
            scopes: scopes.map((scope, index) => ({
              target_type: scope.target_type,
              target_slug: scope.target_slug,
              priority: scope.priority,
              include_practice: scope.include_practice,
              sort_order: index,
            })),
          }),
        },
        true,
      );
      syncPlan(response);
      setNotice("محدوده مطالعه ذخیره شد.");
    } catch (reason: unknown) {
      setError(planError(reason, "ذخیره محدوده مطالعه انجام نشد."));
    } finally {
      setBusy("");
    }
  }

  async function transition(action: "activate" | "pause" | "archive") {
    if (!plan) return;
    const confirmed = action !== "archive" || window.confirm("این برنامه بایگانی شود؟ داده‌های آن حذف نمی‌شوند.");
    if (!confirmed) return;

    setBusy(action);
    setError("");
    setNotice("");
    try {
      const response = await api<StudyPlan>(
        `/study/plans/${plan.id}/${action}/`,
        { method: "POST", body: JSON.stringify({}) },
        true,
      );
      syncPlan(response);
      setNotice(
        action === "activate"
          ? "برنامه فعال شد."
          : action === "pause"
            ? "برنامه متوقف شد و حالا می‌توانی پیکربندی را ویرایش کنی."
            : "برنامه بایگانی شد.",
      );
    } catch (reason: unknown) {
      setError(planError(reason, "تغییر وضعیت برنامه انجام نشد."));
    } finally {
      setBusy("");
    }
  }

  async function generateSchedule() {
    if (!plan) return;
    const confirmed = plan.generation_version === 0 || window.confirm(
      "زمان‌بندی دوباره ساخته شود؟ فقط بلوک‌های generated، pending، آینده و بدون قفل جایگزین می‌شوند؛ تاریخچه و جابه‌جایی‌های قفل‌شده حفظ می‌شوند.",
    );
    if (!confirmed) return;
    setBusy("generate");
    setError("");
    setNotice("");
    try {
      const response = await api<StudyGenerationResponse>(
        `/study/plans/${plan.id}/generate/`,
        { method: "POST", body: JSON.stringify({}) },
        true,
      );
      syncPlan(response.plan);
      await loadSchedule();
      setNotice(
        response.generation.no_op
          ? "ورودی برنامه تغییری نکرده بود؛ زمان‌بندی قبلی بدون بازنویسی حفظ شد."
          : `نسخه ${faNumber(response.generation.generation_version)} زمان‌بندی ساخته شد.`,
      );
    } catch (reason: unknown) {
      if (reason instanceof ApiError && reason.status === 401) {
        redirectToLogin(pagePath);
        return;
      }
      setError(planError(reason, "تولید زمان‌بندی انجام نشد."));
    } finally {
      setBusy("");
    }
  }

  async function rescheduleBlock(block: StudyBlock) {
    const scheduledDate = rescheduleDates[block.id] ?? block.scheduled_date;
    if (scheduledDate === block.scheduled_date && block.locked_by_user) return;
    setBusy(`block-${block.id}-move`);
    setError("");
    setNotice("");
    try {
      await api<StudyBlock>(
        `/study/blocks/${block.id}/reschedule/`,
        {
          method: "POST",
          body: JSON.stringify({ scheduled_date: scheduledDate }),
        },
        true,
      );
      await Promise.all([loadPlan(), loadSchedule()]);
      setNotice("بلوک جابه‌جا و در برابر regenerate قفل شد.");
    } catch (reason: unknown) {
      setError(planError(reason, "جابه‌جایی بلوک انجام نشد."));
    } finally {
      setBusy("");
    }
  }

  async function blockAction(block: StudyBlock, action: "skip" | "complete" | "unlock") {
    setBusy(`block-${block.id}-${action}`);
    setError("");
    setNotice("");
    try {
      await api<StudyBlock>(
        `/study/blocks/${block.id}/${action}/`,
        { method: "POST", body: JSON.stringify({}) },
        true,
      );
      await Promise.all([loadPlan(), loadSchedule()]);
      setNotice(
        action === "skip"
          ? "بلوک رد شد و در regenerate دوباره ساخته نمی‌شود."
          : action === "unlock"
            ? "قفل دستی برداشته شد؛ regenerate بعدی می‌تواند این بلوک را دوباره بچیند."
            : block.evidence_required
              ? "فعالیت واقعی مرتبط پیدا شد و بلوک تکمیل شد."
              : "بلوک به‌عنوان انجام‌شده ثبت شد؛ این فقط پایبندی به برنامه است، نه سنجش تسلط.",
      );
    } catch (reason: unknown) {
      setError(planError(
        reason,
        action === "complete"
          ? "برای این بلوک هنوز شواهد واقعی لازم پیدا نشد."
          : "تغییر بلوک انجام نشد.",
      ));
    } finally {
      setBusy("");
    }
  }

  function addScope(item: StudyScopeCatalogItem) {
    const key = `${item.target_type}:${item.target_slug}`;
    if (selectedKeys.has(key)) return;
    setScopes((current) => [
      ...current,
      {
        id: -Date.now(),
        target_type: item.target_type,
        target_slug: item.target_slug,
        title: item.title,
        priority: 3,
        include_practice: true,
        sort_order: current.length,
        is_active: true,
      },
    ]);
  }

  function updateScope(index: number, patch: Partial<StudyPlanScope>) {
    setScopes((current) => current.map((scope, itemIndex) => (
      itemIndex === index ? { ...scope, ...patch } : scope
    )));
  }

  if (loading) {
    return (
      <main className="shell page">
        <section className="study-plan-loading" aria-live="polite" aria-busy="true">
          <span className="sr-only">در حال بارگذاری برنامه مطالعه...</span>
          <div className="study-plan-loading-line wide" />
          <div className="study-plan-loading-line" />
          <div className="study-plan-loading-grid"><span /><span /><span /></div>
        </section>
      </main>
    );
  }

  if (!plan) {
    return (
      <main className="shell page">
        <section className="card error-state study-plan-state-card" role="alert">
          <div className="meta">برنامه‌ریزی مطالعه</div>
          <h1>برنامه پیدا نشد</h1>
          <p>{error || "این برنامه وجود ندارد یا متعلق به حساب فعلی نیست."}</p>
          <Link className="button primary" href="/study/plans">برنامه‌های من</Link>
        </section>
      </main>
    );
  }

  return (
    <main className="shell page stack study-plan-page">
      <header className="study-plan-head">
        <div>
          <Link className="study-plan-back" href="/study/plans">← برنامه‌های مطالعه</Link>
          <div className="study-plan-heading-line">
            <span className={`study-plan-status ${plan.status}`}>{statusLabel[plan.status]}</span>
            <span className="meta">{plan.plan_kind === "exam" ? "آمادگی امتحان" : "مطالعه عمومی"}</span>
          </div>
          <h1 className="section-title">{plan.name}</h1>
          <p className="section-copy">
            {plan.status === "active"
              ? "برنامه فعال است. برای تغییر محدوده یا ظرفیت، اول آن را متوقف کن."
              : plan.status === "archived"
                ? "این برنامه فقط برای سابقه نگه داشته شده و قابل ویرایش یا فعال‌سازی نیست."
                : "هدف، موضوع‌ها و ظرفیت را تنظیم کن؛ سپس زمان‌بندی روزانه را بساز و بازبینی کن."}
          </p>
        </div>
        <div className="actions">
          {!["archived", "completed"].includes(plan.status) && (
            <button className="button primary" type="button" disabled={!!busy || scheduleLoading} onClick={() => void generateSchedule()}>
              {busy === "generate"
                ? "در حال زمان‌بندی..."
                : plan.generation_version > 0
                  ? "بازچینی زمان‌بندی"
                  : "ساخت زمان‌بندی"}
            </button>
          )}
          {plan.status === "active" && (
            <button className="button" type="button" disabled={!!busy} onClick={() => void transition("pause")}>
              {busy === "pause" ? "در حال توقف..." : "توقف برنامه"}
            </button>
          )}
          {(plan.status === "draft" || plan.status === "paused") && (
            <button className="button primary" type="button" disabled={!!busy} onClick={() => void transition("activate")}>
              {busy === "activate" ? "در حال فعال‌سازی..." : "فعال‌سازی"}
            </button>
          )}
          {plan.status !== "archived" && (
            <button className="button danger-ghost" type="button" disabled={!!busy} onClick={() => void transition("archive")}>
              {busy === "archive" ? "در حال بایگانی..." : "بایگانی"}
            </button>
          )}
        </div>
      </header>

      {notice && <div className="study-plan-notice" role="status">{notice}</div>}
      {error && <div className="study-plan-inline-error" role="alert">{error}</div>}

      <section className="study-plan-summary-strip" aria-label="خلاصه برنامه">
        <div><span>موضوع‌ها</span><strong>{faNumber(scopes.length)}</strong></div>
        <div><span>ظرفیت هفتگی</span><strong>{faNumber(weeklyMinutes)} دقیقه</strong></div>
        <div><span>روزهای فعال</span><strong>{faNumber(availability.filter((row) => row.available_minutes > 0).length)}</strong></div>
        <div>
          <span>نسخه زمان‌بندی</span>
          <strong>{faNumber(plan.generation_version)}</strong>
          <small>{plan.last_generated_at ? "آخرین تولید ثبت شده" : "هنوز تولید نشده"}</small>
        </div>
      </section>

      <section className="card study-plan-editor-section">
        <div className="study-plan-section-head">
          <div>
            <div className="meta">۱ · هدف</div>
            <h2>مشخصات برنامه</h2>
          </div>
          {!coreEditable && <span className="study-readonly-badge">فقط خواندنی</span>}
        </div>
        <div className="study-form-grid">
          <label className="study-form-field span-2">
            <span>نام برنامه</span>
            <input
              value={core.name}
              maxLength={180}
              disabled={!coreEditable}
              onChange={(event) => setCore({ ...core, name: event.target.value })}
            />
          </label>
          <label className="study-form-field">
            <span>نوع برنامه</span>
            <select
              value={core.plan_kind}
              disabled={!coreEditable}
              onChange={(event) => setCore({ ...core, plan_kind: event.target.value as StudyPlan["plan_kind"] })}
            >
              <option value="general">مطالعه عمومی</option>
              <option value="exam">آمادگی امتحان</option>
            </select>
          </label>
          <label className="study-form-field">
            <span>تاریخ شروع</span>
            <input
              type="date"
              value={core.start_date}
              disabled={!coreEditable}
              onChange={(event) => setCore({ ...core, start_date: event.target.value })}
            />
          </label>
          {core.plan_kind === "exam" && (
            <label className="study-form-field">
              <span>تاریخ هدف</span>
              <input
                type="date"
                min={core.start_date}
                value={core.target_date}
                disabled={!coreEditable}
                onChange={(event) => setCore({ ...core, target_date: event.target.value })}
              />
            </label>
          )}
          <label className="study-form-field span-2">
            <span>یادداشت</span>
            <textarea
              rows={4}
              maxLength={12000}
              value={core.notes}
              disabled={!coreEditable}
              onChange={(event) => setCore({ ...core, notes: event.target.value })}
            />
          </label>
        </div>
        {coreEditable && (
          <div className="actions">
            <button className="button primary" type="button" disabled={!!busy} onClick={() => void saveCore()}>
              {busy === "core" ? "در حال ذخیره..." : "ذخیره مشخصات"}
            </button>
          </div>
        )}
      </section>

      <section className="card study-plan-editor-section">
        <div className="study-plan-section-head">
          <div>
            <div className="meta">۲ · ظرفیت</div>
            <h2>زمان آزاد هفتگی</h2>
            <p className="muted small">صفر یعنی آن روز برای این برنامه در دسترس نیست.</p>
          </div>
          {!configurationEditable && <span className="study-readonly-badge">برای ویرایش، برنامه را متوقف کن</span>}
        </div>

        <div className="study-availability-grid">
          {availability.map((row, index) => (
            <label key={row.weekday}>
              <span>{weekdayLabels[row.weekday]}</span>
              <div className="study-number-field">
                <input
                  type="number"
                  min={0}
                  max={1440}
                  step={5}
                  disabled={!configurationEditable}
                  value={row.available_minutes}
                  onChange={(event) => setAvailability((current) => current.map((item, itemIndex) => (
                    itemIndex === index
                      ? { ...item, available_minutes: Number(event.target.value) }
                      : item
                  )))}
                />
                <small>دقیقه</small>
              </div>
            </label>
          ))}
        </div>

        <div className="study-plan-config-foot">
          <span>مجموع هفتگی: <strong>{faNumber(weeklyMinutes)} دقیقه</strong></span>
          {configurationEditable && (
            <button className="button primary" type="button" disabled={!!busy} onClick={() => void saveAvailability()}>
              {busy === "availability" ? "در حال ذخیره..." : "ذخیره ظرفیت"}
            </button>
          )}
        </div>
      </section>

      <section className="card study-plan-editor-section">
        <div className="study-plan-section-head">
          <div>
            <div className="meta">۳ · محدوده</div>
            <h2>چه چیزهایی داخل این برنامه هستند؟</h2>
            <p className="muted small">
              اولویت فقط برای برنامه‌ریز آینده است و به معنی تسلط، اهمیت علمی یا احتمال موفقیت در امتحان نیست.
            </p>
          </div>
          {!configurationEditable && <span className="study-readonly-badge">برای ویرایش، برنامه را متوقف کن</span>}
        </div>

        {configurationEditable && (
          <div className="study-scope-picker">
            <div className="study-scope-search">
              <label>
                <span>نوع محتوا</span>
                <select value={targetType} onChange={(event) => setTargetType(event.target.value as StudyScopeTargetType)}>
                  {targetTypeOptions.map((option) => (
                    <option value={option.value} key={option.value}>{option.label}</option>
                  ))}
                </select>
              </label>
              <label className="wide">
                <span>جست‌وجو</span>
                <input
                  value={scopeQuery}
                  onChange={(event) => setScopeQuery(event.target.value)}
                  placeholder="نام فارسی، انگلیسی یا شناسه محتوا"
                />
              </label>
            </div>

            <div className="study-scope-results" aria-busy={catalogLoading}>
              {catalogLoading ? (
                <p className="muted small">در حال جست‌وجو...</p>
              ) : catalog.length === 0 ? (
                <p className="muted small">مورد فعالی برای این جست‌وجو پیدا نشد.</p>
              ) : catalog.map((item) => {
                const selected = selectedKeys.has(`${item.target_type}:${item.target_slug}`);
                return (
                  <button
                    className={`study-scope-result ${selected ? "selected" : ""}`}
                    type="button"
                    disabled={selected}
                    onClick={() => addScope(item)}
                    key={`${item.target_type}:${item.target_slug}`}
                  >
                    <span>
                      <strong>{item.title}</strong>
                      <small>{catalogCategoryLabels[item.subtitle] || item.subtitle || targetTypeLabel(item.target_type)}</small>
                    </span>
                    <b>{selected ? "اضافه شده" : "+ افزودن"}</b>
                  </button>
                );
              })}
            </div>
          </div>
        )}

        <div className="study-selected-scopes">
          {scopes.length === 0 ? (
            <div className="study-scope-empty">هنوز موضوعی به این برنامه اضافه نشده است.</div>
          ) : scopes.map((scope, index) => (
            <article className={`study-selected-scope ${!scope.is_active ? "inactive" : ""}`} key={`${scope.target_type}:${scope.target_slug}`}>
              <div className="study-selected-scope-title">
                <span>{targetTypeLabel(scope.target_type)}</span>
                <strong>{scope.title}</strong>
                {!scope.is_active && <small>محتوای فعلی غیرفعال است</small>}
              </div>
              <label>
                <span>اولویت</span>
                <select
                  value={scope.priority}
                  disabled={!configurationEditable}
                  onChange={(event) => updateScope(index, { priority: Number(event.target.value) })}
                >
                  <option value={1}>۱ · پایین</option>
                  <option value={2}>۲</option>
                  <option value={3}>۳ · عادی</option>
                  <option value={4}>۴</option>
                  <option value={5}>۵ · بالا</option>
                </select>
              </label>
              <label className="study-check-field">
                <input
                  type="checkbox"
                  checked={scope.include_practice}
                  disabled={!configurationEditable}
                  onChange={(event) => updateScope(index, { include_practice: event.target.checked })}
                />
                <span>تمرین مرتبط مجاز باشد</span>
              </label>
              {configurationEditable && (
                <button
                  className="study-scope-remove"
                  type="button"
                  onClick={() => setScopes((current) => current.filter((_, itemIndex) => itemIndex !== index))}
                >
                  حذف
                </button>
              )}
            </article>
          ))}
        </div>

        {configurationEditable && (
          <div className="study-plan-config-foot">
            <span>{faNumber(scopes.length)} موضوع انتخاب شده</span>
            <button className="button primary" type="button" disabled={!!busy} onClick={() => void saveScopes()}>
              {busy === "scopes" ? "در حال ذخیره..." : "ذخیره محدوده"}
            </button>
          </div>
        )}
      </section>

      <section className="card study-plan-editor-section study-schedule-section">
        <div className="study-plan-section-head">
          <div>
            <div className="meta">۴ · زمان‌بندی قطعی</div>
            <h2>بلوک‌های مطالعه</h2>
            <p className="muted small">
              بلوک‌ها فقط برنامهٔ پیشنهادی برای زمان مطالعه‌اند. زمان‌ها تخمینی هستند و تکمیل بلوک به معنی تسلط یا آمادگی امتحان نیست.
            </p>
          </div>
          <div className="actions">
            {scheduleLoading && <span className="study-readonly-badge">در حال تازه‌سازی...</span>}
            {!["archived", "completed"].includes(plan.status) && (
              <button className="button primary" type="button" disabled={!!busy || scheduleLoading} onClick={() => void generateSchedule()}>
                {busy === "generate"
                  ? "در حال زمان‌بندی..."
                  : plan.generation_version > 0
                    ? "بازچینی"
                    : "ساخت زمان‌بندی"}
              </button>
            )}
          </div>
        </div>

        {plan.schedule_stale && plan.generation_version > 0 && (
          <div className="study-schedule-warning" role="status">
            <strong>برنامه پس از آخرین زمان‌بندی تغییر کرده است.</strong>
            <p>زمان‌بندی قبلی برای حفظ سابقه نمایش داده می‌شود. برای اعمال موضوع‌ها، ظرفیت یا تاریخ‌های جدید، آن را بازچینی کن.</p>
          </div>
        )}

        {latestGeneration ? (
          <>
            <div className="study-generation-metrics">
              <div>
                <span>نسخه</span>
                <strong>{faNumber(latestGeneration.generation_version)}</strong>
              </div>
              <div>
                <span>ظرفیت بازه</span>
                <strong>{faNumber(latestGeneration.available_minutes)} دقیقه</strong>
              </div>
              <div>
                <span>زمان‌بندی‌شده</span>
                <strong>{faNumber(latestGeneration.scheduled_minutes)} دقیقه</strong>
              </div>
              <div>
                <span>حفظ‌شده</span>
                <strong>{faNumber(latestGeneration.preserved_minutes)} دقیقه</strong>
              </div>
              <div>
                <span>خارج از ظرفیت</span>
                <strong>{faNumber(latestGeneration.capacity_shortfall_minutes)} دقیقه</strong>
              </div>
            </div>

            <div className="study-generation-meta">
              <span>
                بازه: <b>{displayDate(latestGeneration.schedule_start)}</b> تا <b>{displayDate(latestGeneration.schedule_end)}</b>
              </span>
              <span>{faNumber(latestGeneration.scheduled_blocks)} بلوک جدید</span>
              <span>{faNumber(latestGeneration.preserved_blocks)} بلوک حفظ‌شده</span>
              {latestGeneration.superseded_blocks > 0 && (
                <span>{faNumber(latestGeneration.superseded_blocks)} بلوک قدیمی جایگزین شد</span>
              )}
            </div>

            {latestGeneration.capacity_shortfall_minutes > 0 && (
              <div className="study-schedule-warning" role="status">
                <strong>ظرفیت این بازه برای همه کارها کافی نیست.</strong>
                <p>
                  {faNumber(latestGeneration.capacity_shortfall_minutes)} دقیقه از کارهای پیشنهادی خارج از تقویم مانده‌اند. زمان‌بندی از ظرفیت روزانه یا تاریخ هدف عبور نکرده است.
                </p>
                {latestGeneration.backlog.length > 0 && (
                  <div className="study-backlog-list">
                    {latestGeneration.backlog.slice(0, 8).map((item) => (
                      <span key={item.key}>
                        {item.title} · {faNumber(item.estimated_minutes)} دقیقه
                      </span>
                    ))}
                  </div>
                )}
              </div>
            )}

            {latestGeneration.unavailable_scopes.length > 0 && (
              <div className="study-schedule-warning muted-warning">
                <strong>بخشی از موضوع‌های برنامه فعلاً قابل زمان‌بندی نیست.</strong>
                <p>محتوای غیرفعال جایگزین یا حدس زده نشده است.</p>
                <div className="study-backlog-list">
                  {latestGeneration.unavailable_scopes.map((item) => (
                    <span key={item.scope_id}>{item.title || item.target_slug || "موضوع نامعتبر"}</span>
                  ))}
                </div>
              </div>
            )}
          </>
        ) : (
          <div className="study-schedule-empty">
            <strong>هنوز بلوک مطالعه‌ای ساخته نشده است.</strong>
            <p>بعد از تنظیم موضوع‌ها و ظرفیت، «ساخت زمان‌بندی» را بزن. بازچینی، سابقه و بلوک‌های دستی، قفل‌شده یا انجام‌شده را حفظ می‌کند.</p>
          </div>
        )}

        {schedule && schedule.summary.cross_plan_overcapacity.length > 0 && (
          <div className="study-schedule-warning muted-warning">
            <strong>فشار هم‌زمان چند برنامه</strong>
            <p>
              این هشدار فقط مجموع بلوک‌های برنامه‌های فعال را با ظرفیت روزانه پیش‌فرض مقایسه می‌کند؛ امتیاز آمادگی یا پیش‌بینی موفقیت نیست.
            </p>
            <div className="study-backlog-list">
              {schedule.summary.cross_plan_overcapacity.slice(0, 8).map((row) => (
                <span key={row.date}>
                  {displayDate(row.date)} · {faNumber(row.scheduled_minutes)} / {faNumber(row.default_daily_minutes)} دقیقه
                </span>
              ))}
            </div>
          </div>
        )}

        {scheduleBlocks.length > 0 ? (
          <div className="study-schedule-days">
            {schedule?.days.map((day) => (
              <section className="study-schedule-day" key={day.date}>
                <header>
                  <div>
                    <h3>{displayDate(day.date)}</h3>
                  </div>
                  <strong>
                    {faNumber(day.blocks.reduce((sum, block) => sum + block.estimated_minutes, 0))} دقیقه
                  </strong>
                </header>

                <div className="study-block-list">
                  {day.blocks.map((block) => (
                    <article className={`study-block-row ${block.status} ${block.locked_by_user ? "locked" : ""}`} key={block.id}>
                      <div className="study-block-main">
                        <div className="study-block-title-line">
                          <span className={`study-block-status ${block.status}`}>{blockStatusLabel[block.status]}</span>
                          <span className="study-block-kind">{blockKindLabel[block.block_kind]}</span>
                          {block.locked_by_user && <span className="study-block-lock">قفل دستی</span>}
                        </div>
                        <strong>{block.snapshot_title}</strong>
                        {block.snapshot_subtitle && <p>{block.snapshot_subtitle}</p>}
                        <small>
                          {faNumber(block.estimated_minutes)} دقیقه · نوبت زمان‌بندی {faNumber(block.generation_version)}
                          {block.evidence_required ? " · تکمیل با شواهد موتور اصلی" : " · تکمیل با تأیید کاربر"}
                        </small>
                      </div>

                      <div className="study-block-actions">
                        <Link className="button" href={block.action_href}>
                          {block.evidence_required ? "انجام فعالیت" : "باز کردن محتوا"}
                        </Link>

                        {block.status === "pending" && !["archived", "completed"].includes(plan.status) && (
                          <>
                            <div className="study-block-move">
                              <input
                                aria-label={`تاریخ جدید برای ${block.snapshot_title}`}
                                type="date"
                                min={plan.start_date}
                                max={plan.target_date ?? undefined}
                                value={rescheduleDates[block.id] ?? block.scheduled_date}
                                onChange={(event) => setRescheduleDates((current) => ({
                                  ...current,
                                  [block.id]: event.target.value,
                                }))}
                              />
                              <button
                                className="button"
                                type="button"
                                disabled={!!busy}
                                onClick={() => void rescheduleBlock(block)}
                              >
                                {busy === `block-${block.id}-move` ? "..." : "ثبت تاریخ"}
                              </button>
                            </div>

                            {block.locked_by_user && block.origin === "generated" && (
                              <button
                                className="button"
                                type="button"
                                disabled={!!busy}
                                onClick={() => void blockAction(block, "unlock")}
                              >
                                {busy === `block-${block.id}-unlock` ? "..." : "آزاد کردن قفل"}
                              </button>
                            )}

                            <button
                              className="button"
                              type="button"
                              disabled={!!busy}
                              onClick={() => void blockAction(block, "complete")}
                            >
                              {busy === `block-${block.id}-complete`
                                ? "در حال بررسی..."
                                : block.evidence_required
                                  ? "بررسی تکمیل"
                                  : "ثبت انجام"}
                            </button>

                            <button
                              className="button danger-ghost"
                              type="button"
                              disabled={!!busy}
                              onClick={() => void blockAction(block, "skip")}
                            >
                              {busy === `block-${block.id}-skip` ? "..." : "رد کردن"}
                            </button>
                          </>
                        )}
                      </div>
                    </article>
                  ))}
                </div>
              </section>
            ))}
          </div>
        ) : latestGeneration ? (
          <div className="study-schedule-empty">
            <strong>در این بازه بلوک فعالی وجود ندارد.</strong>
            <p>ممکن است ظرفیت روزها صفر باشد، موضوع‌ها غیرفعال باشند، یا همهٔ کارهای پیشنهادی قبلاً انجام یا رد شده باشند. خلاصهٔ بالا وضعیت را نشان می‌دهد.</p>
          </div>
        ) : null}
      </section>

      <aside className="study-plan-boundary">
        <strong>دربارهٔ این برنامه</strong>
        <p>
          بلوک مطالعه فقط زمان پیشنهادی و سابقهٔ انجام آن را ثبت می‌کند. وضعیت مرور فلش‌کارت، نتیجهٔ آزمون و نتیجهٔ کیس در بخش‌های خودشان ثبت می‌شوند. زمان‌بندی آمادگی امتحان را پیش‌بینی نمی‌کند و پیشنهادهای مطالعه فعالیت تازه‌ای را خودکار ایجاد نمی‌کنند.
        </p>
      </aside>
    </main>
  );
}
