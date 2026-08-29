"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import BookmarkButton from "./BookmarkButton";
import ConceptMap from "./ConceptMap";
import NoteEditor from "./NoteEditor";
import ProgressTracker from "./ProgressTracker";
import { StructuredValue } from "./DSMRecordView";
import type { DSMRecordDetail, DisorderDetail } from "@/lib/types";
import { rememberDisorder } from "@/lib/recentlyViewed";

const tabs = [
  ["overview", "معرفی"],
  ["symptoms", "نشانه‌ها"],
  ["clinical", "ویژگی‌های بالینی"],
  ["differential", "تشخیص افتراقی"],
  ["assessment", "ارزیابی"],
  ["treatment", "درمان"],
  ["study", "تمرین"],
  ["dsm", "DSM MASTER"],
  ["map", "نقشه مفهومی"],
  ["notes", "یادداشت من"],
  ["sources", "منابع"],
] as const;

type TabId = typeof tabs[number][0];

function difficultyLabel(value: string) {
  if (value === "introductory") return "مقدماتی";
  if (value === "intermediate") return "متوسط";
  if (value === "advanced") return "پیشرفته";
  return value;
}

function domainLabel(value: string) {
  const labels: Record<string, string> = {
    cognitive: "شناختی",
    emotional: "هیجانی",
    behavioral: "رفتاری",
    somatic: "جسمانی",
    interpersonal: "بین‌فردی",
    other: "سایر",
  };
  return labels[value] || "ویژگی";
}

