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
          <div className="meta">Theory Atlas · v0.6.4</div>
          <h1>نظریه‌ها را با سازه‌ها، افراد، کاربردها و جایگاه تاریخی‌شان کنار هم ببین.</h1>
          <p>این اطلس theory را یک entity مستقل می‌داند؛ domain، modern status و relationهای آن همان داده ثبت‌شده‌اند و UI آن‌ها را به ادعای تازه درباره «درست‌ترین نظریه» تبدیل نمی‌کند.</p>
          <div className="actions">
            <Link className="button primary" href="/psychologists">روان‌شناسان مرتبط</Link>
            <Link className="button" href="/timeline">خط زمانی نظریه‌ها</Link>
          </div>
        </div>
        <aside className="v6-atlas-head-stat theory-head-stat">
          <strong>{data.count.toLocaleString("fa-IR")}</strong><span>نظریه canonical</span>
          <div><b>{domains.size.toLocaleString("fa-IR")}</b><small>domain ثبت‌شده · {relationTotal.toLocaleString("fa-IR")} اتصال صریح در runtime</small></div>
        </aside>
      </header>

      <section className="v6-principles">
        <div className="card"><span>01</span><strong>Theory ≠ Therapy</strong><p>نظریه می‌تواند به Therapy یا Technique وصل باشد، اما خودش مداخله درمانی نیست.</p></div>
        <div className="card"><span>02</span><strong>Constructs are edges</strong><p>سازه‌های نظری مثل Conceptها با relationship_type صریح و منبع relation نگه‌داری می‌شوند.</p></div>
        <div className="card"><span>03</span><strong>Status is metadata</strong><p>modern_status زمینه مطالعه می‌دهد؛ این UI آن را score اثربخشی یا رأی علمی نهایی تفسیر نمی‌کند.</p></div>
      </section>

      <TheoryExplorer items={data.results} />
    </main>
  );
}
