"use client";
import {useEffect, useState} from "react";
import {cms, CmsPage} from "@/lib/cms";
import {CmsState, useCms} from "@/components/cms/CmsShell";

type Node = {id:number;slug:string;name_en:string;name_fa:string;kind:string;laterality:string;is_active:boolean;review_status:string;parent_id:number|null;cms_state_id:string|null};
type Tree = CmsPage<Node> & {publication_available:false;notice:string};
type Impact = {child_id:number;before:{parent_id:number|null};after:{parent_id:number;valid:boolean;blockers:string[]};affected_descendants:number[];affected_count:number;requires_scientific_source_review:true;requires_publication_manifest:true;publication_available:false;notice:string};
const blockers:Record<string,string>={CYCLE:"ایجاد چرخه در درخت",LATERALITY_CONFLICT:"ناسازگاری جهت چپ، راست یا خط میانی",INACTIVE_ENDPOINT:"رکورد غیرفعال"};
export default function BrainTree() {
  const {can}=useCms();
  const allowed=can("cms_brain_view"), preview=can("cms_brain_preview");
  const [page,setPage]=useState(1);
  const [data,setData]=useState<Tree>();
  const [selected,setSelected]=useState("");
  const [parent,setParent]=useState("");
  const [impact,setImpact]=useState<Impact>();
  const [error,setError]=useState<unknown>();
  const [busy,setBusy]=useState(false);
  const [retry,setRetry]=useState(0);
  useEffect(()=>{
    if (!allowed)return;
    let valid=true;setData(undefined);setError(undefined);
    cms<Tree>(`/content/brain/tree/?page=${page}&page_size=30`).then(({data})=>{
      if (valid)setData(data);
    }).catch(e=>{if(valid)setError(e);});
    return ()=>{valid=false;};
  },[allowed,page,retry]);
  const inspect=async(e:React.FormEvent)=>{
    e.preventDefault();
    setImpact(undefined);setError(undefined);
    if(!preview||!selected||!parent||!/^[0-9]+$/.test(selected)||!/^[0-9]+$/.test(parent))return;
    setBusy(true);
    try{
      const res=await cms<Impact>(`/content/brain/tree/?child=${encodeURIComponent(selected)}&parent=${encodeURIComponent(parent)}`);
      setImpact(res.data);
    }catch(err){setError(err);}
    finally{setBusy(false);}
  };
  if(!allowed)return <CmsState empty="برای مشاهدهٔ درخت مغز، مجوز مدیریت Brain لازم است."/>;
  return <div className="stack" dir="rtl">
    <a href="/admin-console/content" className="cms-link">→ محتوای مرجع</a>
    <h1>درخت آناتومی و پیش‌نمایش جابه‌جایی والد</h1>
    <p className="cms-notice">این نمایش از دادهٔ موجود خوانده می‌شود. انتخاب والد جدید هیچ تغییری در دیتابیس عمومی ایجاد نمی‌کند. هر تغییر باید در فرم اختصاصی رابطه، با منبع و بازبینی علمی ثبت شود؛ انتشار مستقل در P16 انجام می‌شود.</p>
    <section className="card stack">
      <h2>پیش‌نمایش قبل و بعد</h2>
      <form className="cms-filters" onSubmit={inspect}>
        <label>شناسهٔ ناحیهٔ فرزند<input type="number" inputMode="numeric" min="1" required value={selected} onChange={e=>setSelected(e.target.value)}/></label>
        <label>شناسهٔ والد پیشنهادی<input type="number" inputMode="numeric" min="1" required value={parent} onChange={e=>setParent(e.target.value)}/></label>
        <button className="button secondary" type="submit" disabled={!preview||busy}>{busy?"بررسی…":"محاسبهٔ اثر بدون ذخیره"}</button>
      </form>
      {!preview && <p>مجوز پیش‌نمایش ساختار لازم است.</p>}
      {impact && <div className="stack" role="status" aria-live="polite">
        <p>والد فعلی: <bdi>{impact.before.parent_id??"بدون والد"}</bdi> | والد پیشنهادی: <bdi>{impact.after.parent_id}</bdi></p>
        <p>تعداد نواحی تحت تأثیر: {impact.affected_count}</p>
        {impact.after.valid?<p>موانع ساختاری فوری پیدا نشد. تأیید منبع، حقوق و داوری علمی همچنان لازم است.</p>:
          <p>تغییر پیشنهادی نامعتبر است: {impact.after.blockers.map(x=>blockers[x]??x).join("، ")}</p>}
        <p className="muted">شناسهٔ فرزندان وابسته: {impact.affected_descendants.join("، ")||"ندارد"}</p>
        <a className="cms-link" href="/admin-console/content/brain-hierarchy-link">ویرایش پیشنهاد رابطه در فرم امن ←</a>
      </div>}
    </section>
    {error!=null?<CmsState error={error} retry={()=>setRetry(n=>n+1)}/>:!data?<CmsState loading/>:
      <section className="stack">
        <h2>ساختار فعلی ({data.count} ناحیه)</h2>
        <div className="cms-table-wrap" role="region" tabIndex={0} aria-label="فهرست درخت آناتومی">
          <table className="cms-table"><caption>رکوردهای canonical، نه پیش‌نویس‌ها</caption>
            <thead><tr><th scope="col">ناحیه</th><th scope="col">جهت</th><th scope="col">والد</th><th scope="col">وضعیت</th><th scope="col">بررسی</th></tr></thead>
            <tbody>{data.results.map(row=><tr key={row.id}>
              <th scope="row">{row.cms_state_id?<a className="cms-link" href={`/admin-console/content/brain-anatomical-entity/${row.cms_state_id}`}>{row.name_fa||row.name_en}</a>:row.name_fa||row.name_en}<small> #{row.id}</small></th>
              <td>{row.laterality}</td>
              <td>{row.parent_id??"ریشه"}</td>
              <td>{row.is_active?"فعال":"غیرفعال"} / {row.review_status}</td>
              <td><button type="button" className="button secondary" disabled={!preview} onClick={()=>{setSelected(String(row.id));setImpact(undefined);}}>انتخاب</button></td>
            </tr>)}</tbody>
          </table>
        </div>
        <nav className="cms-pagination" aria-label="صفحه‌بندی درخت مغز">
          <button type="button" className="button secondary" disabled={page<=1} onClick={()=>setPage(n=>n-1)}>قبلی</button>
          <span>صفحه {page}</span>
          <button type="button" className="button secondary" disabled={page*data.page_size>=data.count} onClick={()=>setPage(n=>n+1)}>بعدی</button>
        </nav>
      </section>}
  </div>;
}