export default function DisorderDetailClient({ disorder: d, dsmMaster = null }: { disorder: DisorderDetail; dsmMaster?: DSMRecordDetail | null }) {
  const [active, setActive] = useState<TabId>("overview");

  useEffect(() => {
    rememberDisorder(d);
  }, [d]);

  return (
    <>
      <ProgressTracker slug={d.slug} />
      <header className="detail-header">
        <div className="meta">{d.category}</div>
        <h1>{d.name_fa || d.name_en}</h1>
        {d.name_en && d.name_en !== d.name_fa && <div className="latin-title disorder-detail-en">{d.name_en}</div>}
        <p className="section-copy">{d.short_description}</p>
        <div className="actions" style={{ marginTop: 20 }}>
          <BookmarkButton slug={d.slug} />
          <Link className="button" href={`/compare?add=${d.slug}`}>مقایسه با اختلال دیگر</Link>
          {dsmMaster && <Link className="button dsm-master-button" href={`/dsm/${encodeURIComponent(dsmMaster.master_id)}`}>DSM MASTER · {dsmMaster.master_id.replace("DSM5TR-FA-", "")}</Link>}
        </div>
      </header>

      <div className="tabs" role="tablist" aria-label="بخش‌های صفحه اختلال">
        {tabs.map(([id, label]) => (
          <button
            className={`tab ${active === id ? "active" : ""}`}
            key={id}
            onClick={() => setActive(id)}
            role="tab"
            aria-selected={active === id}
          >
            {label}
          </button>
        ))}
      </div>

      <section className="tab-panel">
        {active === "overview" && (
          <div className="grid-2">
            <article className="prose card">
              <h2>معرفی</h2>
              <p>{d.overview}</p>
              <h2>شروع معمول</h2>
              <p>{d.typical_onset || "زمان شروع می‌تواند متفاوت باشد."}</p>
              <h2>سیر</h2>
              <p>{d.course_note}</p>
            </article>
            <aside className="card">
              <div className="meta">خلاصه مطالعه</div>
              <h3 style={{ marginTop: 10 }}>{d.name_fa || d.name_en}</h3>
              <p>{d.short_description}</p>
              <div className="study-hint">
                این صفحه برای یادگیری و مرور دانشگاهی طراحی شده و ابزار تشخیص فردی نیست.
              </div>
              {dsmMaster && (
                <Link className="dsm-master-bridge" href={`/dsm/${encodeURIComponent(dsmMaster.master_id)}`}>
                  <span>DSM MASTER</span>
                  <strong>{dsmMaster.classification_status}</strong>
                  <small>پروفایل آموزشی ممیزی‌شده، ارزیابی هدفمند، افتراق، سیر، مدیریت و منابع ←</small>
                </Link>
              )}
            </aside>
          </div>
        )}

        {active === "symptoms" && (
          <div className="stack">
            <div>
              <h2 className="section-title">نشانه‌ها و ویژگی‌های مرتبط</h2>
              <p className="section-copy">این موارد برای سازمان‌دهی آموزشی‌اند و فهرست تشخیصی کامل محسوب نمی‌شوند.</p>
            </div>
            <div className="symptom-grid">
              {d.symptoms.map(s => (
                <div className="symptom-card" key={s.slug}>
                  <div className="meta">{domainLabel(s.domain)}</div>
                  <h3>{s.name_fa || s.name_en}</h3>
                  {s.description && <p>{s.description}</p>}
                </div>
              ))}
            </div>
          </div>
        )}

        {active === "clinical" && (
          <article className="prose card">
            <h2>ویژگی‌های بالینی</h2>
            <p>{d.clinical_features}</p>
            <h2>عوامل خطر و زمینه‌ای</h2>
            <p>{d.risk_factors}</p>
          </article>
        )}

        {active === "differential" && (
          <div className="stack">
            <div>
              <h2 className="section-title">تشخیص افتراقی و موضوعات مرتبط</h2>
              <p className="section-copy">روابط زیر فقط زمانی نمایش داده می‌شوند که در داده ساختاریافته پروژه ثبت شده باشند.</p>
            </div>
            {d.related.length ? d.related.map(r => (
              <div className="card differential-card" key={`${r.slug}-${r.relationship_type}`}>
                <div>
                  <div className="meta">{r.relationship_type === "differential" ? "تشخیص افتراقی" : r.relationship_type === "commonly_confused" ? "اغلب اشتباه می‌شود با" : "مرتبط"}</div>
                  <Link href={`/disorders/${r.slug}`}><h3>{r.name_fa || r.name_en}</h3></Link>
                </div>
                <p>{r.explanation}</p>
              </div>
            )) : <div className="card"><p>هنوز رابطه افتراقی برای این اختلال ثبت نشده است.</p></div>}
          </div>
        )}

        {active === "assessment" && (
          <article className="prose card">
            <h2>تمرکز ارزیابی</h2>
            <p>{d.assessment_overview}</p>
            <div className="study-hint">در ارزیابی واقعی، شرایط جسمانی، مصرف مواد، ایمنی و زمینه فردی باید بر اساس مورد بررسی شوند.</div>
          </article>
        )}

        {active === "treatment" && (
          <article className="prose card">
            <h2>نمای کلی درمان</h2>
            <p>{d.treatment_overview}</p>
            <div className="study-hint">این بخش آموزشی است و توصیه درمانی شخصی ارائه نمی‌کند.</div>
          </article>
        )}

        {active === "study" && (
          <div className="grid-2">
            <div className="card stack" style={{ gap: 12 }}>
              <div className="meta">آزمون‌های مرتبط</div>
              {d.study_resources.quizzes.length ? d.study_resources.quizzes.map(q => (
                <Link className="resource-link" href={`/quizzes/${q.slug}`} key={q.slug}>
                  <strong>{q.title}</strong><span>شروع آزمون ←</span>
                </Link>
              )) : <p>آزمون مستقیمی برای این اختلال ثبت نشده است.</p>}
            </div>
            <div className="card stack" style={{ gap: 12 }}>
              <div className="meta">کیس‌های مرتبط</div>
              {d.study_resources.cases.length ? d.study_resources.cases.map(c => (
                <Link className="resource-link" href={`/cases/${c.slug}`} key={c.slug}>
                  <strong>{c.title}</strong><span>سطح {difficultyLabel(c.difficulty)} ←</span>
                </Link>
              )) : <p>کیس مستقیمی برای این اختلال ثبت نشده است.</p>}
            </div>
          </div>
        )}

        {active === "dsm" && dsmMaster && (
          <div className="stack dsm-disorder-tab">
            <div className="dsm-scope-warning">
              <strong>{dsmMaster.classification_status}</strong>
              <p>{dsmMaster.summary}</p>
            </div>
            <div className="grid-2">
              <article className="card">
                <div className="meta">ارزیابی هدفمند MASTER</div>
                <StructuredValue value={dsmMaster.assessment} />
              </article>
              <article className="card">
                <div className="meta">افتراق تشخیصی هدفمند</div>
                <StructuredValue value={dsmMaster.differential} />
              </article>
              <article className="card">
                <div className="meta">سیر و پیش‌آگهی آموزشی</div>
                <p>{dsmMaster.course}</p>
              </article>
              <article className="card">
                <div className="meta">ملاحظات فرهنگی و زمینه‌ای</div>
                <p>{dsmMaster.context_considerations}</p>
              </article>
            </div>
            <div className="dsm-exam-tip"><div className="meta">نکته امتحانی MASTER</div><p>{dsmMaster.exam_tip}</p></div>
            <section className="card">
              <div className="meta">Self-Test پیشرفته</div>
              <StructuredValue value={dsmMaster.self_test} />
            </section>
            <div className="actions"><Link className="button primary" href={`/dsm/${dsmMaster.master_id}`}>باز کردن پروفایل کامل MASTER</Link><Link className="button" href={`/map?scope=dsm&node=${dsmMaster.master_id}`}>دیدن در DSM Graph</Link></div>
          </div>
        )}
        {active === "dsm" && !dsmMaster && <div className="card">برای این اختلال رکورد DSM MASTER متصل پیدا نشد.</div>}
        {active === "map" && <ConceptMap disorder={d} />}
        {active === "notes" && <NoteEditor slug={d.slug} />}

        {active === "sources" && (
          <div className="stack">
            <div>
              <h2 className="section-title">منابع آموزشی</h2>
              <p className="section-copy">در این نسخه منابع نهادی سطح بالا به داده‌ها متصل شده‌اند؛ در نسخه‌های بعدی می‌توان منبع اختصاصی هر ادعا را ریزتر ثبت کرد.</p>
            </div>
            {d.sources.map(s => (
              <a className="card resource-link" key={s.id} href={s.url} target="_blank" rel="noreferrer">
                <strong>{s.organization === "National Institute of Mental Health" ? "مؤسسه ملی سلامت روان آمریکا" : s.organization === "World Health Organization" ? "سازمان جهانی بهداشت" : s.organization || s.title}</strong>
                <span>مشاهده منبع ↗</span>
              </a>
            ))}
          </div>
        )}
      </section>
    </>
  );
}
