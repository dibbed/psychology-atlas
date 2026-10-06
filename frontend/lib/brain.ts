import type { BrainAnatomyBrief, BrainKind, BrainLaterality } from "./types";

export const brainKinds: Record<BrainKind, string> = {
  whole_brain: "کل مغز", hemisphere: "نیمکره", lobe: "لوب",
  cortical_region: "ناحیهٔ قشری", subcortical_structure: "ساختار زیرقشری",
  region: "سایر نواحی", structure: "سایر ساختارها",
};
export const brainLateralities: Record<BrainLaterality, string> = {
  left: "چپ", right: "راست", midline: "خط میانی",
  bilateral: "دوطرفه یا بدون تفکیک سمت", not_established: "سمت تعیین نشده",
};
export function brainName(entity: BrainAnatomyBrief) {
  return entity.review_status === "reviewed" && entity.name_fa.trim() ? entity.name_fa : entity.name_en;
}
export function brainHref(values: URLSearchParams, changes: Record<string, string> = {}) {
  const query = new URLSearchParams(values);
  for (const [key, value] of Object.entries(changes)) {
    if (value) query.set(key, value);
    else query.delete(key);
  }
  return query.size ? `/brain?${query}` : "/brain";
}
