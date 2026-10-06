import Link from "next/link";
import { ArrowUpLeft, BookOpenText, GitBranch, Layers3 } from "lucide-react";
import type { BrainAnatomyBrief, BrainSourceLink } from "@/lib/types";
import { brainKinds, brainLateralities, brainName } from "@/lib/brain";
import { faNumber, ReviewStatus, ScientificSourceList } from "./ScientificMeta";

export function BrainLabel({ entity }: { entity: BrainAnatomyBrief }) {
  const persian = brainName(entity) !== entity.name_en;
  return <bdi lang={persian ? "fa" : "en"} dir={persian ? "rtl" : "ltr"}>{brainName(entity)}</bdi>;
}

export function BrainName({ entity, heading = false }: { entity: BrainAnatomyBrief; heading?: boolean }) {
  const persian = brainName(entity) !== entity.name_en;
  const name = <BrainLabel entity={entity} />;
  return <div className="brain-name">{heading ? <h1>{name}</h1> : <h3>{name}</h3>}{persian && <span className="brain-english" lang="en" dir="ltr">{entity.name_en}</span>}</div>;
}

export function BrainCard({ entity }: { entity: BrainAnatomyBrief }) {
  return <Link href={`/brain/${entity.slug}`} prefetch={false} className="brain-card">
    <div className="brain-card-meta"><span><Layers3 size={15} aria-hidden="true" />{brainKinds[entity.kind]}</span><span>{brainLateralities[entity.laterality]}</span></div>
    <BrainName entity={entity} />
    <div className="brain-card-foot"><span>ساختار و منابع</span><ArrowUpLeft size={19} aria-hidden="true" /></div>
  </Link>;
}

export function BrainLoading() {
  return <div className="brain-loading" role="status" aria-live="polite"><p>در حال بارگذاری اطلاعات اطلس مغز…</p><div className="brain-card-grid" aria-hidden="true">{[0, 1, 2, 3, 4, 5].map(key => <div className="brain-skeleton" key={key} />)}</div></div>;
}

export function BrainUnavailable({ href, invalid = false }: { href: string; invalid?: boolean }) {
  return <section className="brain-empty" role="alert"><BookOpenText size={28} aria-hidden="true" /><h2>{invalid ? "این انتخاب قابل نمایش نیست" : "اطلاعات مغز بارگذاری نشد"}</h2><p>{invalid ? "آدرس یا فیلترها معتبر نیستند؛ از فهرست ساختارها دوباره شروع کنید." : "ارتباط با سرویس برقرار نشد. کمی بعد دوباره تلاش کنید."}</p><div className="actions">{!invalid && <a href={href} className="button primary">تلاش دوباره</a>}<Link className="button" href="/brain">همهٔ ساختارها</Link></div></section>;
}

export function BrainSources({ links, truncated = false, title = "منابع این ساختار" }: { links: BrainSourceLink[]; truncated?: boolean; title?: string }) {
  return <div className="brain-sources"><ScientificSourceList sources={links.map(link => link.source)} title={title} />{links.some(link => link.note) && <details className="brain-disclosure"><summary>یادداشت‌های استناد</summary><ul>{links.filter(link => link.note).map((link, index) => <li key={`${link.source.id}-${index}`}><strong><bdi>{link.source.title}</bdi></strong><p dir="auto">{link.note}</p></li>)}</ul></details>}{truncated && <p className="muted">فهرست منابع در این پاسخ کامل نیست.</p>}</div>;
}

export function BrainAttribution() {
  return <details className="brain-disclosure brain-attribution"><summary><BookOpenText size={17} aria-hidden="true" />منبع داده و حقوق استفاده</summary><div className="stack">
    <p>داده‌های ساختاری این مجموعه، گزیده‌ای با نام‌گذاری و توضیحات آموزشی از <bdi lang="en">Foundational Model of Anatomy (FMA), 5.1.0</bdi>، متعلق به <bdi lang="en">University of Washington — Structural Informatics Group</bdi> هستند.</p>
    <p>این گزینش و ساده‌سازیِ سلسله‌مراتب تحت مجوز <a href="https://creativecommons.org/licenses/by/4.0/" target="_blank" rel="noreferrer" className="brain-inline-link"><bdi lang="en">CC BY 4.0</bdi></a> ارائه می‌شود؛ بدون ضمانت و بدون ادعای تأیید از سوی صاحب اثر. محدودیت استفادهٔ نرم‌افزار، حقوق داده‌های دارای این مجوز را محدود نمی‌کند.</p>
    <p>این رابط تصویر، مختصات یا مدل سه‌بعدی آناتومی ارائه نمی‌کند. نبود یک پیوند به معنای استقلال آناتومیک نیست؛ روابط عملکردی و عضویت شبکه‌ای نیز از این ساختارها استنباط نمی‌شوند.</p>
    <a href="https://github.com/uw-sig/FMA/tree/c6f70808ba2859b88cb0b8362c34fa9017c6f96a" target="_blank" rel="noreferrer" className="brain-inline-link">نسخهٔ منبع FMA ↗</a>
  </div></details>;
}

export function BrainReview({ entity, sources }: { entity: BrainAnatomyBrief; sources?: BrainSourceLink[] }) {
  return <div className="brain-review"><ReviewStatus status={entity.review_status} compact />{sources && <span>{faNumber(sources.length)} منبع در این پاسخ</span>}<span><GitBranch size={15} aria-hidden="true" />سلسله‌مراتب جزئیِ منتشرشده</span></div>;
}
