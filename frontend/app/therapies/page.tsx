import Link from "next/link";
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
          <div className="eyebrow">اطلس درمان</div>
          <h1>رویکردهای درمانی را در زمینهٔ علمی‌شان ببین.</h1>
          <p>
            خانواده‌ها، تکنیک‌ها، زمینه‌های کاربرد و پشتوانهٔ منابع را جداگانه بررسی کن. این بخش برای یادگیری ساختار رویکردهاست.
          </p>
          <div className="actions" style={{ marginTop: 16 }}>
            <Link className="button primary" href="/compare?type=therapy">مقایسه ساختاریافته درمان‌ها</Link>
            <Link className="button" href="/saved">کتابخانه خصوصی من</Link>
          </div>
        </div>
        <div className="therapy-overview-stats" aria-label="آمار اطلس درمان">
          <div><strong>{therapyData.count.toLocaleString("fa-IR")}</strong><span>رویکرد درمانی</span></div>
          <div><strong>{techniqueData.count.toLocaleString("fa-IR")}</strong><span>تکنیک</span></div>
          <div><strong>{taxonomy.families.length.toLocaleString("fa-IR")}</strong><span>خانواده اصلی</span></div>
          <div><strong>{taxonomy.classifications.length.toLocaleString("fa-IR")}</strong><span>طبقه‌بندی هم‌پوشان</span></div>
        </div>
      </header>

      <p className="atlas-method-note">خانواده، نقش بالینی و پشتوانهٔ شواهد هر رویکرد جداگانه نمایش داده می‌شوند؛ این اطلس درمان‌ها را رتبه‌بندی نمی‌کند.</p>

      <TherapyExplorer therapies={therapyData.results} techniques={techniqueData.results} taxonomy={taxonomy} />
    </main>
  );
}
