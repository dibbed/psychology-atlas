import Link from "next/link";
import type { ReactNode } from "react";
import type {
  AssessmentAccess, AssessmentAlias, AssessmentCollection, AssessmentInstrument,
  AssessmentLanguageForm, AssessmentRelation, AssessmentSourceLink,
  AssessmentValidationStudy, AssessmentVersionDetail,
} from "@/lib/types";
import { assessmentAvailabilities, assessmentFormKinds, assessmentIntendedUses, assessmentLicenses } from "@/lib/assessment";
import { BilingualText, faNumber, ReviewStatus, ScientificSourceList } from "./ScientificMeta";

export function AssessmentLabel({ instrument }: { instrument: Pick<AssessmentInstrument, "name_fa" | "name_en"> }) {
  const persian = !!instrument.name_fa.trim();
  return <bdi lang={persian ? "fa" : "en"} dir={persian ? "rtl" : "ltr"}>{persian ? instrument.name_fa : instrument.name_en}</bdi>;
}

export function AssessmentName({ instrument, heading = false }: { instrument: AssessmentInstrument; heading?: boolean }) {
  const label = <AssessmentLabel instrument={instrument} />;
  return <div className="assessment-name">{heading ? <h1>{label}</h1> : <h3>{label}</h3>}{instrument.name_fa.trim() && <p className="muted" lang="en" dir="ltr">{instrument.name_en}</p>}</div>;
}

export function AssessmentScope() {
  return <aside className="assessment-notice" aria-label="محدودیت استفاده">
    <strong>اطلس آموزشی ابزارهای سنجش</strong>
    <p>غربالگری و اندازه‌گیری، تشخیص بالینی نیستند. هر یافته فقط به نسخه، فرم زبانی، جمعیت و مطالعهٔ مشخص خود مربوط است.</p>
    <p>عنوان فارسیِ معرفی ابزار، تأیید ترجمه یا مجوز فرم فارسی نیست. دسترسی به مقاله یا صفحهٔ عمومی، مجوز بازنشر یا نمره‌گذاری ایجاد نمی‌کند؛ وضعیت نامعلوم به معنای رایگان‌بودن نیست.</p>
    <p>این بخش سؤال‌های آزمون، اجرای آزمون، نمره‌گذاری، راهنما، نقطهٔ برش، هنجار یا نتیجهٔ تشخیصی ارائه نمی‌کند.</p>
  </aside>;
}

export function AssessmentTruncated({ collection, label }: { collection: { truncated: boolean }; label: string }) {
  return collection.truncated ? <p className="assessment-notice">فقط بخشی از {label} در این پاسخ منتشر شده است؛ این فهرست کامل نیست.</p> : null;
}

export function AssessmentCard({ instrument }: { instrument: AssessmentInstrument }) {
  return <Link href={`/assessments/${encodeURIComponent(instrument.slug)}`} prefetch={false} className="assessment-card">
    <div className="assessment-card-meta"><span>خانوادهٔ ابزار</span><ReviewStatus status={instrument.review_status} compact /></div>
    <AssessmentName instrument={instrument} />
    <p className="muted">نسخه‌های منتشرشدهٔ این خانواده</p>
    {instrument.versions.results.length ? <ul className="assessment-card-versions">{instrument.versions.results.map(version => <li key={version.key}>
      <strong lang="en" dir="ltr">{version.label}</strong>
      <span>{assessmentFormKinds[version.form_kind]}{version.publication_year !== null && ` · ${version.publication_year.toLocaleString("fa-IR", { useGrouping: false })}`}</span>
      <span>{version.intended_use ? assessmentIntendedUses[version.intended_use] : "کاربرد مشخصی منتشر نشده"}</span>
    </li>)}</ul> : <p className="muted">نسخهٔ بازبینی‌شده‌ای برای این خانواده منتشر نشده است.</p>}
    <AssessmentTruncated collection={instrument.versions} label="نسخه‌ها" />
    <span className="assessment-card-foot">مرور نسخه‌ها، شواهد و حقوق دسترسی ←</span>
  </Link>;
}

export function AssessmentLoading() {
  return <section className="assessment-loading" role="status" aria-live="polite" aria-busy="true"><p>در حال بارگذاری اطلاعات ابزارهای سنجش…</p><div className="assessment-card-grid" aria-hidden="true">{[0, 1, 2].map(key => <div className="assessment-skeleton" key={key} />)}</div></section>;
}

