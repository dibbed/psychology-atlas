import Link from "next/link";
import type { TechniqueDetail } from "@/lib/types";

const roleLabels: Record<string, string> = {
  core: "محوری",
  common: "رایج",
  optional: "اختیاری",
  adapted: "اقتباس‌شده",
  component: "جزء مداخله",
};

const relationLabels: Record<string, string> = {
  targets: "هدف می‌گیرد",
  addresses: "به آن می‌پردازد",
  teaches: "آموزش می‌دهد",
  mechanism: "سازوکار",
  applied_to: "در آن به‌کار می‌رود",
};

function fa(value: number) {
  return value.toLocaleString("fa-IR");
}

export default function TechniqueDetailView({ technique }: { technique: TechniqueDetail }) {
  return (
    <div className="stack technique-detail">
      <header className="detail-header technique-detail-header">
        <div className="therapy-detail-breadcrumb">
          <Link href="/therapies">اطلس درمان</Link><span>/</span><span>تکنیک‌ها</span>
        </div>
        <div className="meta">Therapy Atlas · Technique</div>
        <h1>{technique.name_fa || technique.name_en}</h1>
        <div className="latin-title">{technique.name_en}</div>
        <p className="section-copy">{technique.summary}</p>
        {!!technique.aliases.length && (
          <div className="therapy-aliases therapy-detail-aliases">
            {technique.aliases.map(alias => <span key={`${alias.language}-${alias.text}`}>{alias.text}</span>)}
          </div>
        )}
        <div className="therapy-detail-metrics technique-detail-metrics">
          <div><strong>{fa(technique.therapy_count)}</strong><span>درمان مرتبط</span></div>
          <div><strong>{fa(technique.concept_count)}</strong><span>مفهوم مرتبط</span></div>
          <div><strong>{fa(technique.sources.length)}</strong><span>منبع مستقیم</span></div>
        </div>
      </header>

      <section className="grid-2 therapy-overview-grid">
        <article className="card prose therapy-prose-card">
          <div className="meta">تعریف دانشگاهی</div>
          <h2>این تکنیک چیست؟</h2>
          <p>{technique.academic_definition || "تعریف دانشگاهی تکمیلی هنوز ثبت نشده است."}</p>
        </article>
        <article className="card prose therapy-prose-card">
          <div className="meta">کاربرد آموزشی</div>
          <h2>در چه چارچوبی مطرح می‌شود؟</h2>
          <p>{technique.application_notes || "یادداشت کاربردی تکمیلی هنوز ثبت نشده است."}</p>
        </article>
        <article className="card prose therapy-prose-card">
          <div className="meta">محدودیت‌ها</div>
          <h2>مرز تفسیر</h2>
          <p>{technique.limitations || "محدودیت اختصاصی تکمیلی هنوز ثبت نشده است."}</p>
        </article>
        <article className="card prose therapy-prose-card therapy-safety-card">
          <div className="meta">Safety note</div>
          <h2>اجرای واقعی مداخله</h2>
          <p>{technique.safety_notes || "این صفحه برای یادگیری ساختار تکنیک است و دستور درمان فردی ارائه نمی‌کند."}</p>
        </article>
      </section>

      <section className="stack">
        <div><h2 className="section-title">این تکنیک در کدام درمان‌ها ثبت شده؟</h2><p className="section-copy">رابطه Technique ↔ Therapy در دیتابیس مستقل ذخیره می‌شود.</p></div>
        <div className="therapy-relation-grid">
          {technique.therapies.length ? technique.therapies.map(item => (
            <Link href={`/therapies/${item.therapy.slug}`} className="card therapy-relation-card" key={`${item.therapy.slug}-${item.role}`}>
              <div className="therapy-relation-card-head"><span>{roleLabels[item.role] || item.role}</span><small>{item.therapy.family.name_fa || item.therapy.family.name_en}</small></div>
              <h3>{item.therapy.name_fa || item.therapy.name_en}</h3>
              <div className="latin-title">{item.therapy.name_en}</div>
              <p>{item.explanation}</p>
              {!!item.sources.length && <small className="muted">منبع رابطه: {item.sources.map(source => source.organization || source.title).join(" · ")}</small>}
            </Link>
          )) : <div className="card therapy-empty-state"><p>هنوز درمان فعالی به این تکنیک متصل نشده است.</p></div>}
        </div>
      </section>

      <section className="stack">
        <div><h2 className="section-title">اتصال مفهومی</h2><p className="section-copy">این بخش نشان می‌دهد تکنیک به کدام Conceptهای اطلس متصل شده است.</p></div>
        {technique.concepts.length ? technique.concepts.map(item => (
          <Link href={`/concepts/${item.concept.slug}`} className="card relation-row therapy-concept-row" key={`${item.concept.slug}-${item.relationship_type}`}>
            <div>
              <div className="meta">{relationLabels[item.relationship_type] || item.relationship_type}</div>
              <h3>{item.concept.name_fa || item.concept.name_en}</h3>
              <div className="latin-title">{item.concept.name_en}</div>
            </div>
            <div>
              <p>{item.explanation}</p>
              {!!item.sources.length && <small className="muted">منبع رابطه: {item.sources.map(source => source.organization || source.title).join(" · ")}</small>}
            </div>
          </Link>
        )) : <div className="card therapy-empty-state"><p>هنوز Concept مستقیمی به این تکنیک متصل نشده است.</p></div>}
      </section>

      <section className="stack therapy-source-list">
        <div><h2 className="section-title">منابع مستقیم تکنیک</h2><p className="section-copy">منابع relationها در کارت همان رابطه نمایش داده می‌شوند.</p></div>
        {technique.sources.length ? technique.sources.map(source => (
          <a className="card therapy-source-card" key={source.id} href={source.url} target="_blank" rel="noreferrer">
            <div>
              <div className="meta">{source.source_type || "source"}{source.publication_year ? ` · ${source.publication_year}` : ""}</div>
              <strong>{source.title}</strong>
              <span>{source.organization}</span>
              {source.citation && <p>{source.citation}</p>}
            </div>
            <b>مشاهده منبع ↗</b>
          </a>
        )) : <div className="card therapy-empty-state"><p>منبع مستقیمی ثبت نشده است.</p></div>}
      </section>
    </div>
  );
}
