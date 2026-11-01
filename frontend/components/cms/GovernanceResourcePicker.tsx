"use client";

import { useEffect, useState } from "react";
import { cms, CmsPage } from "@/lib/cms";
import { ResourceBinding, governanceResources } from "@/lib/cmsGovernance";
import { faNumber } from "@/lib/fa";
import { CmsState, useCms } from "./CmsShell";
import { GovernancePagination } from "./GovernanceForms";

export default function GovernanceResourcePicker({ value, onChange, disabled, immutable = false }: {
  value?: ResourceBinding; onChange: (value: ResourceBinding) => void; disabled: boolean; immutable?: boolean;
}) {
  const { can } = useCms();
  const types = Object.entries(governanceResources).filter(([, item]) => can(`cms_${item.domain}_view`));
  const [type, setType] = useState(value?.resource_type || types[0]?.[0] || "");
  const [search, setSearch] = useState("");
  const [query, setQuery] = useState("");
  const [page, setPage] = useState(1);
  const [retry, setRetry] = useState(0);
  const [data, setData] = useState<CmsPage<ResourceBinding>>();
  const [error, setError] = useState<unknown>();
  const actualType = immutable ? value?.resource_type : type;
  const allowed = !!actualType && !!governanceResources[actualType] && can(`cms_${governanceResources[actualType].domain}_view`);
  useEffect(() => {
    if (!allowed || !actualType) return;
    let active = true; setData(undefined); setError(undefined);
    const params = new URLSearchParams({ resource_type: actualType, q: query, page: String(page) });
    cms<CmsPage<ResourceBinding>>(`/governance/resources/?${params}`).then(result => { if (active) setData(result.data); }).catch(failure => { if (active) setError(failure); });
    return () => { active = false; };
  }, [actualType, allowed, query, page, retry]);
  return <section className="card stack"><h2>{immutable ? "نسخهٔ دقیق هدف" : "انتخاب منبع هدف و نسخهٔ سرور"}</h2>
    {value && <div className="cms-notice stack"><p><bdi>{value.name_fa || value.name_en || `${governanceResources[value.resource_type]?.label} ${faNumber(value.resource_id)}`}</bdi></p><p className="cms-id">شناسه: {faNumber(value.resource_id)} · نسخه: <bdi>{value.resource_version}</bdi></p></div>}
    <div className="cms-filters">
      {!immutable && <label>نوع هدف<select value={type} disabled={disabled} onChange={event => { setType(event.target.value); setPage(1); setSearch(""); setQuery(""); }}>{types.map(([key, item]) => <option key={key} value={key}>{item.label}</option>)}</select></label>}
      <label>جست‌وجوی هدف<input type="search" dir="auto" value={search} maxLength={200} disabled={disabled} onChange={event => setSearch(event.target.value)} /></label>
      <button type="button" className="button secondary" disabled={disabled || !allowed} onClick={() => { setPage(1); setQuery(search.trim()); setRetry(n => n + 1); }}>جست‌وجوی نسخهٔ فعلی</button>
    </div>
    {!allowed ? <CmsState empty="هدف قابل‌دسترسی ندارید." /> : error ? <CmsState error={error} retry={() => setRetry(n => n + 1)} /> : !data ? <CmsState loading /> : <>
      {!data.results.length && <CmsState empty="هدف مجازی با این جست‌وجو یافت نشد." />}
      <ul className="cms-review-sources">{data.results.map(resource => <li key={resource.resource_id}><div><strong dir="auto">{resource.name_fa || resource.name_en || faNumber(resource.resource_id)}</strong><p dir="ltr">{resource.name_en}</p><p className="cms-id">نسخه: <bdi>{resource.resource_version}</bdi></p></div>
        <button type="button" className="button secondary" disabled={disabled || (immutable && value?.resource_id !== resource.resource_id)} onClick={() => onChange(resource)}>{immutable ? "پذیرش صریح این نسخهٔ فعلی" : "انتخاب هدف"} {faNumber(resource.resource_id)}</button>
      </li>)}</ul><GovernancePagination data={data} disabled={disabled} onPage={setPage} />
    </>}
    {immutable && <p className="muted">هدف و دامنه تغییر نمی‌کنند. پذیرش نسخهٔ تازه، پیشنهاد تازه‌ای می‌سازد و به بازبینی دوباره نیاز دارد.</p>}
  </section>;
}
