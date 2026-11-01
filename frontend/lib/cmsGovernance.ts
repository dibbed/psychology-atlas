import { CmsError } from "./cms";

export type SourcePayload = {
  title: string; organization: string; citation: string; url: string; publication_year: number | null;
  source_type: string; authors: string[]; doi: string; pmid: string; verification_status: string;
  resource_version: string;
};
export const sourceBlank: SourcePayload = {
  title: "", organization: "", citation: "", url: "", publication_year: null, source_type: "", authors: [],
  doi: "", pmid: "", verification_status: "", resource_version: "",
};
export const sourceLabels: Record<keyof SourcePayload, string> = {
  title: "عنوان اصلی منبع", organization: "سازمان", citation: "ارجاع اصلی", url: "نشانی منبع", publication_year: "سال انتشار میلادی",
  source_type: "نوع منبع", authors: "نویسندگان؛ هر نام در یک خط", doi: "DOI", pmid: "PMID",
  verification_status: "وضعیت راستی‌آزمایی", resource_version: "نسخهٔ منبع",
};
export type SourceSummary = SourcePayload & { id: number; version: number; usage_count: number | null; impact_available: boolean | null; archived: boolean; provenance_versions: Record<string, string | number> };
export function sourcePayload(source: SourceSummary): SourcePayload {
  return Object.fromEntries(Object.keys(sourceBlank).map(key => [key, source[key as keyof SourcePayload]])) as SourcePayload;
}
export type SourceUsage = {
  key: string; model: string; id: number | string; field?: string; source_id: number; mutable: boolean; protected?: boolean;
  owners?: { model: string; id: number; review_status: string | null; is_active?: boolean }[];
  claim?: Record<string, unknown>; locator?: string; fields?: string[]; path?: string; paths?: string[]; retained?: boolean;
  evidence?: { source_id: number; locator: string; fields: string[] }[];
};
export type SourceSuccessor = { id: number; source_id: number; successor_id: number; operation: string; plan_id: string };
export type SourceImpact = {
  canonical: SourceUsage[]; review: SourceUsage[]; archives: SourceUsage[]; successors: SourceSuccessor[];
  counts: { canonical: number; review: number; archives: number; successors: number }; protection: { code: string; key: string; message: string }[];
};
export type SourceDetail = { source: SourceSummary; impact: SourceImpact; fingerprint: string; successors: SourceSuccessor[]; reason_codes: string[] };
export type SourceOperation = "create" | "update" | "archive" | "delete" | "merge" | "split" | "successor";
export type SourceMapping = { key: string; action: "retain" | "move"; target_id?: number };
export type SourceRequest = { operation: SourceOperation; source_id?: number; changes?: Partial<SourcePayload>; candidates?: number[]; field_choices?: Partial<Record<keyof SourcePayload, number>>; mapping?: SourceMapping[] };
export type SourcePlan = {
  id: string; schema_version: number; version: number; status: "preview" | "applied"; operation: SourceOperation; source_id: number | null;
  request: SourceRequest; fingerprint: string; created_at: string; preview: {
    normalization: Record<string, unknown>; comparisons: Record<string, unknown>[]; identity_conflicts: Record<string, unknown>[];
    mapping: SourceMapping[]; blockers: { code: string; key: string; message: string }[]; manual_plan: Record<string, unknown>[];
    counts: { moved: number; unchanged: number; blocked: number }; rereview: Record<string, unknown>[]; can_apply: boolean;
  }; receipt: { source_ids: number[]; counts: { moved: number; unchanged: number; blocked: number }; history_ids: number[]; successor_ids: number[] } | null;
};
export type SourceHistoryEntry = { id: number; source_id: number; version: number; plan_id: string; operation: SourceOperation; before: Partial<SourcePayload>; after: Partial<SourcePayload>; actor_ref: string; created_at: string };
export const sourceOperationLabels: Record<SourceOperation, string> = { create: "ثبت منبع", update: "ویرایش فراداده", archive: "بایگانی", delete: "حذف منبع بدون مصرف", merge: "ادغام منابع هم‌هویت", split: "تفکیک ادعاها به منابع", successor: "ثبت منبع جانشین" };
export function governanceBlocked(error: unknown) {
  return error instanceof CmsError && (error.status === 409 || error.status === 412 || error.code === "UNKNOWN_OUTCOME");
}

