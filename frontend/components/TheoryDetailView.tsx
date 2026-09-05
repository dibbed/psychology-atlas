"use client";

import Link from "next/link";
import { useState } from "react";
import type { TheoryDetail } from "@/lib/types";
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
  ["people", "افراد"],
  ["concepts", "مفاهیم"],
  ["practice", "درمان و تکنیک"],
  ["theories", "نظریه‌های مرتبط"],
  ["timeline", "خط زمانی"],
  ["sources", "منابع"],
] as const;

type TabId = typeof tabs[number][0];

const theoryRelationLabels: Record<string, string> = {
  grounds: "مبنای نظری",
  includes_construct: "شامل سازه",
  informs: "اطلاع‌رسان / شکل‌دهنده",
  supports: "پشتیبان",
  complements: "مکمل",
  challenges: "به چالش می‌کشد",
  challenged_by: "به چالش کشیده شده توسط",
  reformulated_as: "بازصورت‌بندی شده به",
  supports_interpretation_of: "پشتیبان تفسیر",
  extends: "گسترش می‌دهد",
  refines: "دقیق‌تر می‌کند",
  associated_with: "مرتبط با",
};

const attributionLabels: Record<string, string> = {
  originated: "صورت‌بندی آغازین",
  proposed: "پیشنهاد / صورت‌بندی",
  co_proposed: "هم‌پیشنهاددهنده",
  developed: "توسعه‌دهنده",
  co_developed: "هم‌توسعه‌دهنده",
  developed_or_majorly_associated_with: "توسعه‌دهنده یا وابستگی تاریخی اصلی",
  expanded: "گسترش‌دهنده",
  researched: "پژوهشگر",
  researched_or_developed: "پژوهش یا توسعه مستند",
  contributed_to: "مشارکت مستند",
  associated_with: "وابستگی مستند",
  majorly_associated_with: "وابستگی تاریخی مهم",
};

function explanation(fa: string, en: string) {
  if (fa) return <p>{fa}</p>;
  if (en) return <p className="ltr-summary" lang="en" dir="ltr">{en}</p>;
  return <p className="muted">توضیح متنی برای این relation ثبت نشده است.</p>;
}

export default function TheoryDetailView({ theory }: { theory: TheoryDetail }) {
  const [active, setActive] = useState<TabId>("overview");

  return (
    <div className="stack v6-detail theory-detail">
      <header className="v6-detail-header theory-detail-header">
        <div className="v6-breadcrumb"><Link href="/theories">اطلس نظریه‌ها</Link><span>/</span><span>{theory.name_fa || theory.name_en}</span></div>
        <div className="meta">Theory Atlas · {humanizeCode(theory.domain)}</div>
        <h1>{theory.name_fa || theory.name_en}</h1>
        <div className="latin-title">{theory.name_en}</div>
        <div className="v6-header-context">
          {theory.period_text && <span>{humanizeCode(theory.period_text)}</span>}
          {theory.modern_status && <span>{humanizeCode(theory.modern_status)}</span>}
          <span>{humanizeCode(theory.domain)}</span>
        </div>
        <BilingualText fa={theory.summary_fa} en={theory.summary_en} empty="summary عمومی مستقیمی برای این نظریه ثبت نشده است؛ proposition، relationها و منابع پایین صفحه را ببین." className="v6-header-copy" />
        {!!theory.aliases.length && <div className="v6-aliases v6-detail-aliases">{theory.aliases.map(alias => <span key={`${alias.language}-${alias.text}`}>{alias.text}</span>)}</div>}
        <div className="v6-detail-metrics six-col">
          <div><strong>{faNumber(theory.psychologist_count)}</strong><span>روان‌شناس</span></div>
          <div><strong>{faNumber(theory.concept_count)}</strong><span>مفهوم</span></div>
          <div><strong>{faNumber(theory.therapy_count)}</strong><span>درمان</span></div>
          <div><strong>{faNumber(theory.technique_count)}</strong><span>تکنیک</span></div>
          <div><strong>{faNumber(theory.timeline_event_count)}</strong><span>رویداد</span></div>
          <div><strong>{faNumber(theory.sources.length)}</strong><span>منبع مستقیم</span></div>
        </div>
        <div className="v6-detail-status"><ReviewStatus status={theory.review_status} /></div>
        <div className="actions v6-detail-actions">
          {theory.timeline_event_count > 0 && <Link className="button primary" href={`/timeline?theory=${theory.slug}`}>رویدادهای این نظریه در Timeline</Link>}
          <Link className="button" href="/psychologists">روان‌شناسان</Link>
        </div>
      </header>

      <div className="tabs v6-tabs" role="tablist" aria-label="بخش‌های پروفایل نظریه">
        {tabs.map(([id, label]) => <button className={`tab ${active === id ? "active" : ""}`} key={id} onClick={() => setActive(id)} role="tab" aria-selected={active === id}>{label}</button>)}
      </div>

      <section className="v6-tab-panel">
        {active === "overview" && <Overview theory={theory} />}
        {active === "people" && <People theory={theory} />}
        {active === "concepts" && <Concepts theory={theory} />}
        {active === "practice" && <Practice theory={theory} />}
        {active === "theories" && <RelatedTheories theory={theory} />}
        {active === "timeline" && <Timeline theory={theory} />}
        {active === "sources" && <ScientificSourceList links={theory.sources} title="منابع مستقیم نظریه" description="این فهرست provenance مستقیم Theory است؛ sourceهای هر relation در همان relation نمایش داده می‌شوند." />}
      </section>
    </div>
  );
}

