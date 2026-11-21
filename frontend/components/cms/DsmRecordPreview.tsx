"use client";
import { useEffect, useState } from 'react';
import { cms, reviewFieldLabels } from '@/lib/cms';
import { DsmGraph, DsmStudy } from '@/lib/cmsDomains';
import { DomainValueView } from './DomainFields';
import { CmsState } from './CmsShell';

export default function DsmRecordPreview({corpus, record}: {corpus: number; record: number}) {
  const [graph, setGraph] = useState<DsmGraph>();
  const [study, setStudy] = useState<DsmStudy>();
  const [graphError, setGraphError] = useState<unknown>();
  const [studyError, setStudyError] = useState<unknown>();
  const [graphRetry, setGraphRetry] = useState(0);
  const [studyRetry, setStudyRetry] = useState(0);
  useEffect(() => {
    let active = true; setGraph(undefined); setGraphError(undefined);
    cms<DsmGraph>(`/content/dsm/graph/?${new URLSearchParams({corpus: String(corpus), record: String(record)})}`).then(({data}) => {if (active) setGraph(data);}).catch(e => {if (active) setGraphError(e);});
    return () => {active = false;};
  }, [corpus, record, graphRetry]);
  useEffect(() => {
    let active = true; setStudy(undefined); setStudyError(undefined);
    cms<DsmStudy>(`/content/dsm/study/?record=${record}`).then(({data}) => {if (active) setStudy(data);}).catch(e => {if (active) setStudyError(e);});
    return () => {active = false;};
  }, [record, studyRetry]);
  return <section className="card stack" aria-label="پیش‌نمایش خصوصی مطالعه و گراف"><h2>پیش‌نمایش مطالعه و گراف رکورد</h2><p className="cms-notice">دادهٔ محدود سرور؛ این نما برنامهٔ مطالعه یا corpus را تغییر نمی‌دهد و تأیید یا انتشار علمی نیست.</p>
    <section className="stack"><h3>نمای مطالعه</h3>{studyError ? <CmsState error={studyError} retry={() => setStudyRetry(n => n + 1)}/> : !study ? <CmsState loading/> : <><h4><bdi>{study.name_fa || study.name_en || study.master_id}</bdi></h4><p className="cms-prose" dir="auto">{study.summary || 'خلاصه‌ای ثبت نشده است.'}</p>{study.sections.length ? study.sections.map(section => <section key={section.key}><h4>{reviewFieldLabels[section.key] || section.key}</h4><DomainValueView value={section.value}/></section>) : <p className="muted">بخش مطالعه‌ای برای این رکورد ثبت نشده است.</p>}</>}</section>
    <section className="stack"><h3>گراف همسایگی</h3>{graphError ? <CmsState error={graphError} retry={() => setGraphRetry(n => n + 1)}/> : !graph ? <CmsState loading/> : <><p>محدوده: همسایگی رکورد {graph.focus_id} · {graph.nodes.length} گره · {graph.edges.length} پیوند</p>{graph.truncated && <p role="status" className="cms-notice">نتیجه به سقف امن سرور رسیده و کامل نیست.</p>}{!graph.edges.length && <p className="muted">پیوندی در محدودهٔ پاسخ وجود ندارد.</p>}<ul>{graph.nodes.map(node => <li key={node.id}><bdi>{node.name_fa || node.name_en || node.master_id}</bdi> · شناسه {node.id}</li>)}</ul>{graph.edges.length > 0 && <div className="cms-table-wrap" tabIndex={0} role="region" aria-label="پیوندهای گراف؛ پیمایش افقی"><table className="cms-table"><caption>پیوندهای همسایگی از سرور</caption><thead><tr><th scope="col">مبدأ</th><th scope="col">رابطه</th><th scope="col">مقصد</th></tr></thead><tbody>{graph.edges.map((edge, index) => <tr key={`${edge.source_id}/${edge.target_id}/${edge.relationship_type}/${index}`}><td><bdi>{graph.nodes.find(node => node.id === edge.source_id)?.name_fa || edge.source_id}</bdi></td><td><bdi>{edge.relationship_type}</bdi></td><td><bdi>{graph.nodes.find(node => node.id === edge.target_id)?.name_fa || edge.target_id}</bdi></td></tr>)}</tbody></table></div>}</>}</section>
  </section>;
}
