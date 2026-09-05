"use client";

import Link from "next/link";
import { useState } from "react";
import type { PsychologistDetail, SourceReference } from "@/lib/types";
import {
  BilingualList,
  BilingualText,
  faNumber,
  humanizeCode,
  RelationSourceLine,
  ReviewStatus,
  ScientificSourceList,
} from "./ScientificMeta";

const tabs = [
  ["overview", "نمای کلی"],
  ["theories", "نظریه‌ها"],
  ["concepts", "مفاهیم"],
  ["therapies", "درمان‌ها"],
  ["timeline", "خط زمانی"],
  ["people", "افراد مرتبط"],
  ["sources", "منابع"],
] as const;

type TabId = typeof tabs[number][0];

const relationLabels: Record<string, string> = {
  originated: "صورت‌بندی آغازین",
  proposed: "پیشنهاد / صورت‌بندی",
  co_proposed: "هم‌پیشنهاددهنده",
  developed: "توسعه‌دهنده",
  co_developed: "هم‌توسعه‌دهنده",
  developed_or_majorly_associated_with: "توسعه‌دهنده یا وابستگی تاریخی اصلی",
  expanded: "گسترش‌دهنده",
  popularized: "رواج‌دهنده",
  researched: "پژوهشگر",
  researched_or_developed: "پژوهش یا توسعه مستند",
  applied: "کاربرد / به‌کارگیری",
  contributed_to: "مشارکت مستند",
  criticized: "نقد کرده است",
  challenged: "به چالش کشیده است",
  associated_with: "وابستگی مستند",
  majorly_associated_with: "وابستگی تاریخی مهم",
};

const timelineRoleLabels: Record<string, string> = {
  related: "مرتبط",
  involves_person: "شخص در رویداد دخیل است",
  subject: "موضوع رویداد",
  author: "نویسنده / پدیدآور",
  developer: "توسعه‌دهنده",
  publication: "انتشار",
  institutional: "نهادی",
  context: "زمینه تاریخی",
};

function lifeYears(item: PsychologistDetail) {
  if (!item.birth_year && !item.death_year) return "سال تولد/وفات در داده canonical ثبت نشده";
  const birth = item.birth_year ? faNumber(item.birth_year) : "؟";
  const death = item.death_year ? faNumber(item.death_year) : "اکنون / نامشخص";
  return `${birth} — ${death}`;
}

function explanation(fa: string, en: string) {
  return fa || en;
}

