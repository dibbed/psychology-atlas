"use client";

import { CmsError } from "@/lib/cms";
import { SourcePayload, sourceLabels } from "@/lib/cmsGovernance";
import { GovernanceField } from "./GovernanceForms";

export default function SourceFields({ value, onChange, error, disabled, prefix = "source" }: {
  value: SourcePayload; onChange: (value: SourcePayload) => void;
  error?: unknown; disabled?: boolean; prefix?: string;
}) {
  const invalid = (name: string) => error instanceof CmsError && !!error.details.field_errors?.[name];
  return <fieldset className="cms-fieldset" disabled={disabled}><legend>اطلاعات کتاب‌شناختی</legend>
    {(Object.keys(sourceLabels) as (keyof SourcePayload)[]).map(name => {
      const props = { id: `${prefix}-${name}`, name, "aria-invalid": invalid(name), "aria-describedby": invalid(name) ? `${prefix}-${name}-error` : undefined };
      return <GovernanceField key={name} name={name} label={sourceLabels[name]} prefix={prefix} error={error}>
        {name === "authors" ? <textarea {...props} dir="auto" rows={3} value={value.authors.join("\n")} onChange={event => onChange({ ...value, authors: event.target.value.split("\n") })} />
          : name === "citation" ? <textarea {...props} dir="auto" rows={5} maxLength={20000} value={value.citation} onChange={event => onChange({ ...value, citation: event.target.value })} />
          : name === "publication_year" ? <input {...props} type="number" dir="ltr" min={1} max={9999} value={value.publication_year ?? ""} onChange={event => onChange({ ...value, publication_year: event.target.value === "" ? null : Number(event.target.value) })} />
          : <input {...props} required={name === "title"} type={name === "url" ? "url" : "text"} dir={["doi", "pmid", "url", "resource_version"].includes(name) ? "ltr" : "auto"} maxLength={name === "title" ? 500 : name === "url" ? 1000 : name === "resource_version" ? 120 : ["source_type", "verification_status", "pmid"].includes(name) ? 64 : 255} value={value[name]} onChange={event => onChange({ ...value, [name]: event.target.value })} />}
      </GovernanceField>;
    })}
  </fieldset>;
}
