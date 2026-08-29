import Link from "next/link";
import { dsmTypeLabel, faNumber, textValue } from "@/lib/dsm";
import type { DSMRecordDetail } from "@/lib/types";

const OMIT_SOURCE_KEYS = new Set([
  "شناسه_MASTER",
  "پروفایل_آموزشی_پیشرفته_MASTER",
]);

function isEmpty(value: unknown) {
  if (value == null || value === "") return true;
  if (Array.isArray(value)) return value.length === 0;
  if (typeof value === "object") return Object.keys(value as Record<string, unknown>).length === 0;
  return false;
}

export function StructuredValue({ value, depth = 0 }: { value: unknown; depth?: number }) {
  if (value == null || value === "") return <span className="muted">ثبت نشده</span>;
  if (typeof value === "boolean") return <span>{value ? "بله" : "خیر"}</span>;
  if (typeof value === "string" || typeof value === "number") return <span>{String(value)}</span>;
  if (Array.isArray(value)) {
    if (!value.length) return <span className="muted">موردی ثبت نشده است.</span>;
    return (
      <ul className={`dsm-structured-list depth-${Math.min(depth, 3)}`}>
        {value.map((item, index) => <li key={index}><StructuredValue value={item} depth={depth + 1} /></li>)}
      </ul>
    );
  }
  const entries = Object.entries(value as Record<string, unknown>);
  if (!entries.length) return <span className="muted">موردی ثبت نشده است.</span>;
  return (
    <div className={`dsm-key-value depth-${Math.min(depth, 3)}`}>
      {entries.map(([key, item]) => (
        <div className="dsm-key-value-row" key={key}>
          <dt>{key.replaceAll("_", " ")}</dt>
          <dd><StructuredValue value={item} depth={depth + 1} /></dd>
        </div>
      ))}
    </div>
  );
}

function DataSection({ title, meta, children }: { title: string; meta?: string; children: React.ReactNode }) {
  return (
    <section className="dsm-detail-section">
      <div className="dsm-detail-section-head">
        <div>{meta && <div className="meta">{meta}</div>}<h2>{title}</h2></div>
      </div>
      {children}
    </section>
  );
}

