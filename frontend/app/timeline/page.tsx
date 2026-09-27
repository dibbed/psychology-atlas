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
          <div className="eyebrow">تاریخ روان‌شناسی</div>
          <h1>خط زمانی</h1>
          <p>رویدادها را به ترتیب زمان مرور کن و پیوندهای ثبت‌شدهٔ آن‌ها با اشخاص، نظریه‌ها و مفاهیم را ببین.</p>
          <div className="actions">
            <Link className="button primary" href="/psychologists">اطلس روان‌شناسان</Link>
            <Link className="button" href="/theories">اطلس نظریه‌ها</Link>
          </div>
        </div>
        <aside className="v6-atlas-head-stat timeline-head-stat">
          <strong>{data.count.toLocaleString("fa-IR")}</strong><span>{scope.length ? "رویداد در نمای فعلی" : "رویداد ثبت‌شده"}</span>
          <div><b>{totalCount.toLocaleString("fa-IR")}</b><small>کل رویدادهای فعال</small></div>
        </aside>
      </header>

      {scope.length > 0 && (
        <section className="card timeline-scope-banner">
          <div><div className="meta">نمای مرتبط</div><strong>رویدادهای مرتبط با موضوع انتخاب‌شده نمایش داده می‌شوند.</strong></div>
          <div className="timeline-scope-values">{scope.map(item => <code key={item.key}>{item.key}:{item.value}</code>)}</div>
          <Link className="button ghost" href="/timeline">خروج از نمای محدود</Link>
        </section>
      )}

      <p className="atlas-method-note">سال تقریبی، بازه و تاریخ دقیق از هم جدا می‌مانند؛ تنها پیوندهای ثبت‌شده نمایش داده می‌شوند.</p>

      <TimelineExplorer items={data.results} />
    </main>
  );
}
