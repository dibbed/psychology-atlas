import Link from "next/link";
import PsychologistExplorer from "@/components/PsychologistExplorer";
import { publicFetch } from "@/lib/api";
import type { Paginated, Psychologist } from "@/lib/types";

export default async function PsychologistsPage() {
  const data = await publicFetch<Paginated<Psychologist>>("/psychologists/?page_size=300");
  const relationTotal = data.results.reduce(
    (sum, item) => sum + item.theory_count + item.concept_count + item.therapy_count + item.timeline_event_count,
    0,
  );

  return (
    <main className="shell page stack v6-atlas-page psychologists-page">
      <header className="v6-atlas-head psychologists-page-head">
        <div className="v6-atlas-copy">
          <div className="eyebrow">تاریخ روان‌شناسی</div>
          <h1>روان‌شناسان و پژوهشگران</h1>
          <p>از زندگی و آثار هر شخص به نظریه‌ها، مفاهیم و رویدادهای مرتبط برس. اطلاعات نامشخص با حدس پر نمی‌شوند.</p>
          <div className="actions">
            <Link className="button primary" href="/theories">رفتن به اطلس نظریه‌ها</Link>
            <Link className="button" href="/timeline">خط زمانی روان‌شناسی</Link>
          </div>
        </div>
        <aside className="v6-atlas-head-stat">
          <strong>{data.count.toLocaleString("fa-IR")}</strong><span>شخصیت ثبت‌شده</span>
          <div><b>{relationTotal.toLocaleString("fa-IR")}</b><small>پیوند ثبت‌شده با نظریه، مفهوم، درمان و تاریخ</small></div>
        </aside>
      </header>

      <p className="atlas-method-note">نقش هر شخص در رابطه‌های تاریخی و علمی جداگانه نمایش داده می‌شود.</p>

      <PsychologistExplorer items={data.results} />
    </main>
  );
}
