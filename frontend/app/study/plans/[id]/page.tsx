"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useCallback, useEffect, useMemo, useState } from "react";
import { ApiError, api } from "@/lib/api";
import { hasToken } from "@/lib/auth";
import { faNumber } from "@/lib/fa";
import type {
  StudyPlan,
  StudyPlanAvailability,
  StudyPlanScope,
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
      const response = await api<StudyPlan>(`/study/plans/${planId}/`, {}, true);
      syncPlan(response);
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
          <div className="meta">Study Planning</div>
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
            <span className="meta">{plan.plan_kind === "exam" ? "Exam plan" : "General study"}</span>
          </div>
          <h1 className="section-title">{plan.name}</h1>
          <p className="section-copy">
            {plan.status === "active"
              ? "برنامه فعال است. برای تغییر محدوده یا ظرفیت، اول آن را متوقف کن."
              : plan.status === "archived"
                ? "این برنامه فقط برای سابقه نگه داشته شده و قابل ویرایش یا فعال‌سازی نیست."
                : "مشخصات، موضوع‌ها و ظرفیت هفتگی را تنظیم کن. این نسخه هنوز بلوک روزانه تولید نمی‌کند."}
          </p>
        </div>
        <div className="actions">
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
        <div><span>نسخه تولید</span><strong>{faNumber(plan.generation_version)}</strong><small>هنوز زمان‌بندی نشده</small></div>
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
                      <small>{item.subtitle || targetTypeLabel(item.target_type)}</small>
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

      <aside className="study-plan-boundary">
        <strong>مرز v0.8.1</strong>
        <p>
          generation_version این برنامه هنوز صفر است. فعال‌سازی در این نسخه فقط یعنی برنامه برای مرحله زمان‌بندی آماده است؛ هیچ StudyBlock، due date فلش‌کارت یا نتیجه Quiz/Case در این صفحه ساخته یا تغییر داده نمی‌شود.
        </p>
      </aside>
    </main>
  );
}
