"use client";

import { useEffect, useRef, useState } from "react";
import { CmsError, CmsPage, cmsDate } from "@/lib/cms";
import { AdminArtifact, ArtifactKind, artifactKindLabels, artifactStateLabels, mutationBlocked } from "@/lib/cmsJobs";
import { ResourceBinding, governanceResources } from "@/lib/cmsGovernance";
import { faNumber } from "@/lib/fa";
import { CmsState } from "./CmsShell";
import { GovernancePagination } from "./GovernanceForms";
import GovernanceResourcePicker from "./GovernanceResourcePicker";
import { PrivateMutationError, ResearchBoundary, usePrivateCms } from "./CmsJobsShared";
import ArtifactCard from "./ArtifactCard";

export default function ArtifactLibrary() {
  const { can, request, current, setDirty, leave } = usePrivateCms();
  const allowed = can("cms_enter") && (can("cms_artifact_upload") || can("cms_artifact_download"));
  const [kind, setKind] = useState<ArtifactKind>("research_json"); const [file, setFile] = useState<File>();
  const [binding, setBinding] = useState<ResourceBinding>(); const input = useRef<HTMLInputElement>(null);
  const [data, setData] = useState<CmsPage<AdminArtifact>>(); const [error, setError] = useState<unknown>();
  const [writeError, setWriteError] = useState<unknown>(); const [busy, setBusy] = useState(false); const lock = useRef(false);
  const [cardBusy, setCardBusy] = useState(false);
  const [selected, setSelected] = useState<string>(); const [page, setPage] = useState(1); const [reload, setReload] = useState(0);
  const blocked = mutationBlocked(writeError);
  const domain = kind === "evidence_json" ? binding?.domain : kind === "learning_json" ? "learning" : kind === "dsm_json" ? "dsm" : kind === "assessment_json" ? "assessment" : "research";
  const uploadAllowed = can("cms_artifact_upload") && !!domain && can(`cms_${domain}_view`) && can(domain === "research" ? "cms_research_intake" : `cms_${domain}_edit`);
  useEffect(() => { setDirty(!!file || !!binding || busy || cardBusy); return () => setDirty(false); }, [file, binding, busy, cardBusy, setDirty]);
  useEffect(() => {
    if (!allowed) return;
    let active = true; const abort = new AbortController(); setData(undefined); setError(undefined);
    request<CmsPage<AdminArtifact>>(`/artifacts/?page=${page}`, { signal: AbortSignal.any([abort.signal, AbortSignal.timeout(15000)]) })
      .then(result => { if (active && current()) setData(result.data); }).catch(failure => { if (active && current()) setError(failure); });
    return () => { active = false; abort.abort(); };
  }, [allowed, request, current, page, reload]);
  function clear() { setFile(undefined); setBinding(undefined); if (input.current) input.current.value = ""; }
  async function upload(event: React.FormEvent) {
    event.preventDefault(); if (!file || !uploadAllowed || blocked || lock.current) return;
    if (!file.name.toLowerCase().endsWith(".json") || file.size <= 0 || file.size > 25 * 1024 * 1024) {
      setWriteError(new CmsError(400, "INVALID_UPLOAD", "فایل JSON غیرخالی با حجم حداکثر ۲۵ مگابایت انتخاب کنید؛ سرور قالب و حدود را جداگانه بررسی می‌کند.")); return;
    }
    const body = new FormData();
    body.set("kind", kind); body.set("file", new File([file], file.name, { type: "application/json" }));
    if (kind === "evidence_json" && binding) { body.set("resource_type", binding.resource_type); body.set("resource_id", String(binding.resource_id)); body.set("resource_version", binding.resource_version); }
    lock.current = true; setBusy(true); setWriteError(undefined);
    try {
      const result = await request<{ artifact: AdminArtifact }>("/artifacts/", { method: "POST", body });
      if (current()) { clear(); setSelected(result.data.artifact.id); setReload(n => n + 1); }
    } catch (failure) { if (current()) setWriteError(failure); }
    finally { lock.current = false; if (current()) setBusy(false); }
  }
  if (!allowed) return <CmsState error={new CmsError(403, "PERMISSION_DENIED", "")} />;
  return <div className="stack" dir="rtl">{can("cms_research_view") && <a className="cms-link" href="/admin-console/research">→ مجموعه‌های پژوهشی</a>}<header className="cms-title"><p className="eyebrow">فایل‌های خصوصی</p><h1>ورود و فایل‌های خصوصی</h1><p className="muted">بارگذاری، اعتبارسنجی و ایجاد کار، سه اقدام جداگانه‌اند. فقط فایل محلی JSON پذیرفته می‌شود.</p></header><ResearchBoundary />
    {can("cms_artifact_upload") && <form className="card stack" onSubmit={upload}><h2>بارگذاری در قرنطینه</h2>
      <PrivateMutationError error={writeError} prefix="artifact" busy={busy} reload={() => { clear(); setWriteError(undefined); setReload(n => n + 1); }} />
      <fieldset className="cms-fieldset" disabled={busy || blocked}><label>نوع فایل<select id="artifact-kind" value={kind} onChange={event => { setKind(event.target.value as ArtifactKind); setBinding(undefined); }}>{Object.entries(artifactKindLabels).filter(([value]) => !["learning_export_json","privacy_request_json","privacy_export_json"].includes(value)).map(([value, label]) => <option key={value} value={value}>{label}</option>)}</select></label>
        <label>فایل JSON<input id="artifact-file" ref={input} type="file" accept=".json,application/json,text/json" required onChange={event => setFile(event.target.files?.[0])} /><small>حداکثر ۲۵ مگابایت؛ محتوای علمی یا حقوقی با انتخاب نوع فایل تأیید نمی‌شود.</small></label>
        {kind === "evidence_json" ? <><p className="cms-notice">مدرک به یک هدف و نسخهٔ دقیق سرور متصل می‌شود. نشانی منبع به‌تنهایی مدرک محسوب نمی‌شود.</p><GovernanceResourcePicker value={binding} onChange={setBinding} disabled={busy || blocked} /></> : <p className="muted">فایل ورود {kind === "research_json" ? "پژوهش" : kind === "dsm_json" ? "DSM" : kind === "brain_json" ? "مغز با قالب brain-staging-v1" : kind === "learning_json" ? "محتوای آموزشی خصوصی" : "ارزیابی"} به هدف محتوایی متصل نمی‌شود؛ انتخاب هدف لازم نیست.</p>}
        {binding && <p>هدف انتخاب‌شده: {governanceResources[binding.resource_type]?.label} · {faNumber(binding.resource_id)} · نسخهٔ <bdi>{binding.resource_version}</bdi></p>}
        {!uploadAllowed && <p className="cms-notice">مجوز بارگذاری و مشاهده/ویرایش دامنهٔ انتخاب‌شده لازم است؛ برای مدرک، ابتدا هدف را انتخاب کنید.</p>}
        <div className="cms-actions"><button className="button primary" disabled={!file || !uploadAllowed}>{busy ? "در حال بارگذاری…" : "بارگذاری فایل؛ بدون اعتبارسنجی خودکار"}</button><button type="button" className="button secondary" onClick={() => leave(clear)}>پاک کردن فرم</button></div>
      </fieldset></form>}
    <section className="stack"><div className="cms-section-head"><h2>فایل‌های قابل‌دسترسی حساب فعلی</h2><button className="button secondary" disabled={busy} onClick={() => setReload(n => n + 1)}>بازخوانی فهرست فایل‌ها</button></div>
      {error ? <CmsState error={error} retry={() => setReload(n => n + 1)} /> : !data ? <CmsState loading /> : <>{!data.results.length ? <CmsState empty="فایل خصوصی قابل‌دسترسی وجود ندارد." /> : <div className="cms-table-wrap" role="region" tabIndex={0} aria-label="فایل‌های خصوصی؛ قابل پیمایش افقی"><table className="cms-table"><caption>{faNumber(data.count)} فایل</caption><thead><tr><th scope="col">فایل</th><th scope="col">نوع / وضعیت</th><th scope="col">حجم ثبت‌شده / انقضا</th><th scope="col">اقدام</th></tr></thead><tbody>{data.results.map(artifact => <tr key={artifact.id}><th scope="row"><bdi>{artifact.filename}</bdi><p className="cms-id"><bdi>{artifact.id}</bdi></p></th><td>{artifactKindLabels[artifact.kind]}<p>{artifactStateLabels[artifact.state]}</p>{artifact.purged_at && <p>بایت‌های فایل پاکسازی شده‌اند؛ {cmsDate(artifact.purged_at)}</p>}</td><td>{faNumber(artifact.size)} بایت<p>{cmsDate(artifact.expires_at)}</p></td><td><button type="button" className="button secondary" disabled={busy} onClick={() => leave(() => setSelected(artifact.id))}>جزئیات و اقدامات فایل</button></td></tr>)}</tbody></table></div>}<GovernancePagination data={data} onPage={setPage} disabled={busy} /></>}
    </section>
    {selected && <ArtifactCard key={selected} id={selected} onChange={() => setReload(n => n + 1)} onBusy={setCardBusy} />}
  </div>;
}
