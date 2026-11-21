"use client";
import { useState } from 'react';
import { DomainField, DomainValue } from '@/lib/cmsDomains';
import { DomainValueView } from './DomainFields';

const labels: Record<string, string> = {string: 'متن', number: 'عدد', boolean: 'بله/خیر', null: 'بدون مقدار', array: 'فهرست', object: 'ویژگی‌های ساختاریافته'};
const initial: Record<string, DomainValue> = {string: '', number: 0, boolean: false, null: null, array: [], object: {}};
const typeOf = (value: DomainValue) => value === null ? 'null' : Array.isArray(value) ? 'array' : typeof value;
const protectedKeys = ['raw_document', 'source_payload', 'source_sha256', 'source_filename', 'search_text', '__proto__', 'constructor', 'prototype'];

// Only the server's operational field grammar is editable; raw/system fields never enter this control.
export default function StructuredOperationalField({field, value, label, onChange}: {field: DomainField; value: DomainValue | undefined; label: string; onChange: (value: DomainValue) => void}) {
  const limits = field.structure;
  if (!limits) return <DomainValueView value={value}/>;
  const rootTypes = limits.root === 'number-or-object' ? ['number', 'object'] : [limits.root];
  const current = value === undefined ? initial[rootTypes[0]] : value;
  return <div className="stack"><p className="muted">ساختار عملیاتی؛ حداکثر {limits.max_items} عضو در هر بخش، عمق {limits.max_depth} و متن {limits.max_text_length} نویسه. raw قابل ویرایش نیست.</p><Node field={field} value={current} label={label} depth={0} types={rootTypes} onChange={onChange}/></div>;
}

function Node({field, value, label, depth, types, onChange}: {field: DomainField; value: DomainValue; label: string; depth: number; types: string[]; onChange: (value: DomainValue) => void}) {
  const [key, setKey] = useState('');
  const limits = field.structure!;
  const type = typeOf(value);
  const canNest = depth < limits.max_depth;
  const permittedTypes = types.filter(type => limits.value_types.includes(type) && (canNest || !['array', 'object'].includes(type)));
  const childTypes = limits.value_types;
  const entries = typeof value === 'object' && value !== null && !Array.isArray(value) ? Object.entries(value) : [];
  const validKey = !!key.trim() && key === key.trim() && key.length <= 160 && !protectedKeys.includes(key) && !entries.some(([name]) => name === key);
  return <fieldset className="cms-fieldset" style={{minWidth: 0}}><legend>{label}</legend>
    {permittedTypes.length > 1 && <label>نوع مقدار {label}<select value={type} onChange={e => onChange(structuredClone(initial[e.target.value]))}>{permittedTypes.map(type => <option key={type} value={type}>{labels[type] || type}</option>)}</select></label>}
    {type === 'string' && <label>متن {label}<textarea rows={3} maxLength={limits.max_text_length} value={String(value)} dir="auto" onChange={e => onChange(e.target.value)}/></label>}
    {type === 'number' && <label>عدد {label}<input type="number" step="any" value={Number(value)} onChange={e => {if (e.target.value !== '' && Number.isFinite(Number(e.target.value))) onChange(Number(e.target.value));}}/></label>}
    {type === 'boolean' && <label>مقدار {label}<select value={String(value)} onChange={e => onChange(e.target.value === 'true')}><option value="true">بله</option><option value="false">خیر</option></select></label>}
    {type === 'null' && <p className="muted">بدون مقدار</p>}
    {type === 'array' && Array.isArray(value) && <>{!value.length && <p className="muted">فهرست خالی</p>}{value.map((item, index) => <div key={index} className="cms-merge-field"><Node field={field} value={item} label={`${label} · عضو ${index + 1}`} depth={depth + 1} types={childTypes} onChange={next => onChange(value.map((item, i) => i === index ? next : item))}/><button type="button" className="button secondary" onClick={() => onChange(value.filter((_, i) => i !== index))}>حذف عضو {index + 1}</button></div>)}<button type="button" className="button secondary" disabled={!canNest || value.length >= limits.max_items} onClick={() => onChange([...value, ''])}>افزودن عضو به {label}</button></>}
    {type === 'object' && <>{!entries.length && <p className="muted">ویژگی ثبت نشده</p>}{entries.map(([name, item]) => <div className="cms-merge-field" key={name}><Node field={field} value={item} label={name} depth={depth + 1} types={childTypes} onChange={next => onChange({...Object.fromEntries(entries), [name]: next})}/><button type="button" className="button secondary" onClick={() => onChange(Object.fromEntries(entries.filter(([key]) => key !== name)))}>حذف ویژگی {name}</button></div>)}<label>نام ویژگی تازهٔ {label}<input value={key} maxLength={160} dir="auto" onChange={e => setKey(e.target.value)}/></label><button type="button" className="button secondary" disabled={!canNest || !validKey || entries.length >= limits.max_items} onClick={() => {onChange({...Object.fromEntries(entries), [key]: ''}); setKey('');}}>افزودن ویژگی</button></>}
  </fieldset>;
}