export default function DSMRecordView({ record }: { record: DSMRecordDetail }) {
  const sourceBase = Object.fromEntries(
    Object.entries(record.source_payload || {}).filter(([key]) => !OMIT_SOURCE_KEYS.has(key)),
  );

  return (
    <div className="dsm-detail-page stack">
      <nav className="dsm-breadcrumbs" aria-label="مسیر DSM MASTER">
        <Link href="/dsm">DSM MASTER</Link>
        {record.chapter_number && <Link href={`/dsm?chapter=${record.chapter_number}`}>فصل {faNumber(record.chapter_number)}</Link>}
        {record.parent && <Link href={`/dsm/${encodeURIComponent(record.parent.master_id)}`}>{record.parent.name_fa || record.parent.name_en}</Link>}
        <span>{record.master_id}</span>
      </nav>

      <header className={`dsm-detail-hero dsm-type-${record.display_type}`}>
        <div className="dsm-detail-classification">
          <span className="dsm-status-badge">{dsmTypeLabel(record.display_type)}</span>
          <span>{record.classification_status}</span>
        </div>
        <div className="dsm-detail-title-row">
          <div>
            <div className="meta">{record.master_id} · {record.specialization_level}</div>
            <h1>{record.name_fa || record.name_en}</h1>
            {record.name_en && <div className="dsm-detail-en">{record.name_en}</div>}
          </div>
          <div className="dsm-detail-location">
            {record.chapter_number && <div><strong>{faNumber(record.chapter_number)}</strong><span>فصل</span></div>}
            {record.group_name && <div><strong>{record.group_name}</strong><span>گروه</span></div>}
            <div><strong>{record.root_section.replaceAll("_", " ")}</strong><span>ریشه ساختاری</span></div>
          </div>
        </div>
        <p className="dsm-detail-summary">{record.summary}</p>
        <div className="actions">
          {record.linked_disorder && <Link className="button primary" href={`/disorders/${record.linked_disorder.slug}`}>باز کردن صفحه Atlas</Link>}
          <Link className="button" href={`/dsm?q=${encodeURIComponent(record.name_fa || record.name_en)}`}>جست‌وجوی عنوان‌های مشابه</Link>
        </div>
      </header>

      <div className="dsm-scope-warning">
        <strong>نوع رکورد قبل از محتوا اهمیت دارد.</strong>
        <p>این صفحه از MASTER آموزشی استخراج شده است. شرط پژوهشی، مشخص‌کننده، ارجاع ساختاری یا کانون توجه بالینی در این سایت به‌عنوان «تشخیص رسمی مستقل» نمایش داده نمی‌شود مگر خود فایل چنین وضعیتی ثبت کرده باشد.</p>
      </div>

      {!isEmpty(record.key_features) && (
        <DataSection title="ویژگی‌های کلیدی آموزشی" meta="Core learning points">
          <StructuredValue value={record.key_features} />
        </DataSection>
      )}

      <div className="dsm-two-column">
        <DataSection title="ارزیابی هدفمند" meta="Assessment">
          <StructuredValue value={record.assessment} />
        </DataSection>
        <DataSection title="افتراق تشخیصی هدفمند" meta="Differential">
          <StructuredValue value={record.differential} />
        </DataSection>
      </div>

      <div className="dsm-two-column">
        <DataSection title="همبودی و همپوشانی">
          <p className="dsm-long-copy">{record.comorbidity || "موردی ثبت نشده است."}</p>
        </DataSection>
        <DataSection title="سیر و پیش‌آگهی آموزشی">
          <p className="dsm-long-copy">{record.course || "موردی ثبت نشده است."}</p>
        </DataSection>
      </div>

      <div className="dsm-two-column">
        <DataSection title="مدیریت و درمان کلی آموزشی">
          <StructuredValue value={record.management} />
        </DataSection>
        <DataSection title="ابزارهای سنجش نمونه">
          <StructuredValue value={record.assessment_tools} />
        </DataSection>
      </div>

      <DataSection title="زمینه فرهنگی، رشدی و بافتی" meta="Context matters">
        <p className="dsm-long-copy">{record.context_considerations || "موردی ثبت نشده است."}</p>
      </DataSection>

      <div className="dsm-two-column">
        <section className="dsm-detail-section dsm-safety-section">
          <div className="meta">Safety</div>
          <h2>پرچم‌های قرمز و ایمنی</h2>
          <p className="dsm-long-copy">{record.red_flags || "هشدار اختصاصی ثبت نشده است."}</p>
        </section>
        <DataSection title="دام‌های رایج در مطالعه یا تشخیص">
          <StructuredValue value={record.pitfalls} />
        </DataSection>
      </div>

      {record.exam_tip && (
        <section className="dsm-exam-tip">
          <div className="meta">نکته امتحانی کلیدی</div>
          <p>{record.exam_tip}</p>
        </section>
      )}

      <div className="dsm-two-column">
        <DataSection title="کدگذاری">
          <p className="dsm-long-copy">{record.coding}</p>
        </DataSection>
        <DataSection title="شیوع و سیاست ثبت عدد">
          {record.prevalence_numeric != null && <StructuredValue value={record.prevalence_numeric} />}
          <p className="dsm-long-copy">{record.prevalence_policy}</p>
        </DataSection>
      </div>

      {!isEmpty(record.official_updates) && (
        <DataSection title="به‌روزرسانی‌های رسمی مرتبط" meta="Updates">
          <StructuredValue value={record.official_updates} />
        </DataSection>
      )}

      {record.relations.length > 0 && (
        <DataSection title="روابط لینک‌شده در DSM Graph" meta="Resolved relations">
          <div className="dsm-hierarchy-grid">
            {record.relations.map((relation, index) => (
              <Link className="dsm-hierarchy-row" href={`/dsm/${encodeURIComponent(relation.record.master_id)}`} key={`${relation.relationship_type}-${relation.direction}-${relation.record.master_id}-${index}`}>
                <span>{relation.relationship_type === "nearby" ? "عنوان نزدیک" : "افتراق لینک‌شده"} · {relation.direction === "out" ? "خروجی" : "ورودی"}</span>
                <strong>{relation.record.name_fa || relation.record.name_en}</strong>
                <small>{relation.record.master_id}</small>
              </Link>
            ))}
          </div>
        </DataSection>
      )}

      {!isEmpty(record.nearby_titles) && (
        <DataSection title="عنوان‌های نزدیک یا ارجاعات">
          <div className="dsm-nearby-links">
            {record.nearby_titles.map((item, index) => {
              const label = textValue(item);
              return <Link href={`/dsm?q=${encodeURIComponent(label)}`} key={`${label}-${index}`}>{label}</Link>;
            })}
          </div>
        </DataSection>
      )}

      {(record.parent || record.children.length > 0) && (
        <DataSection title="ساختار سلسله‌مراتبی" meta="Hierarchy">
          <div className="dsm-hierarchy-grid">
            {record.parent && (
              <Link className="dsm-hierarchy-row parent" href={`/dsm/${encodeURIComponent(record.parent.master_id)}`}>
                <span>والد</span><strong>{record.parent.name_fa || record.parent.name_en}</strong><small>{record.parent.master_id}</small>
              </Link>
            )}
            {record.children.map(child => (
              <Link className="dsm-hierarchy-row" href={`/dsm/${encodeURIComponent(child.master_id)}`} key={child.master_id}>
                <span>{dsmTypeLabel(child.display_type)}</span><strong>{child.name_fa || child.name_en}</strong><small>{child.master_id}</small>
              </Link>
            ))}
          </div>
        </DataSection>
      )}

      {!isEmpty(record.self_test) && (
        <DataSection title="سؤال‌های خودآزمایی پیشرفته" meta="Active recall">
          <ol className="dsm-self-test">
            {record.self_test.map((item, index) => <li key={index}>{textValue(item)}</li>)}
          </ol>
        </DataSection>
      )}

      <div className="dsm-two-column">
        <DataSection title="منابع پایه" meta="Source registry">
          <div className="dsm-source-list">
            {record.sources.map(source => (
              source.نشانی ? (
                <a href={source.نشانی} target="_blank" rel="noreferrer" key={source.key}>
                  <span>{source.key}</span><strong>{source.عنوان || source.key}</strong><p>{source.کاربرد}</p>
                </a>
              ) : (
                <div key={source.key}><span>{source.key}</span><strong>{source.عنوان || source.key}</strong><p>{source.کاربرد}</p></div>
              )
            ))}
          </div>
        </DataSection>
        <DataSection title="کیفیت و محدودیت">
          <StructuredValue value={record.quality} />
          {!isEmpty(record.homonym_info) && <div className="dsm-subsection"><h3>هم‌نامی یا تکرار ساختاری</h3><StructuredValue value={record.homonym_info} /></div>}
        </DataSection>
      </div>

      <details className="dsm-raw-data card">
        <summary>داده پایه و فیلدهای تکمیلی همین رکورد</summary>
        <p className="muted small">این بخش فیلدهای منبع را که بیرون از نمای استاندارد بالا قرار می‌گیرند حفظ می‌کند. زیررکوردهای دارای شناسه مستقل به‌صورت reference ذخیره شده‌اند و از بخش ساختار قابل باز شدن هستند.</p>
        <StructuredValue value={sourceBase} />
      </details>
    </div>
  );
}
