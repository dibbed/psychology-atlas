"use client";

import Link from "next/link";
import { useState } from "react";
import type { TimelineEvent, TimelineEventDetail } from "@/lib/types";
import {
  BilingualText,
  faNumber,
  humanizeCode,
  RelationSourceLine,
  ReviewStatus,
  ScientificSourceList,
} from "./ScientificMeta";

const tabs = [
  ["overview", "شرح رویداد"],
  ["people", "افراد"],
  ["theories", "نظریه‌ها"],
  ["practice", "درمان و تکنیک"],
  ["concepts", "مفاهیم"],
  ["sources", "منابع"],
] as const;

type TabId = typeof tabs[number][0];

const eventTypeLabels: Record<string, string> = {
  publication: "انتشار",
  theory_development: "توسعه نظریه",
  therapy_development: "توسعه درمان",
  research_finding: "یافته پژوهشی",
  institutional: "نقطه عطف نهادی",
  professional: "نقطه عطف حرفه‌ای",
  classification: "طبقه‌بندی / nosology",
  guideline: "راهنما",
  other: "سایر",
  unspecified: "نوع مشخص نشده",
};

const roleLabels: Record<string, string> = {
  related: "مرتبط",
  involves_person: "شخص در رویداد دخیل است",
  marks_theory_milestone: "نقطه عطف نظریه",
  marks_therapy_milestone: "نقطه عطف درمان",
  marks_technique_evidence_milestone: "نقطه عطف شواهد تکنیک",
  subject: "موضوع",
  author: "نویسنده / پدیدآور",
  developer: "توسعه‌دهنده",
  publication: "انتشار",
  institutional: "نهادی",
  context: "زمینه",
};

function displayDate(item: TimelineEventDetail | TimelineEvent) {
  if (item.date_precision === "exact_date" && item.exact_date) return item.exact_date;
  if (item.date_precision === "year_range" && item.year_start) return `${faNumber(item.year_start)} — ${item.year_end ? faNumber(item.year_end) : "؟"}`;
  if (item.date_precision === "approximate_year" && item.year_start) return `حدود ${faNumber(item.year_start)}`;
  if (item.year_start) return faNumber(item.year_start);
  return item.date_text || "تاریخ نامشخص";
}

function relationLabel(role: string, fallback: string) {
  return roleLabels[role] || fallback || humanizeCode(role);
}

export default function TimelineDetailView({
  event,
  previous,
  next,
}: {
  event: TimelineEventDetail;
  previous?: TimelineEvent | null;
  next?: TimelineEvent | null;
}) {
  const [active, setActive] = useState<TabId>("overview");
  const totalLinks = event.psychologist_count + event.theory_count + event.therapy_count + event.technique_count + event.concept_count;

  return (
    <div className="stack timeline-detail v6-detail">
      <header className="timeline-detail-header v6-detail-header">
        <div className="v6-breadcrumb"><Link href="/timeline">خط زمانی روان‌شناسی</Link><span>/</span><span>{displayDate(event)}</span></div>
        <div className="timeline-detail-date" dir={event.date_precision === "exact_date" ? "ltr" : undefined}>{displayDate(event)}</div>
        <div className="meta">Psychology Timeline · {eventTypeLabels[event.event_type] || event.event_type_label || humanizeCode(event.event_type)}</div>
        <h1>{event.title_fa || event.title_en}</h1>
        {event.title_fa && event.title_en && <div className="latin-title">{event.title_en}</div>}
        <div className="v6-header-context timeline-header-context">
          <span>{event.date_precision_label || humanizeCode(event.date_precision)}</span>
          {event.category && <span>{humanizeCode(event.category)}</span>}
          {event.date_text && <span className="ltr-token" dir="ltr">raw: {event.date_text}</span>}
        </div>
        <BilingualText fa={event.description_fa} en={event.description_en} empty="شرح تکمیلی مستقیمی برای این رویداد ثبت نشده است." className="v6-header-copy" />
        <div className="v6-detail-metrics six-col timeline-detail-metrics">
          <div><strong>{faNumber(event.psychologist_count)}</strong><span>شخص</span></div>
          <div><strong>{faNumber(event.theory_count)}</strong><span>نظریه</span></div>
          <div><strong>{faNumber(event.therapy_count)}</strong><span>درمان</span></div>
          <div><strong>{faNumber(event.technique_count)}</strong><span>تکنیک</span></div>
          <div><strong>{faNumber(event.concept_count)}</strong><span>مفهوم</span></div>
          <div><strong>{faNumber(event.sources.length)}</strong><span>منبع مستقیم</span></div>
        </div>
        <div className="v6-detail-status"><ReviewStatus status={event.review_status} /></div>
        <div className="timeline-detail-link-count">{faNumber(totalLinks)} اتصال cross-domain روی این رویداد</div>
      </header>

      {(previous || next) && (
        <nav className="timeline-neighbor-nav" aria-label="رویداد قبلی و بعدی">
          {previous ? <Link href={`/timeline/${previous.slug}`} className="timeline-neighbor previous"><span>رویداد قبلی</span><strong>{displayDate(previous)} · {previous.title_fa || previous.title_en}</strong></Link> : <span />}
          {next ? <Link href={`/timeline/${next.slug}`} className="timeline-neighbor next"><span>رویداد بعدی</span><strong>{displayDate(next)} · {next.title_fa || next.title_en}</strong></Link> : <span />}
        </nav>
      )}

      <div className="tabs v6-tabs timeline-tabs" role="tablist" aria-label="بخش‌های رویداد Timeline">
        {tabs.map(([id, label]) => <button className={`tab ${active === id ? "active" : ""}`} key={id} onClick={() => setActive(id)} role="tab" aria-selected={active === id}>{label}</button>)}
      </div>

      <section className="v6-tab-panel">
        {active === "overview" && <Overview event={event} />}
        {active === "people" && <People event={event} />}
        {active === "theories" && <Theories event={event} />}
        {active === "practice" && <Practice event={event} />}
        {active === "concepts" && <Concepts event={event} />}
        {active === "sources" && <ScientificSourceList links={event.sources} title="منابع مستقیم رویداد" description="Sourceهای relationهای cross-domain جداگانه روی همان relation نمایش داده می‌شوند." />}
      </section>
    </div>
  );
}