export function AssessmentUnavailable({ href, invalid = false }: { href: string; invalid?: boolean }) {
  return <section className="assessment-empty" role="alert"><h2>{invalid ? "این انتخاب یا شمارهٔ صفحه قابل نمایش نیست" : "اطلاعات ابزارهای سنجش بارگذاری نشد"}</h2>
    <p>{invalid ? "فیلتر یا شمارهٔ صفحه معتبر نیست. از فهرست ابزارها دوباره شروع کنید؛ شناسهٔ سازه و کد زبان باید در مجموعهٔ منتشرشده وجود داشته باشند." : "ارتباط با سرویس برقرار نشد یا سرویس با خطا روبه‌رو شد. دوباره تلاش کنید؛ این خطا به معنای خالی‌بودن مجموعه نیست."}</p>
    <div className="assessment-actions">{!invalid && <a className="button primary" href={href}>تلاش دوباره</a>}<Link className="button" href="/assessments">نمایش همهٔ ابزارها</Link></div>
  </section>;
}

function AssessmentField({ label, text, empty = "در این پاسخ ثبت نشده است.", children }: { label: string; text?: string | null; empty?: string; children?: ReactNode }) {
  return <div><dt>{label}</dt><dd>{children ?? (text?.trim() ? <bdi lang="en" dir="ltr">{text}</bdi> : <span className="muted">{empty}</span>)}</dd></div>;
}

export function AssessmentSources({ collection, title = "منابع و یادداشت‌های استناد" }: { collection: AssessmentCollection<AssessmentSourceLink>; title?: string }) {
  return <div className="assessment-sources">
    <ScientificSourceList sources={collection.results.map(link => ({ ...link.source, organization: "" }))} title={title} />
    {!!collection.results.length && <details className="assessment-disclosure"><summary>یادداشت‌های هر استناد</summary><ul>{collection.results.map((link, index) => <li key={`${link.source.id}-${index}`}><strong dir="auto">{link.source.title}</strong><BilingualText en={link.note} empty="یادداشت استناد در این پاسخ ثبت نشده است." /></li>)}</ul></details>}
    <AssessmentTruncated collection={collection} label="منابع" />
  </div>;
}

export function AssessmentAliases({ collection }: { collection: AssessmentCollection<AssessmentAlias> }) {
  const kinds = { name: "نام جایگزین", acronym: "اختصار", translated_title: "عنوان ترجمه‌شدهٔ معرفی" };
  return <div>{collection.results.length ? <ul className="assessment-aliases">{collection.results.map((alias, index) => <li key={`${alias.language}-${alias.text}-${index}`}>
    <bdi lang={alias.language} dir={/^(fa|ar|ur)(-|$)/.test(alias.language) ? "rtl" : "ltr"}>{alias.text}</bdi><span className="muted">{kinds[alias.alias_type]} · <bdi lang="en">{alias.language}</bdi></span>
    <details className="assessment-disclosure"><summary>منبع نام</summary><AssessmentSources collection={{ results: [{ source: alias.source, note: "" }], truncated: false }} title="منبع این نام" /></details>
  </li>)}</ul> : <p className="muted">نام جایگزینی در این پاسخ منتشر نشده است.</p>}<AssessmentTruncated collection={collection} label="نام‌های جایگزین" /></div>;
}

function LanguageForm({ form, version }: { form: AssessmentLanguageForm; version: string }) {
  const kinds = { original: "فرم زبان اصلی", translation: "ترجمه", adaptation: "انطباق" };
  return <details className="assessment-disclosure">
    <summary><span lang="en" dir="ltr">{form.label}</span><span className="assessment-tag">{kinds[form.form_kind]} · <bdi lang="en" dir="ltr">{form.language}</bdi></span></summary>
    <dl className="assessment-facts">
      <AssessmentField label="نسخهٔ متعلق به این فرم" text={version} />
      <AssessmentField label="شناسهٔ دقیق فرم زبانی" text={form.key} />
      <AssessmentField label="کد زبان"><Link className="assessment-inline-link" href={`/assessments?language=${encodeURIComponent(form.language)}`}><bdi lang="en" dir="ltr">{form.language}</bdi></Link></AssessmentField>
      <AssessmentField label="صاحب فرم" text={form.owner} empty="صاحب فرم در این پاسخ تعیین نشده است." />
      <AssessmentField label="وضعیت اجازهٔ این فرم"><span>{form.authorization_status === "authorized" ? "اجازه برای همین فرم احراز شده؛ دامنه را در منبع بخوانید" : "اجازهٔ این فرم احراز نشده؛ به معنای استفادهٔ آزاد نیست"}</span></AssessmentField>
    </dl>
    <ReviewStatus status={form.review_status} compact />
    <BilingualText en={form.authorization_note} empty="توضیح اجازهٔ این فرم ثبت نشده است." />
    {form.authorization_source ? <AssessmentSources collection={{ results: [{ source: form.authorization_source, note: form.authorization_note }], truncated: false }} title="منبع اجازهٔ فرم" /> : <p className="muted">منبع مستقلی برای احراز اجازهٔ این فرم منتشر نشده است.</p>}
    <AssessmentSources collection={form.sources} title="منابع هویت فرم زبانی" />
  </details>;
}

