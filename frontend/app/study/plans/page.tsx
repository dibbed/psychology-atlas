"use client";

import Link from "next/link";
import { useCallback, useEffect, useMemo, useState } from "react";
import { ApiError, api } from "@/lib/api";
import { hasToken } from "@/lib/auth";
import { faNumber } from "@/lib/fa";
import type { StudyPlan, StudyPlanListResponse, UserStudySettings } from "@/lib/types";

const PAGE_PATH = "/study/plans";

const statusLabel: Record<StudyPlan["status"], string> = {
  draft: "پیش‌نویس",
  active: "فعال",
  paused: "متوقف",
  completed: "تکمیل‌شده",
  archived: "بایگانی",
};

const kindLabel: Record<StudyPlan["plan_kind"], string> = {
  general: "مطالعه عمومی",
  exam: "برنامه امتحان",
};

const weekdayLabels = ["دوشنبه", "سه‌شنبه", "چهارشنبه", "پنج‌شنبه", "جمعه", "شنبه", "یکشنبه"];

function redirectToLogin() {
  location.href = `/login?next=${encodeURIComponent(PAGE_PATH)}`;
}

function formatDate(value: string | null) {
  if (!value) return "بدون تاریخ هدف";
  const parts = value.split("-").map(Number);
  if (parts.length !== 3 || parts.some(Number.isNaN)) return value;
  return new Intl.DateTimeFormat("fa-IR", {
    year: "numeric",
    month: "short",
    day: "numeric",
    timeZone: "UTC",
  }).format(new Date(Date.UTC(parts[0], parts[1] - 1, parts[2])));
}

function activeMinutesLabel(plan: StudyPlan) {
  const activeDays = plan.availability.filter((row) => row.available_minutes > 0).length;
  return `${faNumber(plan.weekly_available_minutes)} دقیقه در ${faNumber(activeDays)} روز`;
}

