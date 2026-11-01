"use client";
import { useEffect, useState } from 'react';
import { cms, CmsError, CmsPage, publicationLabels, revisionLabels } from '@/lib/cms';
import { contentPath, DomainRecord, domainTitle } from '@/lib/cmsDomains';
import { CmsState, useCms } from './CmsShell';
import { useDomainSchemas } from './DomainFields';

export default function DomainList({kind}: {kind: string}) {
  const {can} = useCms();
  const {schemas, error: schemaError, retry: retrySchema} = useDomainSchemas();
  const schema = schemas?.find(item => item.kind === kind);
  const [query, setQuery] = useState<URLSearchParams>();
  const [data, setData] = useState<CmsPage<DomainRecord>>();
  const [error, setError] = useState<unknown>();
  const [retry, setRetry] = useState(0);
  useEffect(() => {setQuery(new URLSearchParams(location.search));}, []);
  useEffect(() => {
    if (!schema || !query) return;
    let active = true; setData(undefined); setError(undefined);
    cms<CmsPage<DomainRecord>>(`${contentPath(kind)}?${query}`).then(({data}) => {if (active) setData(data);}).catch(e => {if (active) setError(e);});
    return () => {active = false;};
  }, [kind, schema, query, retry]);
  if (schemaError) return <CmsState error={schemaError} retry={retrySchema}/>;
  if (!schemas) return <CmsState loading/>;
  if (!schema) return <CmsState error={new CmsError(404, 'NOT_FOUND', '')}/>;
  const base = `/admin-console/content/${kind}`;
  const pageHref = (page: number) => {const params = new URLSearchParams(query); params.set('page', String(page)); return `?${params}`;};
  return <div className="stack" dir="rtl"><a className="cms-link" href="/admin-console/content">→ همهٔ انواع محتوا</a>
    <div className="cms-section-head"><h1>{schema.label}</h1>{can(`cms_${schema.domain}_create`) && <a className="button primary" href={`${base}/new`}>پیش‌نویس جدید</a>}</div>
    <p className="cms-notice">ذخیره، بررسی و درخواست بایگانی فقط پیشنهاد هستند؛ انتشار یا برداشت اصل در P16 انجام می‌شود.</p>
    {query && <form className="cms-filters card" method="get"><label>جست‌وجو<input name="q" type="search" maxLength={200} defaultValue={query.get('q') || ''}/></label><label>وضعیت<select name="status" defaultValue={query.get('status') || ''}><option value="">همه</option>{Object.entries(revisionLabels).map(([key, label]) => <option key={key} value={key}>{label}</option>)}</select></label><label>ترتیب<select name="sort" defaultValue={query.get('sort') || 'newest'}><option value="newest">جدیدترین</option><option value="oldest">قدیمی‌ترین</option></select></label><button className="button secondary">اعمال فیلتر</button><a className="cms-link" href={base}>پاک کردن</a></form>}
    {error ? <CmsState error={error} retry={() => setRetry(n => n + 1)}/> : !data ? <CmsState loading/> : !data.results.length ? <CmsState empty="رکوردی با این فیلتر یافت نشد."/> : <div className="cms-table-wrap" tabIndex={0} role="region" aria-label={`فهرست ${schema.label}؛ پیمایش افقی`}><table className="cms-table"><caption>{schema.label} · {data.count} نتیجه</caption><thead><tr><th scope="col">محتوا</th><th scope="col">نسخه</th><th scope="col">وضعیت پیشنهاد</th><th scope="col">اصل</th></tr></thead><tbody>{data.results.map(row => <tr key={row.id}><th scope="row"><a className="cms-record-link" href={`${base}/${row.id}?list=${encodeURIComponent(query?.toString() || '')}`}>{domainTitle(row.payload)}{row.intent === 'archive' && <span className="cms-badge">درخواست بایگانی آینده</span>}</a></th><td>{row.version}</td><td>{revisionLabels[row.revision_status] || row.revision_status}</td><td>{publicationLabels[row.publication] || row.publication}</td></tr>)}</tbody></table></div>}
    {data && <nav className="cms-pagination" aria-label="صفحه‌بندی محتوا">{data.page > 1 && <a className="button secondary" href={pageHref(data.page - 1)}>قبلی</a>}<span>صفحه {data.page}</span>{data.page * data.page_size < data.count && <a className="button secondary" href={pageHref(data.page + 1)}>بعدی</a>}</nav>}
  </div>;
}