function AccessRecord({ access, version }: { access: AssessmentAccess; version: string }) {
  const materials = { questionnaire: "پرسش‌نامه", manual: "راهنما", translation: "ترجمه", metadata: "فراداده" };
  const uses = { owner_access: "دسترسی از طریق صاحب اثر", redistribution: "بازنشر", metadata_listing: "معرفی فراداده" };
  return <article className="assessment-record">
    <h4>{assessmentLicenses[access.license_status]}</h4>
    <p className="assessment-tag">{assessmentAvailabilities[access.availability]}</p>
    <dl className="assessment-facts">
      <AssessmentField label="شناسهٔ رکورد دسترسی" text={access.key} />
      <AssessmentField label="نسخه" text={version} />
      <AssessmentField label="فرم زبانیِ این رکورد" text={access.language_form} empty="فرم زبانی تعیین نشده؛ این رکورد به همهٔ ترجمه‌ها تعمیم ندارد." />
      <AssessmentField label="نوع ماده"><span>{materials[access.material_type]}</span></AssessmentField>
      <AssessmentField label="نوع استفادهٔ بررسی‌شده"><span>{uses[access.use]}</span></AssessmentField>
      <AssessmentField label="صاحب اثر" text={access.owner} empty="در این رکورد تعیین نشده است." />
      <AssessmentField label="حوزهٔ قضایی" text={access.jurisdiction} />
      <AssessmentField label="تاریخ بررسی"><span>{access.verified_on ? <time dateTime={access.verified_on} lang="en" dir="ltr">{access.verified_on}</time> : "تاریخ بررسی ثبت نشده است."}</span></AssessmentField>
      <AssessmentField label="تاریخ پایان اعتبار"><span>{access.expires_on ? <time dateTime={access.expires_on} lang="en" dir="ltr">{access.expires_on}</time> : "تاریخ انقضا ثبت نشده؛ به معنای اجازهٔ دائمی نیست."}</span></AssessmentField>
    </dl>
    <h5>شرایط دقیق ثبت‌شده</h5><BilingualText en={access.terms} empty="شرایط استفاده منتشر نشده است." />
    <p className="assessment-notice">دسترسی و مجوز دو وضعیت جدا هستند. این رکورد فقط دربارهٔ ماده، فرم و استفادهٔ بالا است؛ مجوز مقاله، فرم زبانی دیگر یا راهنمای آزمون از آن نتیجه نمی‌شود.</p>
    <AssessmentSources collection={{ results: [{ source: access.source, note: access.source_note }], truncated: false }} title="منبع بررسی حقوق و دسترسی" />
  </article>;
}

