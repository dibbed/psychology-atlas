"use client";

import { CmsError } from "@/lib/cms";
import { RightsPayload, governanceLabels } from "@/lib/cmsGovernance";
import { GovernanceField } from "./GovernanceForms";
import GovernanceEvidenceForm from "./GovernanceEvidenceForm";

export const rightsFieldLabels: Record<string, string> = {
  material: "نوع ماده", intended_use: "استفادهٔ موردنظر", status: "وضعیت مجوز پیشنهادی", rightsholder: "مالک حقوق",
  holder_identification: "شرح شناسایی مالک حقوق", holder_evidence: "مدرک شناسایی مالک", public_access: "دسترسی به مدرک؛ مستقل از اجازهٔ استفاده",
  reviewed_on: "تاریخ بررسی (میلادی)", effective_on: "تاریخ آغاز اعتبار (میلادی)", expires_on: "تاریخ انقضا (میلادی؛ اختیاری)",
  review_on: "موعد بازبینی بعدی (میلادی؛ اختیاری)", limitations: "محدودیت‌های اجازهٔ استفاده", territory: "قلمرو؛ فقط اگر مرتبط است", conflict_note: "شرح تعارض",
  resource_version: "نسخهٔ دقیق هدف", evidence: "مدرک حقوق", reason: "دلیل ثبت پیشنهاد",
};
const options: Record<string, string[]> = {
  material: ["metadata", "image", "text", "translation", "item", "instruction", "questionnaire", "manual"],
  intended_use: ["public_display", "digital", "commercial", "redistribution", "derivative", "translation", "owner_access", "metadata_listing"],
  status: ["unknown", "allowed", "restricted", "conflict"], public_access: ["unknown", "public", "private"],
};

export default function RightsFields({ value, onChange, error, disabled, immutable }: {
  value: RightsPayload; onChange: (value: RightsPayload) => void; error?: unknown; disabled: boolean; immutable: boolean;
}) {
  const fields = ["material", "intended_use", "status", "rightsholder", "holder_identification", "public_access", "reviewed_on", "effective_on", "expires_on", "review_on", "limitations", "territory", "conflict_note"] as const;
  return <fieldset className="cms-fieldset" disabled={disabled}><legend>دامنه و مدرک حقوق</legend>
    <p className="cms-notice">«نامشخص» یک مقدار معتبر است. دسترسی عمومی، مجوز دیجیتال، تجاری، بازتوزیع یا ترجمه ایجاد نمی‌کند. تصمیم فقط برای همین هدف، نسخه، ماده و استفاده معتبر است.</p>
    {fields.map(name => {
      const messages = error instanceof CmsError ? error.details.field_errors?.[name] : undefined;
      const props = { id: `rights-${name}`, name, "aria-invalid": !!messages, "aria-describedby": messages ? `rights-${name}-error` : undefined };
      return <GovernanceField key={name} prefix="rights" name={name} label={rightsFieldLabels[name]} error={error}>
        {options[name] ? <select {...props} value={value[name] ?? ""} disabled={immutable && ["material", "intended_use"].includes(name)} onChange={event => onChange({ ...value, [name]: event.target.value })}>{options[name].map(item => <option key={item} value={item}>{governanceLabels[item] || item}</option>)}</select>
          : name.endsWith("_on") ? <input {...props} type="date" dir="ltr" required={value.status === "allowed" && ["reviewed_on", "effective_on"].includes(name)} value={value[name] || ""} onChange={event => onChange({ ...value, [name]: event.target.value || null })} />
          : ["limitations", "conflict_note", "holder_identification"].includes(name) ? <textarea {...props} rows={4} dir="auto" required={name === "conflict_note" ? value.status === "conflict" : value.status === "allowed"} maxLength={name === "holder_identification" ? 1000 : 4000} value={value[name] || ""} onChange={event => onChange({ ...value, [name]: event.target.value })} />
          : <input {...props} dir="auto" required={name === "rightsholder" && value.status === "allowed"} maxLength={name === "territory" ? 255 : 1000} value={value[name] || ""} onChange={event => onChange({ ...value, [name]: event.target.value })} />}
      </GovernanceField>;
    })}
    <GovernanceEvidenceForm binding={value} label="مدرک شناسایی مالک حقوق" prefix="rights-holder_evidence" value={value.holder_evidence} onChange={holder_evidence => onChange({ ...value, holder_evidence })} disabled={disabled} />
    <GovernanceEvidenceForm binding={value} label="مدرک دامنهٔ حقوق و اجازهٔ استفاده" prefix="rights-evidence" value={value.evidence} onChange={evidence => onChange({ ...value, evidence })} disabled={disabled} />
  </fieldset>;
}
