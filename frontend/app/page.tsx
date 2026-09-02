import Link from "next/link";
import DailyChallengeCard from "@/components/DailyChallengeCard";
import { publicFetch } from "@/lib/api";
import type { AtlasOverview, DSMOverview } from "@/lib/types";

function fa(value: number) {
  return value.toLocaleString("fa-IR");
}

export default async function Home() {
  let overview: AtlasOverview | null = null;
  let dsmOverview: DSMOverview | null = null;
  try {
    [overview, dsmOverview] = await Promise.all([
      publicFetch<AtlasOverview>("/atlas-overview/"),
      publicFetch<DSMOverview>("/dsm/overview/"),
    ]);
  } catch {
    try { overview = await publicFetch<AtlasOverview>("/atlas-overview/"); } catch { overview = null; }
    try { dsmOverview = await publicFetch<DSMOverview>("/dsm/overview/"); } catch { dsmOverview = null; }
  }

  const stats = overview ? [
    [overview.counts.disorders, "اختلال فعال"],
    [overview.counts.concepts, "مفهوم ساختاریافته"],
    [overview.counts.symptoms, "نشانه متصل"],
    [overview.graph.edges, "رابطه واقعی"],
  ] as const : [];

  return (
    <main>
      <section className="shell hero hero-v3 atlas-hero">
        <div className="atlas-hero-copy">
          <div className="meta">Psychology Atlas · v0.5.4</div>
          <h1>روان‌شناسی را مثل یک شبکه یاد بگیر، نه یک فهرست پراکنده.</h1>
          <p>
            اختلال، نشانه، مفهوم و رویکرد درمانی را در یک مدل واحد دنبال کن. بعد با Quiz، Clinical Case، فلش‌کارت،
            مرور فاصله‌دار و چالش روزانه همان شبکه را به مسیر مطالعه شخصی تبدیل کن.
          </p>
          <div className="actions atlas-hero-actions">
            <Link className="button primary" href="/map">کاوش نقشه دانش</Link>
            <Link className="button" href="/dsm">DSM MASTER</Link>
            <Link className="button" href="/therapies">اطلس درمان</Link>
            <Link className="button" href="/study">مرکز مطالعه</Link>
            <Link className="button ghost" href="/search">جست‌وجوی سراسری</Link>
          </div>
        </div>

        <aside className="atlas-hero-network" aria-label="نمای کلی شبکه دانش">
          <div className="network-core-mark">PA</div>
          <div className="network-line network-line-a" />
          <div className="network-line network-line-b" />
          <div className="network-line network-line-c" />
          <Link href="/concepts" className="network-float network-float-a"><strong>Concept</strong><span>تعریف و رابطه</span></Link>
          <Link href="/disorders" className="network-float network-float-b"><strong>Disorder</strong><span>نشانه و افتراق</span></Link>
          <Link href="/search" className="network-float network-float-c"><strong>Symptom</strong><span>اتصال به اختلال</span></Link>
          <div className="network-caption">شبکه از داده ساختاریافته دیتابیس ساخته می‌شود، نه similarity ساختگی.</div>
        </aside>
      </section>

      {stats.length > 0 && (
        <section className="shell atlas-overview-strip" aria-label="آمار فعلی اطلس">
          {stats.map(([value, label]) => (
            <div className="atlas-overview-stat" key={label}>
              <strong>{fa(value)}</strong>
              <span>{label}</span>
            </div>
          ))}
        </section>
      )}

      <section className="shell page stack home-v3-sections">
        <div className="section-heading-row">
          <div>
            <h2 className="section-title">از محتوا تا یادگیری فعال</h2>
            <p className="section-copy">سه لایه محصول به هم متصل‌اند و هرکدام ورودی لایه بعدی است.</p>
          </div>
          <Link className="button ghost" href="/map">مشاهده کل شبکه</Link>
        </div>

        <div className="learning-rail">
          <Link href="/disorders" className="learning-rail-item">
            <span className="rail-index">۰۱</span><div><strong>اطلس بالینی</strong><p>اختلالات، نشانه‌ها، افتراق و منابع آموزشی.</p></div>
          </Link>
          <Link href="/dsm" className="learning-rail-item dsm-learning-rail-item">
            <span className="rail-index">۰۲</span><div><strong>DSM MASTER</strong><p>{dsmOverview ? `${fa(dsmOverview.counts.records)} گره ممیزی‌شده با وضعیت طبقه‌بندی، ارزیابی، افتراق و منابع.` : "مرجع ساختاری DSM-5-TR فارسی با تفکیک نوع رکورد."}</p></div>
          </Link>
          <Link href="/concepts" className="learning-rail-item">
            <span className="rail-index">۰۳</span><div><strong>اطلس مفاهیم</strong><p>تعریف ساده و دانشگاهی، مثال و رابطه با اختلالات.</p></div>
          </Link>
          <Link href="/therapies" className="learning-rail-item">
            <span className="rail-index">۰۴</span><div><strong>Therapy Atlas</strong><p>رویکردها، تکنیک‌ها، زمینه‌های بالینی، شواهد و provenance ساختاریافته.</p></div>
          </Link>
          <Link href="/map" className="learning-rail-item">
            <span className="rail-index">۰۵</span><div><strong>Knowledge Graph</strong><p>حرکت بین Concept، Disorder و Symptom بر اساس edge واقعی.</p></div>
          </Link>
          <Link href="/study" className="learning-rail-item">
            <span className="rail-index">۰۶</span><div><strong>Study Engine</strong><p>SRS، streak، heatmap، challenge و پیشنهاد مرور.</p></div>
          </Link>
        </div>

        {overview && (
          <section className="atlas-data-section">
            <div className="atlas-data-main card">
              <div className="meta">ساختار دیتای فعلی</div>
              <h2>اطلس فقط تعداد صفحه نیست، یک مدل رابطه‌ای است.</h2>
              <div className="data-meter-list">
                {overview.categories.map(category => (
                  <div className="data-meter" key={category.slug}>
                    <div><strong>{category.name_fa || category.name_en}</strong><span>{fa(category.count)} اختلال</span></div>
                    <div className="data-meter-track"><span style={{ width: `${Math.max(8, category.count / Math.max(...overview.categories.map(row => row.count)) * 100)}%` }} /></div>
                  </div>
                ))}
              </div>
            </div>
            <div className="atlas-data-side card">
              <div className="meta">Learning inventory</div>
              <div className="data-big-number">{fa(overview.counts.flashcards)}</div><span>فلش‌کارت فعال</span>
              <div className="data-side-grid">
                <div><strong>{fa(overview.counts.quizzes)}</strong><span>Quiz</span></div>
                <div><strong>{fa(overview.counts.clinical_cases)}</strong><span>Case</span></div>
                <div><strong>{fa(overview.counts.daily_challenges)}</strong><span>Challenge</span></div>
                <div><strong>{fa(overview.graph.nodes)}</strong><span>Graph Node</span></div>
              </div>
            </div>
          </section>
        )}

        <div className="grid-2 home-secondary-grid">
          <DailyChallengeCard />
          <div className="card learning-loop-panel">
            <div className="meta">Learning loop</div>
            <h2>هر فعالیت باید به مرحله بعدی مطالعه وصل شود.</h2>
            <div className="loop-steps">
              <span>یادگیری</span><span>تمرین</span><span>سنجش</span><span>تشخیص ضعف</span><span>مرور</span>
            </div>
            <p>Quiz و Case فقط نمره نیستند؛ در کنار View و Flashcard به Progress، Activity و پیشنهادهای مطالعه وصل می‌شوند.</p>
            <div className="actions">
              <Link className="button" href="/quizzes">آزمون‌ها</Link>
              <Link className="button" href="/cases">کیس‌های بالینی</Link>
              <Link className="button" href="/flashcards">فلش‌کارت‌ها</Link>
            </div>
          </div>
        </div>
      </section>
    </main>
  );
}
