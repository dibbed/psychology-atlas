"use client";
import { useEffect, useState } from 'react';
import { cms, CmsError, CmsPage } from '@/lib/cms';
import { DsmCompareRow, DsmCorpus, DsmTreeRow } from '@/lib/cmsDomains';
import { CmsState, useCms } from './CmsShell';
import { ReferenceSelector, useDomainSchemas } from './DomainFields';
import DsmRecordPreview from './DsmRecordPreview';

type Tree = CmsPage<DsmTreeRow> & {corpus: DsmCorpus; source_registry_keys?: string[] | null};
type Comparison = CmsPage<DsmCompareRow> & {left: DsmCorpus; right: DsmCorpus; counts_scope: 'page'};
export default function DsmWorkspace() {
  const {can} = useCms();
  const {schemas, error: schemaError, retry: retrySchema} = useDomainSchemas();
  const [corpus, setCorpus] = useState<number | null>(null);
  const [right, setRight] = useState<number | null>(null);
  const [record, setRecord] = useState<number>();
  const [parents, setParents] = useState<{id: number; label: string}[]>([]);
  const [page, setPage] = useState(1);
  const [comparePage, setComparePage] = useState(1);
  const [tree, setTree] = useState<Tree>();
  const [comparison, setComparison] = useState<Comparison>();
  const [treeError, setTreeError] = useState<unknown>();
  const [compareError, setCompareError] = useState<unknown>();
  const [retry, setRetry] = useState(0);
  const allowed = schemas?.some(schema => schema.kind === 'dsm-corpus');
  const parent = parents.at(-1)?.id;
  useEffect(() => {
    setTree(undefined); setTreeError(undefined);
    if (!corpus || !allowed) return;
    let active = true;
    const params = new URLSearchParams({corpus: String(corpus), page: String(page), page_size: '20'});
    if (parent) params.set('parent', String(parent));
    cms<Tree>(`/content/dsm/tree/?${params}`).then(({data}) => {if (active) setTree(data);}).catch(e => {if (active) setTreeError(e);});
    return () => {active = false;};
  }, [corpus, parent, page, allowed, retry]);
  useEffect(() => {
    setComparison(undefined); setCompareError(undefined);
    if (!corpus || !right || !allowed) return;
    let active = true;
    cms<Comparison>(`/content/dsm/compare/?${new URLSearchParams({left: String(corpus), right: String(right), page: String(comparePage)})}`).then(({data}) => {if (active) setComparison(data);}).catch(e => {if (active) setCompareError(e);});
    return () => {active = false;};
  }, [corpus, right, comparePage, allowed, retry]);
  if (schemaError) return <CmsState error={schemaError} retry={retrySchema}/>;
  if (!schemas) return <CmsState loading/>;
  if (!allowed) return <CmsState error={new CmsError(403, 'PERMISSION_DENIED', '')}/>;
  const statusLabels = {added: 'افزوده', removed: 'حذف‌شده در نسخهٔ راست', changed: 'تغییریافته', unchanged: 'بدون تغییر'};
  return <div className="stack" dir="rtl"><a className="cms-link" href="/admin-console/content">→ محتوای مرجع</a><h1>DSM؛ درخت و مقایسهٔ corpus</h1>
    <p className="cms-notice">فرادادهٔ canonical به‌صورت صفحه‌بندی‌شده؛ این نما raw را نمایش نمی‌دهد و corpus فعال را تغییر نمی‌دهد.</p>
    <div className="cms-actions"><a className="button secondary" href="/admin-console/content/dsm-corpus">پیشنهادهای corpus</a><a className="button secondary" href="/admin-console/content/dsm-record">پیشنهادهای رکورد</a><a className="button secondary" href="/admin-console/content/dsm-record-relation">پیوندهای DSM</a><a className="cms-link" href="/admin-console/research/intake">ورودی فایل و بایگانی P06</a></div>
    <section className="card stack"><ReferenceSelector kind="dsm-corpus" value={corpus} label="corpus مبنا" onChange={value => {setCorpus(value); setRecord(undefined); setParents([]); setPage(1); setComparePage(1);}}/>
      {!corpus ? <CmsState empty="برای مشاهدهٔ درخت، corpus را از گزینه‌های مجاز انتخاب کنید."/> : treeError ? <CmsState error={treeError} retry={() => setRetry(n => n + 1)}/> : !tree ? <CmsState loading/> : <><h2><bdi>{tree.corpus.title}</bdi> · {tree.corpus.version_name}</h2><p className="cms-id" style={{overflowWrap: 'anywhere'}}>SHA-256: <bdi>{tree.corpus.source_sha256}</bdi></p><nav className="cms-actions" aria-label="مسیر درخت DSM"><button className="button secondary" onClick={() => {setParents([]); setPage(1);}}>ریشه</button>{parents.map((item, index) => <button className="button secondary" key={item.id} onClick={() => {setParents(current => current.slice(0, index + 1)); setPage(1);}}>{item.label}</button>)}</nav>
        {!tree.results.length && <CmsState empty="این گره فرزندی در صفحهٔ جاری ندارد."/>}<ul className="stack">{tree.results.map(row => <li className="cms-merge-field" key={row.id}><h3><bdi>{row.name_fa || row.name_en || row.master_id}</bdi></h3><p><bdi>{row.master_id}</bdi> · {row.display_type} · فرزند {row.children_count}</p><p>والد: {row.parent_id ?? 'ریشه'} · اختلال پیوندی: {row.linked_disorder_id ?? 'بدون پیوند'}</p><div className="cms-actions">{row.children_count > 0 && <button className="button secondary" onClick={() => {setParents(current => [...current, {id: row.id, label: row.name_fa || row.name_en || row.master_id}]); setPage(1);}}>مشاهدهٔ فرزندان</button>}{can('cms_dsm_preview') && <button className="button secondary" onClick={() => setRecord(row.id)}>پیش‌نمایش مطالعه و گراف</button>}</div></li>)}</ul>
        <nav className="cms-pagination" aria-label="صفحه‌بندی درخت"><button className="button secondary" disabled={page <= 1} onClick={() => setPage(n => n - 1)}>قبلی</button><span>صفحه {page}</span><button className="button secondary" disabled={page * tree.page_size >= tree.count} onClick={() => setPage(n => n + 1)}>بعدی</button></nav>
        {Array.isArray(tree.source_registry_keys) && <details><summary>کلیدهای منابع corpus در محدودهٔ دسترسی</summary>{tree.source_registry_keys.length ? <ul>{tree.source_registry_keys.map(key => <li key={key}><bdi>{key}</bdi></li>)}</ul> : <p className="muted">کلید منبعی ثبت نشده است.</p>}</details>}
      </>}
    </section>
    {record && corpus && can('cms_dsm_preview') && <><button className="button secondary" onClick={() => setRecord(undefined)}>بستن پیش‌نمایش رکورد</button><DsmRecordPreview key={`${corpus}/${record}`} corpus={corpus} record={record}/></>}
    <section className="card stack"><h2>مقایسهٔ محدود دو corpus</h2><ReferenceSelector kind="dsm-corpus" value={right} label="corpus سمت راست" onChange={value => {setRight(value); setComparePage(1);}}/>
      {!corpus || !right ? <p className="muted">هر دو corpus را انتخاب کنید.</p> : compareError ? <CmsState error={compareError} retry={() => setRetry(n => n + 1)}/> : !comparison ? <CmsState loading/> : <><p><bdi>{comparison.left.title}</bdi> ← <bdi>{comparison.right.title}</bdi></p><p className="cms-notice">شمار و وضعیت‌ها فقط محدودهٔ همین صفحه هستند؛ ارزیابی کامل علمی یا حقوقی نیستند.</p>{!comparison.results.length && <CmsState empty="رکوردی برای مقایسه در این صفحه موجود نیست."/>}<div className="cms-table-wrap" tabIndex={0} role="region" aria-label="مقایسه DSM؛ پیمایش افقی"><table className="cms-table"><caption>مقایسهٔ فرادادهٔ corpus</caption><thead><tr><th scope="col">رکورد</th><th scope="col">وضعیت</th><th scope="col">فیلدهای متفاوت</th></tr></thead><tbody>{comparison.results.map(row => <tr key={row.master_id}><th scope="row"><bdi>{row.name_fa || row.name_en || row.master_id}</bdi><p><bdi>{row.master_id}</bdi></p></th><td>{statusLabels[row.status]}</td><td>{row.changed_fields.map(field => <p key={field}><bdi>{field}</bdi></p>)}</td></tr>)}</tbody></table></div><nav className="cms-pagination" aria-label="صفحه‌بندی مقایسه"><button className="button secondary" disabled={comparePage <= 1} onClick={() => setComparePage(n => n - 1)}>قبلی</button><span>صفحه {comparePage}</span><button className="button secondary" disabled={comparePage * comparison.page_size >= comparison.count} onClick={() => setComparePage(n => n + 1)}>بعدی</button></nav></>}
    </section>
  </div>;
}
