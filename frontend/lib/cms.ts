import type { DomainPayload } from './cmsDomains';

export type CmsMe = {
  user: { id: number; username: string };
  ready_capabilities: string[];
  ready_content_kinds: string[];
  session: { id: string; expires_at: string };
  security: { production_ready: boolean };
};
export type CmsCatalog = { ready_content_kinds: string[]; capabilities: { codename: string; status: "READY" | "PLANNED" }[] };
export type CmsPage<T> = { count: number; page: number; page_size: number; results: T[] };
export type ReviewKind = string;
export type ReviewType = "source" | "scientific";
export type ReviewPolicy = { scope: "core"; mode: "solo_owner" | "two_person"; version: number };
export type ReviewEvidence = { source_id: number; locator: string; fields: string[] };
export type ReviewSource = { id: number; title: string; doi: string; pmid: string; verification_status: string };
export type ReviewReviewer = { id: number; username: string; conflict: string | null };
export type ReviewTask = {
  id: number; review_type: ReviewType; status: "queued" | "assigned" | "approved" | "rejected" | "cancelled";
  version: number; assignee_id: number | null; assignee: string | null; subject_revision: number;
  revision_hash: string; dependency_digest: string; policy_version: number;
};
export type DisorderPayload = { name_en: string; name_fa: string; short_description: string; overview: string };
export type ReviewRecord = Omit<CmsRecord, "kind" | "payload" | "current_revision" | "revision_status"> & {
  kind: ReviewKind; payload: DomainPayload; domain?: string; intent?: 'edit' | 'archive'; current_revision: number | null;
  revision_status: string | null; payload_digest: string; dependency_digest: string;
};
export type ReviewSummary = {
  record: ReviewRecord; policy: ReviewPolicy; scientific_status: "unreviewed" | "source_checked" | "reviewed";
  approval: { eligible: boolean; blockers: string[] }; canonical_public_eligible: boolean; public_gate: string;
  evidence: ReviewEvidence[]; tasks: ReviewTask[];
};
export type ReviewDetail = ReviewSummary & { rejection_reasons: string[]; evidence_fields: string[] };
export type ReviewQueuePage = CmsPage<ReviewSummary> & { policy: ReviewPolicy };
export type ReviewDecision = {
  id: number; review_type: ReviewType; subject_revision: number; revision: number; outcome: string;
  actor_ref: string; assignee_ref: string; reason: string; fields: string[]; evidence: ReviewEvidence[];
  revision_hash: string; dependency_digest: string; policy_version: number; policy_mode: ReviewPolicy["mode"];
  self_review: boolean; supersedes: number | null; created_at: string;
};
export type ReviewPolicyHistory = { version: number; previous_mode: ReviewPolicy["mode"]; mode: ReviewPolicy["mode"]; reason: string; created_at: string };
export type ReviewPolicyDetail = ReviewPolicy & { reason_codes: string[]; history: CmsPage<ReviewPolicyHistory> };
export const reviewKindLabels: Record<ReviewKind, string> = { category: "دسته‌بندی", disorder: "اختلال" };
export const reviewFieldLabels: Record<string, string> = {
  name_en: 'نام علمی انگلیسی', name_fa: 'نام فارسی', description: 'توضیح', short_description: 'شرح کوتاه', overview: 'نمای کلی',
  id: 'شناسهٔ سیستم', slug: 'شناسهٔ مسیر', sort_order: 'ترتیب', is_active: 'فعال‌بودن اصل', category: 'دسته‌بندی',
  clinical_features: 'ویژگی‌های بالینی', risk_factors: 'عوامل خطر', treatment_overview: 'نمای درمان', assessment_overview: 'نمای ارزیابی', typical_onset: 'شروع معمول', course_note: 'یادداشت سیر', data_origin: 'خاستگاه داده',
  domain: 'حوزه', kind: 'نوع', subtype: 'زیرنوع', disorder: 'اختلال', symptom: 'نشانه', prominence: 'برجستگی', note: 'یادداشت', related_disorder: 'اختلال مرتبط', relationship_type: 'نوع رابطه', explanation: 'توضیح رابطه', source: 'منبع', target: 'مقصد',
  simple_definition: 'تعریف ساده', academic_definition: 'تعریف دانشگاهی', example: 'مثال', counterexample: 'مثال نقض', recognition_cues: 'نشانه‌های تشخیص', common_confusions: 'اشتباه‌های رایج', source_concept: 'مفهوم مبدأ', target_concept: 'مفهوم مقصد', concept: 'مفهوم', text: 'متن', language: 'زبان', alias_type: 'نوع نام جایگزین', relationship: 'رابطه',
  title: 'عنوان', version_name: 'نام نسخه', version_date: 'تاریخ نسخه', purpose: 'هدف', copyright_note: 'یادداشت حق نشر', clinical_note: 'یادداشت بالینی', cultural_note: 'یادداشت فرهنگی', key: 'کلید هویت',
  official_status: 'وضعیت رسمی', source_registry: 'فهرست منابع', quality_audit: 'ارزیابی کیفیت', stats: 'آمار', study_guide: 'راهنمای مطالعه', urgent_warnings: 'هشدارهای فوری', periodic_review: 'بازبینی دوره‌ای', release_updates: 'به‌روزرسانی نسخه', health_check: 'بررسی سلامت داده', metadata: 'فراداده',
  corpus: 'مجموعهٔ DSM', parent: 'والد', linked_disorder: 'اختلال پیوندی', sort_index: 'ترتیب رکورد', root_section: 'بخش اصلی', chapter_number: 'شمارهٔ فصل', chapter_name_fa: 'نام فارسی فصل', chapter_name_en: 'نام انگلیسی فصل', group_name: 'نام گروه', source_type: 'نوع منبع', classification_status: 'وضعیت طبقه‌بندی', display_type: 'نوع نمایش', specialization_level: 'سطح تخصص', summary: 'خلاصه', comorbidity: 'همبودی', course: 'سیر', context_considerations: 'ملاحظات زمینه', red_flags: 'هشدارهای بالینی', prevalence_policy: 'سیاست شیوع', coding: 'کدگذاری', exam_tip: 'نکتهٔ آزمون',
  key_features: 'ویژگی‌های کلیدی', assessment: 'ارزیابی', differential: 'افتراق', management: 'مدیریت', assessment_tools: 'ابزارهای ارزیابی', pitfalls: 'خطاهای رایج', nearby_titles: 'عنوان‌های نزدیک', official_updates: 'به‌روزرسانی‌های رسمی', homonym_info: 'اطلاعات هم‌نامی', prevalence_numeric: 'برآورد عددی شیوع', source_keys: 'کلیدهای منابع', quality: 'کیفیت', self_test: 'خودآزمایی', structural_path: 'مسیر ساختاری', master_id: 'شناسهٔ اصلی رکورد',
  raw_document: 'سند raw حفظ‌شده', source_payload: 'دادهٔ خام منبع', search_text: 'متن جست‌وجوی تولیدشده', source_filename: 'نام فایل ورودی', source_sha256: 'اثر انگشت فایل ورودی', created_at: 'زمان ایجاد', updated_at: 'زمان تغییر',
};
export const reviewPolicyLabels: Record<ReviewPolicy["mode"], string> = { solo_owner: "مالک تنها؛ خودبازبینی با تأیید صریح", two_person: "دو نفر؛ نویسنده نمی‌تواند بازبین باشد" };
export const reviewStatusLabels: Record<ReviewSummary["scientific_status"], string> = { unreviewed: "بدون بازبینی معتبر", source_checked: "منابع بررسی شده؛ بررسی علمی باقی است", reviewed: "پیشنهاد بازبینی شده" };
export const reviewReasonLabels: Record<string, string> = {
  EVIDENCE_INSUFFICIENT: "شواهد ناکافی", LOCATOR_INVALID: "نشانی شاهد نامعتبر", CLAIM_UNSUPPORTED: "ادعای بدون پشتوانه", CORRECTION_REQUIRED: "اصلاح لازم است",
  SOURCE_VERIFIED: "منابع تأیید شد", SCIENCE_VERIFIED: "بررسی علمی تأیید شد", REVIEW_ASSIGN: "تخصیص بازبین", REVIEW_REOPEN: "بازگشایی بررسی",
  TEAM_POLICY: "سیاست تیم", SENSITIVE_DOMAIN: "حوزهٔ حساس", OWNER_OPERATION: "عملیات مالک",
  POLICY_CHANGED: "سیاست تغییر کرده؛ تصمیم قبلی ثابت می‌ماند اما دیگر مجوز معتبر این پیشنهاد نیست. بررسی را بازگشایی و دوباره ارسال کنید.",
  DEPENDENCY_CHANGED: "منابع یا وابستگی‌ها تغییر کرده‌اند؛ بررسی تازه لازم است.", PAYLOAD_CHANGED: "متن پیشنهاد تغییر کرده؛ بررسی تازه لازم است.",
  REVIEW_REQUIRED: "پیشنهاد هنوز برای بررسی ارسال نشده است.", APPROVAL_REQUIRED: "هر دو بررسی باید تأیید شوند.", REVIEW_NOT_CURRENT: "بررسی مربوط به پیشنهاد فعلی نیست.",
  CANONICAL_RECONCILIATION_REQUIRED: "محتوای اصلی تغییر کرده؛ ابتدا پیشنهاد را با نسخهٔ فعلی تطبیق دهید.",
  REVIEWER_PERMISSION_CHANGED: "مجوز بازبین تغییر کرده است.", REVIEWER_UNAVAILABLE: "بازبین دیگر در دسترس نیست.", DECISION_REQUIRED: "تصمیم معتبر برای این نسخه موجود نیست.",
  EVIDENCE_MISSING: "یکی از منابع شاهد دیگر وجود ندارد؛ شاهد جایگزین ثبت و پیشنهاد دوباره بررسی شود.",
  TWO_PERSON_REQUIRED: "سیاست دو نفره خودبازبینی نویسنده را منع می‌کند.", REVIEWER_CONFLICT: "نویسنده یا حساب فعلی واجد شرایط این بررسی نیست.",
};
export type CategoryPayload = { name_en: string; name_fa: string; description: string };
export type CmsRecord = {
  id: string; kind: string; canonical_pk: number | null; version: number; canonical_digest: string;
  publication: string; legacy_origin: boolean; revision_status: string; current_revision: number;
  payload: CategoryPayload;
};
export type CmsRevision = { id: number; sequence: number; status: string; created_at: string; payload: CategoryPayload };
export type CmsAudit = {
  id: number; created_at: string; action: string; outcome: string; target_kind: string; target_key: string;
  diff: string[]; reason: string; base_revision: number | null; new_revision: number | null;
  request_id: string; actor_ref: string; error_code: string;
};
export type CmsDashboard = {
  measured_at: string; scope: string; content: { kind: string; total: number; drafts: number }[] | null;
  audit: { count: number; latest: CmsAudit[] } | null; unavailable: string[];
};
export class CmsError extends Error {
  constructor(public status: number, public code: string, message: string,
    public details: { field_errors?: Record<string, string[]>; blockers?: string[]; request_id?: string } = {}) {
    super(message);
  }
}

