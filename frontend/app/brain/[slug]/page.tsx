import Link from "next/link";
import { notFound } from "next/navigation";
import { ArrowLeft, GitBranch } from "lucide-react";
import { ApiError, publicFetch } from "@/lib/api";
import { brainKinds, brainLateralities } from "@/lib/brain";
import type { BrainAnatomyDetail, BrainHierarchyLink } from "@/lib/types";
import { BrainAttribution, BrainLabel, BrainName, BrainReview, BrainSources, BrainUnavailable } from "@/components/BrainAtlas";
import { BilingualText } from "@/components/ScientificMeta";
import "../brain.css";

export const metadata = { title: "ساختار مغز | اطلس روان‌شناسی" };

function HierarchyClaim({ link }: { link: BrainHierarchyLink }) {
  return <details className="brain-disclosure"><summary>منبع پیوند آناتومی</summary><BilingualText fa={link.explanation_fa} en={link.explanation_en} empty="توضیح تکمیلی برای این پیوند منتشر نشده است." /><p className="muted">نسخهٔ منبع: <bdi lang="en">{link.source_version}</bdi> · رابطهٔ جزء از کل</p><BrainSources links={link.sources} truncated={link.sources_truncated} title="منابع پیوند" /></details>;
}

export default async function BrainDetailPage({ params }: { params: Promise<{ slug: string }> }) {
  const { slug } = await params;
  let entity: BrainAnatomyDetail;
  try {
    entity = await publicFetch<BrainAnatomyDetail>(`/brain-anatomy/${encodeURIComponent(slug)}/`);
  } catch (error) {
    if (error instanceof ApiError && error.status === 404) notFound();
    return <main className="shell page brain-page"><BrainUnavailable href={`/brain/${encodeURIComponent(slug)}`} /></main>;
  }
  return <main className="shell page stack brain-page brain-detail">
    <nav className="brain-breadcrumbs" aria-label="مسیر ساختار"><ol><li><Link href="/brain">اطلس مغز</Link></li>{entity.parent && <li><Link href={`/brain/${entity.parent.entity.slug}`} prefetch={false}><BrainLabel entity={entity.parent.entity} /></Link></li>}<li aria-current="page"><BrainLabel entity={entity} /></li></ol></nav>
    <header className="brain-detail-header"><div className="eyebrow">{brainKinds[entity.kind]} · {brainLateralities[entity.laterality]}</div><BrainName entity={entity} heading /><BrainReview entity={entity} sources={entity.sources} /></header>
    <div className="brain-detail-grid"><div className="stack">
      <section className="brain-panel"><h2>دربارهٔ این ساختار</h2><BilingualText fa={entity.description_fa} en={entity.description_en} empty="برای این ساختار، توضیح تکمیلی منتشر نشده است." /></section>
      {!!entity.aliases.length && <section className="brain-panel"><h2>نام‌های جایگزین</h2><ul className="brain-aliases">{entity.aliases.map((alias, index) => <li key={`${alias.text}-${index}`}><bdi lang={alias.language} dir={alias.language === "fa" ? "rtl" : "ltr"}>{alias.text}</bdi><span>{alias.language === "fa" ? "فارسی" : "انگلیسی"} · {alias.alias_type === "abbreviation" ? "اختصار" : alias.alias_type === "historical" ? "نام تاریخی" : alias.alias_type === "transliteration" ? "آوانویسی" : "نام جایگزین"}</span><details className="brain-disclosure"><summary>منبع نام</summary><p dir="auto">{alias.source_note}</p><BrainSources links={[{ source: alias.source, note: alias.source_note }]} title="استناد نام" /></details></li>)}</ul>{entity.aliases_truncated && <p className="muted">فهرست نام‌ها در این پاسخ کامل نیست.</p>}</section>}
      {!!entity.external_identifiers.length && <section className="brain-panel"><h2>شناسه‌های مرجع</h2><p className="muted">این شناسه‌ها برای مراجعه به منبع‌اند؛ معادل‌بودن فضایی اطلس‌ها را نشان نمی‌دهند.</p><ul className="brain-identifiers">{entity.external_identifiers.map((identifier, index) => <li key={`${identifier.namespace}-${identifier.identifier}-${index}`}><div><strong><bdi lang="en">{identifier.namespace}</bdi></strong><span><bdi lang="en">{identifier.source_version}</bdi></span></div>{identifier.url ? <a href={identifier.url} target="_blank" rel="noreferrer" className="brain-inline-link"><bdi lang="en">{identifier.identifier}</bdi> ↗</a> : <bdi lang="en">{identifier.identifier}</bdi>}<details className="brain-disclosure"><summary>منبع نگاشت شناسه</summary><p dir="auto">{identifier.source_note}</p><BrainSources links={[{ source: identifier.source, note: identifier.source_note }]} title="استناد شناسه" /></details></li>)}</ul>{entity.external_identifiers_truncated && <p className="muted">فهرست شناسه‌ها در این پاسخ کامل نیست.</p>}</section>}
      <section className="brain-panel"><BrainSources links={entity.sources} truncated={entity.sources_truncated} /></section>
    </div><aside className="brain-hierarchy brain-panel" aria-labelledby="brain-hierarchy-title"><div className="eyebrow"><GitBranch size={18} aria-hidden="true" />جایگاه منتشرشده</div><h2 id="brain-hierarchy-title">در سلسله‌مراتب آناتومی</h2>
      <h3>والد منتشرشده</h3>{entity.parent ? <div className="brain-hierarchy-parent"><Link href={`/brain/${entity.parent.entity.slug}`} prefetch={false} className="brain-inline-link"><BrainLabel entity={entity.parent.entity} /></Link><HierarchyClaim link={entity.parent} /></div> : <p className="muted">برای این ساختار، والد منتشرشده‌ای ثبت نشده است. این به معنای استقلال آناتومیک نیست.</p>}
      <div className="brain-hierarchy-current"><span>این ساختار</span><strong><BrainLabel entity={entity} /></strong></div>
      <h3>زیرساختارهای منتشرشده</h3>{entity.children.length ? <ul className="brain-children">{entity.children.map(link => <li key={link.entity.slug}><Link href={`/brain/${link.entity.slug}`} prefetch={false}><BrainLabel entity={link.entity} /><ArrowLeft size={15} aria-hidden="true" /></Link><HierarchyClaim link={link} /></li>)}</ul> : <p className="muted">زیرساختاری در این سلسله‌مراتب منتشر نشده است.</p>}
      {entity.children_truncated && <p className="muted">فقط بخشی از زیرساختارها در این پاسخ آمده است.</p>}{(entity.children.length > 0 || entity.children_truncated) && <Link className="button" href={`/brain?parent=${entity.slug}`}>مرور همهٔ زیرساختارها <ArrowLeft size={16} aria-hidden="true" /></Link>}
      <p className="brain-hierarchy-note">پیوندها فقط رابطهٔ آناتومیِ «جزء از کل» هستند. عملکرد، تشخیص یا عضویت در شبکه از آن‌ها نتیجه نمی‌شود.</p><Link className="brain-inline-link" href="/brain?roots=true">مرور شاخه‌های بدون والد منتشرشده</Link>
    </aside></div>
    <BrainAttribution /><Link className="brain-inline-link" href="/brain">بازگشت به اطلس مغز</Link>
  </main>;
}
