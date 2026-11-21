"use client";

import {useEffect,useRef,useState} from "react";
import {cms,CmsError} from "@/lib/cms";
import {useCms} from "@/components/cms/CmsShell";

type Domain="learning"|"brain"|"assessment";
type Item={
  kind:string;resource_id:string|number;revision_id:number|null;
  action:"create"|"update"|"activate";changed_public_fields:string[];
  current_public_anchor:{status:string;root_count:number;visible_count:number};
  public_reader_contract:{surfaces:Record<string,{status:string;route:string|null}>};
};
type DryRun={
  schema:"cms-frozen-review-manifest-v1";domain:Domain;
  dossier_id:string;dossier_digest:string;manifest_digest:string;
  item_count:number;actions:Item[];review_blocker_count:number;
  authority:"frozen_review_only_no_publication";
  approved:false;publication_available:false;public_projection:null;
};
type FrozenReceipt={
  id:string;dossier_id:string;dossier_digest:string;manifest_digest:string;
  status:"frozen_review_only";item_count:number;actions:Item[];
  recovered:boolean;approved:false;publication_available:false;
  public_projection:null;
};

export default function FrozenManifestPanel({
  domain,dossierId,dossierDigest,valid,
}:{domain:Domain;dossierId:string;dossierDigest:string;valid:boolean}){
  const {can}=useCms();
  const allowed=can("cms_publication_freeze_"+domain)&&
    can("cms_"+domain+"_preview");
  const allowedVerify=can("cms_publication_verify_"+domain);
  const [dry,setDry]=useState<DryRun>();
  const [receipt,setReceipt]=useState<FrozenReceipt>();
  const [error,setError]=useState("");
  const [busy,setBusy]=useState(false);
  const [recordId,setRecordId]=useState("");
  const requestKey=useRef("");
  const generation=useRef(0);

  useEffect(()=>{
    if(!valid||!allowed){
      generation.current++;
      setDry(undefined);setReceipt(undefined);setError("");requestKey.current="";
    }
  },[valid,allowed]);

  async function examine(){
    if(!valid||!allowed||busy)return;
    const stamp=++generation.current;
    setBusy(true);setError("");setDry(undefined);
    try{
      const response=await cms<DryRun>(
        "/publication/preparations/"+encodeURIComponent(dossierId)+"/dry-run/");
      if(stamp!==generation.current)return;
      if(response.data.dossier_id!==dossierId||
          response.data.dossier_digest!==dossierDigest||
          response.data.domain!==domain||
          response.data.public_projection!==null||
          response.data.publication_available)throw Error("MANIFEST_BINDING_MISMATCH");
      setDry(response.data);
    }catch(e){
      if(stamp===generation.current){
        requestKey.current="";
        setError(e instanceof CmsError?e.message:"بررسی نسخهٔ منجمد نامعتبر شد. پرونده را دوباره تطبیق بدهید.");
      }
    }finally{if(stamp===generation.current)setBusy(false);}
  }

  async function freeze(){
    if(!valid||!allowed||busy||!dry||receipt)return;
    const stamp=++generation.current;
    if(!requestKey.current)requestKey.current=crypto.randomUUID();
    setBusy(true);setError("");
    try{
      const res=await cms<FrozenReceipt>(
        "/publication/preparations/"+encodeURIComponent(dossierId)+"/freeze/",{
          method:"POST",body:JSON.stringify({
            dossier_digest:dossierDigest,request_key:requestKey.current,
          }),
        });
      if(stamp!==generation.current)return;
      if(res.data.dossier_id!==dossierId||
          res.data.manifest_digest!==dry.manifest_digest||
          res.data.public_projection!==null||
          res.data.publication_available)throw Error("MANIFEST_BINDING_MISMATCH");
      setReceipt(res.data);setRecordId(res.data.id);
      requestKey.current="";
    }catch(e){
      if(stamp===generation.current)setError(e instanceof CmsError?e.message:
        "ثبت مانیفست انجام نشد؛ تلاش دوباره از همان کلید Idempotency استفاده می‌کند.");
    }finally{if(stamp===generation.current)setBusy(false);}
  }

  async function read(){
    if(!allowedVerify||busy||!recordId.trim())return;
    const stamp=++generation.current;
    setBusy(true);setError("");setReceipt(undefined);
    try{
      const res=await cms<FrozenReceipt>("/publication/plans/"+
        encodeURIComponent(recordId.trim())+"/");
      if(stamp!==generation.current)return;
      if(res.data.dossier_id!==dossierId||
          res.data.dossier_digest!==dossierDigest||
          res.data.publication_available||
          res.data.public_projection!==null)throw Error("MANIFEST_BINDING_MISMATCH");
      setReceipt(res.data);
    }catch(e){
      if(stamp===generation.current)setError(e instanceof CmsError?e.message:
        "رسید فقط برای ایجادکنندهٔ دارای دسترسی معتبر قابل خواندن است.");
    }finally{if(stamp===generation.current)setBusy(false);}
  }

  if(!allowed&&!allowedVerify)return null;
  return <section className="card stack" aria-label="مانیفست ثابت بررسی پیش از انتشار">
    <h4>W16-02: مانیفست ثابت بررسی، بدون انتشار</h4>
    <p className="muted">Dry-run فقط نوع تغییر، نام فیلدها و مسیرهای واقعاً موجود در سایت را می‌سنجد.
      هیچ محتوای خصوصی، پاسخ آزمون یا حقوق انتشار از این مرحله به عمومی منتقل نمی‌شود.</p>
    {allowed&&<button type="button" className="button secondary"
      disabled={!valid||busy} onClick={()=>void examine()}>
      {busy?"در حال بررسی…":"ساخت Dry-run با نسخهٔ فعلی پرونده"}
    </button>}
    {!valid&&<p className="muted">ابتدا «تطبیق پروندهٔ ثابت با وضعیت زنده» را انجام بدهید؛
      دادهٔ قبلی اجازهٔ ساخت مانیفست ندارد.</p>}
    {dry&&<>
      <p role="status">تعداد اقدامات بررسی‌شده: {dry.item_count.toLocaleString("fa-IR")}؛
        موارد نیازمند بازبینی مستقل: {dry.review_blocker_count.toLocaleString("fa-IR")}</p>
      <p>شناسهٔ اثرانگشت: <code dir="ltr" style={{overflowWrap:"anywhere"}}>
        {dry.manifest_digest}</code></p>
      <ul>{dry.actions.map(item=><li key={item.kind+":"+item.resource_id}>
        {item.kind}: {item.action==="create"?"ایجاد":item.action==="update"?"اصلاح":"فعال‌سازی احتمالی"}
        ؛ فیلدهای تغییر: {item.changed_public_fields.join("، ")||"نامشخص"}
        ؛ والدهای عمومی موجود: {item.current_public_anchor.visible_count.toLocaleString("fa-IR")}
        /{item.current_public_anchor.root_count.toLocaleString("fa-IR")}
      </li>)}</ul>
      {!receipt&&allowed&&<button type="button" className="button secondary"
        disabled={!valid||busy} onClick={()=>void freeze()}>
        ثبت Immutable Frozen Review Manifest
      </button>}
    </>}
    {allowedVerify&&<div className="stack">
      <label>شناسهٔ مانیفست قبلی
        <input value={recordId} autoComplete="off" spellCheck={false} dir="ltr"
          onChange={event=>setRecordId(event.target.value)} placeholder="UUID"/>
      </label>
      <button type="button" className="button secondary"
        disabled={busy||!recordId.trim()} onClick={()=>void read()}>
        مشاهدهٔ رسید ثابت ثبت‌شده
      </button>
    </div>}
    {receipt&&<div className="stack" role="status">
      <p>مانیفست بررسی منجمد شد. شناسه: <code dir="ltr" style={{overflowWrap:"anywhere"}}>
        {receipt.id}</code>؛ این رسید تأیید علمی/حقوقی یا اجازهٔ Apply نیست.</p>
      <a className="button secondary"
        href={"/admin-console/publication-attestations?plan_id="+encodeURIComponent(receipt.id)+
          "&domain="+encodeURIComponent(domain)}>
        بازکردن فرم مستقل ثبت سوابق بازبین
      </a>
      <p className="muted">برای تصمیم مستقل، بازبین دیگری با مجوز منبع، علمی یا حقوق و شناسهٔ مانیفست لازم است.</p>
    </div>}
    {error&&<p role="alert">{error}</p>}
  </section>;
}