function ValidationStudy({ study, version }: { study: AssessmentValidationStudy; version: string }) {
  const properties = { reliability: "پایایی", validity: "روایی", responsiveness: "پاسخ‌دهی به تغییر" };
  return <article className="assessment-study">
    <header><h4>مطالعهٔ <bdi lang="en" dir="ltr">{study.key}</bdi></h4><ReviewStatus status={study.review_status} compact /></header>
    <dl className="assessment-facts">
      <AssessmentField label="نسخهٔ دقیق" text={study.version} />
      <AssessmentField label="عنوان نسخه" text={version} />
      <AssessmentField label="شناسهٔ فرم زبانی" text={study.language_form} />
      <AssessmentField label="زبان"><bdi lang="en" dir="ltr">{study.language}</bdi></AssessmentField>
      <AssessmentField label="طرح مطالعه" text={study.design} />
      <AssessmentField label="جمعیت" text={study.population} />
      <AssessmentField label="تعداد نمونه"><span>{study.sample_size === null ? "در این پاسخ گزارش نشده است." : faNumber(study.sample_size)}</span></AssessmentField>
      <AssessmentField label="زمینهٔ نمونه‌گیری" text={study.sample_context} />
      <AssessmentField label="شیوهٔ اجرا" text={study.administration} />
      <AssessmentField label="گزارش‌دهنده" text={study.informant} />
      <AssessmentField label="روش مطالعه" text={study.method} />
      <AssessmentField label="مقایسه‌گر مطالعه" text={study.comparator} empty="مقایسه‌گری در این پاسخ گزارش نشده است." />
    </dl>
    <p className="muted">مقایسه‌گر به مطالعه مربوط است؛ لزوماً مقایسه‌گر هر برآورد پایایی نیست.</p>
    <h5>محدودیت‌های مطالعه</h5><BilingualText en={study.limitations} />
    <AssessmentSources collection={{ results: [{ source: study.source, note: study.source_note }], truncated: false }} title="منبع و محل استناد مطالعه" />
    <div className="assessment-findings">{study.findings.results.length ? study.findings.results.map(finding => <section className="assessment-finding" key={finding.key}>
      <header><h5>{properties[finding.measurement_property]} · <bdi lang="en" dir="ltr">{finding.statistic}</bdi></h5><ReviewStatus status={finding.review_status} compact /></header>
      <dl className="assessment-facts">
        <AssessmentField label="شناسهٔ یافته" text={finding.key} />
        <AssessmentField label="مقدار گزارش‌شده، با دقت منبع"><span className="assessment-value">{finding.value_text ? <bdi lang="en" dir="ltr">{finding.value_text}</bdi> : "مقدار عددی منتشر نشده است."}</span></AssessmentField>
        <AssessmentField label="واحد" text={finding.units} empty="واحد در این پاسخ گزارش نشده است." />
        <AssessmentField label="روش این یافته" text={finding.method} />
        <AssessmentField label="عدم قطعیت / فاصلهٔ گزارش‌شده" text={finding.uncertainty} empty="فاصله یا عدم قطعیت در این پاسخ استخراج نشده است." />
        <AssessmentField label="محل استخراج در منبع" text={finding.extraction_locator} />
      </dl>
      <BilingualText en={finding.finding} />
      <h5>محدودیت‌های همین یافته</h5><BilingualText en={finding.limitations} />
      <p className="assessment-notice">این مقدار فقط برای نسخه، فرم، جمعیت و نمونهٔ مطالعهٔ بالا گزارش شده است؛ امتیاز فردی یا ویژگی همگانی ابزار نیست.</p>
    </section>) : <p className="muted">یافتهٔ روان‌سنجی بازبینی‌شده‌ای برای این مطالعه منتشر نشده است؛ از این نبودن، روایی یا بی‌اعتباری نتیجه نمی‌شود.</p>}</div>
    <AssessmentTruncated collection={study.findings} label="یافته‌های این مطالعه" />
  </article>;
}

function RelationRecord({ relation, version }: { relation: AssessmentRelation; version: string }) {
  const predicates = { measures: "اندازه‌گیری سازه", research_measure_of: "اندازه‌گیری پژوهشی سازه", screens_for: "غربالگری", monitors: "پایش", diagnostic_support_for: "کمک به ارزیابی حرفه‌ای" };
  const types = { concept: "مفهوم", symptom: "نشانه", disorder: "اختلال" };
  return <article className="assessment-record"><h4>{predicates[relation.predicate]}</h4>
    <dl className="assessment-facts"><AssessmentField label="شناسهٔ رابطه" text={relation.key} /><AssessmentField label="نسخه" text={version} /><AssessmentField label="فرم زبانی" text={relation.language_form} empty="فرم زبانی برای این رابطه تعیین نشده است." /><AssessmentField label="مقصد ثبت‌شده"><span>{types[relation.target.type]} · <bdi lang="en" dir="ltr">{relation.target.name_en}</bdi> · <bdi lang="en" dir="ltr">{relation.target.slug}</bdi></span></AssessmentField></dl>
    <h5>ادعای مستند</h5><BilingualText en={relation.claim} /><h5>زمینه</h5><BilingualText en={relation.context} /><h5>محدودیت</h5><BilingualText en={relation.limitations} />
    <p className="muted">این رابطه تأیید تشخیص یا توصیهٔ درمانی نیست.</p><AssessmentSources collection={relation.sources} title="منابع این رابطه" />
  </article>;
}

