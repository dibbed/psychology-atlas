import { Suspense } from "react";
import Link from "next/link";
import type { Metadata } from "next";
import { ApiError, publicFetch } from "@/lib/api";
import {
  assessmentAvailabilities, assessmentFormKinds, assessmentHref, assessmentIntendedUses,
  assessmentLicenses, assessmentPaginationHref, assessmentQuery,
} from "@/lib/assessment";
import type { AssessmentInstrument, Paginated } from "@/lib/types";
import { AssessmentCard, AssessmentLoading, AssessmentScope, AssessmentUnavailable } from "@/components/AssessmentAtlas";
import { faNumber } from "@/components/ScientificMeta";
import "./assessments.css";

export const metadata: Metadata = { title: "ابزارهای سنجش | اطلس روان‌شناسی", description: "مرور خانواده‌ها و نسخه‌های ابزار سنجش، شواهد وابسته به مطالعه و حقوق دسترسی." };

async function AssessmentResults({ query }: { query: string }) {
  const params = new URLSearchParams(query);
  let data: Paginated<AssessmentInstrument>;
  try {
    data = await publicFetch<Paginated<AssessmentInstrument>>(`/assessments/?${params}`);
  } catch (error) {
    return <AssessmentUnavailable href={assessmentHref(params)} invalid={error instanceof ApiError && [400, 404].includes(error.status)} />;
  }
  const filtered = ["q", "construct", "intended_use", "form_kind", "language", "access", "license"].some(key => params.has(key));
  const page = data.previous ? Number(new URL(data.previous, "http://pagination.local").searchParams.get("page") || 1) + 1 : 1;
  return <section aria-labelledby="assessment-results-title">
    <div className="assessment-results-heading"><div><h2 id="assessment-results-title">خانواده‌های ابزارِ منتشرشده</h2><p>{faNumber(data.count)} خانواده{filtered ? " مطابق انتخاب شما" : " در این مجموعه"}</p></div>{filtered && <Link className="assessment-inline-link" href="/assessments">پاک‌کردن همهٔ انتخاب‌ها</Link>}</div>
    {filtered && <p className="assessment-notice">فیلترها وجودِ یک نسخهٔ مطابق را بررسی می‌کنند. فهرست و صفحهٔ خانواده، سایر نسخه‌های منتشرشده را نیز نمایش می‌دهند؛ مجوز یا شواهد یک فرم به فرم دیگر تعمیم ندارد.</p>}
    {data.results.length ? <div className="assessment-card-grid">{data.results.map(instrument => <AssessmentCard key={instrument.slug} instrument={instrument} />)}</div> : <div className="assessment-empty"><h3>{filtered ? "ابزاری مطابق این انتخاب پیدا نشد" : "هنوز ابزاری در این مجموعه منتشر نشده است"}</h3><p>{filtered ? "نام دیگری را جست‌وجو کنید یا فیلترها را بردارید." : "مرور ابزارها پس از انتشار داده‌های بازبینی‌شده و منبع‌دار ممکن می‌شود."}</p>{filtered && <Link className="button" href="/assessments">نمایش همهٔ ابزارها</Link>}</div>}
    {(data.previous || data.next) && <nav className="assessment-pagination" aria-label="صفحه‌های ابزارهای سنجش">
      {data.previous ? <Link className="button" href={assessmentPaginationHref(params, data.previous)} prefetch={false}>صفحهٔ قبل</Link> : <span />}
      <span>صفحهٔ {faNumber(page)}</span>
      {data.next ? <Link className="button" href={assessmentPaginationHref(params, data.next)} prefetch={false}>صفحهٔ بعد ←</Link> : <span />}
    </nav>}
  </section>;
}

