"use client";
import { useEffect, useState } from 'react';
import { cms, CmsPage, reviewFieldLabels } from '@/lib/cms';
import { DomainField, DomainOption, DomainPayload, DomainSchema, DomainValue, fieldWritable } from '@/lib/cmsDomains';
import { CmsState } from './CmsShell';
import StructuredOperationalField from './StructuredOperationalField';

export function useDomainSchemas() {
  const [schemas, setSchemas] = useState<DomainSchema[]>();
  const [error, setError] = useState<unknown>();
  const [retry, setRetry] = useState(0);
  useEffect(() => {
    let active = true; setError(undefined); setSchemas(undefined);
    cms<{ kinds: DomainSchema[] }>('/content/schema/').then(({data}) => { if (active) setSchemas(data.kinds); }).catch(e => { if (active) setError(e); });
    return () => { active = false; };
  }, [retry]);
  return {schemas, error, retry: () => setRetry(n => n + 1)};
}
export const fieldLabel = (field: DomainField) => field.label || reviewFieldLabels[field.name] || field.name.replaceAll('_', ' ');
export function readonlyExplanation(field: DomainField) {
  if (field.create_only) return 'هویت پس از ثبت ثابت است؛ اصلاح از مسیر جانشین یا ورودی تازه انجام می‌شود.';
  if (field.readonly_reason?.startsWith('IMMUTABLE_RAW')) return 'سند خام حفظ می‌شود؛ اصلاح فقط با ورودی تازه و مشاهده با ثبت دسترسی است.';
  if (field.readonly_reason?.startsWith('WORKFLOW_ONLY')) return 'فقط از مسیر انتشار یا برداشت مجاز قابل تغییر است؛ ذخیرهٔ پیشنهاد این مقدار را تغییر نمی‌دهد.';
  return 'مقدار توسط سامانه تولید یا حفظ می‌شود و در پیشنهاد قابل نوشتن نیست.';
}

export function DomainValueView({ value }: {value: DomainValue | undefined}) {
  if (value === null || value === undefined || value === '') return <span className="muted">ثبت نشده</span>;
  if (Array.isArray(value)) return <ul>{value.map((item, index) => <li key={index}><DomainValueView value={item}/></li>)}</ul>;
  if (typeof value === 'object') return <dl>{Object.entries(value).map(([key, item]) => <div key={key}><dt><bdi>{key}</bdi></dt><dd><DomainValueView value={item}/></dd></div>)}</dl>;
  return <span className="cms-prose" dir="auto" style={{overflowWrap: 'anywhere'}}>{typeof value === 'boolean' ? value ? 'بله' : 'خیر' : String(value)}</span>;
}

export function ReferenceSelector({kind, value, disabled, required, label, onChange}: {
  kind: string; value: number | null; disabled?: boolean; required?: boolean; label: string; onChange: (value: number | null) => void;
}) {
  const [search, setSearch] = useState('');
  const [query, setQuery] = useState('');
  const [page, setPage] = useState(1);
  const [data, setData] = useState<CmsPage<DomainOption>>();
  const [error, setError] = useState<unknown>();
  const [retry, setRetry] = useState(0);
  const [chosen, setChosen] = useState<DomainOption>();
  useEffect(() => {
    let active = true; setData(undefined); setError(undefined);
    cms<CmsPage<DomainOption>>(`/content/options/${encodeURIComponent(kind)}/?${new URLSearchParams({q: query, page: String(page)})}`).then(({data}) => { if (active) setData(data); }).catch(e => { if (active) setError(e); });
    return () => { active = false; };
  }, [kind, query, page, retry]);
  return <fieldset className="cms-fieldset" disabled={disabled}><legend>{label}{required ? ' (الزامی)' : ''}</legend>
    <label>جست‌وجوی {label}<input type="search" value={search} maxLength={200} onChange={e => setSearch(e.target.value)}/></label>
    <button type="button" className="button secondary" onClick={() => {setPage(1); setQuery(search.trim());}}>جست‌وجو در گزینه‌های مجاز</button>
    {error ? <CmsState error={error} retry={() => setRetry(n => n + 1)}/> : !data ? <CmsState loading/> : <>
      <label>{label}<select required={required} value={value ?? ''} onChange={e => { const id = e.target.value ? Number(e.target.value) : null; setChosen(data.results.find(item => item.id === id)); onChange(id); }}>
        <option value="">انتخاب نشده</option>
        {value !== null && !data.results.some(item => item.id === value) && <option value={value}>{chosen?.id === value ? chosen.label : `شناسهٔ انتخاب‌شده: ${value}؛ برای تأیید، جست‌وجو کنید`}</option>}
        {data.results.map(item => <option key={item.id} value={item.id}>{item.label} · نسخه {item.version}</option>)}
      </select></label>
      {!data.results.length && <p className="muted">گزینهٔ مجازی یافت نشد.</p>}
      <nav className="cms-pagination" aria-label={`صفحه‌بندی ${label}`}><button type="button" className="button secondary" disabled={page <= 1} onClick={() => setPage(n => n - 1)}>قبلی</button><span>صفحه {page}</span><button type="button" className="button secondary" disabled={page * data.page_size >= data.count} onClick={() => setPage(n => n + 1)}>بعدی</button></nav>
    </>}
  </fieldset>;
}