export type GovernanceKind = "rights" | "terminology";
export type GovernanceEvidence = { source_id?: number; artifact_id?: string; locator: string };
export type ResourceBinding = { resource_type: string; resource_id: number; domain: string; resource_version: string; resource_digest: string; name_en: string; name_fa: string };
export const governanceResources: Record<string, { domain: string; label: string }> = {
  source_reference: { domain: "source", label: "منبع" }, category: { domain: "core", label: "دسته‌بندی" }, disorder: { domain: "core", label: "اختلال" },
  symptom: { domain: "core", label: "نشانه" }, concept: { domain: "core", label: "مفهوم" }, dsm_record: { domain: "dsm", label: "رکورد DSM" },
  therapy: { domain: "therapy", label: "درمان" }, technique: { domain: "therapy", label: "تکنیک" }, psychologist: { domain: "history", label: "روان‌شناس" },
  theory: { domain: "history", label: "نظریه" }, timeline_event: { domain: "history", label: "رویداد تاریخی" }, clinical_case: { domain: "cases", label: "کیس بالینی" },
  flashcard: { domain: "learning", label: "فلش‌کارت" }, quiz: { domain: "learning", label: "آزمون آموزشی" },
  brain_anatomical_entity: { domain: "brain", label: "ساختار مغز" }, brain_network: { domain: "brain", label: "شبکهٔ مغز" },
  assessment_instrument: { domain: "assessment", label: "ابزار ارزیابی" }, assessment_version: { domain: "assessment", label: "نسخهٔ ارزیابی" },
  assessment_language_form: { domain: "assessment", label: "فرم زبانی ارزیابی" }, assessment_validation_study: { domain: "assessment", label: "مطالعهٔ اعتبارسنجی" },
  assessment_psychometric_evidence: { domain: "assessment", label: "شاهد روان‌سنجی" }, assessment_alias: { domain: "assessment", label: "نام جایگزین ارزیابی" },
  assessment_access: { domain: "assessment", label: "دسترسی ارزیابی" },
};
export const governanceLabels: Record<string, string> = {
  submitted: "ارسال‌شده", in_review: "در بررسی", approved: "تأیید نسخهٔ مشخص", rejected: "نیازمند اصلاح", revoked: "لغوشده",
  unknown: "نامشخص", allowed: "اجازهٔ استفاده", restricted: "محدود", conflict: "تعارض", expired: "منقضی", stale: "نسخه یا شواهد تغییر کرده",
  review_overdue: "موعد بازبینی گذشته", not_effective: "هنوز نافذ نشده", unreviewed: "بدون تصمیم معتبر", legacy: "میراث؛ بدون مجوز تازه",
  metadata: "فراداده", image: "تصویر", text: "متن", translation: "ترجمه", item: "آیتم", instruction: "دستور اجرا", questionnaire: "پرسشنامه", manual: "راهنما",
  public_display: "نمایش عمومی", digital: "استفادهٔ دیجیتال", commercial: "استفادهٔ تجاری", redistribution: "بازتوزیع", derivative: "اثر مشتق", owner_access: "دسترسی مالک", metadata_listing: "فهرست فراداده",
  public: "دسترسی عمومی", private: "دسترسی خصوصی", display: "نام نمایشی", alias: "نام جایگزین (alias)",
  CORRECTION_REQUIRED: "اصلاح یا انتخاب مستدل", LOCATOR_INVALID: "نشانی شاهد نامعتبر", EVIDENCE_INSUFFICIENT: "مدرک ناکافی", CLAIM_UNSUPPORTED: "ادعای بدون پشتوانه",
  RIGHTS_SCOPE_VERIFIED: "مدرک اجازهٔ استفاده برای همین دامنه بررسی شد", TERMINOLOGY_SELECTED: "اصطلاح همین نسخه با دلیل انتخاب شد",
  TWO_PERSON_REQUIRED: "سیاست دو نفره؛ مشارکت‌کننده نمی‌تواند بازبین باشد", SELF_REVIEW_ACK_REQUIRED: "مالک باید خودبازبینی را صریحاً تأیید کند",
  SOURCE_CHANGED: "منبع تغییر کرده؛ نسخهٔ تازه و بازبینی لازم است", POLICY_CHANGED: "سیاست بازبینی تغییر کرده", RESOURCE_CHANGED: "نسخهٔ منبع هدف تغییر کرده",
  RESOURCE_VERSION_CHANGED: "نسخهٔ هدف تغییر کرده؛ پیشنهاد تازه لازم است", DEPENDENCY_CHANGED: "منبع یا شواهد تغییر کرده؛ بازبینی تازه لازم است",
  EVIDENCE_MISSING: "مدرک ثبت‌شده در دسترس نیست", SOURCE_UNAVAILABLE: "منبع بایگانی یا حذف شده است", PAYLOAD_CHANGED: "پیشنهاد تغییر کرده است",
  RESOURCE_MISSING: "هدف دیگر در دسترس نیست", REVIEWER_UNAVAILABLE: "بازبین در دسترس نیست", REVIEWER_PERMISSION_CHANGED: "مجوز بازبین تغییر کرده است",
  REVIEWER_CHANGED: "تخصیص بازبین تغییر کرده است", DECISION_REQUIRED: "تصمیم معتبر برای این نسخه لازم است", APPROVAL_REQUIRED: "تأیید همین نسخه لازم است",
  RIGHTS_REVOKED: "اجازهٔ استفاده لغو شده", RIGHTS_EXPIRED: "مدت اجازهٔ استفاده پایان یافته", RIGHTS_REVIEW_OVERDUE: "موعد بازبینی حقوق گذشته", RIGHTS_NOT_EFFECTIVE: "اجازه هنوز نافذ نشده است",
};
export const governanceComputedStatuses = ["unknown", "allowed", "restricted", "conflict", "expired", "revoked", "stale", "not_effective", "review_overdue", "submitted", "in_review", "approved", "rejected"];
export type RightsPayload = {
  resource_type: string; resource_id: number; resource_version: string; evidence: GovernanceEvidence[]; reason: string;
  material: string; intended_use: string; status: "unknown" | "allowed" | "restricted" | "conflict";
  rightsholder: string; holder_identification: string; holder_evidence: GovernanceEvidence[]; public_access: string;
  reviewed_on: string | null; effective_on: string | null; expires_on: string | null; review_on: string | null;
  limitations: string; territory: string; conflict_note: string;
};
export type TerminologyPayload = {
  resource_type: string; resource_id: number; resource_version: string; evidence: GovernanceEvidence[]; reason: string;
  name_en: string; name_fa: string; term_kind: "display" | "alias"; alternatives: string[]; selection_note: string;
};
export type GovernanceRecordData = {
  id: string; kind: GovernanceKind; domain: string; resource_type: string; resource_id: number; resource_version: string;
  version: number; status: string; computed_status: string; payload: RightsPayload | TerminologyPayload; resource_digest: string;
  dependency_digest: string; assignee_id: number | null; policy_version: number; policy_mode: "solo_owner" | "two_person";
  blockers: string[]; eligible: boolean; preview?: { dir: "rtl"; name_en_dir: "ltr"; name_en: string; name_fa: string; term_kind: string; alternatives: string[] };
  candidate_conflicts?: { id: string; name_en?: string; name_fa?: string; resource_type?: string; resource_id?: number; term_kind?: string }[];
  candidate_conflicts_more?: boolean;
};
export type GovernanceDetail = { record: GovernanceRecordData; policy: { mode: "solo_owner" | "two_person"; version: number }; reason_codes: { approve: string[]; reject: string[]; revoke: string[] } };
export type GovernanceReviewer = { id: number; username: string; conflicts: string[] };
export const rightsBlank: RightsPayload = {
  resource_type: "", resource_id: 0, resource_version: "", evidence: [], reason: "CORRECTION_REQUIRED",
  material: "metadata", intended_use: "public_display", status: "unknown", rightsholder: "", holder_identification: "", holder_evidence: [],
  public_access: "unknown", reviewed_on: null, effective_on: null, expires_on: null, review_on: null, limitations: "", territory: "", conflict_note: "",
};
export const terminologyBlank: TerminologyPayload = {
  resource_type: "", resource_id: 0, resource_version: "", evidence: [], reason: "CORRECTION_REQUIRED", name_en: "", name_fa: "", term_kind: "display", alternatives: [], selection_note: "",
};