export function AssessmentVersionSection({ version, instrumentSlug }: { version: AssessmentVersionDetail; instrumentSlug: string }) {
  return <section id={`version-${version.key}`} className="assessment-version" aria-labelledby={`version-title-${version.key}`}>
    <header className="assessment-version-header"><div><span className="eyebrow">نسخهٔ مشخص · {assessmentFormKinds[version.form_kind]}</span><h2 id={`version-title-${version.key}`} lang="en" dir="ltr">{version.label}</h2><p><bdi lang="en" dir="ltr">{instrumentSlug} / {version.key}</bdi></p></div><ReviewStatus status={version.review_status} compact /></header>
    <dl className="assessment-facts">
      <AssessmentField label="سال انتشار"><span>{version.publication_year === null ? "ثبت نشده است." : version.publication_year.toLocaleString("fa-IR", { useGrouping: false })}</span></AssessmentField>
      <AssessmentField label="شناسهٔ سازه">{version.construct ? <Link className="assessment-inline-link" href={`/assessments?construct=${encodeURIComponent(version.construct)}`}><bdi lang="en" dir="ltr">{version.construct}</bdi></Link> : <span className="muted">سازه‌ای منتشر نشده است.</span>}</AssessmentField>
      <AssessmentField label="کاربرد ثبت‌شده"><span>{version.intended_use ? assessmentIntendedUses[version.intended_use] : "کاربردی منتشر نشده است."}</span></AssessmentField>
      <AssessmentField label="شیوهٔ اجرا" text={version.administration} />
      <AssessmentField label="گزارش‌دهنده" text={version.informant} />
      <AssessmentField label="جمعیت نسخه" text={version.population} />
      <AssessmentField label="نسخهٔ مبنای مشتق‌شدن" text={version.derived_from} empty="نسخهٔ مبنای عمومی در این پاسخ ثبت نشده است؛ این به معنای استقلال نسخه نیست." />
    </dl>
    <h3>محدودیت‌های این نسخه</h3><BilingualText en={version.limitations} />
    <details className="assessment-disclosure"><summary>نام‌های جایگزین همین نسخه</summary><AssessmentAliases collection={version.aliases} /></details>
    <details className="assessment-disclosure"><summary>منابع هویت و توضیحات نسخه</summary><AssessmentSources collection={version.sources} /></details>
    <div className="assessment-version-sections">
      <section><h3>فرم‌های زبانیِ همین نسخه</h3>{version.language_forms.results.length ? version.language_forms.results.map(form => <LanguageForm key={form.key} form={form} version={version.key} />) : <p className="muted">فرم زبانی بازبینی‌شده‌ای در این پاسخ منتشر نشده است؛ نام فارسیِ ابزار جایگزین فرم فارسی نیست.</p>}<AssessmentTruncated collection={version.language_forms} label="فرم‌های زبانی" /></section>
      <section><h3>حقوق و دسترسی در دامنهٔ مشخص</h3>{version.access.results.length ? version.access.results.map(access => <AccessRecord key={access.key} access={access} version={version.key} />) : <p className="assessment-notice">رکورد حقوق و دسترسی منتشر نشده است؛ اجازهٔ استفاده یا رایگان‌بودن احراز نشده است.</p>}<AssessmentTruncated collection={version.access} label="رکوردهای دسترسی" /></section>
      <section><h3>شواهد روان‌سنجی در متن مطالعه</h3><p className="muted">نمونه‌ها و روش‌های متفاوت جدا نمایش داده می‌شوند. هیچ میانگین یا رتبهٔ کلی برای ابزار محاسبه نمی‌شود.</p>{version.validation_studies.results.length ? version.validation_studies.results.map(study => <ValidationStudy key={study.key} study={study} version={version.label} />) : <p className="assessment-notice">مطالعه و یافتهٔ بازبینی‌شده‌ای برای این نسخه در این پاسخ منتشر نشده است. این نبودن، تأیید یا رد ویژگی‌های روان‌سنجی نیست.</p>}<AssessmentTruncated collection={version.validation_studies} label="مطالعات" /></section>
      <section><h3>روابط علمیِ منتشرشده</h3>{version.relations.results.length ? version.relations.results.map(relation => <RelationRecord key={relation.key} relation={relation} version={version.key} />) : <p className="muted">رابطهٔ مستندی برای این نسخه در این پاسخ منتشر نشده است؛ از کاربرد یا شباهت نام، رابطه‌ای استنباط نمی‌شود.</p>}<AssessmentTruncated collection={version.relations} label="روابط" /></section>
    </div>
  </section>;
}
