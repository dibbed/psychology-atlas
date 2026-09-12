import type { ScientificEntitySourceLink, SourceReference } from "@/lib/types";

const reviewLabels: Record<string, string> = {
  unreviewed: "بازبینی‌نشده",
  source_checked: "دارای منبع؛ بازبینی نهایی نشده",
  reviewed: "بازبینی علمی ثبت‌شده",
};

const sourceRoleLabels: Record<string, string> = {
  biography: "زندگی‌نامه",
  primary_work: "اثر اصلی",
  institutional: "منبع نهادی",
  historical_review: "مرور تاریخی",
  primary_publication: "انتشار اصلی",
  evidence_review: "مرور شواهد",
  primary: "منبع اصلی",
  other: "منبع تکمیلی",
};

const verificationLabels: Record<string, string> = {
  verified: "راستی‌آزمایی‌شده",
  web_verified_doi_and_pmid: "DOI و PMID راستی‌آزمایی‌شده",
  web_verified_doi: "DOI راستی‌آزمایی‌شده",
  search_verified: "راستی‌آزمایی‌شده با جست‌وجو",
  search_context_verified: "زمینه منبع راستی‌آزمایی‌شده",
  citation_from_model_knowledge: "ارجاع آرشیوی؛ نیازمند بازبینی مستقل",
};

export function verificationStatusLabel(status: string) {
  return verificationLabels[status] || humanizeCode(status);
}

export function faNumber(value: number) {
  return value.toLocaleString("fa-IR");
}

export function humanizeCode(value: string) {
  if (!value) return "ثبت‌نشده";
  return value.replaceAll("_", " ").replace(/\s+/g, " ").trim();
}

export function ReviewStatus({ status, compact = false }: { status: string; compact?: boolean }) {
  return (
    <span className={`scientific-review-status review-${status} ${compact ? "compact" : ""}`}>
      <span aria-hidden="true" />
      {reviewLabels[status] || humanizeCode(status)}
    </span>
  );
}

export function BilingualText({
  fa,
  en,
  empty = "متن تکمیلی برای این بخش ثبت نشده است.",
  className = "",
}: {
  fa?: string | null;
  en?: string | null;
  empty?: string;
  className?: string;
}) {
  if (fa?.trim()) return <p className={className}>{fa}</p>;
  if (en?.trim()) {
    return (
      <div className={`scientific-english-fallback ${className}`.trim()}>
        <span>متن موجود در داده منبع انگلیسی است</span>
        <p lang="en" dir="ltr">{en}</p>
      </div>
    );
  }
  return <p className={`muted ${className}`.trim()}>{empty}</p>;
}

export function BilingualList({
  fa,
  en,
  empty = "موردی ثبت نشده است.",
}: {
  fa?: string[] | null;
  en?: string[] | null;
  empty?: string;
}) {
  const rows = fa?.length ? fa : en?.length ? en : [];
  const isEnglish = !fa?.length && !!en?.length;
  if (!rows.length) return <p className="muted">{empty}</p>;
  return (
    <ul className={`scientific-bullet-list ${isEnglish ? "ltr-content" : ""}`} lang={isEnglish ? "en" : undefined} dir={isEnglish ? "ltr" : undefined}>
      {rows.map((row, index) => <li key={`${index}-${row}`}>{humanizeCode(row)}</li>)}
    </ul>
  );
}

export function SourceVerificationSummary({ sources }: { sources: { verification_status?: string }[] }) {
  const weakOnly = sources.length > 0 && sources.every(
    source => source.verification_status === "citation_from_model_knowledge"
  );
  if (!weakOnly) return null;
  return (
    <small className="scientific-source-warning">
      {verificationStatusLabel("citation_from_model_knowledge")}
    </small>
  );
}

export function RelationSourceLine({ sources }: { sources: SourceReference[] }) {
  if (!sources.length) return null;
  return (
    <div className="scientific-relation-sources">
      <span>{faNumber(sources.length)} منبع رابطه</span>
      <small>{sources.slice(0, 3).map(source => source.organization || source.title).filter(Boolean).join(" · ")}</small>
      <SourceVerificationSummary sources={sources} />
    </div>
  );
}

export function ScientificSourceList({
  links,
  sources,
  title = "منابع",
  description,
}: {
  links?: ScientificEntitySourceLink[];
  sources?: SourceReference[];
  title?: string;
  description?: string;
}) {
  const rows = links?.length
    ? links.map(link => ({ source: link.source, role: link.role, roleLabel: sourceRoleLabels[link.role] || link.role_label, note: link.note }))
    : (sources || []).map(source => ({ source, role: "", roleLabel: "", note: "" }));

  if (!rows.length) {
    return <div className="card scientific-empty"><h3>منبعی ثبت نشده</h3><p>برای این بخش منبع مستقیمی در runtime موجود نیست.</p></div>;
  }

  return (
    <div className="stack scientific-source-section">
      <div>
        <h2 className="section-title">{title}</h2>
        {description && <p className="section-copy">{description}</p>}
      </div>
      <div className="scientific-source-list">
        {rows.map(({ source, role, roleLabel, note }, index) => {
          const body = (
            <>
              <div className="scientific-source-main">
                <div className="scientific-source-meta">
                  {roleLabel && <span>{roleLabel}</span>}
                  {source.source_type && <span>{humanizeCode(source.source_type)}</span>}
                  {source.publication_year && <span>{faNumber(source.publication_year)}</span>}
                </div>
                <strong>{source.title}</strong>
                {source.organization && <span className="scientific-source-organization">{source.organization}</span>}
                {source.citation && <p>{source.citation}</p>}
                {!!source.authors?.length && <small lang="en" dir="ltr">{source.authors.join(" · ")}</small>}
                {note && <small>{note}</small>}
              </div>
              <div className="scientific-source-audit">
                {source.verification_status && (
                  <span className={`source-verification verification-${source.verification_status}`}>
                    {verificationStatusLabel(source.verification_status)}
                  </span>
                )}
                {source.doi && <code>DOI {source.doi}</code>}
                {source.pmid && <code>PMID {source.pmid}</code>}
                {source.url && <b>مشاهده منبع ↗</b>}
              </div>
            </>
          );
          const key = `${source.id}-${role}-${index}`;
          return source.url ? (
            <a className="card scientific-source-card" href={source.url} target="_blank" rel="noreferrer" key={key}>{body}</a>
          ) : (
            <article className="card scientific-source-card" key={key}>{body}</article>
          );
        })}
      </div>
    </div>
  );
}
