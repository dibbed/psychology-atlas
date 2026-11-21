"use client";

import { useEffect, useRef, useState } from "react";
import { cms, CmsError, CmsPage } from "@/lib/cms";
import { GovernanceEvidence } from "@/lib/cmsGovernance";
import { CmsState, useCms } from "./CmsShell";
import { GovernancePagination } from "./GovernanceForms";
import { faNumber } from "@/lib/fa";

type EvidenceSource = { id: number; title: string; url: string; doi: string; pmid: string; verification_status: string };
type EvidenceArtifact = { id: string; state: string; version: number; filename: string; resource_type: string; resource_id: number; resource_version: string };

export default function GovernanceEvidenceForm({ label, value, onChange, disabled, prefix, binding }: {
  label: string; value: GovernanceEvidence[]; onChange: (value: GovernanceEvidence[]) => void; disabled: boolean; prefix: string;
  binding?: { resource_type: string; resource_id: number; resource_version: string };
}) {
  const { can, me } = useCms();
  const [file, setFile] = useState<File>();
  const [artifact, setArtifact] = useState<EvidenceArtifact>();
  const [artifactError, setArtifactError] = useState<unknown>();
  const [uploading, setUploading] = useState(false);
  const [unknown, setUnknown] = useState(false);
  const scope = `${binding?.resource_type}/${binding?.resource_id}/${binding?.resource_version}`;
  const currentScope = useRef(scope); currentScope.current = scope;
  useEffect(() => { setArtifact(undefined); setFile(undefined); setArtifactError(undefined); setUnknown(false); }, [scope]);
  async function fileAction(action: "upload" | "validate" | "refresh") {
    if (!binding || uploading) return;
    setUploading(true); setArtifactError(undefined);
    const startedScope = scope;
    try {
      let response: { data: { artifact: EvidenceArtifact } };
      if (action === "upload") {
        if (!file) return;
        const body = new FormData(); body.set("file", file); body.set("kind", "evidence_json");
        body.set("resource_type", binding.resource_type); body.set("resource_id", String(binding.resource_id)); body.set("resource_version", binding.resource_version);
        response = await cms<{ artifact: EvidenceArtifact }>("/artifacts/", { method: "POST", body }, me.user.id);
      } else if (artifact) {
        response = await cms<{ artifact: EvidenceArtifact }>(`/artifacts/${artifact.id}/${action === "validate" ? "validate/" : ""}`,
          action === "validate" ? { method: "POST", headers: { "If-Match": `"${artifact.version}"` }, body: "{}" } : {}, me.user.id);
      } else return;
      if (currentScope.current === startedScope) { setArtifact(response.data.artifact); setUnknown(false); }
    } catch (failure) {
      if (currentScope.current === startedScope) { setArtifactError(failure); setUnknown(failure instanceof CmsError && failure.code === "UNKNOWN_OUTCOME"); }
    } finally { setUploading(false); }
  }
  const [search, setSearch] = useState("");
  const [query, setQuery] = useState("");
  const [page, setPage] = useState(1);
  const [retry, setRetry] = useState(0);
  const [target, setTarget] = useState(0);
  const [data, setData] = useState<CmsPage<EvidenceSource>>();
  const [error, setError] = useState<unknown>();
  const [selected, setSelected] = useState<Record<number, EvidenceSource>>({});
  const allowed = can("cms_source_view");
  useEffect(() => {
    if (!allowed) return;
    let active = true; setData(undefined); setError(undefined);
    const params = new URLSearchParams({ q: query, page: String(page) });
    cms<CmsPage<EvidenceSource>>(`/governance/evidence/?${params}`).then(result => { if (active) setData(result.data); }).catch(failure => { if (active) setError(failure); });
    return () => { active = false; };
  }, [allowed, query, page, retry]);
  const update = (index: number, patch: Partial<GovernanceEvidence>) => onChange(value.map((item, i) => {
    if (i !== index) return item;
    const changed = { ...item, ...patch };
    if ("source_id" in patch) delete changed.artifact_id;
    if ("artifact_id" in patch) delete changed.source_id;
    return changed;
  }));
  return <fieldset className="cms-merge-field stack" disabled={disabled} id={prefix}><legend>{label}</legend>
    <p className="muted">هر مدرک ثبت‌شده، یک منبع و نشانی دقیق دارد؛ حداکثر ۲۰. مرجع علمی یا مدرک عمومی به‌تنهایی اجازهٔ استفاده نیست. فایل خصوصی JSON پس از بررسی ساختار قابل اتصال است؛ بررسی ساختار، تأیید علمی یا حقوقی نیست.</p>
    {value.map((item, index) => <div className="stack cms-history-entry" key={index}>
      <p>منبع شاهد {faNumber(index + 1)}: <bdi>{item.artifact_id ? `فایل خصوصی ${item.artifact_id}` : selected[item.source_id ?? 0]?.title || (item.source_id ? faNumber(item.source_id) : "انتخاب نشده")}</bdi></p>
      <label htmlFor={`${prefix}-${index}-locator`}>نشانی دقیق شاهد {faNumber(index + 1)}</label><input id={`${prefix}-${index}-locator`} dir="auto" value={item.locator} required maxLength={1000} onChange={event => update(index, { locator: event.target.value })} />
      <button type="button" className="button secondary" onClick={() => { onChange(value.filter((_, i) => i !== index)); setTarget(0); }}>حذف شاهد {faNumber(index + 1)}</button>
    </div>)}
    <button type="button" className="button secondary" disabled={value.length >= 20 || !allowed} onClick={() => { setTarget(value.length); onChange([...value, { source_id: 0, locator: "" }]); }}>افزودن شاهد</button>
    {!allowed ? <p className="cms-notice">برای جست‌وجو و انتخاب منبع مدرک، مجوز مشاهدهٔ منابع لازم است.</p> : <>
      <label>شاهد دریافت‌کنندهٔ منبع<select value={target} disabled={!value.length} onChange={event => setTarget(Number(event.target.value))}>{value.map((_, index) => <option key={index} value={index}>شاهد {faNumber(index + 1)}</option>)}</select></label>
      <div className="cms-filters"><label>جست‌وجوی منبع مدرک<input value={search} type="search" dir="auto" maxLength={200} onChange={event => setSearch(event.target.value)} /></label><button type="button" className="button secondary" onClick={() => { setPage(1); setQuery(search.trim()); setRetry(n => n + 1); }}>جست‌وجوی مدرک</button></div>
      {error ? <CmsState error={error} retry={() => setRetry(n => n + 1)} /> : !data ? <CmsState loading /> : <>
        {!data.results.length && <CmsState empty="منبع مدرکی یافت نشد." />}
        <ul className="cms-review-sources">{data.results.map(source => <li key={source.id}><div><strong dir="auto">{source.title}</strong><p dir="ltr">DOI: {source.doi || "—"} · PMID: {source.pmid || "—"}</p><p className="cms-id"><bdi>{source.url}</bdi></p></div>
          <button type="button" className="button secondary" disabled={!value[target]} onClick={() => { setSelected(items => ({ ...items, [source.id]: source })); update(target, { source_id: source.id }); }}>انتخاب مدرک {faNumber(source.id)}</button>
        </li>)}</ul><GovernancePagination data={data} disabled={disabled} onPage={setPage} />
      </>}
    </>}
    {binding?.resource_id && can("cms_artifact_upload") && can("cms_artifact_download") ? <section className="stack cms-history-entry">
      <h3>مدرک خصوصی برای همین نسخهٔ هدف</h3>
      <p className="muted">فقط JSON، حداکثر ۲۵ MiB. پس از بارگذاری و بررسی ساختار، فایل را به شاهد اضافه کنید و نشانی دقیق آن را بنویسید. فایل جایگزین منبع علمی یا اجازهٔ استفاده نیست.</p>
      <label htmlFor={`${prefix}-file`}>فایل مدرک خصوصی</label>
      <input id={`${prefix}-file`} type="file" accept=".json,application/json" disabled={uploading || unknown} onChange={event => { setFile(event.target.files?.[0]); setArtifact(undefined); }} />
      <div className="cms-actions">
        <button type="button" className="button secondary" disabled={!file || uploading || unknown || !!artifact} onClick={() => fileAction("upload")}>بارگذاری در قرنطینه</button>
        <button type="button" className="button secondary" disabled={!artifact || artifact.state !== "quarantine" || uploading || unknown} onClick={() => fileAction("validate")}>بررسی ساختار فایل</button>
        <button type="button" className="button secondary" disabled={!artifact || uploading} onClick={() => fileAction("refresh")}>بازخوانی وضعیت فایل</button>
        <button type="button" className="button secondary" disabled={!artifact || artifact.state !== "ready" || uploading || unknown || value.length >= 20 || value.some(item => item.artifact_id === artifact.id)} onClick={() => { if (artifact) onChange([...value, { artifact_id: artifact.id, locator: "" }]); }}>افزودن فایل آماده به شواهد</button>
      </div>
      {artifact && <p dir="auto">{artifact.filename} · {artifact.state === "ready" ? "ساختار بررسی شده؛ بدون تأیید علمی یا حقوقی" : artifact.state === "quarantine" ? "در قرنطینه" : "قابل استفاده نیست"}</p>}
      {artifactError ? <CmsState error={artifactError} /> : null}
      {unknown && <p className="cms-notice">نتیجه نامعلوم است؛ درخواست را تکرار نکنید. وضعیت فایل را بازخوانی کنید یا <a className="cms-link" href="/admin-console/research">فهرست فایل‌ها</a> را بررسی کنید.</p>}
    </section> : null}
  </fieldset>;
}
