"use client";

import { CmsError } from "@/lib/cms";
import { TerminologyPayload, governanceLabels } from "@/lib/cmsGovernance";
import GovernanceEvidenceForm from "./GovernanceEvidenceForm";
import { GovernanceField } from "./GovernanceForms";

export const terminologyFieldLabels: Record<string, string> = {
  name_en: "اصطلاح انگلیسی", name_fa: "پیشنهاد فارسی", term_kind: "کاربرد اصطلاح", alternatives: "گزینه‌های جایگزین؛ هر گزینه در یک خط",
  selection_note: "دلیل انتخاب و رفع ابهام", evidence: "منبع و نشانی اصطلاح", resource_version: "نسخهٔ دقیق هدف", reason: "دلیل ثبت پیشنهاد",
};

export default function TerminologyFields({ value, onChange, error, disabled, immutable }: {
  value: TerminologyPayload; onChange: (value: TerminologyPayload) => void; error?: unknown; disabled: boolean; immutable: boolean;
}) {
  return <fieldset className="cms-fieldset" disabled={disabled}><legend>پیشنهاد اصطلاح فارسی</legend>
    <p className="cms-notice">نام نمایشی و alias دامنه‌های معنایی جدا دارند. تأیید این پیشنهاد، تأیید علمی یا حقوقی و مجوز فرم ارزیابی ایجاد نمی‌کند.</p>
    {(["name_en", "name_fa", "term_kind", "alternatives", "selection_note"] as const).map(name => {
      const messages = error instanceof CmsError ? error.details.field_errors?.[name] : undefined;
      const props = { id: `terminology-${name}`, name, "aria-invalid": !!messages, "aria-describedby": messages ? `terminology-${name}-error` : undefined };
      return <GovernanceField key={name} name={name} prefix="terminology" label={terminologyFieldLabels[name]} error={error}>
        {name === "term_kind" ? <select {...props} disabled={immutable} value={value.term_kind} onChange={event => onChange({ ...value, term_kind: event.target.value as "display" | "alias" })}><option value="display">{governanceLabels.display}</option><option value="alias">{governanceLabels.alias}</option></select>
          : name === "alternatives" ? <textarea {...props} dir="rtl" rows={4} value={value.alternatives.join("\n")} onChange={event => onChange({ ...value, alternatives: event.target.value.split("\n") })} />
          : name === "selection_note" ? <textarea {...props} required dir="rtl" rows={5} maxLength={4000} value={value.selection_note} onChange={event => onChange({ ...value, selection_note: event.target.value })} />
          : <input {...props} required dir={name === "name_en" ? "ltr" : "rtl"} maxLength={500} value={value[name]} onChange={event => onChange({ ...value, [name]: event.target.value })} />}
      </GovernanceField>;
    })}
    <section className="cms-preview stack" aria-label="پیش‌نمایش راست‌به‌چپ اصطلاح پیشنهادی" dir="rtl"><p className="cms-badge">پیشنهاد فرم؛ منتشر نشده</p><h3>{value.name_fa || "اصطلاح فارسی"}</h3><p dir="ltr">{value.name_en || "English term"}</p><p>کاربرد: {governanceLabels[value.term_kind]}</p><p className="cms-prose">جایگزین‌ها: {value.alternatives.filter(term => term.trim()).join("، ") || "ثبت نشده"}</p></section>
    <GovernanceEvidenceForm binding={value} label="منبع اصطلاح و نشانی دقیق" prefix="terminology-evidence" value={value.evidence} disabled={disabled} onChange={evidence => onChange({ ...value, evidence })} />
  </fieldset>;
}