export default function DomainFields({schema, form, immutable = {}, creating, disabled, errors, onChange}: {
  schema: DomainSchema; form: DomainPayload; immutable?: DomainPayload; creating: boolean; disabled: boolean; errors?: Record<string, string[]>; onChange: (name: string, value: DomainValue) => void;
}) {
  return <fieldset className="cms-fieldset" disabled={disabled}>{schema.fields.map(field => {
    const id = `domain-${field.name}`, label = fieldLabel(field), value = field.name in form ? form[field.name] : immutable[field.name];
    const writable = fieldWritable(field, creating);
    const props = { id, name: field.name, required: field.required, 'aria-invalid': !!errors?.[field.name], 'aria-describedby': `${id}-hint` };
    return <div className="cms-form-field" id={`${id}-container`} key={field.name}>
      {!writable ? <><h3>{label}</h3><DomainValueView value={value}/><p className="muted">فقط خواندنی: {readonlyExplanation(field)}</p></>
      : field.related_kind ? <ReferenceSelector kind={field.related_kind === 'source-reference' ? 'source' : field.related_kind} label={label} required={field.required} value={typeof value === 'number' ? value : null} onChange={next => onChange(field.name, next)}/>
      : field.type === 'structured' && field.structure ? <><h3>{label}</h3><StructuredOperationalField field={field} value={value} label={label} onChange={next => onChange(field.name, next)}/></>
      : <><label htmlFor={id}>{label}{field.required ? ' (الزامی)' : ''}</label>
        {field.choices?.length ? <select {...props} value={String(value ?? '')} onChange={e => onChange(field.name, e.target.value)}><option value="">انتخاب کنید</option>{field.choices.map(choice => <option key={choice.value} value={choice.value}>{choice.label}</option>)}</select>
        : ['integer', 'number', 'float'].includes(field.type) ? <input {...props} type="number" step={field.type === 'integer' ? 1 : 'any'} value={typeof value === 'number' ? value : ''} onChange={e => onChange(field.name, e.target.value === '' ? null : Number(e.target.value))}/>
        : field.type === 'boolean' ? <select {...props} value={value === true ? 'true' : value === false ? 'false' : ''} onChange={e => onChange(field.name, e.target.value === '' ? null : e.target.value === 'true')}><option value="">انتخاب کنید</option><option value="true">بله</option><option value="false">خیر</option></select>
        : ['string', 'text', 'date', 'url'].includes(field.type) ? (field.type === 'text' || (field.max_length ?? 0) > 500 ? <textarea {...props} dir="auto" rows={5} maxLength={field.max_length ?? undefined} value={typeof value === 'string' ? value : ''} onChange={e => onChange(field.name, e.target.value)}/> : <input {...props} type={field.type === 'date' ? 'date' : field.type === 'url' ? 'url' : 'text'} dir={field.name.endsWith('_en') ? 'ltr' : 'auto'} maxLength={field.max_length ?? undefined} value={typeof value === 'string' ? value : ''} onChange={e => onChange(field.name, e.target.value)}/>)
        : <><DomainValueView value={value}/><p className="cms-notice">این ساختار از مسیر فرم بستهٔ اختصاصی یا ورودی P06 مدیریت می‌شود؛ ویرایش JSON آزاد مجاز نیست.</p></>}
      </>}
      <small id={`${id}-hint`}>{field.create_only && creating ? 'هویت فقط هنگام ساخت قابل ثبت است. ' : ''}{errors?.[field.name]?.join(' · ')}</small>
    </div>;
  })}</fieldset>;
}