export default function PsychologistDetailView({ psychologist }: { psychologist: PsychologistDetail }) {
  const [active, setActive] = useState<TabId>("overview");
  const sourceCount = psychologist.sources.length;

  return (
    <div className="stack v6-detail psychologist-detail">
      <header className="v6-detail-header psychologist-detail-header">
        <div className="v6-breadcrumb"><Link href="/psychologists">اطلس روان‌شناسان</Link><span>/</span><span>{psychologist.name_fa || psychologist.name_en}</span></div>
        <div className="meta">Psychologists Atlas</div>
        <h1>{psychologist.name_fa || psychologist.name_en}</h1>
        <div className="latin-title">{psychologist.name_en}</div>
        <div className="v6-header-context">
          <span>{lifeYears(psychologist)}</span>
          {(psychologist.nationality_fa || psychologist.nationality_en) && <span>{psychologist.nationality_fa || psychologist.nationality_en}</span>}
          {(psychologist.role_fa || psychologist.role_en) && <span>{psychologist.role_fa || psychologist.role_en}</span>}
        </div>
        <BilingualText
          fa={psychologist.summary_fa}
          en={psychologist.summary_en}
          empty="برای این شخصیت summary عمومی مستقلی در runtime ثبت نشده است؛ relationها، contributionها و منابع پایین صفحه مبنای نمایش هستند."
          className="v6-header-copy"
        />
        {!!psychologist.aliases.length && <div className="v6-aliases v6-detail-aliases">{psychologist.aliases.map(alias => <span key={`${alias.language}-${alias.text}`}>{alias.text}</span>)}</div>}
        <div className="v6-detail-metrics five-col">
          <div><strong>{faNumber(psychologist.theory_count)}</strong><span>نظریه</span></div>
          <div><strong>{faNumber(psychologist.concept_count)}</strong><span>مفهوم</span></div>
          <div><strong>{faNumber(psychologist.therapy_count)}</strong><span>درمان</span></div>
          <div><strong>{faNumber(psychologist.timeline_event_count)}</strong><span>رویداد</span></div>
          <div><strong>{faNumber(sourceCount)}</strong><span>منبع مستقیم</span></div>
        </div>
        <div className="v6-detail-status"><ReviewStatus status={psychologist.review_status} /></div>
        <div className="actions v6-detail-actions">
          {psychologist.timeline_event_count > 0 && <Link className="button primary" href={`/timeline?psychologist=${psychologist.slug}`}>رویدادهای این شخص در Timeline</Link>}
          <Link className="button" href="/theories">کاوش نظریه‌ها</Link>
        </div>
      </header>

      <div className="tabs v6-tabs" role="tablist" aria-label="بخش‌های پروفایل روان‌شناس">
        {tabs.map(([id, label]) => (
          <button className={`tab ${active === id ? "active" : ""}`} key={id} onClick={() => setActive(id)} role="tab" aria-selected={active === id}>{label}</button>
        ))}
      </div>

      <section className="v6-tab-panel">
        {active === "overview" && <Overview psychologist={psychologist} />}
        {active === "theories" && <TheoryRelations psychologist={psychologist} />}
        {active === "concepts" && <ConceptRelations psychologist={psychologist} />}
        {active === "therapies" && <TherapyRelations psychologist={psychologist} />}
        {active === "timeline" && <TimelineRelations psychologist={psychologist} />}
        {active === "people" && <PeopleRelations psychologist={psychologist} />}
        {active === "sources" && <ScientificSourceList links={psychologist.sources} title="منابع مستقیم پروفایل" description="منابع هر relation در همان relation نمایش داده می‌شوند. این فهرست provenance مستقیم خود Psychologist است." />}
      </section>
    </div>
  );
}

function Overview({ psychologist }: { psychologist: PsychologistDetail }) {
  return (
    <div className="grid-2 v6-overview-grid">
      <article className="card v6-prose-card">
        <div className="meta">Contributions</div>
        <h2>مشارکت‌های ثبت‌شده</h2>
        <BilingualList fa={psychologist.contributions_fa} en={psychologist.contributions_en} empty="مشارکت متنی مستقلی ثبت نشده؛ relationهای علمی را در تب‌های بعدی ببین." />
      </article>
      <article className="card v6-prose-card">
        <div className="meta">Historical context</div>
        <h2>زمینه تاریخی</h2>
        <BilingualText fa={psychologist.historical_context_fa} en={psychologist.historical_context_en} />
      </article>
      <article className="card v6-prose-card">
        <div className="meta">Academic disciplines</div>
        <h2>حوزه‌های دانشگاهی ثبت‌شده</h2>
        {psychologist.academic_disciplines.length ? (
          <div className="v6-token-list">{psychologist.academic_disciplines.map(item => <span key={item}>{humanizeCode(item)}</span>)}</div>
        ) : <p className="muted">حوزه دانشگاهی ساختاریافته‌ای ثبت نشده است.</p>}
      </article>
      <article className="card v6-prose-card">
        <div className="meta">Affiliations</div>
        <h2>وابستگی‌های نهادی</h2>
        {psychologist.affiliations.length ? (
          <ul className="scientific-bullet-list ltr-content" lang="en" dir="ltr">{psychologist.affiliations.map((item, index) => <li key={`${index}-${item}`}>{item}</li>)}</ul>
        ) : <p className="muted">Affiliation ساختاریافته‌ای در runtime ثبت نشده است.</p>}
      </article>
      <article className="card v6-guardrail-card">
        <div className="meta">روش نمایش</div>
        <h2>خلأ داده با حدس پر نمی‌شود.</h2>
        <p>سال زندگی، biography، نقش یا ملیت فقط وقتی نمایش داده می‌شوند که در مدل canonical ثبت شده باشند. relationهای تاریخی نیز فقط از edgeهای explicit و provenance‌دار می‌آیند.</p>
      </article>
    </div>
  );
}

