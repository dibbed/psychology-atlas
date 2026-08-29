"use client";

import Link from "next/link";
import { useState } from "react";
import type { ConceptDetail } from "@/lib/types";
import ConceptBookmarkButton from "./ConceptBookmarkButton";
import ConceptNoteEditor from "./ConceptNoteEditor";
import ConceptNeighborhood from "./ConceptNeighborhood";
import ConceptProgressTracker from "./ConceptProgressTracker";
import { conceptKindLabel } from "./ConceptCard";

const tabs = [
  ["overview", "تعریف"],
  ["example", "مثال"],
  ["relations", "روابط مفهومی"],
  ["disorders", "اختلالات مرتبط"],
  ["symptoms", "نشانه‌ها"],
  ["neighborhood", "همسایگی"],
  ["notes", "یادداشت من"],
  ["sources", "منابع"],
] as const;

type TabId = typeof tabs[number][0];

const relationLabels: Record<string, string> = {
  related: "مرتبط",
  part_of: "جزئی از",
  subtype_of: "زیرنوع",
  prerequisite: "پیش‌نیاز",
  maintains: "حفظ‌کننده",
  influences: "اثرگذار",
  mechanism: "سازوکار",
  contrasts: "مقایسه/تفاوت",
  commonly_confused_with: "اغلب اشتباه می‌شود با",
  associated_with: "همراه/مرتبط با",
  applied_in: "کاربرد",
};

const symptomRelationLabels: Record<string, string> = {
  associated: "مرتبط",
  manifestation: "بازنمایی در لایه نشانه",
  overlaps_with: "همپوشانی",
  contrasts: "افتراق",
};

const roleLabels: Record<string, string> = {
  core: "مفهوم محوری",
  associated: "مرتبط",
  maintaining: "عامل حفظ‌کننده",
  assessment: "ارزیابی",
  treatment: "درمان/مداخله",
  differential: "افتراقی",
};