function Overview({ theory }: { theory: TheoryDetail }) {
  return (
    <div className="grid-2 v6-overview-grid theory-overview-grid">
      <article className="card v6-prose-card theory-core-card">
        <div className="meta">Core proposition</div><h2>گزاره محوری</h2>
        <BilingualText fa={theory.core_proposition_fa} en={theory.core_proposition_en} />
      </article>
      <article className="card v6-prose-card">
        <div className="meta">Historical context</div><h2>زمینه تاریخی</h2>
        <BilingualText fa={theory.historical_context_fa} en={theory.historical_context_en} />
      </article>
      <article className="card v6-prose-card">
        <div className="meta">Key propositions</div><h2>گزاره‌های کلیدی</h2>
        <BilingualList fa={theory.key_propositions_fa} en={theory.key_propositions_en} />
      </article>
      <article className="card v6-prose-card">
        <div className="meta">Applications</div><h2>کاربردهای ثبت‌شده</h2>
        <BilingualList fa={theory.applications_fa} en={theory.applications_en} />
      </article>
      <article className="card v6-prose-card theory-critical-card">
        <div className="meta">Criticisms</div><h2>نقدهای ثبت‌شده در corpus</h2>
        <BilingualList fa={theory.criticisms_fa} en={theory.criticisms_en} empty="نقد ساختاریافته‌ای در این رکورد ثبت نشده است." />
      </article>
      <article className="card v6-prose-card theory-critical-card">
        <div className="meta">Limitations</div><h2>محدودیت‌های ثبت‌شده</h2>
        <BilingualList fa={theory.limitations_fa} en={theory.limitations_en} empty="محدودیت ساختاریافته‌ای در این رکورد ثبت نشده است." />
      </article>
      <article className="card v6-prose-card">
        <div className="meta">Historical importance</div><h2>اهمیت تاریخی</h2>
        <BilingualText fa={theory.historical_importance_fa} en={theory.historical_importance_en} />
      </article>
      <article className="card v6-guardrail-card">
        <div className="meta">تفسیر status</div><h2>Modern status حکم ارزشی نیست.</h2>
        <p>مقدار ثبت‌شده: <code>{theory.modern_status || "ثبت‌نشده"}</code>. UI آن را برای خوانایی humanize می‌کند اما ادعای «اثبات/رد» جدیدی از آن نمی‌سازد.</p>
      </article>
    </div>
  );
}

function People({ theory }: { theory: TheoryDetail }) {
  if (!theory.psychologists.length) return <Empty text="Psychologist صریحی به این Theory متصل نشده است." />;
  return (
    <RelationSection title="روان‌شناسان متصل" copy="Attribution تاریخی با relationship_type و provenance خود relation نمایش داده می‌شود.">
      {theory.psychologists.map(item => (
        <Link href={`/psychologists/${item.psychologist.slug}`} className="card v6-relation-card" key={`${item.psychologist.slug}-${item.relationship_type}`}>
          <RelationHead label={attributionLabels[item.relationship_type] || item.relationship_label} status={item.review_status} />
          <h3>{item.psychologist.name_fa || item.psychologist.name_en}</h3><div className="latin-title">{item.psychologist.name_en}</div>
          {explanation(item.explanation_fa, item.explanation_en)}
          <RelationSourceLine sources={item.sources} />
        </Link>
      ))}
    </RelationSection>
  );
}

function Concepts({ theory }: { theory: TheoryDetail }) {
  if (!theory.concepts.length) return <Empty text="Concept صریحی به این Theory متصل نشده است." />;
  return (
    <RelationSection title="سازه‌ها و مفاهیم متصل" copy="Connection فقط از relationهای explicit دیتابیس می‌آید.">
      {theory.concepts.map(item => (
        <Link href={`/concepts/${item.concept.slug}`} className="card v6-relation-card" key={`${item.concept.slug}-${item.relationship_type}`}>
          <RelationHead label={theoryRelationLabels[item.relationship_type] || item.relationship_label} status={item.review_status} />
          <h3>{item.concept.name_fa || item.concept.name_en}</h3><div className="latin-title">{item.concept.name_en}</div>
          <div className="v6-token-list"><span>{humanizeCode(item.concept.kind)}</span><span>{humanizeCode(item.concept.domain)}</span></div>
          {explanation(item.explanation_fa, item.explanation_en)}
          <RelationSourceLine sources={item.sources} />
        </Link>
      ))}
    </RelationSection>
  );
}

