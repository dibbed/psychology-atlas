"use client";

import { SourcePayload, sourceLabels } from "@/lib/cmsGovernance";
import { faNumber } from "@/lib/fa";

export function sourceValue(value: unknown): string {
  if (value === null || value === undefined || value === "") return "ثبت نشده";
  if (typeof value === "object") return JSON.stringify(value, null, 2);
  return String(value);
}

export default function SourceComparison({ sources, choices, onChange, disabled }: {
  sources: { id: number; payload: SourcePayload }[]; choices: Partial<Record<keyof SourcePayload, number>>;
  onChange: (choices: Partial<Record<keyof SourcePayload, number>>) => void; disabled?: boolean;
}) {
  return <fieldset className="cms-fieldset" disabled={disabled}><legend>انتخاب صریح مقدار هر فیلد در منبع باقی‌مانده</legend>
    {(Object.keys(sourceLabels) as (keyof SourcePayload)[]).filter(field => new Set(sources.map(source => JSON.stringify(source.payload[field]))).size > 1).map(field => <fieldset key={field} className="cms-merge-field"><legend>{sourceLabels[field]}</legend>
      <div className="cms-compare">{sources.map(source => <label key={source.id} className="stack">
        <span className="cms-review-check"><input type="radio" name={`choice-${field}`} checked={choices[field] === source.id} onChange={() => onChange({ ...choices, [field]: source.id })} />منبع {faNumber(source.id)}</span>
        <p className="cms-prose" dir={["doi", "pmid", "url", "metadata"].includes(field) ? "ltr" : "auto"}>{sourceValue(source.payload[field])}</p>
      </label>)}</div>
    </fieldset>)}
  </fieldset>;
}
