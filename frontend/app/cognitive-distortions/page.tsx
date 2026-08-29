import Link from "next/link";
import DistortionPractice from "@/components/DistortionPractice";
import { publicFetch } from "@/lib/api";
import type { CognitiveDistortionsOverview } from "@/lib/types";

export default async function CognitiveDistortionsPage() {
  const data = await publicFetch<CognitiveDistortionsOverview>("/cognitive-distortions/overview/");

  return (
    <main className="shell page stack distortion-page">
      <header className="distortion-hero">
        <div>
          <div className="meta">Cognitive Distortions Explorer</div>
          <h1>تحریف شناختی را تعریف نکن؛ الگوی استدلالش را تشخیص بده.</h1>
          <p>این بخش تحریف‌ها را به‌عنوان subtype واقعی Concept نگه می‌دارد. هر مورد تعریف، مثال، counterexample، cueهای تشخیص، افتراق مفهومی، منبع و اتصال به Knowledge Graph دارد.</p>
          <div className="actions">
            <a className="button primary" href="#practice">شروع تمرین تشخیص</a>
            <Link className="button" href="/map?node=concept:cognitive-distortions">بازکردن در Knowledge Graph</Link>
            <Link className="button" href="/concepts">همه مفاهیم</Link>
          </div>
        </div>
        <div className="distortion-hero-metrics">
          <div><strong>{data.count.toLocaleString("fa-IR")}</strong><span>تحریف ساختاریافته</span></div>
          <div><strong>{data.practice_count.toLocaleString("fa-IR")}</strong><span>تمرین تشخیص</span></div>
          <div><strong>{data.items.reduce((sum, item) => sum + (item.flashcard_count ?? 0), 0).toLocaleString("fa-IR")}</strong><span>فلش‌کارت مرتبط</span></div>
        </div>
      </header>

      <section className="stack">
        <div>
          <div className="meta">Distortion Catalog</div>
          <h2 className="section-title">۱۲ الگوی آموزشی منبع‌دار</h2>
          <p className="section-copy">این فهرست به‌عنوان taxonomy آموزشی پروژه ثبت شده است و به‌معنای وجود یک فهرست جهانی و رسمی واحد برای همه منابع CBT نیست.</p>
        </div>
        <div className="distortion-grid">
          {data.items.map(item => (
            <Link className="card distortion-card" href={`/concepts/${item.slug}`} key={item.slug}>
              <div className="distortion-card-topline">
                <span className="meta">{item.domain_label || item.domain}</span>
                <span>{(item.relationship_count ?? 0).toLocaleString("fa-IR")} رابطه</span>
              </div>
              <h3>{item.name_fa || item.name_en}</h3>
              <div className="latin-title">{item.name_en}</div>
              <p>{item.simple_definition}</p>
              {!!item.aliases?.length && <small>نام‌های جایگزین: {item.aliases.map(alias => alias.text).join(" · ")}</small>}
              <div className="distortion-card-footer">
                <span>{(item.flashcard_count ?? 0).toLocaleString("fa-IR")} فلش‌کارت</span>
                <span>{(item.disorder_count ?? 0).toLocaleString("fa-IR")} اختلال مرتبط</span>
              </div>
            </Link>
          ))}
        </div>
      </section>

      <DistortionPractice totalAvailable={data.practice_count} />
    </main>
  );
}
