import Link from "next/link";
import DSMExplorer from "@/components/DSMExplorer";
import DSMMetadataPanel from "@/components/DSMMetadataPanel";
import { StructuredValue } from "@/components/DSMRecordView";
import { publicFetch } from "@/lib/api";
import { dsmTypeLabel, faNumber } from "@/lib/dsm";
import type { DSMDisplayType, DSMOverview } from "@/lib/types";

const VALID_TYPES = new Set<DSMDisplayType>([
  "diagnosis",
  "structural",
  "clinical_attention",
  "research",
  "alternative_model",
  "specifier",
  "reference",
  "code",
  "other",
]);

export default async function DSMPage({
  searchParams,
}: {
  searchParams: Promise<{ q?: string; chapter?: string; type?: string }>;
}) {
  const params = await searchParams;
  const overview = await publicFetch<DSMOverview>("/dsm/overview/");
  const initialType = params.type && VALID_TYPES.has(params.type as DSMDisplayType)
    ? params.type as DSMDisplayType
    : "all";
  const initialChapter = params.chapter && overview.chapters.some(row => String(row.chapter_number) === params.chapter)
    ? params.chapter
    : "all";
  const typeCounts = overview.counts.types;

  return (
    <main className="shell page stack dsm-page">
      <section className="dsm-page-hero">
        <div>
          <div className="meta">DSM-5-TR فارسی · MASTER آموزشی ممیزی‌شده · {overview.corpus.version_date}</div>
          <h1>طبقه‌بندی را با وضعیت واقعی هر رکورد بخوان، نه به شکل یک فهرست تخت.</h1>
          <p>{overview.corpus.purpose}</p>
          <div className="actions">
            <a className="button primary" href="#dsm-explorer">کاوش همه رکوردها</a>
            <Link className="button" href="/search">جست‌وجوی کل سایت</Link>
          </div>
        </div>
        <aside className="dsm-page-manifest">
          <span>Dataset integrity</span>
          <strong>{overview.health_check["نتیجه"] === "PASS" ? "PASS" : "ثبت شده"}</strong>
          <small>{overview.corpus.source_filename}</small>
          <code>{overview.corpus.source_sha256.slice(0, 16)}…</code>
        </aside>
      </section>

      <section className="dsm-stats-grid" aria-label="آمار DSM MASTER">
        <div><strong>{faNumber(overview.counts.records)}</strong><span>گره آدرس‌پذیر</span></div>
        <div><strong>{faNumber(typeCounts.diagnosis || 0)}</strong><span>{dsmTypeLabel("diagnosis")}</span></div>
        <div><strong>{faNumber(typeCounts.clinical_attention || 0)}</strong><span>{dsmTypeLabel("clinical_attention")}</span></div>
        <div><strong>{faNumber(typeCounts.research || 0)}</strong><span>{dsmTypeLabel("research")}</span></div>
        <div><strong>{faNumber(overview.chapters.length)}</strong><span>فصل اختلال</span></div>
        <div><strong>{faNumber(overview.counts.linked_atlas_disorders)}</strong><span>اتصال به Atlas فعلی</span></div>
      </section>

      <section className="dsm-classification-note">
        <div className="meta">Classification first</div>
        <h2>همه عنوان‌های این فایل «اختلال مستقل» نیستند.</h2>
        <p>{overview.corpus.clinical_note}</p>
        <div className="dsm-type-summary">
          {Object.entries(typeCounts).map(([type, count]) => (
            <Link href={`/dsm?type=${type}`} key={type}>
              <strong>{faNumber(count || 0)}</strong><span>{dsmTypeLabel(type as DSMDisplayType)}</span>
            </Link>
          ))}
        </div>
      </section>

      <div id="dsm-explorer">
        <DSMExplorer
          overview={overview}
          initialQuery={params.q || ""}
          initialType={initialType}
          initialChapter={initialChapter}
        />
      </div>

      <section className="dsm-chapter-overview stack">
        <div className="section-heading-row">
          <div>
            <div className="meta">۲۰ فصل اصلی</div>
            <h2 className="section-title">پوشش فصل‌ها</h2>
            <p className="section-copy">تعداد رکورد و تشخیص رسمی هر فصل مستقیماً از MASTER واردشده محاسبه می‌شود.</p>
          </div>
        </div>
        <div className="dsm-chapter-grid">
          {overview.chapters.map(chapter => (
            <Link href={`/dsm?chapter=${chapter.chapter_number}`} key={chapter.chapter_number}>
              <span>{faNumber(chapter.chapter_number).padStart(2, "۰")}</span>
              <div><strong>{chapter.chapter_name_fa}</strong><small>{chapter.chapter_name_en}</small></div>
              <div className="dsm-chapter-counts"><b>{faNumber(chapter.record_count)}</b><small>رکورد</small><b>{faNumber(chapter.diagnosis_count)}</b><small>تشخیص رسمی</small></div>
            </Link>
          ))}
        </div>
      </section>

      <section className="dsm-overview-columns">
        <div className="card dsm-study-guide">
          <div className="meta">روش مطالعه پیشنهادشده در خود فایل</div>
          <h2>MASTER را چطور بخوانیم؟</h2>
          <ol>{overview.study_guide.map((item, index) => <li key={index}>{item}</li>)}</ol>
        </div>
        <div className="card dsm-cultural-note">
          <div className="meta">زمینه فرهنگی و رشدی</div>
          <h2>تفسیر بدون زمینه کافی نیست.</h2>
          <p>{overview.cultural_note}</p>
          <div className="dsm-scope-mini"><strong>حق نشر و دامنه</strong><p>{overview.corpus.copyright_note}</p></div>
        </div>
      </section>

      <section className="dsm-meta-panels">
        <details className="card" open>
          <summary>وضعیت رسمی و پیشنهادهای غیرنهایی</summary>
          <StructuredValue value={overview.official_status} />
        </details>
        <details className="card">
          <summary>ممیزی کیفیت MASTER</summary>
          <StructuredValue value={overview.quality_audit} />
        </details>
        <details className="card">
          <summary>به‌روزرسانی‌های سپتامبر ۲۰۲۵</summary>
          <StructuredValue value={overview.release_updates} />
        </details>
        <details className="card">
          <summary>موارد نیازمند بازبینی دوره‌ای</summary>
          <StructuredValue value={overview.periodic_review} />
        </details>
        <details className="card">
          <summary>راهنمای هشدارهای فوری</summary>
          <StructuredValue value={overview.urgent_warnings} />
        </details>
        <DSMMetadataPanel />
      </section>

      <section className="dsm-source-registry card">
        <div className="meta">ثبت منابع MASTER</div>
        <h2>منابعی که خود فایل به آن‌ها ارجاع داده است</h2>
        <div className="dsm-source-registry-grid">
          {Object.entries(overview.source_registry).map(([key, source]) => (
            <a href={source.نشانی || "#"} target={source.نشانی ? "_blank" : undefined} rel={source.نشانی ? "noreferrer" : undefined} key={key}>
              <span>{key}</span><strong>{source.عنوان || key}</strong><p>{source.کاربرد}</p>
            </a>
          ))}
        </div>
      </section>
    </main>
  );
}
