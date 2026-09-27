import Link from "next/link";
import { ArrowUpLeft, BookOpenText, Brain, CalendarDays, Layers3, Network, Search, Sparkles } from "lucide-react";
import HomeStudyEntry from "@/components/HomeStudyEntry";
import { publicFetch } from "@/lib/api";
import type { AtlasOverview } from "@/lib/types";

const fa = (value: number) => value.toLocaleString("fa-IR");
const pathways = [
  { href: "/disorders", title: "اختلالات", description: "از نشانه و افتراق تا پیوندهای مفهومی", icon: Brain, accent: "sage" },
  { href: "/concepts", title: "مفاهیم", description: "تعریف، مثال و رابطه با دانش بالینی", icon: Layers3, accent: "violet" },
  { href: "/therapies", title: "درمان‌ها", description: "رویکردها، تکنیک‌ها و زمینهٔ شواهد", icon: BookOpenText, accent: "blue" },
] as const;

export default async function Home() {
  const overview = await publicFetch<AtlasOverview>("/atlas-overview/").catch(() => null);
  return <main className="shell atlas-home">
    <section className="home-welcome">
      <div className="home-welcome-copy">
        <div className="eyebrow"><span className="eyebrow-line" /> اطلس یادگیری روان‌شناسی</div>
        <h1>دانش را به هم وصل کن.<br /><span>یادگیری را ادامه بده.</span></h1>
        <p>از یک مفهوم شروع کن، رابطه‌های مستندش را ببین و آنچه آموخته‌ای را با مرور و تمرین دنبال کن.</p>
        <div className="home-search-row">
          <Link href="/search" className="home-search-prompt"><Search size={19} aria-hidden="true" /><span>در اختلالات، مفاهیم، درمان‌ها و تاریخ جست‌وجو کن</span><kbd>جست‌وجو</kbd></Link>
        </div>
      </div>
      <aside className="home-orientation" aria-label="راه‌های شروع">
        <span className="home-orientation-mark"><Network size={25} aria-hidden="true" /></span>
        <p>هر موضوع، بخشی از یک شبکهٔ دانش است.</p>
        <div><Link href="/map">دیدن نقشهٔ دانش <ArrowUpLeft size={16} aria-hidden="true" /></Link><Link href="/timeline">کاوش تاریخ روان‌شناسی <ArrowUpLeft size={16} aria-hidden="true" /></Link></div>
      </aside>
    </section>

    <div className="home-columns">
      <div className="home-primary-column">
        <HomeStudyEntry />
        <section className="home-section" aria-labelledby="atlas-pathways-title">
          <div className="home-section-heading"><div><span className="eyebrow">کاوش اطلس</span><h2 id="atlas-pathways-title">از کجا می‌خواهی شروع کنی؟</h2><p>سه مسیر اصلی برای ساختن تصویری پیوسته از روان‌شناسی.</p></div><Link href="/map" className="text-link">همهٔ ارتباط‌ها <ArrowUpLeft size={16} aria-hidden="true" /></Link></div>
          <div className="home-pathways">{pathways.map(item => <Link href={item.href} key={item.href} className={`home-pathway home-pathway-${item.accent}`}><span className="home-pathway-icon"><item.icon size={23} aria-hidden="true" /></span><strong>{item.title}</strong><p>{item.description}</p><span className="home-pathway-action">کاوش <ArrowUpLeft size={16} aria-hidden="true" /></span></Link>)}</div>
        </section>
        <section className="home-map-entry" aria-labelledby="home-map-title">
          <div><span className="eyebrow">نقشهٔ دانش</span><h2 id="home-map-title">فراتر از یک فهرست موضوعی</h2><p>ارتباط میان اختلال، مفهوم، درمان و تاریخ را از داده‌های ساختاریافتهٔ اطلس دنبال کن.</p><Link href="/map" className="button">باز کردن نقشه <ArrowUpLeft size={16} aria-hidden="true" /></Link></div>
          <div className="home-map-diagram" aria-hidden="true"><span>مفهوم</span><span>اختلال</span><span>درمان</span><span>نظریه</span><span>تاریخ</span></div>
        </section>
      </div>
      <aside className="home-side-column" aria-label="ابزارهای یادگیری">
        <section className="home-side-section"><div className="home-side-heading"><CalendarDays size={19} aria-hidden="true" /><h2>مسیر مطالعه</h2></div><p>برنامه، مرور فاصله‌دار و پیشنهادهای توضیح‌پذیر را در یک‌جا ببین.</p><Link href="/study" className="button primary">رفتن به مرکز مطالعه</Link></section>
        <section className="home-side-section"><div className="home-side-heading"><Sparkles size={19} aria-hidden="true" /><h2>تمرین فعال</h2></div><div className="home-side-links"><Link href="/flashcards">فلش‌کارت‌ها <ArrowUpLeft size={15} /></Link><Link href="/quizzes">آزمون‌ها <ArrowUpLeft size={15} /></Link><Link href="/cases">کیس‌های بالینی <ArrowUpLeft size={15} /></Link></div></section>
        {overview && <section className="home-side-section home-atlas-numbers"><div className="home-side-heading"><BookOpenText size={19} aria-hidden="true" /><h2>در اطلس</h2></div><div><span><strong>{fa(overview.counts.disorders)}</strong> اختلال فعال</span><span><strong>{fa(overview.counts.concepts)}</strong> مفهوم</span><span><strong>{fa(overview.graph.edges)}</strong> رابطهٔ ثبت‌شده</span></div><p>این شمارش‌ها از دادهٔ فعلی اطلس می‌آیند.</p></section>}
      </aside>
    </div>
  </main>;
}
