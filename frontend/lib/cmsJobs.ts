import { cms, CmsError, CmsMe } from "./cms";

export type ArtifactKind = "research_json" | "dsm_json" | "assessment_json" | "brain_json" | "research_request_json" | "research_export_json" | "evidence_json" | "learning_json" | "learning_export_json" | "privacy_request_json" | "privacy_export_json";
export type LearningKind = "quiz" | "flashcard" | "daily" | "distortions";
export const learningKindLabels: Record<LearningKind, string> = {quiz:"آزمون",flashcard:"فلش‌کارت",daily:"چالش روزانه",distortions:"تمرین خطاهای شناختی"};
export const learningEditorPaths: Record<LearningKind, string> = {quiz:"learning-quizzes",flashcard:"learning-flashcards",daily:"learning-practice",distortions:"learning-practice"};
export type AdminArtifact = {
  id: string; kind: ArtifactKind; domain: string; resource_type: string; resource_id: number | null;
  resource_version: string; filename: string; sha256: string; size: number;
  state: "quarantine" | "ready" | "rejected" | "revoked" | "expired"; version: number;
  expires_at: string; purged_at: string | null; cleanup_supported?: boolean; validation_code: string; created_at: string;
};
export type AdminJob = {
  id: string; kind: "research_intake" | "research_export" | "artifact_cleanup" | "learning_import" | "learning_export" | "privacy_export"; status: "queued" | "running" | "succeeded" | "failed" | "cancelled" | "reconciling";
  version: number; attempt: number; progress_done: number; progress_total: number | null;
  error_code: string; artifact_id: string; output_artifact_id: string | null; retry_available: boolean; cancel_requested: boolean;
  result: { dataset_id?: number; records?: number; duplicate?: boolean; artifact_id?: string; cleaned?: boolean;
    items?:number;created?:{kind:LearningKind;resource_id:number}[] };
  created_at: string; updated_at: string;
};
export type ResearchDataset = {
  id: number; dataset_name: string; dataset_version: string; source_filename: string;
  sha256: string; records: number; intake_complete: boolean; brain_staging: boolean; created_at: string;
};
export type ResearchMapping = { canonical_key?: string; name_en?: string; name_fa?: string; source_ids?: number[] };
export type ResearchAction = "map" | "reject" | "defer" | "stage";
export type ResearchDecision = {
  id: number; sequence: number; action: ResearchAction; mapping: ResearchMapping; reason: string;
  actor_ref: string; created_at: string;
};
export type ResearchRecord = {
  id: number; dataset_id: number; section: string; external_id: string; name_en: string; name_fa: string;
  version: number; decision: ResearchDecision | null; staging_state: ResearchAction | "unmapped";
  canonical_promotion: false;
};
export type ResearchRaw = { payload: unknown };
export type Snapshot<T> = { data: T; etag: string | null };

