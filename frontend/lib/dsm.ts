import type { DSMDisplayType } from "./types";

export const DSM_TYPE_LABELS: Record<DSMDisplayType, string> = {
  diagnosis: "تشخیص رسمی",
  structural: "ساختار / عنوان",
  clinical_attention: "کانون توجه بالینی",
  research: "شرط پژوهشی",
  alternative_model: "مدل جایگزین",
  specifier: "مشخص‌کننده",
  reference: "ارجاع ساختاری",
  code: "کد اضافی",
  other: "سایر",
};

export function dsmTypeLabel(value: DSMDisplayType) {
  return DSM_TYPE_LABELS[value] || value;
}

export function faNumber(value: number) {
  return value.toLocaleString("fa-IR");
}

export function textValue(value: unknown): string {
  if (value == null) return "";
  if (typeof value === "string") return value;
  if (typeof value === "number" || typeof value === "boolean") return String(value);
  return JSON.stringify(value, null, 2);
}
