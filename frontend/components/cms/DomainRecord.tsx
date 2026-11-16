"use client";
import { useEffect, useRef, useState } from 'react';
import { cms, CmsError, CmsPage, cmsDate, publicationLabels, revisionLabels } from '@/lib/cms';
import { ArchiveImpact, contentPath, ContentCheckResult, DomainPayload, DomainRecord as RecordData, DomainRevision, DomainValue, DuplicateResult, domainAction, domainHeaders, domainTitle, domainWriteBlocked, draftPayload, duplicateKinds, duplicateTierLabels, fieldWritable, impactLabels, rebaseChoices, recordFields, revisionPatch } from '@/lib/cmsDomains';
import { CmsState, useCms } from './CmsShell';
import DomainFields, { DomainValueView, fieldLabel, readonlyExplanation, useDomainSchemas } from './DomainFields';
import DomainPreview from './DomainPreview';

type Snapshot = {data: RecordData; etag: string | null};
export default function DomainRecord({kind, id}: {kind: string; id?: string}) {
  const {me, can, setDirty, leave} = useCms();
  const {schemas, error: schemaError, retry: schemaRetry} = useDomainSchemas();
  const schema = schemas?.find(item => item.kind === kind);
  const [base, setBase] = useState<Snapshot>();
  const [form, setForm] = useState<DomainPayload>({});
  const [error, setError] = useState<unknown>();
  const [writeError, setWriteError] = useState<unknown>();
  const [readError, setReadError] = useState<unknown>();
  const [busy, setBusy] = useState(false);
  const running = useRef(false);
  const [tab, setTab] = useState(id ? 'detail' : 'edit');
  const [history, setHistory] = useState<CmsPage<DomainRevision>>();
  const [historyError, setHistoryError] = useState<unknown>();
  const [historyPage, setHistoryPage] = useState(1);
  const [historyRetry, setHistoryRetry] = useState(0);
  const [authoring, setAuthoring] = useState<{duplicates: DuplicateResult; impact: ArchiveImpact}>();
  const [authoringError, setAuthoringError] = useState<unknown>();
  const [authoringRetry, setAuthoringRetry] = useState(0);
  const [retry, setRetry] = useState(0);
  const [result, setResult] = useState<ContentCheckResult>();
  const [raw, setRaw] = useState<DomainValue>();
  const [rawAck, setRawAck] = useState(false);
  const [archiveAck, setArchiveAck] = useState(false);
  const [conflict, setConflict] = useState<Snapshot>();
  const [choices, setChoices] = useState<Record<string, 'mine' | 'current'>>({});
  const [saved, setSaved] = useState(false);
  const [back, setBack] = useState(`/admin-console/content/${kind}`);
  const baseline = base ? recordFields(base.data) : {};
  const dirty = JSON.stringify(form) !== JSON.stringify(baseline);
  const blocked = domainWriteBlocked(writeError) || !!conflict;
  const editable = !!schema && can(`cms_${schema.domain}_${id ? 'edit' : 'create'}`) && (!base || ['legacy', 'draft', 'changes_requested'].includes(base.data.revision_status));
  const failure = writeError instanceof CmsError ? writeError : undefined;
  useEffect(() => {setDirty(dirty || busy); return () => setDirty(false);}, [dirty, busy, setDirty]);
  useEffect(() => {
    const original = new URLSearchParams(new URLSearchParams(location.search).get('list') || '');
    const params = new URLSearchParams();
    for (const key of ['q', 'status', 'sort', 'page', 'page_size']) if (original.has(key)) params.set(key, original.get(key)!);
    setBack(`/admin-console/content/${kind}${params.size ? `?${params}` : ''}`);
  }, [kind]);
  useEffect(() => {
    if (!id || !schema) return;
    let active = true; setError(undefined);
    cms<RecordData>(contentPath(kind, id)).then(snapshot => {if (active) {setBase(snapshot); setForm(recordFields(snapshot.data));}}).catch(e => {if (active) setError(e);});
    return () => {active = false;};
  }, [kind, id, schema, retry]);
  useEffect(() => {
    if (tab !== 'history' || !id || !schema) return;
    let active = true; setHistory(undefined); setHistoryError(undefined);
    cms<CmsPage<DomainRevision>>(`${contentPath(kind, id)}revisions/?page=${historyPage}`).then(({data}) => {if (active) setHistory(data);}).catch(e => {if (active) setHistoryError(e);});
    return () => {active = false;};
  }, [kind, id, schema, tab, historyPage, historyRetry, base?.data.version]);
  useEffect(() => {
    if (tab !== 'authoring' || !id || !schema || !base || base.data.canonical_pk === null) return;
    let active = true; setAuthoring(undefined); setAuthoringError(undefined);
    Promise.all([cms<DuplicateResult>(`${contentPath(kind, id)}duplicates/`), cms<ArchiveImpact>(`${contentPath(kind, id)}archive-impact/`)])
      .then(([duplicates, impact]) => {if (active) setAuthoring({duplicates: duplicates.data, impact: impact.data});})
      .catch(e => {if (active) setAuthoringError(e);});
    return () => {active = false;};
  }, [tab, kind, id, schema, base?.data.version, authoringRetry]);
  async function save(event: React.FormEvent) {
    event.preventDefault();
    if (!schema || !editable || running.current || blocked) return;
    running.current = true; setBusy(true); setWriteError(undefined); setSaved(false); setResult(undefined);
    try {
      const snapshot = await cms<RecordData>(id ? `${contentPath(kind, id)}revisions/` : contentPath(kind), {
        method: 'POST', headers: id ? domainHeaders(base?.etag) : {},
        body: JSON.stringify({payload: id ? revisionPatch(schema, baseline, form) : draftPayload(schema, form, true), ...(id ? {base_digest: base?.data.canonical_digest, reason: 'CONTENT_UPDATE'} : {reason: 'DRAFT_CREATION'})}),
      }, me.user.id);
      setBase(snapshot); setForm(recordFields(snapshot.data)); setSaved(true); setDirty(false);
      if (!id) location.assign(`/admin-console/content/${kind}/${snapshot.data.id}`);
    } catch (e) {setWriteError(e);} finally {running.current = false; setBusy(false);}
  }
  async function perform(action: 'validate' | 'preview' | 'archive' | 'discard' | 'raw-preview') {
    if (!id || !base || running.current || blocked || dirty) return;
    running.current = true; setBusy(true); setWriteError(undefined); setSaved(false); setResult(undefined);
    let committed = false;
    try {
      if (action === 'discard') {
        const snapshot = await cms<RecordData>(`${contentPath(kind, id)}discard/`, {method: 'POST', headers: domainHeaders(base.etag), body: JSON.stringify({base_digest: base.data.canonical_digest})}, me.user.id);
        setBase(snapshot); setForm(recordFields(snapshot.data)); setSaved(true);
      } else if (action === 'raw-preview') {
        const {data} = await cms<DomainValue>(`${contentPath(kind, id)}raw-preview/`, {method: 'POST', headers: domainHeaders(base.etag), body: JSON.stringify({purpose: 'source_review', reason: 'RESEARCH_RAW'})}, me.user.id);
        setRaw(data);
      } else {
        const {data} = await domainAction<ContentCheckResult>(kind, id, action, base.etag, me.user.id);
        if (action === 'archive') {
          committed = true;
          const snapshot = await cms<RecordData>(contentPath(kind, id)); setBase(snapshot); setForm(recordFields(snapshot.data)); setArchiveAck(false); setSaved(true);
        } else setResult(data);
      }
    } catch (e) {setWriteError(committed ? new CmsError(0, 'UNKNOWN_OUTCOME', 'درخواست ثبت شد اما دریافت نتیجه ناموفق بود؛ نسخه و تاریخچهٔ سرور را بررسی کنید.') : e);} finally {running.current = false; setBusy(false);}
  }
  async function compareCurrent() {
    if (!id || running.current) return;
    running.current = true; setBusy(true); setReadError(undefined);
    try {
      const snapshot = await cms<RecordData>(contentPath(kind, id));
      const selections = schema ? rebaseChoices(schema, baseline, form, recordFields(snapshot.data)) : {};
      setConflict(snapshot); setChoices(selections);
    }
    catch (e) {setReadError(e);} finally {running.current = false; setBusy(false);}
  }
  function merge() {
    if (!conflict || !schema) return;
    const merged = {...recordFields(conflict.data)};
    for (const field of schema.fields.filter(field => fieldWritable(field, false))) if (choices[field.name] === 'mine' && field.name in form) merged[field.name] = form[field.name];
    setBase(conflict); setForm(merged); setConflict(undefined); setWriteError(undefined); setResult(undefined); setRaw(undefined);
  }
  if (schemaError) return <CmsState error={schemaError} retry={schemaRetry}/>;
  if (!schemas) return <CmsState loading/>;
  if (!schema) return <CmsState error={new CmsError(404, 'NOT_FOUND', '')}/>;
  if (error) return <CmsState error={error} retry={() => {setError(undefined); setRetry(n => n + 1);}}/>;
  if (id && !base) return <CmsState loading/>;
  const writable = schema.fields.filter(field => fieldWritable(field, !id));
  return <div className="stack" dir="rtl" data-testid="domain-record">
    <div className="cms-actions"><a className="cms-link" href={back}>→ بازگشت به فهرست با فیلتر قبلی</a>{base && <a className="button secondary" data-testid={kind === 'category' ? 'category-review-link' : 'domain-review-link'} href={`/admin-console/reviews/${kind}/${base.data.id}`}>بررسی پیشنهاد و شواهد</a>}</div>
    <div className="cms-title"><p className="eyebrow">{schema.label}</p><h1><bdi>{domainTitle(form)}</bdi></h1></div>
    {base && <div className="cms-actions"><span className="cms-badge">نسخه {base.data.version}</span><span className="cms-badge">{revisionLabels[base.data.revision_status] || base.data.revision_status}</span><span>{publicationLabels[base.data.publication] || base.data.publication}</span></div>}
    {base?.data.intent === 'archive' && <p className="cms-notice">درخواست بایگانی برای برداشت آینده در P16؛ محتوای اصلی فعلاً بدون تغییر و مطابق وضعیت قبلی قابل نمایش است.</p>}
    <nav className="cms-tabs" aria-label="نماهای محتوا">{[...(id ? [['detail', 'نمای کلی']] : []), ...(editable ? [['edit', 'ویرایش پیشنهاد']] : []), ...(id ? [['preview', 'پیش‌نمایش و اختلاف'], ['history', 'تاریخچهٔ نسخه‌ها']] : []), ...(id && base && base.data.canonical_pk !== null && duplicateKinds.has(kind) && can(`cms_${schema.domain}_preview`) ? [['authoring', 'تکرار و اثر بایگانی']] : [])].map(([key, label]) => <button className="button secondary" key={key} aria-pressed={tab === key} onClick={() => setTab(key)}>{label}</button>)}</nav>
    {writeError != null && <><CmsState error={writeError}/>{failure?.details.field_errors && <ul>{Object.entries(failure.details.field_errors).map(([name, errors]) => <li key={name}><a className="cms-link" href={`#domain-${name}-container`}>{fieldLabel(schema.fields.find(field => field.name === name) || {name, type: '', required: false})}: {errors.join(' · ')}</a></li>)}</ul>}{blocked && <p role="alert" className="cms-notice">نتیجه نامعلوم یا نسخه قدیمی است؛ اقدام تازه قفل شده و خودکار تکرار نمی‌شود. نسخه و تاریخچهٔ سرور را بررسی کنید.</p>}</>}
    {id && <button type="button" className="button secondary" disabled={busy} onClick={compareCurrent}>دریافت نسخهٔ سرور و مقایسه</button>}
    {readError != null && <CmsState error={readError} retry={compareCurrent}/>}
    {!id && blocked && <p className="cms-notice">پیش از ساخت دوباره، فهرست و <a className="cms-link" href="/admin-console/audit">تاریخچهٔ عملیات</a> را بررسی کنید.</p>}
    {conflict && <section className="card stack"><h2>مقایسه با نسخهٔ {conflict.data.version}</h2><p>هر فیلد را صریحاً انتخاب کنید. برای نتیجهٔ نامعلوم، تاریخچه را نیز بررسی کنید؛ عملیات قبلی تکرار نمی‌شود.</p>{writable.map(field => <fieldset className="cms-merge-field" key={field.name}><legend>{fieldLabel(field)}</legend><div className="cms-compare"><div>فرم شما<DomainValueView value={form[field.name]}/></div><div>نسخهٔ سرور<DomainValueView value={recordFields(conflict.data)[field.name]}/></div></div><label>انتخاب مقدار<select value={choices[field.name] || ''} onChange={e => setChoices({...choices, [field.name]: e.target.value as 'mine' | 'current'})}><option value="">انتخاب کنید</option><option value="mine">فرم من</option><option value="current">سرور</option></select></label></fieldset>)}<button className="button secondary" disabled={writable.some(field => !choices[field.name])} onClick={merge}>پذیرش مقایسه و ادامهٔ ویرایش</button><button className="button secondary" onClick={() => leave(() => {setBase(conflict); setForm(recordFields(conflict.data)); setConflict(undefined); setWriteError(undefined); setResult(undefined); setRaw(undefined);})}>بازنشانی کامل به نسخهٔ سرور</button></section>}
    {tab === 'detail' && base && <section className="card stack"><h2>پیشنهاد ذخیره‌شده</h2>{schema.fields.map(field => <div key={field.name}><h3>{fieldLabel(field)}</h3><DomainValueView value={field.name in baseline ? baseline[field.name] : base.data.immutable_fields?.[field.name]}/>{(field.create_only || field.readonly_reason) && <p className="muted">فقط خواندنی: {readonlyExplanation(field)}</p>}</div>)}</section>}
    {tab === 'edit' && <form className="card stack" onSubmit={save}><h2>ویرایش پیشنهاد · {dirty ? 'ذخیره نشده' : 'بدون تغییر'}</h2><p className="cms-notice">ذخیرهٔ پیشنهاد محتوای اصلی را تغییر نمی‌دهد؛ هویت‌های ثابت و سند خام در این فرم قابل تغییر نیستند.</p><DomainFields schema={schema} form={form} immutable={base?.data.immutable_fields} creating={!id} disabled={busy || blocked || !editable} errors={failure?.details.field_errors} onChange={(name, value) => {setForm(current => ({...current, [name]: value})); setSaved(false);}}/><div className="cms-actions"><button className="button primary" disabled={busy || blocked || !editable || !dirty}>ذخیرهٔ پیشنهاد</button>{base && <button className="button secondary" type="button" disabled={busy || blocked} onClick={() => leave(() => {setForm(recordFields(base.data)); setDirty(false); setResult(undefined);})}>بازگرداندن فرم به نسخهٔ ذخیره‌شده</button>}</div></form>}
    {tab === 'preview' && <section className="card stack"><h2>اعتبارسنجی و پیش‌نمایش نامزد</h2><p className="cms-notice">این نتیجهٔ سرور مربوط به آخرین پیشنهاد ذخیره‌شده است؛ نه تأیید علمی است و نه انتشار عمومی. ابتدا تغییرهای فرم را ذخیره کنید.</p><div className="cms-actions">{(['validate', 'preview'] as const).filter(action => can(`cms_${schema.domain}_${action}`)).map(action => <button className="button secondary" key={action} disabled={busy || blocked || dirty || !base?.etag} onClick={() => void perform(action)}>{action === 'validate' ? 'اعتبارسنجی پیشنهاد در سرور' : 'پیش‌نمایش نامزد از سرور'}</button>)}</div>{result !== undefined && <DomainPreview result={result} schema={schema}/>}
      <h3>اختلاف فرم با پیشنهاد ذخیره‌شده</h3>{dirty ? writable.filter(field => JSON.stringify(form[field.name]) !== JSON.stringify(baseline[field.name])).map(field => <div className="cms-merge-field" key={field.name}><h4>{fieldLabel(field)}</h4><div className="cms-compare"><div><strong>ذخیره‌شده</strong><DomainValueView value={baseline[field.name]}/></div><div><strong>فرم فعلی؛ ذخیره نشده</strong><DomainValueView value={form[field.name]}/></div></div></div>) : <p className="muted">اختلافی با آخرین پیشنهاد ذخیره‌شده ندارد.</p>}
      {kind === 'therapy' && <a className="cms-link" href="/admin-console/content/therapy-compare">مقایسهٔ واقعی و فقط خواندنی نسخهٔ عمومی درمان‌ها</a>}
      {kind.startsWith('dsm-') && <a className="cms-link" href="/admin-console/content/dsm">درخت و مقایسهٔ corpusهای DSM</a>}
    </section>}
    {tab === 'history' && <section className="card stack"><h2>تاریخچهٔ نسخه‌های مستقل</h2>{historyError ? <CmsState error={historyError} retry={() => setHistoryRetry(n => n + 1)}/> : !history ? <CmsState loading/> : <>{!history.results.length && <CmsState empty="نسخه‌ای ثبت نشده است."/>}{history.results.map(row => <details className="cms-history-entry" key={row.id}><summary>نسخه {row.sequence} · {revisionLabels[row.status] || row.status} · {cmsDate(row.created_at)}{row.intent === 'archive' ? ' · درخواست بایگانی آینده' : ''}</summary>{Object.entries(row.payload).map(([name, value]) => <div key={name}><h3>{fieldLabel(schema.fields.find(field => field.name === name) || {name, type: '', required: false})}</h3><DomainValueView value={value}/></div>)}</details>)}<nav className="cms-pagination" aria-label="صفحه‌بندی تاریخچه"><button className="button secondary" disabled={historyPage <= 1} onClick={() => setHistoryPage(n => n - 1)}>جدیدتر</button><button className="button secondary" disabled={historyPage * history.page_size >= history.count} onClick={() => setHistoryPage(n => n + 1)}>قدیمی‌تر</button></nav></>}</section>}
    {tab === 'authoring' && <section className="card stack" data-testid="domain-authoring-review"><h2>نامزدهای تکرار و اثر بایگانی</h2><p className="cms-notice">این نما فقط خواندنی است؛ هیچ merge، حذف یا بازنویسی هویت انجام نمی‌شود و دادهٔ خام یا تاریخچه تغییر نمی‌کند.</p>{authoringError != null ? <CmsState error={authoringError} retry={() => setAuthoringRetry(n => n + 1)}/> : !authoring ? <CmsState loading/> : <><h3>نامزدهای تکرار نام یا alias</h3>{!authoring.duplicates.candidates.length ? <CmsState empty="نامزد تکراری با شواهد ثبت‌شده یافت نشد."/> : <div className="cms-table-wrap" role="region" tabIndex={0} aria-label="نامزدهای تکرار"><table className="cms-table"><caption>{authoring.duplicates.count} نامزد؛ بدون اقدام خودکار</caption><thead><tr><th scope="col">سطح</th><th scope="col">نام</th><th scope="col">شواهد</th><th scope="col">وضعیت</th></tr></thead><tbody>{authoring.duplicates.candidates.map(row => <tr key={row.id}><td>{duplicateTierLabels[row.tier]}</td><th scope="row">{row.state_id ? <a className="cms-link" href={`/admin-console/content/${kind}/${row.state_id}`}><bdi>{row.label}</bdi></a> : <bdi>{row.label}</bdi>}</th><td>{row.evidence.map((evidence, index) => <span className="cms-badge" key={`${row.id}-${index}`}>{evidence.type === 'identity' ? `هویت ${evidence.field}` : evidence.type === 'name' ? `نام ${(evidence.fields || []).join('، ')}` : evidence.type === 'alias' ? 'alias مشترک' : `شباهت ${Math.round((evidence.similarity || 0) * 100)}٪`}</span>)}</td><td>{row.is_active ? 'فعال' : 'غیرفعال'}</td></tr>)}</tbody></table></div>}{authoring.duplicates.truncated && <p className="cms-notice">فهرست به سقف خواندنی محدود شده است؛ نامزدهای بیشتری ممکن است وجود داشته باشند.</p>}<h3>اثر بایگانی بر داده‌های وابسته</h3>{!authoring.impact.totals.relations ? <CmsState empty="هیچ ردیف وابسته‌ای در روابط ORM فعلی ثبت نشده است."/> : <div className="cms-table-wrap" role="region" tabIndex={0} aria-label="اثر بایگانی"><table className="cms-table"><caption>{authoring.impact.totals.relations} رابطهٔ دارای ردیف · {authoring.impact.totals.rows} ردیف وابسته</caption><thead><tr><th scope="col">وابستگی</th><th scope="col">تعداد</th><th scope="col">اثر حذف</th></tr></thead><tbody>{authoring.impact.relations.filter(row => row.count > 0).map(row => <tr key={`${row.model}-${row.field}`}><th scope="row"><bdi>{row.label}</bdi><p className="cms-id" dir="ltr">{row.model}.{row.field}</p></th><td>{row.count}</td><td>{impactLabels[row.impact] || row.impact}<p className="muted" dir="ltr">{row.on_delete}</p></td></tr>)}</tbody></table></div>}<p className="muted">digest اثر: <bdi dir="ltr">{authoring.impact.impact_digest}</bdi> · canonical write: {authoring.impact.canonical_write} · raw archive changed: {String(authoring.impact.raw_archive_changed)}</p><p className="muted">{authoring.duplicates.notice} {authoring.impact.notice}</p></>}</section>}
    {base && <section className="card stack"><h2>عملیات پیشنهاد</h2>{dirty && <p className="cms-notice">فرم تغییر ذخیره‌نشده دارد؛ عملیات نسخهٔ سرور تا ذخیره یا بازنشانی فرم بسته است.</p>}{can(`cms_${schema.domain}_archive`) && base.data.intent !== 'archive' && base.data.canonical_pk !== null && ['legacy', 'draft', 'changes_requested', 'approved'].includes(base.data.revision_status) && <><label className="cms-review-check"><input type="checkbox" checked={archiveAck} onChange={e => setArchiveAck(e.target.checked)}/>درخواست برداشت آینده در P16؛ اصل فعلی اکنون برداشته نمی‌شود.</label><button className="button secondary" disabled={!archiveAck || busy || blocked || dirty || !base.etag} onClick={() => void perform('archive')}>ثبت پیشنهاد بایگانی</button></>}{can(`cms_${schema.domain}_edit`) && base.data.canonical_pk === null && base.data.revision_status === 'draft' && <button className="button secondary" disabled={busy || blocked || dirty || !base.etag} onClick={() => leave(() => {void perform('discard');})}>کنارگذاری پیش‌نویس منتشرنشده</button>}</section>}
    {base && base.data.canonical_pk !== null && ['dsm-corpus', 'dsm-record'].includes(kind) && can('cms_research_raw_read') && <section className="card stack"><h2>مشاهدهٔ raw حفظ‌شده؛ فقط خواندنی</h2><p>این دسترسی خصوصی برای بررسی منبع با دلیل RESEARCH_RAW در audit ثبت می‌شود. اصلاح raw فقط از ورودی تازهٔ P06 است.</p><label className="cms-review-check"><input type="checkbox" checked={rawAck} onChange={e => setRawAck(e.target.checked)}/>هدف source_review و ثبت دلیل دسترسی را تأیید می‌کنم.</label><button className="button secondary" disabled={!rawAck || busy || blocked || dirty || !base.etag} onClick={() => void perform('raw-preview')}>مشاهدهٔ فقط خواندنی raw با ثبت دسترسی</button>{raw !== undefined && <><button className="button secondary" onClick={() => setRaw(undefined)}>بستن نمای raw</button><div role="region" aria-label="raw فقط خواندنی" tabIndex={0} style={{maxHeight: '32rem', overflow: 'auto'}}><DomainValueView value={raw}/></div></>}</section>}
    {busy && <p role="status">در حال دریافت پاسخ…</p>}{saved && <p role="status" className="cms-success">پیشنهاد ذخیره شد. محتوای عمومی بدون تغییر است.</p>}
  </div>;
}