function TheoryRelations({ psychologist }: { psychologist: PsychologistDetail }) {
  if (!psychologist.theories.length) return <Empty text="رابطه مستقیمی با Theory در runtime ثبت نشده است." />;
  return (
    <RelationSection title="نظریه‌های متصل" copy="نوع attribution و منبع رابطه مستقل از خود Theory نگه‌داری می‌شود.">
      {psychologist.theories.map(item => (
        <Link href={`/theories/${item.theory.slug}`} className="card v6-relation-card" key={`${item.theory.slug}-${item.relationship_type}`}>
          <RelationHeader label={relationLabels[item.relationship_type] || item.relationship_label} status={item.review_status} />
          <h3>{item.theory.name_fa || item.theory.name_en}</h3><div className="latin-title">{item.theory.name_en}</div>
          <div className="v6-token-list"><span>{humanizeCode(item.theory.domain)}</span>{item.theory.modern_status && <span>{humanizeCode(item.theory.modern_status)}</span>}</div>
          <RelationExplanation fa={item.explanation_fa} en={item.explanation_en} />
          <RelationSourceLine sources={item.sources} />
        </Link>
      ))}
    </RelationSection>
  );
}

function ConceptRelations({ psychologist }: { psychologist: PsychologistDetail }) {
  if (!psychologist.concepts.length) return <Empty text="رابطه مستقیمی با Concept در runtime ثبت نشده است." />;
  return (
    <RelationSection title="مفاهیم متصل" copy="این‌ها attributionهای صریح بین شخص و Concept هستند، نه شباهت محاسبه‌شده.">
      {psychologist.concepts.map(item => (
        <Link href={`/concepts/${item.concept.slug}`} className="card v6-relation-card" key={`${item.concept.slug}-${item.relationship_type}`}>
          <RelationHeader label={relationLabels[item.relationship_type] || item.relationship_label} status={item.review_status} />
          <h3>{item.concept.name_fa || item.concept.name_en}</h3><div className="latin-title">{item.concept.name_en}</div>
          <div className="v6-token-list"><span>{humanizeCode(item.concept.kind)}</span><span>{humanizeCode(item.concept.domain)}</span></div>
          <RelationExplanation fa={item.explanation_fa} en={item.explanation_en} />
          <RelationSourceLine sources={item.sources} />
        </Link>
      ))}
    </RelationSection>
  );
}

function TherapyRelations({ psychologist }: { psychologist: PsychologistDetail }) {
  if (!psychologist.therapies.length) return <Empty text="رابطه مستقیمی با Therapy در runtime ثبت نشده است." />;
  return (
    <RelationSection title="درمان‌های متصل" copy="ارتباط تاریخی شخص با Therapy از ادعای اثربخشی یا توصیه درمانی جدا است.">
      {psychologist.therapies.map(item => (
        <Link href={`/therapies/${item.therapy.slug}`} className="card v6-relation-card" key={`${item.therapy.slug}-${item.relationship_type}`}>
          <RelationHeader label={relationLabels[item.relationship_type] || item.relationship_label} status={item.review_status} />
          <h3>{item.therapy.name_fa || item.therapy.name_en}</h3><div className="latin-title">{item.therapy.name_en}</div>
          {item.therapy.family && <div className="v6-token-list"><span>{item.therapy.family.name_fa || item.therapy.family.name_en}</span></div>}
          <RelationExplanation fa={item.explanation_fa} en={item.explanation_en} />
          <RelationSourceLine sources={item.sources} />
        </Link>
      ))}
    </RelationSection>
  );
}

