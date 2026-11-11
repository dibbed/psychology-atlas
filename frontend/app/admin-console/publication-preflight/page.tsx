"use client";
import {useEffect,useRef,useState} from "react";
import {cms,CmsError,type CmsPage} from "@/lib/cms";
import {CmsState,useCms} from "@/components/cms/CmsShell";

type Domain="cases"|"learning"|"brain"|"assessment";
type Entry={kind:string;resource_id:string|number;case_id?:number;version?:number;
  revision_digest?:string;content_digest?:string;proposal_digest?:string;revision_status?:string;
  dependency_ids?:Record<string,number[]>;content_issues?:string[];
  fingerprint_version?:string;eligible:boolean;blockers:string[]};
type Inventory=CmsPage<Entry>&{domain:Domain;publication_available:boolean;scope:string};
type SelectionReceipt={id:string;domain:Domain;selection_digest:string;status:string;
  item_count:number;publication_available:false;approved:false;recovered:boolean};
type SelectionPayload={domain:Domain;entries:{kind:string;resource_id:string|number;expected_digest:string}[];request_key:string};
type VerificationItem={kind:string;resource_id:string|number;
  snapshot_state:"matching"|"stale"|"unavailable"|"unverifiable";content_issues:string[];
  dependency_state:"matching"|"stale"|"baseline_missing"|"invalid"|"content_only";dependency_issues:string[];
  editorial_review?:{status:"blocked"|"editorial_tasks_current"|"unverifiable";blockers:string[]};
  source_rights_evidence?:{scope:"source_metadata_public_display_only";
    status:"recorded"|"insufficient"|"not_established"|"no_sources"|"unverifiable";
    source_count:number;permitted_count:number;unverified_count:number;
    publication_rights_cleared:false}};
type RecheckSummary={item_count:number;
  snapshot_counts:Record<VerificationItem["snapshot_state"],number>;
  dependency_counts:Record<VerificationItem["dependency_state"],number>;
  editorial_review_counts:Record<NonNullable<VerificationItem["editorial_review"]>["status"],number>;
  source_rights_counts:Record<NonNullable<VerificationItem["source_rights_evidence"]>["status"],number>;
  content_issue_items:number;dependency_issue_items:number;
  denominator:"review_selection_items_not_unique_sources_or_publications";
  publication_readiness_proven:false};
type VerificationResult={id:string;domain:Domain;status:string;selection_digest:string;
  item_count:number;items:VerificationItem[];policy_matches:boolean;all_snapshots_current:boolean;
  recheck_summary:RecheckSummary;
  review_blockers:string[];verified_at:string;publication_available:false;approved:false};