export default function ConceptDetailClient({ concept }: { concept: ConceptDetail }) {
  const [active, setActive] = useState<TabId>("overview");

  return (
    <>
      <ConceptProgressTracker slug={concept.slug} />
      <header className="detail-header concept-detail-header">
        <div className="meta">{conceptKindLabel(concept.kind)} · {concept.domain_label || concept.domain} · واژه‌نامه و نقشه دانش</div>
        <h1>{concept.name_fa || concept.name_en}</h1>
        <div className="latin-title">{concept.name_en}</div>
        <p className="section-copy">{concept.simple_definition}</p>
        {!!concept.aliases?.length && (
          <p className="muted small">نام‌های جایگزین: {concept.aliases.map(alias => alias.text).join(" · ")}</p>
        )}
        <div className="concept-detail-metrics">
          <div><strong>{(concept.relationship_count ?? 0).toLocaleString("fa-IR")}</strong><span>رابطه مفهومی</span></div>
          <div><strong>{(concept.disorder_count ?? 0).toLocaleString("fa-IR")}</strong><span>اختلال مرتبط</span></div>
          <div><strong>{(concept.flashcard_count ?? 0).toLocaleString("fa-IR")}</strong><span>فلش‌کارت</span></div>
        </div>
        <div className="actions" style={{ marginTop: 20 }}>
          <ConceptBookmarkButton slug={concept.slug} />
          {(concept.flashcard_count ?? 0) > 0 && <Link className="button" href={`/flashcards?concept=${concept.slug}`}>مرور فلش‌کارت‌های این مفهوم</Link>}
          <Link className="button" href={`/map?node=concept:${concept.slug}`}>دیدن در نقشه دانش</Link>
        </div>
      </header>

      <div className="tabs" role="tablist" aria-label="بخش‌های مفهوم">
        {tabs.map(([id, label]) => (
          <button className={`tab ${active === id ? "active" : ""}`} key={id} onClick={() => setActive(id)} role="tab" aria-selected={active === id}>
            {label}
          </button>
        ))}
      </div>

      <section className="tab-panel">
        {active === "overview" && (
          <div className="grid-2">
            <article className="prose card">
              <div className="meta">تعریف ساده</div>
              <h2>{concept.name_fa || concept.name_en}</h2>
              <p>{concept.simple_definition}</p>
            </article>
            <article className="prose card">
              <div className="meta">تعریف دانشگاهی</div>
              <h2>در سطح مفهومی</h2>
              <p>{concept.academic_definition || "تعریف دانشگاهی تکمیلی هنوز ثبت نشده است."}</p>
            </article>
            {concept.subtype === "cognitive_distortion" && concept.recognition_cues && (
              <article className="prose card">
                <div className="meta">نشانه‌های شناخت الگو</div>
                <h2>چطور تشخیصش بدهیم؟</h2>
                <p>{concept.recognition_cues}</p>
              </article>
            )}
            {concept.subtype === "cognitive_distortion" && concept.common_confusions && (
              <article className="prose card">
                <div className="meta">افتراق مفهومی</div>
                <h2>با چه چیزی اشتباه می‌شود؟</h2>
                <p>{concept.common_confusions}</p>
              </article>
            )}
          </div>
        )}

        {active === "example" && (
          <div className="card concept-example">
            <div className="meta">مثال آموزشی</div>
            <blockquote>{concept.example || "برای این مفهوم هنوز مثال آموزشی ثبت نشده است."}</blockquote>
            {concept.counterexample && (
              <div className="card" style={{ marginTop: 16 }}>
                <div className="meta">نمونه متوازن / غیرتحریف‌شده</div>
                <p>{concept.counterexample}</p>
              </div>
            )}
            <p className="muted small">مثال برای فهم مفهوم است و برای نتیجه‌گیری تشخیصی درباره افراد طراحی نشده است.</p>
          </div>
        )}

        {active === "relations" && (
          <div className="stack">
            <div><h2 className="section-title">روابط ثبت‌شده در Knowledge Graph</h2><p className="section-copy">رابطه‌ها از داده ساختاریافته پروژه می‌آیند و درصد شباهت ساختگی ندارند.</p></div>
            {concept.relationships.length ? concept.relationships.map(item => (
              <Link className="card relation-row" href={`/concepts/${item.slug}`} key={`${item.slug}-${item.relationship_type}-${item.direction}`}>
                <div>
                  <div className="meta">{relationLabels[item.relationship_type] || item.relationship_type}</div>
                  <h3>{item.name_fa || item.name_en}</h3>
                </div>
                <div>
                  <p>{item.explanation || "رابطه ساختاریافته بین این دو مفهوم ثبت شده است."}</p>
                  {!!item.sources?.length && <small className="muted">منبع رابطه: {item.sources.map(source => source.organization || source.title).join(" · ")}</small>}
                </div>
              </Link>
            )) : <div className="card">هنوز رابطه مفهومی مستقیمی ثبت نشده است.</div>}
          </div>
        )}

        {active === "disorders" && (
          <div className="stack">
            {concept.disorders.length ? concept.disorders.map(item => (
              <Link className="card relation-row" href={`/disorders/${item.disorder.slug}`} key={`${item.disorder.slug}-${item.role}`}>
                <div>
                  <div className="meta">{roleLabels[item.role] || item.role}</div>
                  <h3>{item.disorder.name_fa || item.disorder.name_en}</h3>
                </div>
                <p>{item.explanation || item.disorder.short_description}</p>
              </Link>
            )) : <div className="card">هنوز اختلال مستقیمی به این مفهوم متصل نشده است.</div>}
          </div>
        )}

        {active === "symptoms" && (
          <div className="stack">
            {concept.symptoms.length ? concept.symptoms.map(item => (
              <Link className="card relation-row" href={`/search?q=${encodeURIComponent(item.name_fa || item.name_en)}`} key={`${item.slug}-${item.relationship_type}`}>
                <div>
                  <div className="meta">{symptomRelationLabels[item.relationship_type] || item.relationship_type}</div>
                  <h3>{item.name_fa || item.name_en}</h3>
                  <div className="latin-title">{item.name_en}</div>
                </div>
                <p>{item.explanation || "رابطه ساختاریافته میان این مفهوم و نشانه ثبت شده است."}</p>
              </Link>
            )) : <div className="card">هنوز نشانه ساختاریافته‌ای به این مفهوم متصل نشده است.</div>}
          </div>
        )}

        {active === "neighborhood" && <ConceptNeighborhood slug={concept.slug} />}

        {active === "notes" && <ConceptNoteEditor slug={concept.slug} />}

        {active === "sources" && (
          <div className="stack">
            <p className="section-copy">منابع این نسخه در سطح نهادی به مفهوم متصل شده‌اند و در نسخه‌های بعدی می‌توان citation را تا سطح ادعا ریزتر کرد.</p>
            {concept.sources.map(source => (
              <a className="card resource-link" key={source.id} href={source.url} target="_blank" rel="noreferrer">
                <strong>{source.organization || source.title}</strong><span>مشاهده منبع ↗</span>
              </a>
            ))}
          </div>
        )}
      </section>
    </>
  );
}
