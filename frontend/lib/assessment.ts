import type { AssessmentAvailability, AssessmentFormKind, AssessmentIntendedUse, AssessmentLicense } from "./types";

export const assessmentFormKinds: Record<AssessmentFormKind, string> = {
  original: "فرم اصلی", revision: "ویرایش", short: "فرم کوتاه", unknown: "ویرایش تعیین نشده",
};
export const assessmentIntendedUses: Record<AssessmentIntendedUse, string> = {
  screening: "غربالگری", research: "اندازه‌گیری پژوهشی", severity: "اندازه‌گیری شدت",
  monitoring: "پایش تغییرات", diagnostic_support: "کمک به ارزیابی حرفه‌ای؛ بدون تشخیص مستقل",
};
export const assessmentAvailabilities: Record<AssessmentAvailability, string> = {
  unknown: "دسترسی تعیین نشده", owner_access: "دسترسی از طریق صاحب اثر", public_access: "دسترسی عمومی تأییدشده برای دامنهٔ ثبت‌شده",
};
export const assessmentLicenses: Record<AssessmentLicense, string> = {
  unknown: "مجوز استفاده احراز نشده", restricted: "محدودیت‌های صاحب اثر",
  public_domain: "اعلام مالکیت عمومی توسط صاحب اثر، فقط برای دامنهٔ ثبت‌شده",
  explicit_permission: "اجازهٔ صریح فقط برای دامنهٔ ثبت‌شده",
};

const queryKeys = ["q", "construct", "intended_use", "form_kind", "language", "access", "license", "page", "page_size"];

export function assessmentQuery(values: Record<string, string | string[] | undefined>) {
  const params = new URLSearchParams();
  const invalid = Object.keys(values).some(key => !queryKeys.includes(key) || Array.isArray(values[key]));
  for (const key of queryKeys) {
    const value = values[key];
    if (typeof value === "string" && value.trim()) params.set(key, value.trim());
  }
  return { params, invalid };
}

export function assessmentHref(values: URLSearchParams, changes: Record<string, string> = {}) {
  const query = new URLSearchParams(values);
  for (const [key, value] of Object.entries(changes)) {
    if (value) query.set(key, value);
    else query.delete(key);
  }
  return query.size ? `/assessments?${query}` : "/assessments";
}

// Only the page number comes from pagination URLs; links stay on the frontend route.
export function assessmentPaginationHref(values: URLSearchParams, apiHref: string) {
  const page = new URL(apiHref, "http://pagination.local").searchParams.get("page") || "1";
  return assessmentHref(values, { page });
}