export default function StudyPlansPage() {
  const [plans, setPlans] = useState<StudyPlan[]>([]);
  const [settings, setSettings] = useState<UserStudySettings | null>(null);
  const [settingsDraft, setSettingsDraft] = useState<UserStudySettings | null>(null);
  const [loading, setLoading] = useState(true);
  const [savingSettings, setSavingSettings] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");

  const load = useCallback(async () => {
    if (!hasToken()) {
      redirectToLogin();
      return;
    }
    setLoading(true);
    setError("");
    try {
      const [plansResponse, settingsResponse] = await Promise.all([
        api<StudyPlanListResponse>("/study/plans/", {}, true),
        api<UserStudySettings>("/study/settings/", {}, true),
      ]);
      setPlans(plansResponse.plans);
      setSettings(settingsResponse);
      setSettingsDraft(settingsResponse);
    } catch (reason: unknown) {
      if (reason instanceof ApiError && reason.status === 401) {
        redirectToLogin();
        return;
      }
      setError(reason instanceof Error ? reason.message : "اطلاعات برنامه‌های مطالعه دریافت نشد.");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  const visiblePlans = useMemo(
    () => plans.filter((plan) => plan.status !== "archived"),
    [plans],
  );
  const archivedPlans = useMemo(
    () => plans.filter((plan) => plan.status === "archived"),
    [plans],
  );

  async function saveSettings() {
    if (!settingsDraft) return;
    setSavingSettings(true);
    setError("");
    setNotice("");
    try {
      const saved = await api<UserStudySettings>(
        "/study/settings/",
        {
          method: "PUT",
          body: JSON.stringify({
            study_timezone: settingsDraft.study_timezone,
            default_daily_minutes: settingsDraft.default_daily_minutes,
            default_session_minutes: settingsDraft.default_session_minutes,
            week_starts_on: settingsDraft.week_starts_on,
          }),
        },
        true,
      );
      setSettings(saved);
      setSettingsDraft(saved);
      setNotice("تنظیمات پیش‌فرض مطالعه ذخیره شد.");
    } catch (reason: unknown) {
      if (reason instanceof ApiError && reason.status === 401) {
        redirectToLogin();
        return;
      }
      setError(reason instanceof Error ? reason.message : "ذخیره تنظیمات انجام نشد.");
    } finally {
      setSavingSettings(false);
    }
  }

  function useDeviceTimezone() {
    if (!settingsDraft) return;
    const detected = Intl.DateTimeFormat().resolvedOptions().timeZone;
    if (detected) {
      setSettingsDraft({ ...settingsDraft, study_timezone: detected });
    }
  }

  if (loading) {
    return (
      <main className="shell page">
        <section className="study-plan-loading" aria-busy="true" aria-live="polite">
          <span className="sr-only">در حال بارگذاری برنامه‌های مطالعه...</span>
          <div className="study-plan-loading-line wide" />
          <div className="study-plan-loading-line" />
          <div className="study-plan-loading-grid">
            <span /><span /><span />
          </div>
        </section>
      </main>
    );
  }

  if (error && !settingsDraft && plans.length === 0) {
    return (
      <main className="shell page">
        <section className="card error-state study-plan-state-card" role="alert">
          <div className="meta">Study Planning</div>
          <h1>برنامه‌های مطالعه بارگذاری نشد</h1>
          <p>{error}</p>
          <div className="actions">
            <button className="button primary" type="button" onClick={() => void load()}>تلاش دوباره</button>
            <Link className="button" href="/study">مرکز مطالعه</Link>
          </div>
        </section>
      </main>
    );
  }

  return (
    <main className="shell page stack study-plan-page">
      <header className="study-plan-head">
        <div>
          <div className="meta">Study Planning · v0.8.1</div>
          <h1 className="section-title">قصد مطالعه‌ات را قبل از زمان‌بندی مشخص کن.</h1>
          <p className="section-copy">
            این بخش هدف، محدوده و ظرفیت هفتگی را نگه می‌دارد. زمان‌بندی خودکار و بلوک‌های روزانه در مرحله بعد ساخته می‌شوند.
          </p>
        </div>
        <div className="actions">
          <Link className="button primary" href="/study/plans/new">برنامه جدید</Link>
          <Link className="button" href="/study">مرکز مطالعه</Link>
        </div>
      </header>

      {notice && <div className="study-plan-notice" role="status">{notice}</div>}
      {error && <div className="study-plan-inline-error" role="alert">{error}</div>}

      {settingsDraft && (
        <section className="card study-settings-card" aria-labelledby="study-settings-title">
          <div className="study-plan-section-head">
            <div>
              <div className="meta">پیش‌فرض‌های شخصی</div>
              <h2 id="study-settings-title">تنظیمات مطالعه</h2>
              <p className="muted small">
                منطقه زمانی فقط برای برنامه‌ریزی مطالعه استفاده می‌شود و تاریخچه قدیمی یا چالش روزانه را بازنویسی نمی‌کند.
              </p>
            </div>
            {settings && (
              <span className="study-settings-summary">
                {faNumber(settings.default_daily_minutes)} دقیقه روزانه · {faNumber(settings.default_session_minutes)} دقیقه هر جلسه
              </span>
            )}
          </div>

          <div className="study-settings-grid">
            <label>
              <span>منطقه زمانی IANA</span>
              <input
                value={settingsDraft.study_timezone}
                onChange={(event) => setSettingsDraft({ ...settingsDraft, study_timezone: event.target.value })}
                dir="ltr"
                placeholder="Asia/Tehran"
              />
              <button className="study-inline-action" type="button" onClick={useDeviceTimezone}>
                استفاده از منطقه زمانی دستگاه
              </button>
            </label>
            <label>
              <span>ظرفیت پیش‌فرض روزانه</span>
              <div className="study-number-field">
                <input
                  type="number"
                  min={5}
                  max={720}
                  value={settingsDraft.default_daily_minutes}
                  onChange={(event) => setSettingsDraft({
                    ...settingsDraft,
                    default_daily_minutes: Number(event.target.value),
                  })}
                />
                <small>دقیقه</small>
              </div>
            </label>
            <label>
              <span>مدت پیش‌فرض هر جلسه</span>
              <div className="study-number-field">
                <input
                  type="number"
                  min={5}
                  max={240}
                  value={settingsDraft.default_session_minutes}
                  onChange={(event) => setSettingsDraft({
                    ...settingsDraft,
                    default_session_minutes: Number(event.target.value),
                  })}
                />
                <small>دقیقه</small>
              </div>
            </label>
            <label>
              <span>شروع هفته</span>
              <select
                value={settingsDraft.week_starts_on}
                onChange={(event) => setSettingsDraft({
                  ...settingsDraft,
                  week_starts_on: Number(event.target.value),
                })}
              >
                {weekdayLabels.map((label, index) => <option value={index} key={label}>{label}</option>)}
              </select>
            </label>
          </div>

          <div className="actions">
            <button
              className="button primary"
              type="button"
              disabled={savingSettings}
              onClick={() => void saveSettings()}
            >
              {savingSettings ? "در حال ذخیره..." : "ذخیره تنظیمات"}
            </button>
          </div>
        </section>
      )}

      <section className="study-plan-section" aria-labelledby="active-plans-title">
        <div className="study-plan-section-head">
          <div>
            <div className="meta">برنامه‌های من</div>
            <h2 id="active-plans-title">هدف‌ها و محدوده‌های مطالعه</h2>
          </div>
          <span className="muted small">{faNumber(visiblePlans.length)} برنامه باز</span>
        </div>

        {visiblePlans.length === 0 ? (
          <div className="card study-plan-empty">
            <div>
              <h3>هنوز برنامه‌ای نساخته‌ای.</h3>
              <p>یک هدف عمومی یا امتحان بساز، موضوع‌ها را انتخاب کن و ظرفیت هفتگی‌ات را مشخص کن.</p>
            </div>
            <Link className="button primary" href="/study/plans/new">ساخت اولین برنامه</Link>
          </div>
        ) : (
          <div className="study-plan-list">
            {visiblePlans.map((plan) => (
              <Link className="study-plan-row" href={`/study/plans/${plan.id}`} key={plan.id}>
                <div className="study-plan-row-main">
                  <div className="study-plan-row-title">
                    <span className={`study-plan-status ${plan.status}`}>{statusLabel[plan.status]}</span>
                    <strong>{plan.name}</strong>
                  </div>
                  <p>
                    {kindLabel[plan.plan_kind]} · شروع {formatDate(plan.start_date)}
                    {plan.target_date ? ` · هدف ${formatDate(plan.target_date)}` : ""}
                  </p>
                </div>
                <div className="study-plan-row-metrics">
                  <div><strong>{faNumber(plan.scopes.length)}</strong><span>موضوع</span></div>
                  <div><strong>{faNumber(plan.weekly_available_minutes)}</strong><span>دقیقه/هفته</span></div>
                </div>
                <div className="study-plan-row-tail">
                  <span>{activeMinutesLabel(plan)}</span>
                  <strong>مدیریت ←</strong>
                </div>
              </Link>
            ))}
          </div>
        )}
      </section>

      {archivedPlans.length > 0 && (
        <details className="card study-archived-plans">
          <summary>{faNumber(archivedPlans.length)} برنامه بایگانی‌شده</summary>
          <div className="study-plan-list compact">
            {archivedPlans.map((plan) => (
              <Link className="study-plan-row" href={`/study/plans/${plan.id}`} key={plan.id}>
                <div className="study-plan-row-main">
                  <div className="study-plan-row-title">
                    <span className="study-plan-status archived">بایگانی</span>
                    <strong>{plan.name}</strong>
                  </div>
                  <p>{kindLabel[plan.plan_kind]} · {faNumber(plan.scopes.length)} موضوع</p>
                </div>
                <strong className="study-plan-row-link">مشاهده ←</strong>
              </Link>
            ))}
          </div>
        </details>
      )}

      <aside className="study-plan-boundary">
        <strong>این مرحله چه چیزی را انجام نمی‌دهد؟</strong>
        <p>
          در v0.8.1 هیچ کارت فلش، Quiz، Case یا تاریخ مرور دوباره زمان‌بندی نمی‌شود. این صفحه فقط ورودی برنامه‌ریز آینده را به‌صورت امن و قابل ویرایش نگه می‌دارد.
        </p>
      </aside>
    </main>
  );
}
