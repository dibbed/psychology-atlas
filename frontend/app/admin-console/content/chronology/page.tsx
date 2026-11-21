"use client";
import {useEffect,useState} from "react";
import {cms,CmsPage} from "@/lib/cms";
import {originLabels} from "@/lib/cmsDomains";
import {CmsState,useCms} from "@/components/cms/CmsShell";

type OriginRecord={record_id:number;dataset_id:number;dataset_name:string;external_id:string;section:string;staging_state:string};
type Origin={status:"linked"|"unlinked"|"unknown"|"restricted"|"unavailable";reason?:string;records:OriginRecord[];count:number;restricted_count:number};
type TimelineRow={id:number;cms_state_id?:string;slug:string;title_en:string;title_fa:string;year_start:number|null;year_end:number|null;exact_date:string|null;date_text:string;date_precision:string;event_type:string;source_count:number;checked_source_count:number;citation_debt:boolean;revision_status:string;origin?:Origin};
type DebtRow={id:number;cms_state_id?:string;name:string;source_count:number;checked_source_count:number;citation_debt:boolean;revision_status:string;auto_approval:false};
type Results<T>=CmsPage<T>&{notice:string;scope?:string;date_inference?:string};
const precisionLabels:Record<string,string>={exact_date:"تاریخ قطعی",year:"فقط سال",year_range:"بازهٔ سال",approximate_year:"سال تقریبی",unknown:"نامشخص"};
const debtKinds=[{kind:"psychologist",label:"روان‌شناسان"},{kind:"theory",label:"نظریه‌ها"},{kind:"timeline-event",label:"رویدادها"}] as const;
// Only trusted route segments may enter a CMS href, never unvalidated DOM text.
const safeDebtKind=(input:string)=>debtKinds.find(row=>row.kind===input)?.kind??"timeline-event";
const safeStateId=(input:unknown):input is string=>typeof input==="string"&&/^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i.test(input);
export default function HistoryChronology(){
  const {can}=useCms();
  const [mode,setMode]=useState<"timeline"|"debt">("timeline");
  const [kind,setKind]=useState("timeline-event");
  const [input,setInput]=useState("");
  const [query,setQuery]=useState("");
  const [precision,setPrecision]=useState("");
  const [weak,setWeak]=useState(false);
  const [page,setPage]=useState(1);
  const [value,setValue]=useState<Results<TimelineRow>|Results<DebtRow>>();
  const [error,setError]=useState<unknown>();
  const [retry,setRetry]=useState(0);
  const allowed=can("cms_history_view");
  useEffect(()=>{
    if(!allowed)return;
    let active=true;setValue(undefined);setError(undefined);
    const params=new URLSearchParams({page:String(page)});
    if(mode==="debt")params.set("kind",kind);
    else{if(query)params.set("q",query);if(precision)params.set("precision",precision);if(weak)params.set("weak_only","1");}
    const endpoint=mode==="debt"?"citation-debt":"chronology";
    cms<Results<TimelineRow>|Results<DebtRow>>(`/content/history/${endpoint}/?${params}`).then(({data})=>{if(active)setValue(data);}).catch(e=>{if(active)setError(e);});
    return()=>{active=false;};
  },[allowed,mode,kind,query,precision,weak,page,retry]);
  if(!allowed)return <CmsState empty="برای مشاهدهٔ تاریخچه، دسترسی مدیریت این دامنه لازم است."/>;
  return <div className="stack" dir="rtl">
    <a className="cms-link" href="/admin-console/content">→ محتوای مرجع</a>
    <h1>زمان‌بندی و ارجاعات تاریخ روان‌شناسی</h1>
    <p className="cms-notice">تاریخ و قطعیت دقیقاً مطابق دادهٔ ثبت‌شده‌اند. رویداد ناشناخته تاریخِ فرضی نمی‌گیرد؛ ارجاع ضعیف به‌معنای تأیید علمی نیست و داوری بدون تصمیم انسان انجام نمی‌شود.</p>
    <nav className="cms-tabs" aria-label="نمای تاریخچه">
      <button className="button secondary" aria-pressed={mode==="timeline"} onClick={()=>{setMode("timeline");setPage(1);}}>خط زمان</button>
      <button className="button secondary" aria-pressed={mode==="debt"} onClick={()=>{setMode("debt");setPage(1);}}>بدهی ارجاع</button>
    </nav>
    <section className="card stack">
      {mode==="timeline"?<form className="cms-filters" onSubmit={e=>{e.preventDefault();setPage(1);setQuery(input.trim());}}>
        <label>عنوان یا شناسهٔ رویداد<input type="search" maxLength={200} value={input} onChange={e=>setInput(e.target.value)} /></label>
        <label>قطعیت زمان<select value={precision} onChange={e=>{setPrecision(e.target.value);setPage(1);}}><option value="">همه</option>{Object.entries(precisionLabels).map(([k,v])=><option value={k} key={k}>{v}</option>)}</select></label>
        <label><input type="checkbox" checked={weak} onChange={e=>{setWeak(e.target.checked);setPage(1);}}/> فقط رویداد بدون منبع بررسی‌شده</label>
        <button className="button secondary" type="submit">جست‌وجو</button>
      </form>:<label>نوع هویت<select value={kind} onChange={e=>{setKind(safeDebtKind(e.currentTarget.value));setPage(1);}}>{debtKinds.map(row=><option value={row.kind} key={row.kind}>{row.label}</option>)}</select></label>}
    </section>
    {error!=null?<CmsState error={error} retry={()=>setRetry(n=>n+1)}/>:!value?<CmsState loading/>:!value.results.length?<CmsState empty="برای این فیلتر رکوردی وجود ندارد."/>:<>
      <div className="cms-table-wrap" role="region" tabIndex={0} aria-label="مرور تاریخ و منبع">
        <table className="cms-table"><caption>{mode==="timeline"?"خط زمان با دقت ثبت‌شده":"رکوردهای دارای بدهی ارجاع"} · {value.count} رکورد</caption>
          <thead><tr><th scope="col">عنوان و ویرایش</th><th scope="col">{mode==="timeline"?"تاریخ ثبت‌شده":"نوع"}</th><th scope="col">منابع و داوری</th><th scope="col">منشأ پژوهشی</th></tr></thead>
          <tbody>{value.results.map((record)=>{
            const timeline=mode==="timeline"?record as TimelineRow:null;
            const label=timeline?(timeline.title_fa||timeline.title_en):(record as DebtRow).name;
            const state=record.cms_state_id;
            const routeKind=mode==="timeline"?"timeline-event":safeDebtKind(kind);
            return <tr key={record.id}>
              <th scope="row">{safeStateId(state)?<a className="cms-link" href={`/admin-console/content/${routeKind}/${state}`}><bdi>{label}</bdi></a>:<bdi>{label}</bdi>}</th>
              <td>{timeline?<><span>{precisionLabels[timeline.date_precision]||timeline.date_precision}</span><p><bdi>{timeline.exact_date||timeline.date_text||[timeline.year_start,timeline.year_end].filter(x=>x!==null).join(" تا ")||"نامشخص"}</bdi></p></>:debtKinds.find(row=>row.kind===safeDebtKind(kind))?.label}</td>
              <td>{record.checked_source_count} منبع بررسی‌شده از {record.source_count}<p>{record.citation_debt?"نیازمند شواهد بهتر":"دارای ارجاع بررسی‌شده"}</p><small>{record.revision_status}</small></td>
              <td>{timeline?.origin?<>{timeline.origin.status==="linked"?<a className="cms-link" href={`/admin-console/research/records/${timeline.origin.records[0]?.record_id}`}>{timeline.origin.count} locator مجاز</a>:<span>{originLabels[timeline.origin.status]}</span>}{timeline.origin.restricted_count>0&&<p className="muted">بخشی خارج از scope</p>}</>:"—"}</td>
            </tr>;
          })}</tbody>
        </table>
      </div>
      <nav className="cms-pagination" aria-label="صفحه‌بندی تاریخچه">
        <button type="button" className="button secondary" disabled={page<=1} onClick={()=>setPage(n=>n-1)}>قبلی</button>
        <span>صفحه {page}</span>
        <button type="button" className="button secondary" disabled={page*value.page_size>=value.count} onClick={()=>setPage(n=>n+1)}>بعدی</button>
      </nav>
    </>}
    <p className="muted">نمای فقط خواندنی canonical، بدون انتشار، تغییر منابع، تاریخ‌سازی یا برچسب علمی خودکار.</p>
  </div>;
}
