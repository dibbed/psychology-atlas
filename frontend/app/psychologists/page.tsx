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
          <div className="meta">Psychologists Atlas · v0.6.4</div>
          <h1>روان‌شناسان را از مسیر آثار، نظریه‌ها و رابطه‌های مستندشان دنبال کن.</h1>
          <p>هر پروفایل یک identity canonical با aliasهای جدا، relationهای تاریخی صریح و provenance مستقل است. نبودن biography یا سال دقیق با حدس پر نمی‌شود.</p>
          <div className="actions">
            <Link className="button primary" href="/theories">رفتن به اطلس نظریه‌ها</Link>
            <Link className="button" href="/timeline">خط زمانی روان‌شناسی</Link>
          </div>
        </div>
        <aside className="v6-atlas-head-stat">
          <strong>{data.count.toLocaleString("fa-IR")}</strong><span>شخصیت canonical</span>
          <div><b>{relationTotal.toLocaleString("fa-IR")}</b><small>اتصال مستقیم در چهار لایه Theory / Concept / Therapy / Timeline</small></div>
        </aside>
      </header>

      <section className="v6-principles">
        <div className="card"><span>01</span><strong>Identity ≠ Alias</strong><p>نام‌های جایگزین و transliteration روی alias نگه‌داری می‌شوند تا identity اصلی به‌خاطر تفاوت نگارشی تکثیر نشود.</p></div>
        <div className="card"><span>02</span><strong>Attribution is explicit</strong><p>«پیشنهاد داد»، «توسعه داد»، «پژوهش کرد» و «وابستگی تاریخی» به یک creator مبهم collapse نمی‌شوند.</p></div>
        <div className="card"><span>03</span><strong>Provenance per relation</strong><p>منبع رابطه شخص با Theory/Concept/Therapy مستقل از منابع عمومی همان شخص نمایش داده می‌شود.</p></div>
      </section>

      <PsychologistExplorer items={data.results} />
    </main>
  );
}
