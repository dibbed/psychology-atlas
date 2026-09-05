import Link from "next/link";
import TimelineExplorer from "@/components/TimelineExplorer";
import { publicFetch } from "@/lib/api";
import type { Paginated, TimelineEvent } from "@/lib/types";

type SearchParams = Promise<Record<string, string | string[] | undefined>>;

const relationParams = ["psychologist", "theory", "therapy", "technique", "concept"] as const;

export default async function TimelinePage({ searchParams }: { searchParams: SearchParams }) {
  const raw = await searchParams;
  const query = new URLSearchParams({ page_size: "300" });
  const scope: { key: string; value: string }[] = [];

  for (const key of relationParams) {
    const value = raw[key];
    if (typeof value === "string" && value.trim()) {
      query.set(key, value.trim());
      scope.push({ key, value: value.trim() });
    }
  }

  const dataPromise = publicFetch<Paginated<TimelineEvent>>(`/timeline/?${query.toString()}`);
  const totalPromise = scope.length
    ? publicFetch<Paginated<TimelineEvent>>("/timeline/?page_size=1")
    : null;
  const [data, totalData] = await Promise.all([dataPromise, totalPromise]);
  const totalCount = totalData?.count ?? data.count;

  return (
    <main className="shell page stack timeline-page v6-atlas-page">
      <header className="v6-atlas-head timeline-page-head">
        <div className="v6-atlas-copy">
          <div className="meta">Psychology Timeline · v0.6.4</div>
          <h1>تاریخ روان‌شناسی را روی یک محور زمانی provenance-aware دنبال کن.</h1>
          <p>رویدادها به Psychologist، Theory، Therapy، Technique و Concept فقط وقتی متصل می‌شوند که edge صریح runtime وجود داشته باشد. دقت سال/بازه/تاریخ نیز عین API حفظ می‌شود.</p>
          <div className="actions">
            <Link className="button primary" href="/psychologists">اطلس روان‌شناسان</Link>
            <Link className="button" href="/theories">اطلس نظریه‌ها</Link>
          </div>
        </div>
        <aside className="v6-atlas-head-stat timeline-head-stat">
          <strong>{data.count.toLocaleString("fa-IR")}</strong><span>{scope.length ? "رویداد در نمای محدود فعلی" : "رویداد canonical"}</span>
          <div><b>{totalCount.toLocaleString("fa-IR")}</b><small>کل رویدادهای فعال Timeline</small></div>
        </aside>
      </header>

      {scope.length > 0 && (
        <section className="card timeline-scope-banner">
          <div><div className="meta">Server-side relation scope</div><strong>این نما قبل از رندر روی relation مشخص محدود شده است.</strong></div>
          <div className="timeline-scope-values">{scope.map(item => <code key={item.key}>{item.key}:{item.value}</code>)}</div>
          <Link className="button ghost" href="/timeline">خروج از نمای محدود</Link>
        </section>
      )}

      <section className="v6-principles timeline-principles">
        <div className="card"><span>01</span><strong>Precision first</strong><p>سال تنها، سال تقریبی، بازه و تاریخ دقیق چهار حالت متفاوت‌اند و UI آن‌ها را یکی نمی‌کند.</p></div>
        <div className="card"><span>02</span><strong>Cross-domain milestones</strong><p>Milestoneهای نظریه، درمان و تکنیک با roleهای مستقل روی event نگه‌داری می‌شوند.</p></div>
        <div className="card"><span>03</span><strong>No inferred history</strong><p>وجود هم‌زمان دو entity در یک دوره باعث ساخت edge تاریخی نمی‌شود؛ فقط relationهای explicit نمایش داده می‌شوند.</p></div>
      </section>

      <TimelineExplorer items={data.results} />
    </main>
  );
}
