"use client";

import Link from "next/link";
import { useState } from "react";
import type { SourceReference, TherapyDetail } from "@/lib/types";
import TherapyBookmarkButton from "./TherapyBookmarkButton";
import TherapyNoteEditor from "./TherapyNoteEditor";

const tabs = [
  ["overview", "معرفی"],
  ["techniques", "تکنیک‌ها"],
  ["disorders", "زمینه‌های بالینی"],
  ["concepts", "مفاهیم"],
  ["evidence", "شواهد و محدودیت‌ها"],
  ["notes", "یادداشت من"],
  ["sources", "منابع"],
] as const;

type TabId = typeof tabs[number][0];

const techniqueRoleLabels: Record<string, string> = {
  core: "تکنیک محوری",
  common: "تکنیک رایج",
  optional: "اختیاری",
  adapted: "اقتباس‌شده",
  component: "جزء مداخله",
};

const clinicalRoleLabels: Record<string, string> = {
  unspecified: "نقش مشخص‌نشده",
  guideline_recommended: "توصیه‌شده در راهنما",
  commonly_used: "کاربرد رایج",
  adjunctive: "مکمل",
  alternative: "گزینه جایگزین",
  context_dependent: "وابسته به زمینه",
  not_first_line: "غیرخط اول",
  research_context: "زمینه پژوهشی",
};

const evidenceLabels: Record<string, string> = {
  not_assessed: "ارزیابی‌نشده",
  guideline: "راهنمای بالینی",
  systematic_review: "مرور نظام‌مند / فراتحلیل",
  controlled_trials: "کارآزمایی‌های کنترل‌شده",
  observational: "شواهد مشاهده‌ای",
  mixed: "شواهد مختلط",
  emerging: "شواهد در حال شکل‌گیری",
  insufficient: "شواهد ناکافی",
};

const conceptRelationLabels: Record<string, string> = {
  targets: "هدف می‌گیرد",
  uses: "به‌کار می‌گیرد",
  addresses: "به آن می‌پردازد",
  teaches: "آموزش می‌دهد",
  mechanism: "سازوکار",
  applied_to: "در آن به‌کار می‌رود",
};

function fa(value: number) {
  return value.toLocaleString("fa-IR");
}

export default function TherapyDetailView({ therapy }: { therapy: TherapyDetail }) {
  const [active, setActive] = useState<TabId>("overview");

  return (
    <div className="therapy-detail stack">
      <header className="detail-header therapy-detail-header">
        <div className="therapy-detail-breadcrumb">
          <Link href="/therapies">اطلس درمان</Link><span>/</span><span>{therapy.family.name_fa || therapy.family.name_en}</span>
        </div>
        <div className="meta">Therapy Atlas · {therapy.family.name_en}</div>
        <h1>{therapy.name_fa || therapy.name_en}</h1>
        <div className="latin-title">{therapy.name_en}</div>
        <p className="section-copy">{therapy.summary}</p>
        {!!therapy.aliases.length && (
          <div className="therapy-aliases therapy-detail-aliases">
            {therapy.aliases.map(alias => <span key={`${alias.language}-${alias.text}`}>{alias.text}</span>)}
          </div>
        )}
        {!!therapy.classifications.length && (
          <div className="therapy-classifications therapy-detail-classifications">
            {therapy.classifications.map(item => <span key={item.slug}>{item.name_fa || item.name_en}</span>)}
          </div>
        )}
        <div className="therapy-detail-metrics">
          <div><strong>{fa(therapy.technique_count)}</strong><span>تکنیک ساختاریافته</span></div>
          <div><strong>{fa(therapy.disorder_count)}</strong><span>رابطه با اختلال</span></div>
          <div><strong>{fa(therapy.concept_count)}</strong><span>رابطه مفهومی</span></div>
          <div><strong>{fa(therapy.sources.length)}</strong><span>منبع مستقیم</span></div>
        </div>
        <div className="therapy-review-badge">
          <span className="therapy-review-dot" />
          {therapy.review_status === "source_checked" ? "محتوای seed این نسخه با منبع ثبت شده است" : `وضعیت بررسی: ${therapy.review_status}`}
        </div>
        <div className="actions therapy-detail-actions">
          <TherapyBookmarkButton slug={therapy.slug} />
          <Link className="button primary" href={`/compare?type=therapy&add=${therapy.slug}`}>مقایسه با درمان دیگر</Link>
          <Link className="button" href={`/map?node=therapy:${therapy.slug}`}>دیدن در Knowledge Graph</Link>
        </div>
      </header>

      <div className="tabs therapy-tabs" role="tablist" aria-label="بخش‌های پروفایل درمان">
        {tabs.map(([id, label]) => (
          <button className={`tab ${active === id ? "active" : ""}`} key={id} onClick={() => setActive(id)} role="tab" aria-selected={active === id}>
            {label}
          </button>
        ))}
      </div>

      <section className="tab-panel therapy-tab-panel">
        {active === "overview" && <Overview therapy={therapy} />}
        {active === "techniques" && <Techniques therapy={therapy} />}
        {active === "disorders" && <Disorders therapy={therapy} />}
        {active === "concepts" && <Concepts therapy={therapy} />}
        {active === "evidence" && <Evidence therapy={therapy} />}
        {active === "notes" && <TherapyNoteEditor slug={therapy.slug} />}
        {active === "sources" && <Sources sources={therapy.sources} />}
      </section>
    </div>
  );
}