function Practice({ theory }: { theory: TheoryDetail }) {
  if (!theory.therapies.length && !theory.techniques.length) return <Empty text="Therapy یا Technique صریحی به این Theory متصل نشده است." />;
  return (
    <div className="stack">
      {!!theory.therapies.length && (
        <RelationSection title="اتصال به Therapy" copy="این relation تاریخی/نظری است و رتبه‌بندی اثربخشی یا توصیه درمانی نیست.">
          {theory.therapies.map(item => (
            <Link href={`/therapies/${item.therapy.slug}`} className="card v6-relation-card" key={`${item.therapy.slug}-${item.relationship_type}`}>
              <RelationHead label={theoryRelationLabels[item.relationship_type] || item.relationship_label} status={item.review_status} />
              <h3>{item.therapy.name_fa || item.therapy.name_en}</h3><div className="latin-title">{item.therapy.name_en}</div>
              {item.therapy.family && <div className="v6-token-list"><span>{item.therapy.family.name_fa || item.therapy.family.name_en}</span></div>}
              {explanation(item.explanation_fa, item.explanation_en)}
              <RelationSourceLine sources={item.sources} />
            </Link>
          ))}
        </RelationSection>
      )}
      {!!theory.techniques.length && (
        <RelationSection title="اتصال به Technique" copy="Technique مستقل از Therapy نمایش داده می‌شود.">
          {theory.techniques.map(item => (
            <Link href={`/techniques/${item.technique.slug}`} className="card v6-relation-card" key={`${item.technique.slug}-${item.relationship_type}`}>
              <RelationHead label={theoryRelationLabels[item.relationship_type] || item.relationship_label} status={item.review_status} />
              <h3>{item.technique.name_fa || item.technique.name_en}</h3><div className="latin-title">{item.technique.name_en}</div>
              {explanation(item.explanation_fa, item.explanation_en)}
              <RelationSourceLine sources={item.sources} />
            </Link>
          ))}
        </RelationSection>
      )}
    </div>
  );
}

function RelatedTheories({ theory }: { theory: TheoryDetail }) {
  if (!theory.related_theories.length) return <Empty text="Theory↔Theory صریحی برای این رکورد ثبت نشده است." />;
  return (
    <RelationSection title="نظریه‌های مرتبط" copy="جهت رابطه و semantics خام relation حفظ می‌شود.">
      {theory.related_theories.map(item => (
        <Link href={`/theories/${item.theory.slug}`} className="card v6-relation-card" key={`${item.direction}-${item.theory.slug}-${item.relationship_type}`}>
          <RelationHead label={`${item.direction === "outgoing" ? "→" : "←"} ${theoryRelationLabels[item.relationship_type] || item.relationship_label}`} status={item.review_status} />
          <h3>{item.theory.name_fa || item.theory.name_en}</h3><div className="latin-title">{item.theory.name_en}</div>
          <div className="v6-token-list"><span>{humanizeCode(item.theory.domain)}</span>{item.theory.modern_status && <span>{humanizeCode(item.theory.modern_status)}</span>}</div>
          {explanation(item.explanation_fa, item.explanation_en)}
          <RelationSourceLine sources={item.sources} />
        </Link>
      ))}
    </RelationSection>
  );
}

function Timeline({ theory }: { theory: TheoryDetail }) {
  if (!theory.timeline_events.length) return <Empty text="رویداد Timeline مستقیمی برای این Theory ثبت نشده است." />;
  const rows = [...theory.timeline_events].sort((a, b) => (a.event.year_start ?? 9999) - (b.event.year_start ?? 9999));
  return (
    <div className="stack">
      <div className="section-heading-row"><div><h2 className="section-title">رویدادهای متصل</h2><p className="section-copy">Milestoneهای Theory با role و provenance همان relation نمایش داده می‌شوند.</p></div><Link className="button ghost" href={`/timeline?theory=${theory.slug}`}>نمایش در Timeline کامل</Link></div>
      <div className="v6-timeline-mini-list">
        {rows.map(item => (
          <Link href={`/timeline/${item.event.slug}`} className="v6-timeline-mini-row" key={`${item.event.slug}-${item.role}`}>
            <time>{item.event.year_start ? faNumber(item.event.year_start) : item.event.date_text || "؟"}</time>
            <div><span>{humanizeCode(item.role)}</span><strong>{item.event.title_fa || item.event.title_en}</strong><small>{item.event.title_en}</small></div>
            <RelationSourceLine sources={item.sources} />
          </Link>
        ))}
      </div>
    </div>
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
