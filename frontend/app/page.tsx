import Link from "next/link";
import DailyChallengeCard from "@/components/DailyChallengeCard";
import { publicFetch } from "@/lib/api";
import type { AtlasOverview, DSMOverview, Paginated, Psychologist, Theory, TimelineEvent } from "@/lib/types";

function fa(value: number) {
  return value.toLocaleString("fa-IR");
}

export default async function Home() {
  const [overviewResult, dsmResult, psychologistResult, theoryResult, timelineResult] = await Promise.allSettled([
    publicFetch<AtlasOverview>("/atlas-overview/"),
    publicFetch<DSMOverview>("/dsm/overview/"),
    publicFetch<Paginated<Psychologist>>("/psychologists/?page_size=1"),
    publicFetch<Paginated<Theory>>("/theories/?page_size=1"),
    publicFetch<Paginated<TimelineEvent>>("/timeline/?page_size=1"),
  ]);
  const overview = overviewResult.status === "fulfilled" ? overviewResult.value : null;
  const dsmOverview = dsmResult.status === "fulfilled" ? dsmResult.value : null;
  const psychologistCount = psychologistResult.status === "fulfilled" ? psychologistResult.value.count : null;
  const theoryCount = theoryResult.status === "fulfilled" ? theoryResult.value.count : null;
  const timelineCount = timelineResult.status === "fulfilled" ? timelineResult.value.count : null;

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
          <div className="meta">Psychology Atlas · v0.6.6</div>
          <h1>روان‌شناسی را مثل یک شبکه تاریخی و مفهومی یاد بگیر، نه یک فهرست پراکنده.</h1>
          <p>
            اختلال، نشانه، مفهوم و درمان را کنار روان‌شناسان، نظریه‌ها و رویدادهای تاریخی دنبال کن. بعد با Quiz، Clinical Case، فلش‌کارت،
            مرور فاصله‌دار و چالش روزانه همان ساختار را به مسیر مطالعه شخصی تبدیل کن.
          </p>
          <div className="actions atlas-hero-actions">
            <Link className="button primary" href="/timeline">کاوش خط زمانی</Link>
            <Link className="button" href="/psychologists">روان‌شناسان</Link>
            <Link className="button" href="/theories">نظریه‌ها</Link>
            <Link className="button" href="/therapies">اطلس درمان</Link>
            <Link className="button" href="/map">نقشه دانش فعلی</Link>
            <Link className="button ghost" href="/study">مرکز مطالعه</Link>
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

      {(psychologistCount != null || theoryCount != null || timelineCount != null) && (
        <section className="shell v6-home-domain-strip" aria-label="دامنه‌های تاریخی نسخه ۰.۶">
          <Link href="/psychologists"><strong>{psychologistCount != null ? fa(psychologistCount) : "—"}</strong><span>روان‌شناس canonical</span><small>Psychologists Atlas</small></Link>
          <Link href="/theories"><strong>{theoryCount != null ? fa(theoryCount) : "—"}</strong><span>نظریه canonical</span><small>Theory Atlas</small></Link>
          <Link href="/timeline"><strong>{timelineCount != null ? fa(timelineCount) : "—"}</strong><span>رویداد تاریخی</span><small>Psychology Timeline</small></Link>
        </section>
      )}

      <section className="shell page stack home-v3-sections">
        <div className="section-heading-row">
          <div>
            <h2 className="section-title">از محتوا تا یادگیری فعال</h2>
            <p className="section-copy">لایه‌های بالینی، مفهومی، درمانی و تاریخی کنار ابزارهای یادگیری یک مسیر پیوسته می‌سازند.</p>
          </div>
          <Link className="button ghost" href="/map">مشاهده Graph فعلی</Link>
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
          <Link href="/psychologists" className="learning-rail-item">
            <span className="rail-index">۰۵</span><div><strong>Psychologists Atlas</strong><p>{psychologistCount != null ? `${fa(psychologistCount)} identity canonical با alias، attribution و sourceهای مستقیم.` : "Identity، alias، attribution و provenance شخصیت‌های تاریخی."}</p></div>
          </Link>
          <Link href="/theories" className="learning-rail-item">
            <span className="rail-index">۰۶</span><div><strong>Theory Atlas</strong><p>{theoryCount != null ? `${fa(theoryCount)} نظریه با domain، modern status و relationهای صریح.` : "نظریه‌ها با domain، status و relationهای source-backed."}</p></div>
          </Link>
          <Link href="/timeline" className="learning-rail-item">
            <span className="rail-index">۰۷</span><div><strong>Psychology Timeline</strong><p>{timelineCount != null ? `${fa(timelineCount)} رویداد precision-aware با اتصال‌های تاریخی explicit.` : "رویدادهای تاریخی با date precision و provenance رابطه."}</p></div>
          </Link>
          <Link href="/map" className="learning-rail-item">
            <span className="rail-index">۰۸</span><div><strong>Knowledge Graph یکپارچه</strong><p>Psychologist، Theory و Timeline اکنون کنار دامنه‌های قبلی با edgeهای صریح، provenance و pathfinding واقعی وارد Graph شده‌اند.</p></div>
          </Link>
          <Link href="/study" className="learning-rail-item">
            <span className="rail-index">۰۹</span><div><strong>Study Engine</strong><p>SRS، streak، heatmap، challenge و پیشنهاد مرور.</p></div>
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
