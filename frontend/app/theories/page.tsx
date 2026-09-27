import Link from "next/link";
import TheoryExplorer from "@/components/TheoryExplorer";
import { publicFetch } from "@/lib/api";
import type { Paginated, Theory } from "@/lib/types";

export default async function TheoriesPage() {
  const data = await publicFetch<Paginated<Theory>>("/theories/?page_size=300");
  const relationTotal = data.results.reduce(
    (sum, item) => sum + item.psychologist_count + item.concept_count + item.therapy_count + item.technique_count + item.timeline_event_count,
    0,
  );
  const domains = new Set(data.results.map(item => item.domain).filter(Boolean));

  return (
    <main className="shell page stack v6-atlas-page theories-page">
      <header className="v6-atlas-head theories-page-head">
        <div className="v6-atlas-copy">
          <div className="eyebrow">اطلس نظریه‌ها</div>
          <h1>نظریه‌ها را در زمینهٔ تاریخی‌شان بشناس.</h1>
          <p>سازه‌ها، افراد و جایگاه هر نظریه را کنار هم ببین. این بخش نظریه‌ها را رتبه‌بندی نمی‌کند.</p>
          <div className="actions">
            <Link className="button primary" href="/psychologists">روان‌شناسان مرتبط</Link>
            <Link className="button" href="/timeline">خط زمانی نظریه‌ها</Link>
          </div>
        </div>
        <aside className="v6-atlas-head-stat theory-head-stat">
          <strong>{data.count.toLocaleString("fa-IR")}</strong><span>نظریهٔ ثبت‌شده</span>
          <div><b>{domains.size.toLocaleString("fa-IR")}</b><small>حوزه · {relationTotal.toLocaleString("fa-IR")} پیوند ثبت‌شده</small></div>
        </aside>
      </header>

      <p className="atlas-method-note">وضعیت و پیوندهای هر نظریه برای مطالعهٔ زمینه نمایش داده می‌شوند؛ معیار اثربخشی یا داوری نهایی نیستند.</p>

      <TheoryExplorer items={data.results} />
    </main>
  );
}
