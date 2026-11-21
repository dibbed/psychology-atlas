"use client";
import { useEffect, useState } from 'react';
import { cms, CmsPage } from '@/lib/cms';
import { ContentCheckResult, DomainField, DomainOption, DomainSchema, recordFields } from '@/lib/cmsDomains';
import { DomainValueView, fieldLabel } from './DomainFields';
import { CmsState } from './CmsShell';

function PreviewReference({field, id}: {field: DomainField; id: number}) {
  const [option, setOption] = useState<DomainOption>();
  const [error, setError] = useState<unknown>();
  const [retry, setRetry] = useState(0);
  const kind = field.related_kind === 'source-reference' ? 'source' : field.related_kind;
  useEffect(() => {
    let active = true; setOption(undefined); setError(undefined);
    cms<CmsPage<DomainOption>>(`/content/options/${encodeURIComponent(kind || '')}/?q=${id}`).then(({data}) => {if (active) setOption(data.results.find(item => item.id === id));}).catch(e => {if (active) setError(e);});
    return () => {active = false;};
  }, [kind, id, retry]);
  return <div><h4>{fieldLabel(field)}</h4>{error ? <CmsState error={error} retry={() => setRetry(n => n + 1)}/> : option ? <p><bdi>{option.label}</bdi> · شناسه {id} · نسخه <bdi style={{overflowWrap: 'anywhere'}}>{option.version}</bdi></p> : <p className="muted">شناسه {id}؛ عنوان قابل مشاهده دریافت نشده است.</p>}</div>;
}

export default function DomainPreview({result, schema}: {result: ContentCheckResult; schema: DomainSchema}) {
  const candidate = {...recordFields(result.record), ...result.preview?.candidate};
  return <article className="stack" aria-live="polite"><h3>نتیجهٔ اعتبارسنجی پیشنهاد در سرور</h3><p>{result.valid ? 'ساختار پیشنهاد معتبر است.' : 'اعتبار ساختار تأیید نشده است.'}</p><p className="cms-notice">پیش‌نمایش نامزد خصوصی و منتشرنشده؛ تأیید علمی، تأیید حقوقی یا مجوز انتشار نیست. انتشار canonical در این مرحله در دسترس نیست.</p>
    {result.preview && <><h3>نمای نامزد ذخیره‌شده</h3>{schema.fields.filter(field => field.name in candidate).map(field => <section key={field.name}><h4>{fieldLabel(field)}</h4><DomainValueView value={candidate[field.name]}/></section>)}
      {schema.fields.filter(field => field.related_kind && typeof candidate[field.name] === 'number').map(field => <PreviewReference field={field} id={Number(candidate[field.name])} key={field.name}/>)}
    </>}
  </article>;
}
