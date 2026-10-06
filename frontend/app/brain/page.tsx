import { Suspense } from "react";
import Link from "next/link";
import type { Metadata } from "next";
import { ArrowLeft, GitBranch, Search } from "lucide-react";
import { ApiError, publicFetch } from "@/lib/api";
import { brainHref, brainKinds, brainLateralities } from "@/lib/brain";
import type { BrainAnatomy, BrainAnatomyDetail, Paginated } from "@/lib/types";
import { BrainAttribution, BrainCard, BrainLabel, BrainLoading, BrainUnavailable } from "@/components/BrainAtlas";
import { faNumber } from "@/components/ScientificMeta";
import "./brain.css";

export const metadata: Metadata = { title: "اطلس مغز | اطلس روان‌شناسی", description: "مرور ساختارهای منتشرشدهٔ مغز، سلسله‌مراتب آناتومی و منابع علمی." };

async function BrainResults({ query }: { query: string }) {
  const params = new URLSearchParams(query);
  let data: Paginated<BrainAnatomy>;
  let parent: BrainAnatomyDetail | null;
  try {
    [data, parent] = await Promise.all([
      publicFetch<Paginated<BrainAnatomy>>(`/brain-anatomy/?${params}`),
      params.get("parent") ? publicFetch<BrainAnatomyDetail>(`/brain-anatomy/${encodeURIComponent(params.get("parent")!)}/`) : Promise.resolve(null),
    ]);
  } catch (error) {
    return <BrainUnavailable href={brainHref(params)} invalid={error instanceof ApiError && [400, 404].includes(error.status)} />;
  }
  const page = data.previous ? Number(new URL(data.previous).searchParams.get("page") || 1) + 1 : 1;
  const filtered = ["q", "kind", "laterality", "parent", "roots"].some(key => !!params.get(key));
  return <section className="brain-results" aria-labelledby="brain-results-title">
    {parent && <div className="brain-parent-context"><GitBranch size={21} aria-hidden="true" /><div><span>زیرساختارهای منتشرشدهٔ</span><h2><BrainLabel entity={parent} /></h2><Link href={`/brain/${parent.slug}`} prefetch={false} className="brain-inline-link">مشاهدهٔ ساختار والد و منابع</Link></div></div>}
    <div className="brain-results-heading"><div><h2 id="brain-results-title">{params.get("roots") === "true" ? "ساختارهای بدون والد منتشرشده" : "ساختارهای منتشرشده"}</h2><p>{faNumber(data.count)} ساختار{filtered ? " مطابق انتخاب شما" : " در این مجموعه"}</p></div>{filtered && <Link className="brain-inline-link" href="/brain">پاک‌کردن انتخاب‌ها</Link>}</div>
    {data.results.length ? <div className="brain-card-grid">{data.results.map(entity => <BrainCard entity={entity} key={entity.slug} />)}</div> : <div className="brain-empty"><Search size={28} aria-hidden="true" /><h3>{filtered ? "ساختاری مطابق این انتخاب پیدا نشد" : "هنوز ساختاری منتشر نشده است"}</h3><p>{filtered ? "نام دیگری را جست‌وجو کنید یا فیلترها را بردارید." : "این بخش پس از انتشار داده‌های بازبینی‌شده قابل مرور خواهد بود."}</p>{filtered && <Link className="button" href="/brain">نمایش همهٔ ساختارها</Link>}</div>}
    {(data.previous || data.next) && <nav className="brain-pagination" aria-label="صفحه‌های ساختارهای مغز">{data.previous ? <Link className="button" href={brainHref(params, { page: String(page - 1) })} prefetch={false}>صفحهٔ قبل</Link> : <span />}<span>صفحهٔ {faNumber(page)}</span>{data.next ? <Link className="button" href={brainHref(params, { page: String(page + 1) })} prefetch={false}>صفحهٔ بعد <ArrowLeft size={16} aria-hidden="true" /></Link> : <span />}</nav>}
  </section>;
}

export default async function BrainPage({ searchParams }: { searchParams: Promise<Record<string, string | string[] | undefined>> }) {
  const values = await searchParams;
  const params = new URLSearchParams();
  const keys = ["q", "kind", "laterality", "parent", "roots", "page"];
  const repeated = keys.some(key => Array.isArray(values[key]));
  for (const key of keys) if (typeof values[key] === "string" && values[key].trim()) params.set(key, values[key].trim());
  return <main className="shell page stack brain-page">
    <header className="brain-hero"><div><div className="eyebrow"><GitBranch size={18} aria-hidden="true" />اطلس مغز</div><h1>مغز را از ساختارهایش بشناس.</h1><p>از نام یک ساختار شروع کنید، جایگاه آن را در سلسله‌مراتب ببینید و به منابعش برسید.</p><div className="brain-hero-actions"><Link className="button primary" href="/brain?roots=true">شروع از شاخه‌های منتشرشده <ArrowLeft size={16} aria-hidden="true" /></Link><a className="brain-inline-link" href="#brain-browse">جست‌وجوی ساختار</a></div></div><aside className="brain-scope"><span>راهنمای این مجموعه</span><h2>ساختار، جایگاه، منبع</h2><p>این مجموعه یک سلسله‌مراتب جزئی با چند شاخهٔ مستقل است؛ نقشهٔ کامل مغز یا نقشهٔ عملکردها نیست.</p><p>نام‌های فارسی فقط در صورت بازبینی نمایش داده می‌شوند. نام علمی انگلیسی، مبنای مرور سایر ساختارهاست.</p></aside></header>
    <section id="brain-browse" className="brain-browse" aria-label="جست‌وجو و فیلتر ساختارها">
      <nav className="brain-view-tabs" aria-label="روش مرور"><Link href="/brain" aria-current={params.get("roots") !== "true" && !params.get("parent") ? "page" : undefined}>همهٔ ساختارها</Link><Link href="/brain?roots=true" aria-current={params.get("roots") === "true" ? "page" : undefined}>بدون والد منتشرشده</Link></nav>
      <form action="/brain" method="get" className="brain-filter-form" key={params.toString()}>
        <div className="brain-search-field"><label htmlFor="brain-search">نام ساختار یا نام جایگزین</label><div><Search size={18} aria-hidden="true" /><input id="brain-search" name="q" type="search" dir="auto" maxLength={255} defaultValue={params.get("q") || ""} placeholder="نام فارسی یا انگلیسی…" /></div></div>
        <div><label htmlFor="brain-kind">نوع ساختار</label><select id="brain-kind" name="kind" defaultValue={params.get("kind") || ""}><option value="">همهٔ انواع</option>{Object.entries(brainKinds).map(([value, label]) => <option key={value} value={value}>{label}</option>)}</select></div>
        <div><label htmlFor="brain-laterality">سمت</label><select id="brain-laterality" name="laterality" defaultValue={params.get("laterality") || ""}><option value="">همهٔ سمت‌ها</option>{Object.entries(brainLateralities).map(([value, label]) => <option key={value} value={value}>{label}</option>)}</select></div>
        {params.get("parent") && <input type="hidden" name="parent" value={params.get("parent")!} />}
        {params.get("roots") && <input type="hidden" name="roots" value={params.get("roots")!} />}
        <button className="button primary" type="submit">اعمال انتخاب‌ها</button>
      </form>
    </section>
    {repeated ? <BrainUnavailable href="/brain" invalid /> : <Suspense key={params.toString()} fallback={<BrainLoading />}><BrainResults query={params.toString()} /></Suspense>}
    <BrainAttribution />
  </main>;
}