function Overview({ therapy }: { therapy: TherapyDetail }) {
  return (
    <div className="grid-2 therapy-overview-grid">
      <article className="card prose therapy-prose-card">
        <div className="meta">تعریف دانشگاهی</div>
        <h2>این رویکرد چیست؟</h2>
        <p>{therapy.academic_definition || "تعریف دانشگاهی تکمیلی هنوز ثبت نشده است."}</p>
      </article>
      <article className="card prose therapy-prose-card">
        <div className="meta">اصول محوری</div>
        <h2>منطق کار</h2>
        <p>{therapy.core_principles || "اصول محوری تکمیلی هنوز ثبت نشده است."}</p>
      </article>
      <article className="card prose therapy-prose-card">
        <div className="meta">ساختار معمول</div>
        <h2>جلسه یا برنامه چگونه سازمان می‌یابد؟</h2>
        <p>{therapy.typical_structure || "ساختار معمول به شکل عمومی ثبت نشده است."}</p>
      </article>
      <article className="card prose therapy-prose-card">
        <div className="meta">زمینه تاریخی</div>
        <h2>جایگاه در تاریخ رویکردها</h2>
        <p>{therapy.historical_context || "زمینه تاریخی تکمیلی هنوز ثبت نشده است."}</p>
      </article>
      <article className="card prose therapy-prose-card therapy-context-card">
        <div className="meta">زمینه‌های مناسب برای مطالعه</div>
        <h2>این Atlas چه چیزی را نشان می‌دهد؟</h2>
        <p>{therapy.appropriate_contexts || "روابط بالینی این نسخه در بخش زمینه‌های بالینی به‌صورت source-backed نمایش داده می‌شوند."}</p>
        <p className="muted small">این بخش درباره ساختار دانش درمان است، نه انتخاب درمان برای یک فرد مشخص.</p>
      </article>
    </div>
  );
}

function Techniques({ therapy }: { therapy: TherapyDetail }) {
  if (!therapy.techniques.length) return <Empty text="هنوز تکنیک ساختاریافته‌ای به این درمان متصل نشده است." />;
  return (
    <div className="stack">
      <div>
        <h2 className="section-title">تکنیک‌های متصل</h2>
        <p className="section-copy">Technique یک Entity مستقل است؛ رابطه آن با Therapy همراه با نقش و منبع خودش ذخیره می‌شود.</p>
      </div>
      <div className="therapy-relation-grid">
        {therapy.techniques.map(item => (
          <Link href={`/techniques/${item.technique.slug}`} className="card therapy-relation-card" key={`${item.technique.slug}-${item.role}`}>
            <div className="therapy-relation-card-head">
              <span>{techniqueRoleLabels[item.role] || item.role}</span>
              <small>{item.sources.length ? `${fa(item.sources.length)} منبع رابطه` : "بدون منبع رابطه"}</small>
            </div>
            <h3>{item.technique.name_fa || item.technique.name_en}</h3>
            <div className="latin-title">{item.technique.name_en}</div>
            <p>{item.explanation || item.technique.summary}</p>
            <div className="therapy-card-metrics two-col compact-metric-row">
              <div><strong>{fa(item.technique.therapy_count)}</strong><span>درمان</span></div>
              <div><strong>{fa(item.technique.concept_count)}</strong><span>مفهوم</span></div>
            </div>
          </Link>
        ))}
      </div>
    </div>
  );
}