export const artifactKindLabels: Record<ArtifactKind, string> = {
  research_json: "دادهٔ پژوهشی JSON", dsm_json: "دادهٔ DSM به صورت JSON",
  brain_json: "دیتاست مغز JSON (پژوهش خصوصی)",
  research_request_json: "درخواست ثابت خروجی پژوهشی", research_export_json: "خروجی پژوهشی خصوصی JSON",
  assessment_json: "فرادادهٔ ارزیابی JSON", evidence_json: "مدرک JSON؛ بدون گواهی علمی یا حقوقی",
  learning_json: "بستهٔ خصوصی محتوای آموزشی", learning_export_json: "خروجی خصوصی محتوای آموزشی",
  privacy_request_json:"درخواست خصوصی صاحب داده", privacy_export_json:"خروجی خصوصی اطلاعات شخصی",
};
export const artifactStateLabels: Record<AdminArtifact["state"], string> = {
  quarantine: "قرنطینه؛ هنوز اعتبارسنجی نشده", ready: "قالب معتبر؛ آمادهٔ استفادهٔ مجاز",
  rejected: "اعتبارسنجی ناموفق", revoked: "دسترسی لغو شده", expired: "منقضی شده",
};
export const jobStatusLabels: Record<AdminJob["status"], string> = {
  queued: "در صف", running: "در حال پردازش", succeeded: "پایان‌یافته", failed: "ناموفق",
  cancelled: "لغوشده", reconciling: "در حال تطبیق نتیجهٔ قبلی",
};
export const jobKindLabels: Record<AdminJob["kind"], string> = {
  research_intake: "ورود پژوهش", research_export: "خروجی کنترل‌شدهٔ پژوهش", artifact_cleanup: "پاکسازی فایل منقضی بدون وابستگی",
  learning_import:"ورود محتوای آموزشی به Draft تازه", learning_export:"خروجی خصوصی محتوای آموزشی",
  privacy_export:"خروجی خصوصی اطلاعات شخصی",
};
export const researchActionLabels: Record<ResearchAction, string> = {
  map: "ثبت نگاشت مشتق", reject: "رد این رکورد", defer: "تعویق بررسی", stage: "آماده‌سازی برای بررسی آینده",
};
export const researchReasons: Record<ResearchAction, string> = {
  map: "RESEARCH_MAP", reject: "RESEARCH_REJECT", defer: "RESEARCH_DEFER", stage: "RESEARCH_STAGE",
};
export const p06ErrorMessages = {
  PRIVACY_DATA_INVALID:"یکی از مقادیر ذخیره‌شده قالب JSON معتبر ندارد؛ دادهٔ اصلی تغییر نکرده است و باید بررسی مجاز شود.",
  INVALID_LEARNING_BUNDLE:"قالب بستهٔ آموزشی بسته و نسخه‌مند است؛ فیلدها و شناسه‌های محلی فایل را بررسی کنید.",
  LEARNING_EXPORT_PROTECTED:"خروجی فقط برای محتوای خصوصی، غیرفعال، غیربذری و بدون سابقه مجاز است.",
  INVALID_REFERENCE:"slug مرجع باید به مفهوم یا اختلال فعال و معتبر اشاره کند.",
  INVALID_ARTIFACT_OPERATION:"فایل تولیدشدهٔ سرور از فرم بارگذاری اعتبارسنجی نمی‌شود؛ وضعیت کار را بررسی کنید.",
  ARTIFACT_INVALID: "فایل یا قالب داده معتبر نیست؛ نتیجهٔ اعتبارسنجی را بررسی کنید.",
  ARTIFACT_NOT_READY: "فایل هنوز آماده نیست؛ ابتدا اعتبارسنجی جداگانه لازم است.",
  ARTIFACT_EXPIRED: "مدت دسترسی فایل پایان یافته است.", ARTIFACT_REVOKED: "دسترسی این فایل لغو شده است.",
  ARTIFACT_RETENTION_HOLD: "فایل دارای وابستگی یا الزام نگهداری است؛ ارجاع‌های حاکمیت محتوا یا بایگانی مانع پاکسازی می‌شوند.",
  NOT_EXPIRED: "فایل هنوز منقضی نشده است؛ پاکسازی مجاز نیست. وضعیت جاری سرور را بازخوانی کنید.",
  CLEANUP_PLATFORM_UNAVAILABLE: "پاکسازی فیزیکی در این محیط آماده نیست؛ فایل قابل دریافت نیست و نگهداری می‌شود.",
  ARTIFACT_INTEGRITY: "یکپارچگی فایل تأیید نشد؛ پردازش متوقف شده است.",
  ARTIFACT_TOO_LARGE: "حجم فایل از حد مجاز سرور بیشتر است.",
  UPLOAD_TOO_LARGE: "حجم فایل از حد مجاز سرور بیشتر است.",
  INVALID_UPLOAD: "فایل JSON غیرخالی با نوع و حجم مجاز انتخاب کنید.",
  INVALID_JSON: "فایل JSON معتبر نیست؛ خطای قالب را در فایل اصلاح کنید.",
  JSON_LIMIT: "ساختار، شمار رکوردها یا متن فایل از حدود مجاز بیشتر است.",
  INVALID_METADATA: "فرادادهٔ فایل با قالب ورودی سازگار نیست.",
  UNSUPPORTED_SCHEMA: "قالب این JSON برای نوع فایل انتخاب‌شده پشتیبانی نمی‌شود.",
  PROTECTED_CONTENT: "فایل حاوی محتوای محافظت‌شده است و قابل ورود نیست.",
  DUPLICATE_RECORD: "شناسهٔ تکراری در مجموعه وجود دارد؛ فایل را بررسی کنید.",
  INVALID_SCOPE: "دامنه یا اتصال نسخهٔ هدف معتبر نیست.",
  INVALID_PURPOSE: "هدف دسترسی خصوصی معتبر نیست.",
  ARTIFACT_STORAGE_UNAVAILABLE: "فضای خصوصی فایل‌ها در دسترس نیست؛ با مدیر سامانه پیگیری کنید.",
  ARTIFACT_UNAVAILABLE: "فایل خصوصی در دسترس نیست؛ پردازش و دریافت انجام نمی‌شود.",
  ARTIFACT_CHANGED: "فایل یا نسخهٔ آن تغییر کرده است؛ وضعیت جاری را دوباره بررسی کنید.",
  ARCHIVE_INTEGRITY: "ورودی حفظ‌شده با انتظار پردازش سازگار نیست؛ ادامه متوقف شده است.",
  CHECKPOINT_INTEGRITY: "نقطهٔ ادامهٔ کار قابل تأیید نیست؛ نتیجه را با مدیر سامانه بررسی کنید.",
  POLICY_CHANGED: "مجوز یا سیاست جاری تغییر کرده است؛ ادامه نیازمند بررسی تازهٔ سرور است.",
  INVALID_ARTIFACT_KIND: "یکی از نوع‌های JSON مجاز را انتخاب کنید.",
  RESOURCE_VERSION_CHANGED: "نسخهٔ هدف تغییر کرده؛ هدف و نسخهٔ جاری را دوباره بررسی کنید.",
  JOB_NOT_RETRYABLE: "این کار قابل تلاش دوباره نیست؛ علت خطا یا سقف سه تلاش را بررسی کنید.",
  JOB_NOT_CANCELLABLE: "کار در وضعیت قابل لغو نیست؛ نسخهٔ تازه را دریافت کنید.",
  REQUEST_KEY_CONFLICT: "کلید درخواست قبلاً با ورودی دیگری ثبت شده است؛ نتیجهٔ قبلی را بررسی کنید.",
  IDEMPOTENCY_CONFLICT: "کلید درخواست قبلاً با ورودی دیگری ثبت شده است؛ کارهای ثبت‌شده را بررسی کنید.",
  INVALID_MAPPING: "نگاشت یا شناسه‌های منابع معتبر نیستند.",
  MAPPING_REQUIRED: "ابتدا نگاشت مشتق معتبر ثبت کنید؛ آماده‌سازی پس از نگاشت انجام می‌شود.",
  STALE_MAPPING: "نسخه یا منابع نگاشت تغییر کرده است؛ نگاشت فعلی را دوباره بررسی کنید.",
  STALE_REVISION: "نسخهٔ سرور تغییر کرده است؛ پیش از اقدام تازه نسخهٔ جاری را صریحاً دریافت کنید.",
  UNKNOWN_OUTCOME: "نتیجهٔ اقدام نامعلوم است. پیش از هر اقدام تازه، وضعیت سرور، کارها و تاریخچه را بررسی کنید؛ درخواست خودکار تکرار نمی‌شود.",
} as const;
export type P06ErrorCode = keyof typeof p06ErrorMessages;
export class CmsJobsError extends CmsError {
  readonly jobCode: P06ErrorCode | null;
  constructor(error: CmsError) {
    const code = Object.hasOwn(p06ErrorMessages, error.code) ? error.code as P06ErrorCode : null;
    super(error.status, error.code, code ? p06ErrorMessages[code] : error.message, error.details);
    this.jobCode = code;
  }
}