export default async function AssessmentsPage({ searchParams }: { searchParams: Promise<Record<string, string | string[] | undefined>> }) {
  const { params, invalid } = assessmentQuery(await searchParams);
  return <main className="shell page stack assessment-page">
    <header className="assessment-hero"><div><span className="eyebrow">اطلس ابزارهای سنجش</span><h1>ابزار را با نسخه، شواهد و حقوقش بشناسید.</h1><p>نام فارسی، انگلیسی یا اختصار را جست‌وجو کنید و خانوادهٔ ابزار را به نسخه‌ها و فرم‌های دقیق آن دنبال کنید.</p><a className="assessment-inline-link" href="#assessment-browse">جست‌وجو و فیلتر ابزارها ↓</a></div><AssessmentScope /></header>
    <section id="assessment-browse" aria-label="جست‌وجو و فیلتر ابزارهای سنجش">
      <form action="/assessments" method="get" className="assessment-filter-form" key={params.toString()}>
        <div className="assessment-search-field"><label htmlFor="assessment-query">نام ابزار، نسخه یا اختصار</label><input id="assessment-query" name="q" type="search" dir="auto" maxLength={255} defaultValue={params.get("q") || ""} placeholder="نام فارسی یا انگلیسی…" /></div>
        <div><label htmlFor="assessment-purpose">کاربرد نسخه</label><select id="assessment-purpose" name="intended_use" defaultValue={params.get("intended_use") || ""}><option value="">همهٔ کاربردها</option>{Object.entries(assessmentIntendedUses).map(([value, label]) => <option key={value} value={value}>{label}</option>)}</select></div>
        <div><label htmlFor="assessment-kind">نوع نسخه</label><select id="assessment-kind" name="form_kind" defaultValue={params.get("form_kind") || ""}><option value="">همهٔ انواع</option>{Object.entries(assessmentFormKinds).map(([value, label]) => <option key={value} value={value}>{label}</option>)}</select></div>
        <div><label htmlFor="assessment-construct">شناسهٔ سازهٔ منتشرشده</label><input id="assessment-construct" name="construct" lang="en" dir="ltr" maxLength={120} defaultValue={params.get("construct") || ""} aria-describedby="assessment-descriptor-help" /></div>
        <div><label htmlFor="assessment-language">کد زبان فرم منتشرشده</label><input id="assessment-language" name="language" lang="en" dir="ltr" maxLength={16} defaultValue={params.get("language") || ""} aria-describedby="assessment-descriptor-help" /></div>
        <div><label htmlFor="assessment-access">وضعیت دسترسی</label><select id="assessment-access" name="access" defaultValue={params.get("access") || ""}><option value="">همهٔ وضعیت‌ها</option>{Object.entries(assessmentAvailabilities).map(([value, label]) => <option key={value} value={value}>{label}</option>)}</select></div>
        <div><label htmlFor="assessment-license">مجوز در دامنهٔ ثبت‌شده</label><select id="assessment-license" name="license" defaultValue={params.get("license") || ""}><option value="">همهٔ وضعیت‌ها</option>{Object.entries(assessmentLicenses).map(([value, label]) => <option key={value} value={value}>{label}</option>)}</select></div>
        {params.get("page_size") && <input type="hidden" name="page_size" value={params.get("page_size")!} />}
        <div className="assessment-actions"><button className="button primary" type="submit">اعمال انتخاب‌ها</button><Link className="assessment-inline-link" href="/assessments">پاک‌کردن</Link></div>
      </form>
      <p id="assessment-descriptor-help" className="muted">شناسهٔ سازه و کد زبان را از صفحهٔ ابزار انتخاب یا کپی کنید؛ فقط مقدارهای موجود در مجموعهٔ بازبینی‌شده پذیرفته می‌شوند. انتخاب تازه از صفحهٔ نخست شروع می‌شود.</p>
    </section>
    {invalid ? <AssessmentUnavailable href="/assessments" invalid /> : <Suspense key={params.toString()} fallback={<AssessmentLoading />}><AssessmentResults query={params.toString()} /></Suspense>}
  </main>;
}
