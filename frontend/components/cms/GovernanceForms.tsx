"use client";

import { useEffect, useRef } from "react";
import { CmsError, CmsPage } from "@/lib/cms";
import { faNumber } from "@/lib/fa";
import { CmsState } from "./CmsShell";

export function GovernanceError({ error, prefix, labels = {}, children }: {
  error: unknown; prefix: string; labels?: Record<string, string>; children?: React.ReactNode;
}) {
  const focus = useRef<HTMLDivElement>(null);
  useEffect(() => { if (error) focus.current?.focus(); }, [error]);
  if (!error) return null;
  const failure = error instanceof CmsError ? error : undefined;
  return <div ref={focus} tabIndex={-1} role="alert" className="cms-error stack">
    <CmsState error={error} />
    {failure?.details.field_errors && <ul>{Object.entries(failure.details.field_errors).map(([field, messages]) =>
      <li key={field}><a className="cms-link" href={`#${prefix}-${field}`}>{labels[field] || field}: {Array.isArray(messages) ? messages.join(" · ") : String(messages)}</a></li>)}</ul>}
    {failure?.details.blockers?.length ? <ul>{failure.details.blockers.map((blocker, index) => <li key={index}><bdi>{labels[blocker] || blocker}</bdi></li>)}</ul> : null}
    {children}
  </div>;
}

export function GovernancePagination({ data, onPage, disabled = false }: {
  data: Pick<CmsPage<unknown>, "page" | "page_size" | "count">; onPage: (page: number) => void; disabled?: boolean;
}) {
  return <nav className="cms-pagination" aria-label="صفحه‌بندی نتایج">
    <button type="button" className="button secondary" disabled={disabled || data.page <= 1} onClick={() => onPage(data.page - 1)}>صفحهٔ قبلی</button>
    <span>صفحهٔ {faNumber(data.page)} · {faNumber(data.count)} نتیجه</span>
    <button type="button" className="button secondary" disabled={disabled || data.page * data.page_size >= data.count} onClick={() => onPage(data.page + 1)}>صفحهٔ بعدی</button>
  </nav>;
}

export function GovernanceField({ name, label, prefix, error, children }: {
  name: string; label: string; prefix: string; error?: unknown; children: React.ReactNode;
}) {
  const messages = error instanceof CmsError ? error.details.field_errors?.[name] : undefined;
  return <div className="cms-form-field"><label htmlFor={`${prefix}-${name}`}>{label}</label>{children}
    {messages && <p id={`${prefix}-${name}-error`} className="cms-error" role="alert">{Array.isArray(messages) ? messages.join(" · ") : String(messages)}</p>}
  </div>;
}