function Disorders({ therapy }: { therapy: TherapyDetail }) {
  if (!therapy.disorders.length) return <Empty text="هنوز رابطه بالینی source-backed برای این درمان ثبت نشده است." />;
  return (
    <div className="stack">
      <div>
        <h2 className="section-title">زمینه‌های بالینی ثبت‌شده</h2>
        <p className="section-copy">نقش بالینی و نوع پشتوانه شواهد دو فیلد جدا هستند. این جدول توصیه شخصی درمان ارائه نمی‌کند.</p>
      </div>
      <div className="therapy-disorder-list">
        {therapy.disorders.map(item => (
          <article className="card therapy-disorder-row" key={`${item.disorder.slug}-${item.clinical_role}`}>
            <div className="therapy-disorder-title">
              <Link href={`/disorders/${item.disorder.slug}`}><strong>{item.disorder.name_fa || item.disorder.name_en}</strong></Link>
              <small>{item.disorder.name_en}</small>
            </div>
            <div className="therapy-evidence-badges">
              <span>{clinicalRoleLabels[item.clinical_role] || item.clinical_role_label || item.clinical_role}</span>
              <span>{evidenceLabels[item.evidence_basis] || item.evidence_basis_label || item.evidence_basis}</span>
            </div>
            <p>{item.explanation}</p>
            {item.evidence_note && <div className="therapy-inline-note"><strong>یادداشت شواهد:</strong> {item.evidence_note}</div>}
            {!!item.sources.length && <SourceLine sources={item.sources} />}
          </article>
        ))}
      </div>
    </div>
  );
}

function Concepts({ therapy }: { therapy: TherapyDetail }) {
  if (!therapy.concepts.length) return <Empty text="هنوز رابطه مفهومی source-backed برای این درمان ثبت نشده است." />;
  return (
    <div className="stack">
      <div><h2 className="section-title">اتصال به مفاهیم روان‌شناسی</h2><p className="section-copy">این رابطه‌ها توضیح می‌دهند Therapy در مدل دانشی پروژه با کدام Conceptها اتصال مستقیم دارد.</p></div>
      {therapy.concepts.map(item => (
        <Link className="card relation-row therapy-concept-row" href={`/concepts/${item.concept.slug}`} key={`${item.concept.slug}-${item.relationship_type}`}>
          <div>
            <div className="meta">{conceptRelationLabels[item.relationship_type] || item.relationship_type}</div>
            <h3>{item.concept.name_fa || item.concept.name_en}</h3>
            <div className="latin-title">{item.concept.name_en}</div>
          </div>
          <div>
            <p>{item.explanation}</p>
            {!!item.sources.length && <small className="muted">منبع رابطه: {item.sources.map(source => source.organization || source.title).join(" · ")}</small>}
          </div>
        </Link>
      ))}
    </div>
  );
}

function Evidence({ therapy }: { therapy: TherapyDetail }) {
  return (
    <div className="grid-2 therapy-evidence-grid">
      <article className="card prose therapy-prose-card">
        <div className="meta">خلاصه شواهد</div>
        <h2>این نسخه چه ادعایی می‌کند؟</h2>
        <p>{therapy.evidence_note || "خلاصه شواهد عمومی هنوز ثبت نشده است؛ برای روابط بالینی از sourceهای همان رابطه استفاده کن."}</p>
      </article>
      <article className="card prose therapy-prose-card">
        <div className="meta">محدودیت‌ها</div>
        <h2>چه چیزی نباید از این صفحه نتیجه گرفت؟</h2>
        <p>{therapy.limitations || "محدودیت‌های اختصاصی تکمیلی هنوز ثبت نشده است."}</p>
      </article>
      <article className="card prose therapy-prose-card therapy-safety-card">
        <div className="meta">Safety note</div>
        <h2>مرز آموزشی</h2>
        <p>{therapy.safety_notes || "انتخاب درمان در عمل به ارزیابی فردی، شرایط بالینی، ترجیح فرد و نظر متخصص نیاز دارد."}</p>
        <p className="muted small">Psychology Atlas ابزار تشخیص یا درمان فردی نیست.</p>
      </article>
    </div>
  );
}

function Sources({ sources }: { sources: SourceReference[] }) {
  if (!sources.length) return <Empty text="برای این صفحه منبع مستقیمی ثبت نشده است." />;
  return (
    <div className="stack therapy-source-list">
      <div><h2 className="section-title">منابع مستقیم پروفایل</h2><p className="section-copy">منابع relationها در همان بخش relation نمایش داده می‌شوند؛ این فهرست منابع مستقیم خود Therapy است.</p></div>
      {sources.map(source => (
        <a className="card therapy-source-card" key={source.id} href={source.url} target="_blank" rel="noreferrer">
          <div>
            <div className="meta">{source.source_type || "source"}{source.publication_year ? ` · ${source.publication_year}` : ""}</div>
            <strong>{source.title}</strong>
            <span>{source.organization}</span>
            {source.citation && <p>{source.citation}</p>}
          </div>
          <b>مشاهده منبع ↗</b>
        </a>
      ))}
    </div>
  );
}

function SourceLine({ sources }: { sources: SourceReference[] }) {
  return <small className="muted therapy-source-line">منبع رابطه: {sources.map(source => source.organization || source.title).join(" · ")}</small>;
}

function Empty({ text }: { text: string }) {
  return <div className="card therapy-empty-state"><h3>داده‌ای ثبت نشده</h3><p>{text}</p></div>;
}