const errorMessages: Record<string, string> = {
  LOGIN_FAILED: "ورود انجام نشد؛ مشخصات ورود و دسترسی مدیریت حساب را بررسی کنید.",
  LOGIN_THROTTLED: "تعداد تلاش‌های ورود بیش از حد مجاز است؛ کمی بعد دوباره تلاش کنید.",
  MFA_INVALID: "کد تأیید نامعتبر یا منقضی شده است؛ کد تازه وارد کنید.",
  INVALID_MFA: "روش یا قالب کد تأیید معتبر نیست.",
  MFA_ENROLLMENT_REQUIRED: "احراز هویت دومرحله‌ای این حساب هنوز تنظیم نشده است.",
  MFA_REQUIRED: "ابتدا احراز هویت دومرحله‌ای را تکمیل کنید.",
  UNAUTHENTICATED: "نشست مدیریت پایان یافته است؛ دوباره وارد شوید.",
  PERMISSION_DENIED: "برای این عملیات مجوز کافی ندارید.",
  NOT_FOUND: "رکورد وجود ندارد یا خارج از محدودهٔ دسترسی شماست.",
  CSRF_FAILED: "تأیید امنیتی درخواست انجام نشد؛ صفحه را دوباره باز کنید.",
  INVALID_INPUT: "مقدارهای فرم معتبر نیستند؛ خطاهای فیلدها را بررسی کنید.",
  INVALID_FIELDS: "فیلدهای ارسال‌شده با قرارداد این محتوا سازگار نیستند.",
  INVALID_QUERY: "فیلتر یا شمارهٔ صفحه معتبر نیست؛ فیلتر را پاک کنید.",
  INVALID_TRANSITION: "وضعیت محتوا تغییر کرده و این نسخه قابل‌ویرایش نیست؛ نسخهٔ سرور را بررسی کنید.",
  PRECONDITION_REQUIRED: "نسخهٔ پایهٔ ذخیره موجود نیست؛ نسخهٔ سرور را دوباره دریافت کنید.",
  INVALID_PRECONDITION: "نسخهٔ پایهٔ ذخیره معتبر نیست؛ نسخهٔ سرور را دوباره دریافت کنید.",
  STALE_REVISION: "نسخهٔ محتوا تغییر کرده است؛ پیش از هر اقدام، نسخهٔ سرور را صریحاً دوباره دریافت کنید.",
  STALE_DECISION: "وظیفه یا شرایط بررسی تغییر کرده است؛ نسخهٔ سرور و علت‌های عدم اعتبار را دوباره بررسی کنید.",
  EVIDENCE_REQUIRED: "بین یک تا بیست شاهد ثبت کنید.",
  INVALID_EVIDENCE: "منبع، نشانی یا فیلدهای شاهد معتبر نیستند.",
  EVIDENCE_COVERAGE_REQUIRED: "برای همهٔ فیلدهای پُر پیشنهاد شاهد ثبت کنید.",
  INVALID_REVIEWER: "بازبین انتخاب‌شده معتبر نیست یا مجوز لازم را ندارد.",
  REVIEWER_CONFLICT: "فقط بازبین تخصیص‌یافته و بدون تعارض می‌تواند تصمیم بگیرد.",
  TWO_PERSON_REQUIRED: "در سیاست دو نفره، نویسنده نمی‌تواند پیشنهاد خود را بررسی کند.",
  SELF_REVIEW_ACK_REQUIRED: "مالک برای بررسی پیشنهاد خود باید خودبازبینی را صریحاً تأیید کند.",
  SOURCE_CHECK_REQUIRED: "پیش از تأیید علمی، منابع باید جداگانه تأیید شوند.",
  SOURCE_UNRESOLVED: "منابع هنوز تأییدپذیر نیستند؛ وضعیت منابع را بررسی کنید.",
  REJECTION_REASON_REQUIRED: "برای رد پیشنهاد، دلیل مجاز و حداقل یک فیلد را انتخاب کنید.",
  INVALID_DECISION: "نتیجهٔ تصمیم معتبر نیست.", INVALID_REASON: "دلیل با نتیجهٔ بررسی سازگار نیست.",
  INVALID_POLICY: "سیاست یا دلیل انتخاب‌شده معتبر نیست.", POLICY_UNCHANGED: "سیاست انتخاب‌شده با سیاست فعلی یکسان است.",
  STEP_UP_REQUIRED: "این تغییر به تأیید دومرحله‌ای تازه و متصل به همین سیاست نیاز دارد.",
  PRIVACY_LIMIT: "متن این صفحه از سقف امن بیشتر است؛ برای بررسی دادهٔ بزرگ به مدیر مجاز مراجعه کنید.",
  CANONICAL_RECONCILIATION_REQUIRED: "محتوای اصلی تغییر کرده؛ ابتدا پیشنهاد را با نسخهٔ فعلی تطبیق دهید.",
};

