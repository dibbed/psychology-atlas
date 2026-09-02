import TherapyExplorer from "@/components/TherapyExplorer";
import { publicFetch } from "@/lib/api";
import type { Paginated, Technique, Therapy, TherapyTaxonomy } from "@/lib/types";

export default async function TherapiesPage() {
  const [therapyData, techniqueData, taxonomy] = await Promise.all([
    publicFetch<Paginated<Therapy>>("/therapies/?page_size=100"),
    publicFetch<Paginated<Technique>>("/techniques/?page_size=100"),
    publicFetch<TherapyTaxonomy>("/therapies/taxonomy/"),
  ]);

  return (
    <main className="shell page stack therapies-page">
      <header className="therapies-page-head">
        <div className="therapies-page-copy">
          <div className="meta">Therapy Atlas</div>
          <h1>درمان را به‌عنوان یک ساختار علمی یاد بگیر، نه یک لیست «بهترین درمان‌ها».</h1>
          <p>
            هر Therapy خانواده، تکنیک‌ها، زمینه‌های بالینی، مفاهیم و provenance خودش را دارد. Technique هم یک Entity مستقل است تا روش‌های مشترک بین چند رویکرد گم نشوند.
          </p>
        </div>
        <div className="therapy-overview-stats" aria-label="آمار اطلس درمان">
          <div><strong>{therapyData.count.toLocaleString("fa-IR")}</strong><span>رویکرد درمانی</span></div>
          <div><strong>{techniqueData.count.toLocaleString("fa-IR")}</strong><span>تکنیک</span></div>
          <div><strong>{taxonomy.families.length.toLocaleString("fa-IR")}</strong><span>خانواده اصلی</span></div>
          <div><strong>{taxonomy.classifications.length.toLocaleString("fa-IR")}</strong><span>طبقه‌بندی هم‌پوشان</span></div>
        </div>
      </header>

      <section className="therapy-atlas-principles">
        <div className="card">
          <span>01</span><strong>Family ≠ Classification</strong><p>هر درمان یک خانواده اصلی دارد، اما برچسب‌هایی مثل trauma-focused یا exposure-based می‌توانند هم‌زمان روی چند درمان بنشینند.</p>
        </div>
        <div className="card">
          <span>02</span><strong>Clinical Role ≠ Evidence Basis</strong><p>نقش بالینی با نوع پشتوانه شواهد یکی نیست و در API و UI جدا نمایش داده می‌شود.</p>
        </div>
        <div className="card">
          <span>03</span><strong>Source-backed Relations</strong><p>رابطه‌های Therapy با Disorder، Concept و Technique منبع مستقل خودشان را نگه می‌دارند.</p>
        </div>
      </section>

      <TherapyExplorer therapies={therapyData.results} techniques={techniqueData.results} taxonomy={taxonomy} />
    </main>
  );
}