function TimelineRelations({ psychologist }: { psychologist: PsychologistDetail }) {
  if (!psychologist.timeline_events.length) return <Empty text="رویداد Timeline مستقیمی برای این شخص ثبت نشده است." />;
  const events = [...psychologist.timeline_events].sort((a, b) => (a.event.year_start ?? 9999) - (b.event.year_start ?? 9999));
  return (
    <div className="stack">
      <div className="section-heading-row"><div><h2 className="section-title">رویدادهای تاریخی متصل</h2><p className="section-copy">Role هر اتصال و sourceهای همان اتصال حفظ می‌شوند.</p></div><Link className="button ghost" href={`/timeline?psychologist=${psychologist.slug}`}>نمایش در Timeline کامل</Link></div>
      <div className="v6-timeline-mini-list">
        {events.map(item => (
          <Link href={`/timeline/${item.event.slug}`} className="v6-timeline-mini-row" key={`${item.event.slug}-${item.role}`}>
            <time>{item.event.year_start ? faNumber(item.event.year_start) : item.event.date_text || "؟"}</time>
            <div><span>{timelineRoleLabels[item.role] || item.role_label}</span><strong>{item.event.title_fa || item.event.title_en}</strong><small>{item.event.title_en}</small></div>
            <RelationSourceLine sources={item.sources} />
          </Link>
        ))}
      </div>
    </div>
  );
}

function PeopleRelations({ psychologist }: { psychologist: PsychologistDetail }) {
  if (!psychologist.related_psychologists.length) return <Empty text="رابطه مستقیم Psychologist↔Psychologist در مجموعه فعلی ثبت نشده است." />;
  return (
    <RelationSection title="افراد مرتبط" copy="جهت رابطه در API حفظ شده و در این صفحه حذف نمی‌شود.">
      {psychologist.related_psychologists.map(item => (
        <Link href={`/psychologists/${item.psychologist.slug}`} className="card v6-relation-card" key={`${item.direction}-${item.psychologist.slug}-${item.relationship_type}`}>
          <RelationHeader label={`${item.direction === "outgoing" ? "→" : "←"} ${humanizeCode(item.relationship_type)}`} status={item.review_status} />
          <h3>{item.psychologist.name_fa || item.psychologist.name_en}</h3><div className="latin-title">{item.psychologist.name_en}</div>
          <RelationExplanation fa={item.explanation_fa} en={item.explanation_en} />
          <RelationSourceLine sources={item.sources} />
        </Link>
      ))}
    </RelationSection>
  );
}

function RelationSection({ title, copy, children }: { title: string; copy: string; children: React.ReactNode }) {
  return <div className="stack"><div><h2 className="section-title">{title}</h2><p className="section-copy">{copy}</p></div><div className="v6-relation-grid">{children}</div></div>;
}

function RelationHeader({ label, status }: { label: string; status: string }) {
  return <div className="v6-relation-head"><span>{label}</span><ReviewStatus status={status} compact /></div>;
}

function RelationExplanation({ fa, en }: { fa: string; en: string }) {
  const value = explanation(fa, en);
  if (!value) return <p className="muted">توضیح متنی برای این relation ثبت نشده است.</p>;
  return <p className={!fa && !!en ? "ltr-summary" : ""} lang={!fa && !!en ? "en" : undefined} dir={!fa && !!en ? "ltr" : undefined}>{value}</p>;
}

function Empty({ text }: { text: string }) {
  return <div className="card scientific-empty"><h3>داده‌ای ثبت نشده</h3><p>{text}</p></div>;
}

export function CompactRelationSources({ sources }: { sources: SourceReference[] }) {
  return <RelationSourceLine sources={sources} />;
}