function notifySessionChange() {
  if (typeof BroadcastChannel === "undefined") return;
  const channel = new BroadcastChannel("atlas-cms-session");
  channel.postMessage("changed"); channel.close();
}

export async function cms<T>(path: string, options: RequestInit = {}, expectedUserId?: number): Promise<{ data: T; etag: string | null }> {
  const unsafe = options.method && !["GET", "HEAD", "OPTIONS"].includes(options.method);
  const headers = new Headers(options.headers);
  if (unsafe) {
    if (expectedUserId !== undefined && (await cms<CmsMe>("/me/")).data.user.id !== expectedUserId) {
      window.dispatchEvent(new Event("cms-session-expired")); notifySessionChange();
      throw new CmsError(403, "UNAUTHENTICATED", "حساب نشست تغییر کرده است؛ دوباره وارد شوید.");
    }
    // Fetch after each session rotation; CMS never uses the public JWT/localStorage client.
    const { data } = await cms<{ csrf_token: string }>("/auth/csrf/");
    headers.set("X-CSRFToken", data.csrf_token);
    if (!(options.body instanceof FormData)) headers.set("Content-Type", "application/json");
  }
  let response: Response;
  try {
    response = await fetch(`/api/admin${path}`, { ...options, headers, credentials: "same-origin", cache: "no-store", signal: options.signal ?? AbortSignal.timeout(15000) });
  } catch {
    throw new CmsError(0, unsafe ? "UNKNOWN_OUTCOME" : "NETWORK_ERROR", unsafe
      ? "نتیجهٔ ذخیره نامعلوم است. پیش از تکرار، نسخهٔ سرور و تاریخچه را بررسی کنید."
      : "ارتباط با سرور برقرار نشد؛ دوباره تلاش کنید.");
  }
  let body;
  try { body = await response.json(); }
  catch {
    throw new CmsError(response.ok && unsafe ? 0 : response.status, response.ok && unsafe ? "UNKNOWN_OUTCOME" : "SERVER_ERROR",
      response.ok && unsafe ? "نتیجهٔ ذخیره نامعلوم است. پیش از تکرار، نسخهٔ سرور و تاریخچه را بررسی کنید." : "پاسخ سرور قابل‌خواندن نیست؛ دوباره تلاش کنید.");
  }
  if (!response.ok) {
    if (body.code === "UNAUTHENTICATED") { window.dispatchEvent(new Event("cms-session-expired")); notifySessionChange(); }
    throw new CmsError(response.status, body.code || "SERVER_ERROR", errorMessages[body.code] || (body.message !== body.code && body.message) || "درخواست انجام نشد.", body);
  }
  if (unsafe && ["/auth/login/", "/auth/verify/", "/auth/complete/", "/auth/logout/"].includes(path)) notifySessionChange();
  return { data: body as T, etag: response.headers.get("ETag") };
}

export function cmsDate(value: string) {
  return new Intl.DateTimeFormat("fa-IR", { dateStyle: "medium", timeStyle: "short" }).format(new Date(value));
}
export const revisionLabels: Record<string, string> = {
  legacy: "میراث؛ بدون تصمیم علمی", draft: "پیش‌نویس", discarded: "کنارگذاشته‌شده",
  submitted: "ارسال‌شده", in_review: "در بررسی", changes_requested: "نیازمند اصلاح", approved: "تأییدشده", superseded: "جایگزین‌شده",
};
export const publicationLabels: Record<string, string> = {
  current: "محتوای اصلی موجود", pending_update: "پیشنهاد تغییر؛ اصل بدون تغییر", never_published: "منتشر نشده", withdrawn: "برداشته‌شده",
};