const snapshotStates:Record<VerificationItem["snapshot_state"],string>={
  matching:"اثر انگشت نسخهٔ ثبت‌شده مطابق است",
  stale:"محتوا یا وابستگی از زمان انتخاب تغییر کرده است",
  unavailable:"این پیش‌نویس دیگر در محدودهٔ انتخاب مجاز نیست",
  unverifiable:"بررسی ایمن این مورد کامل نشد",
};
const dependencyStates:Record<VerificationItem["dependency_state"],string>={
  matching:"وضعیت زندهٔ وابستگی‌ها، منابع و سوابق حقوق با زمان انتخاب مطابق است.",
  stale:"وابستگی، منبع، سابقهٔ حقوق یا سیاست بازبینی از زمان انتخاب تغییر کرده است.",
  baseline_missing:"این بستهٔ قدیمی تصویر زندهٔ مبنا ندارد. انتخاب تازه لازم است.",
  invalid:"وابستگی فعلی برای ادامهٔ انتشار به اصلاح و بازبینی نیاز دارد.",
  content_only:"وابستگی‌های محتوایی Learning در اثر انگشت محتوا سنجیده شدند. بررسی منبع و حقوق مستقل لازم است.",
};
const sourceRightsStatus:Record<NonNullable<VerificationItem["source_rights_evidence"]>["status"],string>={
  recorded:"مجوز ثبت‌شده و معتبر برای فرادادهٔ منابع مشاهده شد؛ این مجوز شامل متن یا کل پیشنهاد نیست.",
  insufficient:"حداقل یک سابقهٔ حقوقی منبع ناقص، منقضی، متعارض یا تأییدنشده است.",
  not_established:"برای نمایش عمومی فرادادهٔ منابع، مجوز مستقل و تصویب‌شده ثبت نشده است.",
  no_sources:"هیچ منبع قابل‌بررسی برای این پیشنهاد ثبت نشده است.",
  unverifiable:"بررسی تمام منابع در محدودهٔ ایمن کامل نشد؛ هیچ مجوزی قابل استنتاج نیست.",
};
const reasons:Record<string,string>={
  SCIENTIFIC_REVIEW_NOT_LINKED:"تأیید علمی متصل به نسخهٔ فعلی ثبت نشده است.",
  SOURCE_RIGHTS_REVIEW_NOT_LINKED:"مجوز و منبع معتبرِ وابسته به نسخه تأیید نشده است.",
  P16_MANIFEST_AND_RECEIPT_REQUIRED:"Manifest و receipt نسخه‌مند مرکز انتشار هنوز وجود ندارد.",
  CASE_GRAPH_VALIDATION_REQUIRED:"ساختار و مسیرهای گراف باید مستقل اعتبارسنجی شوند.",
  CASE_GRAPH_INVALID:"گراف شاخه‌ای این نسخه خطای ساختاری دارد.",
  SOURCE_REVIEW_REQUIRED:"بازبینی دقیق منبع همین نسخه ثبت نشده است.",
  SCIENTIFIC_REVIEW_REQUIRED:"تأیید علمی همین نسخه ثبت نشده است.",
  RIGHTS_REVIEW_REQUIRED:"تأیید حقوق استفادهٔ عمومی همین نسخه ثبت نشده است.",
  POLICY_CHANGED:"سیاست تأیید تغییر کرده و بازبینی دوباره لازم است.",
  SOURCE_DEPENDENCY_CHANGED:"منبع مستند پس از بازبینی تغییر کرده است.",
  SOURCE_UNAVAILABLE:"منبع معتبر یا در دسترس نیست.",
  SEED_MANAGED_REVISION:"نسخهٔ مدیریت‌شده توسط Seed، بدون تصمیم مهاجرت امن قابل انتشار نیست.",
  REQUIRED_CASE_METADATA_MISSING:"مشخصات ضروری کیس ناقص است.",
  CONTENT_VALIDATION_REQUIRED:"ساختار محتوای پیش‌نویس، کلید پاسخ یا وابستگی‌ها ایراد دارند.",
  QUIZ_ANSWER_KEY_INVALID:"کلید پاسخ صحیحِ پرسش معتبر نیست.",
  ANSWER_KEY_INVALID:"کلید پاسخ فعلی معتبر نیست.",
  CHOICES_INSUFFICIENT:"تعداد انتخاب‌های فعال کافی نیست.",
  INACTIVE_DEPENDENCY:"حداقل یک مفهوم یا اختلال وابسته غیرفعال است.",
  DEPENDENCY_MISSING:"حداقل یک وابستگی محتوایی یافت نشد.",
  TARGET_REQUIRED:"محتوا به مفهوم یا اختلال معتبر متصل نشده است.",
  QUESTION_INVALID:"یک پرسش، متن یا انتخاب‌های معتبر ندارد.",
  NO_ACTIVE_QUESTIONS:"هیچ پرسش فعالی ثبت نشده است.",
  TITLE_MISSING:"عنوان لازم ثبت نشده است.",
  CONTENT_MISSING:"متن اصلی لازم ناقص است.",
  TARGET_INVALID:"مفهوم هدف با نوع تمرین سازگار نیست.",
  DIFFICULTY_INVALID:"درجه دشواری نامعتبر است.",
  SOURCE_DEPENDENCIES_NOT_REVALIDATED:"وابستگی‌های منبع و حقوقِ پیشنهاد هنوز با نسخهٔ جاری تطبیق داده نشده‌اند.",
  SOURCE_SCIENCE_RIGHTS_UNVERIFIED:"منابع، تأیید علمی و حقوق استفادهٔ عمومی هنوز مستقل بررسی نشده‌اند.",
  FROZEN_MANIFEST_AND_APPROVAL_REQUIRED:"مانیفست منجمد و تصویب مستقل برای انتشار وجود ندارد.",
  LIVE_SOURCE_RIGHTS_REVALIDATION_REQUIRED:"تأیید مستقل منبع و حقوق استفادهٔ عمومی لازم است.",
  LIVE_DEPENDENCY_BASELINE_REQUIRED:"برای سنجش تغییرات زندهٔ منابع و وابستگی‌ها، بستهٔ تازه‌ای انتخاب کنید.",
  CANONICAL_BASE_CHANGED:"رکورد اصلی نسبت به مبنای پیشنهاد تغییر کرده است.",
  SOURCE_UNRESOLVED:"هویت کتاب‌شناختی منبع هنوز معتبر و تأییدشده نیست.",
  DEPENDENCY_UNAVAILABLE:"رکورد یا وابستگی فعلی در محدودهٔ مجاز در دسترس نیست.",
  DEPENDENCY_UNVERIFIABLE:"بررسی وابستگی‌ها به محدودیت ایمن رسید. بازبینی و محدودکردن بسته لازم است.",
  SELECTION_RECHECK_REQUIRED:"بسته با وضعیت فعلی محتوا یا سیاست هماهنگ نیست.",
  REVIEW_REQUIRED:"فرایند بازبینی علمی و منبع برای پیشنهاد ثبت نشده است.",
  APPROVAL_REQUIRED:"تصمیم‌های معتبر و کامل بازبینی پیشنهاد ثبت نشده‌اند.",
  DECISION_REQUIRED:"صرف علامت تأیید وظیفه کافی نیست؛ تصمیم نسخه‌مند و ثبت‌شده لازم است.",
  REVIEW_NOT_CURRENT:"پیشنهاد فعلی در وضعیت معتبر بازبینی قرار ندارد.",
  PAYLOAD_CHANGED:"محتوای پیشنهاد نسبت به مبنای بازبینی تغییر کرده است.",
  DEPENDENCY_CHANGED:"وابستگی‌های بازبینی پیشنهاد تغییر کرده‌اند.",
  REVIEWER_PERMISSION_CHANGED:"مجوز بازبین قبلی دیگر معتبر نیست.",
  REVIEWER_UNAVAILABLE:"بازبین ثبت‌شده دیگر معتبر یا در دسترس نیست.",
  CANONICAL_RECONCILIATION_REQUIRED:"مبنای محتوای اصلی نیازمند تطبیق مجدد است.",
  EDITORIAL_REVIEW_UNVERIFIABLE:"بررسی اعتبار تصمیم‌های پیشین کامل نشد.",
  EDITORIAL_CANDIDATE_UNAVAILABLE:"این پیشنهاد برای بازبینی معتبر در دسترس نیست.",
  CANONICAL_UNAVAILABLE:"مبنای اصلی پیشنهاد در دسترس نیست.",
};
export default function PublicationPreflight(){
  const {can}=useCms();
  const canCases=can("cms_publication_validate_cases")&&can("cms_cases_view");
  const canLearning=can("cms_publication_validate_learning")&&can("cms_learning_view");
  const canBrain=can("cms_publication_validate_brain")&&can("cms_brain_view");
  const canAssessment=can("cms_publication_validate_assessment")&&can("cms_assessment_view");
  const [domain,setDomain]=useState<Domain>("cases");
  const activeDomain=(domain==="cases"&&canCases)||(domain==="learning"&&canLearning)||
    (domain==="brain"&&canBrain)||(domain==="assessment"&&canAssessment)
    ?domain:(canCases?"cases":canLearning?"learning":canBrain?"brain":"assessment");
  const [page,setPage]=useState(1);
  const [data,setData]=useState<Inventory>();
  const [error,setError]=useState("");
  const [loading,setLoading]=useState(true);
  const [chosen,setChosen]=useState<Record<string,Entry>>({});
  const [selection,setSelection]=useState<SelectionReceipt>();
  const [selectionError,setSelectionError]=useState("");
  const [saving,setSaving]=useState(false);
  const [verification,setVerification]=useState<VerificationResult>();
  const [verifying,setVerifying]=useState(false);
  const [verifyError,setVerifyError]=useState("");
  const retryRef=useRef<SelectionPayload|undefined>(undefined);
  const generation=useRef(0);
  const canSelect=activeDomain!=="cases"&&can("cms_publication_select_"+activeDomain);
  useEffect(()=>()=>{generation.current++;},[activeDomain,canSelect]);
  const entryKey=(item:Entry)=>item.kind+":"+item.resource_id;
  const toggle=(item:Entry,checked:boolean)=>{
    generation.current++;
    setChosen(previous=>{
      const updated={...previous};
      if(checked&&Object.keys(updated).length<20)updated[entryKey(item)]=item;
      if(!checked)delete updated[entryKey(item)];
      return updated;
    });
    retryRef.current=undefined;setSelection(undefined);setSelectionError("");
    setVerification(undefined);setVerifyError("");
  };
  async function createSelection(){
    if(saving||selection||!canSelect)return;
    const items=Object.values(chosen);
    if(items.length===0||items.length>20)return;
    if(!retryRef.current){
      retryRef.current={
        domain:activeDomain,request_key:crypto.randomUUID(),
        entries:items.map(item=>({
          kind:item.kind,resource_id:item.resource_id,
          expected_digest:(item.content_digest||item.proposal_digest)!,
        })),
      };
    }
    const stamp=generation.current;
    setSaving(true);setSelectionError("");
    try{
      const result=await cms<SelectionReceipt>("/publication/selections/",{
        method:"POST",body:JSON.stringify(retryRef.current),
      });
      if(stamp!==generation.current)return;
      setSelection(result.data);setVerification(undefined);setVerifyError("");retryRef.current=undefined;
    }catch(e){
      if(stamp!==generation.current)return;
      setSelectionError(e instanceof CmsError?e.message:"بستهٔ بازبینی ثبت نشد؛ با همان شناسه می‌توانید دوباره تلاش کنید.");
    }finally{if(stamp===generation.current)setSaving(false);}
  }
  async function verifyCurrentSelection(){
    if(!selection||verifying||!canSelect)return;
    const stamp=generation.current;
    setVerifying(true);setVerifyError("");setVerification(undefined);
    try{
      const result=await cms<VerificationResult>(
        "/publication/selections/"+encodeURIComponent(selection.id)+"/verify/");
      if(stamp!==generation.current)return;
      setVerification(result.data);
    }catch(e){
      if(stamp!==generation.current)return;
      setVerifyError(e instanceof CmsError?e.message:"اعتبارسنجی نسخه‌ها انجام نشد. نتیجهٔ قبلی معتبر تلقی نمی‌شود.");
    }finally{if(stamp===generation.current)setVerifying(false);}
  }
  useEffect(()=>{
    if(!canCases&&!canLearning&&!canBrain&&!canAssessment)return;
    let active=true;setLoading(true);setError("");
    const query=new URLSearchParams({domain:activeDomain,page:String(page),page_size:"30"});
    void cms<Inventory>("/publication/preflight/?"+query.toString())
      .then(r=>{if(active){setData(r.data);setLoading(false);}})
      .catch(e=>{if(active){setData(undefined);
        setError(e instanceof CmsError?e.message:"فهرست بررسی مقدماتی قابل خواندن نیست.");setLoading(false);}});
    return ()=>{active=false;};
  },[canCases,canLearning,canBrain,canAssessment,activeDomain,page]);
  if(!canCases&&!canLearning&&!canBrain&&!canAssessment)return <CmsState empty="بررسی مقدماتی انتشار به مجوز اختصاصی همان دامنه نیاز دارد."/>;
  const clearSelection=()=>{
    generation.current++;
    setChosen({});setSelection(undefined);setSelectionError("");
    setVerification(undefined);setVerifyError("");setSaving(false);setVerifying(false);
    retryRef.current=undefined;
  };
  const change=(value:Domain)=>{setDomain(value);setPage(1);setData(undefined);clearSelection();};
  return <div className="stack" dir="rtl">
    <a className="cms-link" href="/admin-console">بازگشت به خانهٔ مدیریت</a>
    <div className="cms-title">
      <p className="eyebrow">P16 | Publication Preflight</p>
      <h1>صف انتشار، فقط بررسی مقدماتی</h1>
      <p className="muted">این صفحه فقط پیش‌نویس‌ها و پیشنهادهای نسخه‌مند را بازرسی می‌کند. وضعیت یا اثرانگشت، مجوز انتشار مستقیم نیست؛ هر انتشار به تأیید علمی و حقوقی واقعی، مانیفست معتبر و MFA مستقل نیاز دارد. Brain، Assessment و Learning در این صفحه امکان Apply ندارند.</p>
    </div>
    <label>حوزهٔ مجاز<select value={activeDomain} onChange={e=>change(e.target.value as Domain)}>
      {canCases&&<option value="cases">کیس‌های آموزشی</option>}
      {canLearning&&<option value="learning">محتوای یادگیری</option>}
      {canBrain&&<option value="brain">پیشنهادهای اطلس مغز</option>}
      {canAssessment&&<option value="assessment">فرادهٔ ابزارهای سنجش</option>}
    </select></label>
    {error&&<p role="alert">{error}</p>}
    {loading&&<CmsState loading/>}
    {!loading&&data&&<>
      <p><strong>{data.count.toLocaleString("fa-IR")} پیش‌نویس یا پیشنهادِ در حال بررسی</strong></p>
      {canSelect&&<section className="card stack" aria-label="ثبت بستهٔ بازبینی">
        <h2>انتخاب برای بازبینی علمی و حقوقی</h2>
        <p className="muted">حداکثر ۲۰ مورد از همین صفحه را انتخاب کنید. ثبت این بسته، تأیید علمی، تأیید حقوق، Freeze یا انتشار نیست. تغییر نسخه پس از انتخاب، بستهٔ قدیمی را خودکار معتبر نمی‌کند.</p>
        <p role="status">موارد انتخاب‌شده: {Object.keys(chosen).length.toLocaleString("fa-IR")}</p>
        <button className="button secondary" type="button" disabled={saving||!!selection||Object.keys(chosen).length===0}
          onClick={()=>void createSelection()}>{saving?"در حال ثبت…":"ثبت بستهٔ بازبینی بدون انتشار"}</button>
        {selectionError&&<p role="alert">{selectionError}</p>}
        {selection&&<div role="status" className="stack">
          <p>بستهٔ بازبینی ثبت شد؛ هیچ محتوایی منتشر نشده است. {selection.recovered?"پاسخ درخواست قبلی بازیابی شد.":""}</p>
          <p>تعداد موارد: {selection.item_count.toLocaleString("fa-IR")}</p>
          <p>شناسهٔ بسته: <code dir="ltr" style={{overflowWrap:"anywhere"}}>{selection.id}</code></p>
          <p>اثر انگشت: <code dir="ltr" style={{overflowWrap:"anywhere"}}>{selection.selection_digest}</code></p>
          <button className="button secondary" type="button" disabled={verifying}
            onClick={()=>void verifyCurrentSelection()}>
            {verifying?"در حال بررسی نسخه‌ها…":"بررسی وضعیت فعلی بسته"}
          </button>
          {verifyError&&<p role="alert">{verifyError}</p>}
          {verification&&<div className="stack" role="region" aria-label="اعتبارسنجی مجدد بسته">
            <p role="status">{verification.all_snapshots_current?
              "اثر انگشت نسخه‌ها و سیاست مطابق‌اند؛ هنوز هیچ تأیید انتشار وجود ندارد.":
              "بسته به بازبینی مجدد نیاز دارد؛ محتوا یا سیاست تغییر کرده است."}</p>
            <p>وضعیت سیاست دسترسی: {verification.policy_matches?"بدون تغییر":"تغییر کرده"}</p>
            <section className="card stack" aria-label="خلاصهٔ شمارش مجدد بسته">
              <h3>خلاصهٔ شمارش مجدد بستهٔ بازبینی</h3>
              <p>مخرج تمام شمارش‌های زیر، {verification.recheck_summary.item_count.toLocaleString("fa-IR")} موردِ انتخاب‌شده است؛ نه تعداد منابع یکتا و نه انتشارهای مجاز.</p>
              <p>نسخهٔ مطابق: {verification.recheck_summary.snapshot_counts.matching.toLocaleString("fa-IR")}؛
                تغییرکرده: {verification.recheck_summary.snapshot_counts.stale.toLocaleString("fa-IR")}؛
                ناموجود: {verification.recheck_summary.snapshot_counts.unavailable.toLocaleString("fa-IR")}؛
                بررسی‌ناپذیر: {verification.recheck_summary.snapshot_counts.unverifiable.toLocaleString("fa-IR")}</p>
              <p>دارای ایراد محتوا: {verification.recheck_summary.content_issue_items.toLocaleString("fa-IR")}؛
                دارای ایراد وابستگی: {verification.recheck_summary.dependency_issue_items.toLocaleString("fa-IR")}</p>
              {verification.domain!=="learning"&&<>
                <p>بازبینی موجود و معتبر پیشنهاد: {verification.recheck_summary.editorial_review_counts.editorial_tasks_current.toLocaleString("fa-IR")}؛
                  مسدود: {verification.recheck_summary.editorial_review_counts.blocked.toLocaleString("fa-IR")}؛
                  نامشخص: {verification.recheck_summary.editorial_review_counts.unverifiable.toLocaleString("fa-IR")}</p>
                <p>حقوق فرادادهٔ منابع، صرفاً در سطح مورد انتخابی:
                  ثبت‌شده: {verification.recheck_summary.source_rights_counts.recorded.toLocaleString("fa-IR")}؛
                  ناکافی: {verification.recheck_summary.source_rights_counts.insufficient.toLocaleString("fa-IR")}؛
                  بدون مجوز احرازشده: {verification.recheck_summary.source_rights_counts.not_established.toLocaleString("fa-IR")}؛
                  بدون منبع: {verification.recheck_summary.source_rights_counts.no_sources.toLocaleString("fa-IR")}؛
                  بررسی‌ناپذیر: {verification.recheck_summary.source_rights_counts.unverifiable.toLocaleString("fa-IR")}</p>
              </>}
              <p className="muted">هیچ‌یک از این شمارش‌ها و مطابقت نسخه‌ها تأیید انتشار، حقوق محتوا یا مجوز Apply نیستند.</p>
            </section>
            <ul>{verification.items.map(item=><li key={item.kind+":"+item.resource_id}>
              <strong style={{overflowWrap:"anywhere"}}>{item.kind} #{item.resource_id}</strong>
              <p>{snapshotStates[item.snapshot_state]}</p>
              <p>{dependencyStates[item.dependency_state]}</p>
              {item.content_issues.length>0&&<ul>{item.content_issues.map(code=>
                <li key={code}>{reasons[code]??code}</li>)}</ul>}
              {item.dependency_issues.length>0&&<ul>{item.dependency_issues.map(code=>
                <li key={code}>{reasons[code]??code}</li>)}</ul>}
              {item.source_rights_evidence&&<div className="stack" aria-label="شواهد حقوق فراداده منابع">
                <strong>شواهد حقوق نمایش عمومی فرادادهٔ منابع</strong>
                <p>{sourceRightsStatus[item.source_rights_evidence.status]}</p>
                <p>منابع بررسی‌شده: {item.source_rights_evidence.source_count.toLocaleString("fa-IR")}؛
                  محدودهٔ مجازِ ثبت‌شده: {item.source_rights_evidence.permitted_count.toLocaleString("fa-IR")}؛
                  بدون مجوزِ احرازشده: {item.source_rights_evidence.unverified_count.toLocaleString("fa-IR")}</p>
                <p className="muted">این بررسی فقط فرادادهٔ منابع را پوشش می‌دهد، نه حق انتشار پیشنهاد، متن، تصویر، آیتم یا پرسشنامه. تأیید حقوقی مستقل همچنان لازم است.</p>
              </div>}
              {item.editorial_review&&<div className="stack" aria-label="وضعیت بازبینی علمی موجود">
                <strong>بازبینی علمی و منبع ثبت‌شده در CMS، مستقل از مجوز انتشار:</strong>
                <p>{item.editorial_review.status==="editorial_tasks_current"?
                  "تصمیم‌های پیشین برای همین پیشنهاد معتبرند؛ تأیید حقوق و مجوز انتشار همچنان مستقل است.":
                  item.editorial_review.status==="unverifiable"?
                  "اعتبار بازبینی پیشین قابل احراز نیست.":
                  "بازبینی پیشنهاد ناقص یا نامعتبر است."}</p>
                {item.editorial_review.blockers.length>0&&<ul>{item.editorial_review.blockers.map(code=>
                  <li key={code}>{reasons[code]??code}</li>)}</ul>}
              </div>}
            </li>)}</ul>
            <p>موانع مستقل انتشار همچنان برقرارند:</p>
            <ul>{verification.review_blockers.map(code=><li key={code}>{reasons[code]??code}</li>)}</ul>
          </div>}
        </div>}
      </section>}
      {data.results.length===0?<p>در این حوزه پیش‌نویس واجد شرایط بازرسی وجود ندارد.</p>:
      <ul className="stack">{data.results.map(row=><li className="card stack" key={row.kind+"-"+row.resource_id}>
        <strong style={{overflowWrap:"anywhere"}}>{row.kind} #{row.resource_id}</strong>
        {canSelect&&(row.content_digest||row.proposal_digest)&&<label>
          <input type="checkbox" checked={!!chosen[entryKey(row)]} disabled={saving||!!selection||
            (!chosen[entryKey(row)]&&Object.keys(chosen).length>=20)}
            onChange={e=>toggle(row,e.target.checked)}/>
          انتخاب برای بستهٔ بازبینی: {row.kind} #{row.resource_id}
        </label>}
        {row.case_id&&<span>کیس #{row.case_id}، نسخهٔ {row.version}</span>}
        {row.revision_status&&<p>وضعیت پیشنهاد: {row.revision_status}، نسخهٔ {row.version}</p>}
        {(row.revision_digest||row.content_digest)&&<p>اثر انگشت محتوای همین لحظه؛ صرفاً برای تطبیق و نه مجوز انتشار:
          <code dir="ltr" style={{display:"block",overflowWrap:"anywhere"}}>{row.revision_digest||row.content_digest}</code>
        </p>}
        {row.proposal_digest&&<p>اثر انگشت نسخهٔ ثبت‌شدهٔ پیشنهاد (وابستگی‌های جاری هنوز بررسی مجدد نشده‌اند):
          <code dir="ltr" style={{display:"block",overflowWrap:"anywhere"}}>{row.proposal_digest}</code>
        </p>}
        {row.content_issues&&<div className="stack">
          <p>{row.content_issues.length?"ایرادهای ساختاری تشخیص‌داده‌شده:":"ساختار اولیه این پیش‌نویس بررسی شد؛ بازبینی علمی و حقوقی همچنان الزامی است."}</p>
          {row.content_issues.length>0&&<ul>{row.content_issues.map(issue=><li key={issue}>{reasons[issue]??issue}</li>)}</ul>}
          {row.dependency_ids&&Object.keys(row.dependency_ids).length>0&&<p className="muted">وابستگی‌های بررسی‌شده: {Object.entries(row.dependency_ids).map(([kind,ids])=>kind+" ("+ids.join("، ")+")").join("، ")}</p>}
        </div>}
        <span>{row.eligible?"تأییدهای نسخه آماده‌اند، انتشار هنوز انجام نشده":"پیش‌نیازهای انتشار ناقص است"}</span>
        <ul>{row.blockers.map(key=><li key={key}>{reasons[key]??key}</li>)}</ul>
      </li>)}</ul>}
      {data.count>data.page_size&&<div className="cms-filters">
        <button className="button secondary" type="button" disabled={page<=1}
          onClick={()=>{setPage(page-1);clearSelection();}}>قبلی</button>
        <span>صفحهٔ {page} از {Math.ceil(data.count/data.page_size)}</span>
        <button className="button secondary" type="button" disabled={page*data.page_size>=data.count}
          onClick={()=>{setPage(page+1);clearSelection();}}>بعدی</button>
      </div>}
      {activeDomain==="cases"&&<a className="cms-link" href="/admin-console/content/cases">ورود به Case Builder برای بررسی، Freeze، تأیید و انتشار کنترل‌شده</a>}
      <p className="muted">ناشرهای تاریخی Brain و Assessment در این بخش دست‌نخورده‌اند. پیشنهادهای این صفحه انتشار تلقی نمی‌شوند و Apply چنددامنه‌ای هنوز فراهم نیست.</p>
    </>}
  </div>;
}