function Overview({ event }: { event: TimelineEventDetail }) {
  return (
    <div className="grid-2 v6-overview-grid timeline-overview-grid">
      <article className="card v6-prose-card timeline-description-card">
        <div className="meta">Event description</div><h2>شرح رویداد</h2>
        <BilingualText fa={event.description_fa} en={event.description_en} />
      </article>
      <article className="card v6-prose-card">
        <div className="meta">Historical importance</div><h2>اهمیت تاریخی ثبت‌شده</h2>
        <BilingualText fa={event.historical_importance_fa} en={event.historical_importance_en} empty="توضیح مستقلی برای اهمیت تاریخی در این رکورد ثبت نشده است." />
      </article>
      <article className="card v6-prose-card">
        <div className="meta">Date model</div><h2>دقت زمانی این رکورد</h2>
        <dl className="v6-definition-list">
          <div><dt>precision</dt><dd>{event.date_precision}</dd></div>
          <div><dt>date_text</dt><dd dir="ltr">{event.date_text || "—"}</dd></div>
          <div><dt>year_start</dt><dd>{event.year_start ? faNumber(event.year_start) : "—"}</dd></div>
          <div><dt>year_end</dt><dd>{event.year_end ? faNumber(event.year_end) : "—"}</dd></div>
          <div><dt>exact_date</dt><dd dir="ltr">{event.exact_date || "null"}</dd></div>
        </dl>
      </article>
      <article className="card v6-guardrail-card timeline-guardrail-card">
        <div className="meta">قید تاریخی</div><h2>Timeline دقت زمانی را افزایش نمی‌دهد.</h2>
        <p>اگر source فقط سال را پشتیبانی کند، `exact_date` تهی باقی می‌ماند. نمایش UI نیز همان precision را حفظ می‌کند و روز/ماه فرضی تولید نمی‌کند.</p>
      </article>
    </div>
  );
}

function People({ event }: { event: TimelineEventDetail }) {
  if (!event.psychologists.length) return <Empty text="Psychologist صریحی به این رویداد متصل نشده است." />;
  return (
    <RelationSection title="افراد متصل" copy="Role و provenance هر اتصال مستقل از خود Event نگه‌داری می‌شود.">
      {event.psychologists.map(item => (
        <Link href={`/psychologists/${item.psychologist.slug}`} className="card v6-relation-card" key={`${item.psychologist.slug}-${item.role}`}>
          <RelationHead label={relationLabel(item.role, item.role_label)} status={item.review_status} />
          <h3>{item.psychologist.name_fa || item.psychologist.name_en}</h3><div className="latin-title">{item.psychologist.name_en}</div>
          {(item.psychologist.role_fa || item.psychologist.role_en) && <p>{item.psychologist.role_fa || item.psychologist.role_en}</p>}
          <RelationSourceLine sources={item.sources} />
        </Link>
      ))}
    </RelationSection>
  );
}