export async function cmsJobs<T>(path: string, options: RequestInit, session: CmsMe): Promise<Snapshot<T>> {
  try {
    const { data: current } = await cms<CmsMe>("/me/", { signal: options.signal });
    if (current.user.id !== session.user.id || current.session.id !== session.session.id) {
      window.dispatchEvent(new Event("cms-session-expired"));
      throw new CmsError(403, "UNAUTHENTICATED", "نشست مدیریت تغییر کرده است؛ دوباره وارد شوید.");
    }
    return await cms<T>(path, options, session.user.id);
  } catch (error) {
    if (error instanceof CmsError) throw new CmsJobsError(error);
    throw error;
  }
}

export function mutationBlocked(error: unknown) {
  return error instanceof CmsError && (error.status === 409 || error.status === 412 || error.status === 428 || error.code === "UNKNOWN_OUTCOME");
}
export function versionHeaders(etag: string | null): HeadersInit {
  if (!etag || etag.startsWith("W/")) throw new CmsError(428, "PRECONDITION_REQUIRED", "نسخهٔ معتبر سرور موجود نیست؛ جزئیات را دوباره دریافت کنید.");
  return { "If-Match": etag };
}
export function jobActive(job: AdminJob) {
  return ["queued", "running", "reconciling"].includes(job.status);
}
export function artifactUsable(artifact: AdminArtifact) {
  return !artifact.purged_at && artifact.state === "ready" && new Date(artifact.expires_at).getTime() > Date.now();
}
export function researchSourceIds(text: string): number[] {
  const values = text.trim().split(/[,،\s]+/).filter(Boolean);
  const ids = values.map(Number);
  if (values.some((value, i) => !/^[1-9]\d*$/.test(value) || !Number.isSafeInteger(ids[i])) || new Set(ids).size !== ids.length) {
    throw new CmsError(400, "INVALID_MAPPING", "شناسه‌های عددی مثبت و متمایز منابع را با ویرگول جدا کنید.");
  }
  return ids;
}
