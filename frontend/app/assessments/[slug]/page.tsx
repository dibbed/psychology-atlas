import Link from "next/link";
import { notFound } from "next/navigation";
import { ApiError, publicFetch } from "@/lib/api";
import type { AssessmentInstrumentDetail } from "@/lib/types";
import { AssessmentAliases, AssessmentLabel, AssessmentName, AssessmentScope, AssessmentSources, AssessmentTruncated, AssessmentUnavailable, AssessmentVersionSection } from "@/components/AssessmentAtlas";
import { BilingualText, ReviewStatus } from "@/components/ScientificMeta";
import "../assessments.css";

export const metadata = { title: "نسخه‌ها و شواهد ابزار سنجش | اطلس روان‌شناسی" };

export default async function AssessmentDetailPage({ params }: { params: Promise<{ slug: string }> }) {
  const { slug } = await params;
  let instrument: AssessmentInstrumentDetail;
  try {
    instrument = await publicFetch<AssessmentInstrumentDetail>(`/assessments/${encodeURIComponent(slug)}/`);
  } catch (error) {
    if (error instanceof ApiError && error.status === 404) notFound();
    return <main className="shell page assessment-page"><AssessmentUnavailable href={`/assessments/${encodeURIComponent(slug)}`} /></main>;
  }
  return <main className="shell page stack assessment-page assessment-detail">
    <nav className="assessment-breadcrumbs" aria-label="مسیر ابزار"><ol><li><Link href="/assessments">ابزارهای سنجش</Link></li><li aria-current="page"><AssessmentLabel instrument={instrument} /></li></ol></nav>
    <header className="assessment-detail-header"><span className="eyebrow">خانوادهٔ ابزار؛ نسخه‌ها جدا نمایش داده می‌شوند</span><AssessmentName instrument={instrument} heading /><ReviewStatus status={instrument.review_status} /><p className="muted">شناسهٔ خانواده: <bdi lang="en" dir="ltr">{instrument.slug}</bdi></p></header>
    <AssessmentScope />
    <section className="assessment-panel"><h2>دربارهٔ خانوادهٔ ابزار</h2><BilingualText en={instrument.description} empty="توضیح خانواده منتشر نشده است." /><h3>حوزهٔ سازه در معرفی خانواده</h3><BilingualText en={instrument.construct_overview} empty="نمای کلی سازه منتشر نشده است." /><h3>صاحب حقوق خانواده</h3><BilingualText en={instrument.rightsholder} empty="صاحب حقوق در معرفی خانواده تعیین نشده است؛ رکوردهای حقوق هر نسخه را جدا بررسی کنید." /><details className="assessment-disclosure"><summary>محدودیت تفسیر ثبت‌شده در منبع داده</summary><BilingualText en={instrument.interpretation_limitations} /></details></section>
    <section className="assessment-panel"><h2>نام‌های خانواده</h2><p className="muted">اختصار یک خانواده، انتخاب خودکار تازه‌ترین نسخه یا فرم فارسی نیست.</p><AssessmentAliases collection={instrument.aliases} /></section>
    <section className="assessment-panel"><h2>نسخه‌های منتشرشدهٔ این خانواده</h2>{instrument.versions.results.length ? <nav aria-label="رفتن به نسخهٔ مشخص"><ul className="assessment-version-index">{instrument.versions.results.map(version => <li key={version.key}><a className="assessment-inline-link" href={`#version-${version.key}`}><bdi lang="en" dir="ltr">{version.label} · {version.key}</bdi></a></li>)}</ul></nav> : <p className="assessment-notice">نسخهٔ بازبینی‌شده‌ای در این پاسخ منتشر نشده است؛ هیچ نسخه یا فرم زبانی را نمی‌توان از نام خانواده فرض کرد.</p>}<AssessmentTruncated collection={instrument.versions} label="نسخه‌ها" /></section>
    {instrument.versions.results.map(version => <AssessmentVersionSection key={version.key} version={version} instrumentSlug={instrument.slug} />)}
    <section className="assessment-panel"><AssessmentSources collection={instrument.sources} title="منابع هویت خانوادهٔ ابزار" /></section>
    <Link className="assessment-inline-link" href="/assessments">بازگشت به فهرست ابزارهای سنجش</Link>
  </main>;
}