function Theories({ event }: { event: TimelineEventDetail }) {
  if (!event.theories.length) return <Empty text="Theory صریحی به این رویداد متصل نشده است." />;
  return (
    <RelationSection title="نظریه‌های متصل" copy="Milestoneهای نظریه با role صریح خودشان نمایش داده می‌شوند.">
      {event.theories.map(item => (
        <Link href={`/theories/${item.theory.slug}`} className="card v6-relation-card" key={`${item.theory.slug}-${item.role}`}>
          <RelationHead label={relationLabel(item.role, item.role_label)} status={item.review_status} />
          <h3>{item.theory.name_fa || item.theory.name_en}</h3><div className="latin-title">{item.theory.name_en}</div>
          <div className="v6-token-list"><span>{humanizeCode(item.theory.domain)}</span>{item.theory.modern_status && <span>{humanizeCode(item.theory.modern_status)}</span>}</div>
          <RelationSourceLine sources={item.sources} />
        </Link>
      ))}
    </RelationSection>
  );
}

function Practice({ event }: { event: TimelineEventDetail }) {
  if (!event.therapies.length && !event.techniques.length) return <Empty text="Therapy یا Technique صریحی به این رویداد متصل نشده است." />;
  return (
    <div className="stack">
      {!!event.therapies.length && (
        <RelationSection title="درمان‌های متصل" copy="این اتصال milestone تاریخی است و توصیه درمانی شخصی نیست.">
          {event.therapies.map(item => (
            <Link href={`/therapies/${item.therapy.slug}`} className="card v6-relation-card" key={`${item.therapy.slug}-${item.role}`}>
              <RelationHead label={relationLabel(item.role, item.role_label)} status={item.review_status} />
              <h3>{item.therapy.name_fa || item.therapy.name_en}</h3><div className="latin-title">{item.therapy.name_en}</div>
              {item.therapy.family && <div className="v6-token-list"><span>{item.therapy.family.name_fa || item.therapy.family.name_en}</span></div>}
              <RelationSourceLine sources={item.sources} />
            </Link>
          ))}
        </RelationSection>
      )}
      {!!event.techniques.length && (
        <RelationSection title="تکنیک‌های متصل" copy="Technique به‌عنوان entity مستقل نمایش داده می‌شود.">
          {event.techniques.map(item => (
            <Link href={`/techniques/${item.technique.slug}`} className="card v6-relation-card" key={`${item.technique.slug}-${item.role}`}>
              <RelationHead label={relationLabel(item.role, item.role_label)} status={item.review_status} />
              <h3>{item.technique.name_fa || item.technique.name_en}</h3><div className="latin-title">{item.technique.name_en}</div>
              <RelationSourceLine sources={item.sources} />
            </Link>
          ))}
        </RelationSection>
      )}
    </div>
  );
}

function Concepts({ event }: { event: TimelineEventDetail }) {
  if (!event.concepts.length) return <Empty text="Concept صریحی به این رویداد متصل نشده است." />;
  return (
    <RelationSection title="مفاهیم متصل" copy="اتصال‌های مفهومی explicit هستند و از similarity استنتاج نمی‌شوند.">
      {event.concepts.map(item => (
        <Link href={`/concepts/${item.concept.slug}`} className="card v6-relation-card" key={`${item.concept.slug}-${item.role}`}>
          <RelationHead label={relationLabel(item.role, item.role_label)} status={item.review_status} />
          <h3>{item.concept.name_fa || item.concept.name_en}</h3><div className="latin-title">{item.concept.name_en}</div>
          <div className="v6-token-list"><span>{humanizeCode(item.concept.kind)}</span><span>{humanizeCode(item.concept.domain)}</span></div>
          <RelationSourceLine sources={item.sources} />
        </Link>
      ))}
    </RelationSection>
  );
}

function RelationSection({ title, copy, children }: { title: string; copy: string; children: React.ReactNode }) {
  return <div className="stack"><div><h2 className="section-title">{title}</h2><p className="section-copy">{copy}</p></div><div className="v6-relation-grid">{children}</div></div>;
}

function RelationHead({ label, status }: { label: string; status: string }) {
  return <div className="v6-relation-head"><span>{label}</span><ReviewStatus status={status} compact /></div>;
}

function Empty({ text }: { text: string }) {
  return <div className="card scientific-empty"><h3>داده‌ای ثبت نشده</h3><p>{text}</p></div>;
}
