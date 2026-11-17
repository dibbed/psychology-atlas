"use client";
import {useEffect,useRef,useState} from "react";
import {cms,CmsError,type CmsPage} from "@/lib/cms";
import {CmsState,useCms} from "@/components/cms/CmsShell";
import FrozenManifestPanel from "@/components/cms/FrozenManifestPanel";

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
type PreparationReceipt={
  id:string;selection_id:string;selection_digest:string;dossier_digest:string;
  domain:Domain;item_count:number;status:"preparation_only";recovered:boolean;
  approved:false;publication_available:false;notice:string;
};
type PreparationCheck=PreparationReceipt&{
  snapshot_current:boolean;checked_at:string;published:false;
  recheck_summary:RecheckSummary;review_blockers:string[];
};
type PreparationPayload={selection_digest:string;request_key:string};
type CandidatePreview={
  schema:"cms-private-candidate-projection-v1";scope:"authorized_private_candidate_only";
  domain:Domain;selection_id:string;selection_digest:string;dossier_id:string;dossier_digest:string;
  snapshot_current:true;published:false;approved:false;publication_available:false;
  items:Array<{kind:string;resource_id:string|number;revision_id:number|null;
    version:number|null;fingerprint:string;display:Record<string,string>;
    visibility:"authorized_private_draft_only"}>;
  public_projection:{available:false;payload:null;reason:string};
  impact_preview:{schema:"cms-private-public-surface-impact-v1";dossier_digest:string;
    public_effect:false;scope:string;notice:string;
    items:Array<{kind:string;resource_id:string|number;revision_id:number|null;
      readers:Record<"detail"|"search"|"graph"|"compare",string|null>;
      current_public_anchor:{
        schema:"cms-current-public-root-v1";
        status:"learning_candidate_inactive"|"indirect_root_unmapped"|"root_not_created"|
          "root_unresolved"|"visible_public_root"|"hidden_public_root"|"mixed_public_roots";
        root_type:"brain_anatomical_entity"|"assessment_instrument"|null;
        root_count:number;visible_count:number;
        candidate_public:false;post_apply_projection_available:false;
        selector?:string;scope?:string
      };
      public_reader_contract:{
        scope:"existing_public_urls_no_post_apply_promise";
        surfaces:Record<"list"|"detail"|"search"|"graph"|"compare",{
          status:"existing_reader"|"not_implemented_for_kind";
          route:string|null
        }>;
        public_candidate_payload_available:false;
      };
      mapping_complete:false;after_apply:string;
      change_intent:"create"|"update"|"potential_activation";
      before_public_visibility:boolean|null;
      change_footprint:{changed_public_fields:string[];
        unmapped_or_private_changed_count:number;
        surface_field_names:Record<"detail"|"search"|"graph"|"compare",string[]>}}>};
};
type PreparationInbox={count:number;page:number;page_size:number;domain:Domain;
  results:PreparationReceipt[];publication_available:false;approved:false};
type PreparationBulkCheck={scope:string;domain:Domain;checked_count:number;
  current_count:number;stale_count:number;approved:false;publication_available:false;
  results:Array<{id:string;selection_id:string;dossier_digest:string;
    snapshot_current:boolean;content_issue_items:number;
    dependency_issue_items:number;review_blocker_count:number}>};
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
  DEPENDENCY_PUBLIC_UNAVAILABLE:"نمایش عمومی یک وابستگی محتوایی محدود است.",
  CONTENT_PUBLIC_UNAVAILABLE:"نمایش عمومی این محتوای آموزشی محدود است.",
  TARGET_REQUIRED:"محتوا به مفهوم یا اختلال معتبر متصل نشده است.",
  QUESTION_INVALID:"یک پرسش، متن یا انتخاب‌های معتبر ندارد.",
  CHOICE_TEXT_MISSING:"متن یک گزینهٔ فعال خالی است.",
  NO_ACTIVE_QUESTIONS:"هیچ پرسش فعالی ثبت نشده است.",
  TITLE_MISSING:"عنوان لازم ثبت نشده است.",
  CONTENT_MISSING:"متن اصلی لازم ناقص است.",
  TARGET_INVALID:"مفهوم هدف با نوع تمرین سازگار نیست.",
  CHOICE_CONCEPT_INVALID:"یکی از مفهوم‌های گزینه‌های فعال، غیرفعال یا از نوع خطای شناختی نیست؛ یا گزینه تکراری است.",
  REVIEW_RIGHTS_BASELINE_MISSING:"در این بستهٔ قدیمی مبنای داوری و حقوق منابع ثبت نشده است. انتخاب تازه لازم است.",
  EDITORIAL_REVIEW_DRIFT:"وضعیت یا اعتبار بازبینی علمی پس از انتخاب تغییر کرده است.",
  SOURCE_RIGHTS_DRIFT:"شواهد حقوق فرادادهٔ منابع پس از انتخاب تغییر کرده است.",
  SOURCE_RIGHTS_UNVERIFIABLE:"بررسی حقوق همهٔ منابع با محدودیت ایمن کامل نشد.",
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
  const [preparation,setPreparation]=useState<PreparationReceipt>();
  const [preparing,setPreparing]=useState(false);
  const [preparationError,setPreparationError]=useState("");
  const [preparationCheck,setPreparationCheck]=useState<PreparationCheck>();
  const [checkingPreparation,setCheckingPreparation]=useState(false);
  const [preparationCheckError,setPreparationCheckError]=useState("");
  const [candidatePreview,setCandidatePreview]=useState<CandidatePreview>();
  const [candidatePreviewError,setCandidatePreviewError]=useState("");
  const [candidatePreviewLoading,setCandidatePreviewLoading]=useState(false);
  const [previousDossierId,setPreviousDossierId]=useState("");
  const [loadingPrevious,setLoadingPrevious]=useState(false);
  const [previousError,setPreviousError]=useState("");
  const [inbox,setInbox]=useState<PreparationInbox>();
  const [inboxError,setInboxError]=useState("");
  const [inboxVersion,setInboxVersion]=useState(0);
  const [selectedDossierIds,setSelectedDossierIds]=useState<string[]>([]);
  const [bulkCheck,setBulkCheck]=useState<PreparationBulkCheck>();
  const [bulkBusy,setBulkBusy]=useState(false);
  const [bulkError,setBulkError]=useState("");
  const preparationRetryRef=useRef<PreparationPayload|undefined>(undefined);
  const retryRef=useRef<SelectionPayload|undefined>(undefined);
  const generation=useRef(0);
  const canSelect=activeDomain!=="cases"&&can("cms_publication_select_"+activeDomain);
  const canPreview=canSelect&&can("cms_"+activeDomain+"_preview");
  useEffect(()=>()=>{generation.current++;},[activeDomain,canSelect]);
  useEffect(()=>{
    if(!canPreview){
      generation.current++;
      setCandidatePreview(undefined);setCandidatePreviewError("");
    }
  },[canPreview]);
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
    setPreparation(undefined);setPreparationError("");setPreparing(false);
    setPreparationCheck(undefined);setPreparationCheckError("");setCheckingPreparation(false);
    setCandidatePreview(undefined);setCandidatePreviewError("");setCandidatePreviewLoading(false);
    preparationRetryRef.current=undefined;
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
      setPreparation(undefined);setPreparationCheck(undefined);preparationRetryRef.current=undefined;
    }catch(e){
      if(stamp!==generation.current)return;
      setSelectionError(e instanceof CmsError?e.message:"بستهٔ بازبینی ثبت نشد؛ با همان شناسه می‌توانید دوباره تلاش کنید.");
    }finally{if(stamp===generation.current)setSaving(false);}
  }
  async function verifyCurrentSelection(){
    if(!selection||verifying||!canSelect)return;
    const stamp=generation.current;
    setVerifying(true);setVerifyError("");setVerification(undefined);setPreparationCheck(undefined);
    setCandidatePreview(undefined);setCandidatePreviewError("");
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
  async function createPreparation(){
    if(!selection||!verification||preparing||preparation||!canSelect)return;
    if(!verification.all_snapshots_current||
      verification.recheck_summary.content_issue_items>0||
      verification.recheck_summary.dependency_issue_items>0)return;
    if(!preparationRetryRef.current){
      preparationRetryRef.current={
        selection_digest:selection.selection_digest,request_key:crypto.randomUUID(),
      };
    }
    const stamp=generation.current;
    setPreparing(true);setPreparationError("");
    try{
      const result=await cms<PreparationReceipt>(
        "/publication/selections/"+encodeURIComponent(selection.id)+"/prepare/",{
        method:"POST",body:JSON.stringify(preparationRetryRef.current),
      });
      if(stamp!==generation.current)return;
      setPreparation(result.data);setPreparationCheck(undefined);
      setCandidatePreview(undefined);setCandidatePreviewError("");
      setPreparationCheckError("");preparationRetryRef.current=undefined;
      setInboxVersion(v=>v+1);setBulkCheck(undefined);
    }catch(e){
      if(stamp!==generation.current)return;
      setPreparationError(e instanceof CmsError?e.message:
        "پروندهٔ آماده‌سازی ثبت نشد. می‌توانید با همان شناسهٔ درخواست دوباره تلاش کنید.");
    }finally{if(stamp===generation.current)setPreparing(false);}
  }
  async function verifyPreparation(){
    if(!preparation||checkingPreparation||!canSelect)return;
    const stamp=generation.current;
    setCheckingPreparation(true);setPreparationCheckError("");setPreparationCheck(undefined);
    setCandidatePreview(undefined);setCandidatePreviewError("");
    try{
      const result=await cms<PreparationCheck>(
        "/publication/preparations/"+encodeURIComponent(preparation.id)+"/verify/");
      if(stamp!==generation.current)return;
      setPreparationCheck(result.data);
    }catch(e){
      if(stamp!==generation.current)return;
      setPreparationCheckError(e instanceof CmsError?e.message:
        "پروندهٔ ثابت با وضعیت زنده تطبیق داده نشد. اعتبار آن تأیید نشده است.");
    }finally{if(stamp===generation.current)setCheckingPreparation(false);}
  }
  async function previewExactCandidate(){
    if(!preparation||candidatePreviewLoading||!canPreview)return;
    const stamp=generation.current;
    setCandidatePreviewLoading(true);setCandidatePreview(undefined);setCandidatePreviewError("");
    try{
      const res=await cms<CandidatePreview>(
        "/publication/preparations/"+encodeURIComponent(preparation.id)+"/candidate-preview/");
      if(stamp!==generation.current)return;
      if(res.data.dossier_digest!==preparation.dossier_digest||
          res.data.selection_digest!==preparation.selection_digest||
          res.data.domain!==activeDomain)throw new Error("PREVIEW_BINDING_MISMATCH");
      setCandidatePreview(res.data);
    }catch(e){
      if(stamp!==generation.current)return;
      setCandidatePreviewError(e instanceof CmsError?e.message:
        "پیش‌نمایش معتبر نیست یا نسخه تغییر کرده است. پرونده را دوباره بررسی کنید.");
    }finally{if(stamp===generation.current)setCandidatePreviewLoading(false);}
  }
  async function loadPreviousPreparation(identifier?:string){
    const id=(identifier??previousDossierId).trim();
    if(!canSelect||loadingPrevious||!id)return;
    const stamp=generation.current;
    let applied=false;
    setLoadingPrevious(true);setPreviousError("");
    try{
      const saved=await cms<PreparationReceipt>(
        "/publication/preparations/"+encodeURIComponent(id)+"/");
      if(stamp!==generation.current)return;
      if(saved.data.domain!==activeDomain)throw new Error("DOMAIN_MISMATCH");
      const [selected,rechecked]=await Promise.all([
        cms<SelectionReceipt>("/publication/selections/"+encodeURIComponent(saved.data.selection_id)+"/"),
        cms<VerificationResult>("/publication/selections/"+encodeURIComponent(saved.data.selection_id)+"/verify/"),
      ]);
      if(stamp!==generation.current)return;
      if(selected.data.id!==saved.data.selection_id||
          selected.data.selection_digest!==saved.data.selection_digest||
          selected.data.domain!==activeDomain||
          rechecked.data.selection_digest!==saved.data.selection_digest||
          rechecked.data.domain!==activeDomain)throw new Error("DOSSIER_BINDING_MISMATCH");
      generation.current++;
      applied=true;
      setChosen({});setSelection(selected.data);setVerification(rechecked.data);
      setPreparation(saved.data);setPreparationError("");setPreparationCheck(undefined);
      setCandidatePreview(undefined);setCandidatePreviewError("");
      setPreparationCheckError("");setSelectionError("");setVerifyError("");
      preparationRetryRef.current=undefined;retryRef.current=undefined;
    }catch(e){
      if(stamp!==generation.current)return;
      setPreviousError(e instanceof CmsError?e.message:
        "پرونده در دامنهٔ انتخابی یا با مجوز فعلی قابل بازیابی نیست.");
    }finally{if(applied||stamp===generation.current)setLoadingPrevious(false);}
  }
  async function checkRecentPreparations(ids?:string[]){
    if(!canSelect||bulkBusy)return;
    const stamp=generation.current;
    setBulkBusy(true);setBulkError("");setBulkCheck(undefined);
    try{
      const result=await cms<PreparationBulkCheck>(
        "/publication/preparations/recheck/?"+
        new URLSearchParams(ids?.length?
          {domain:activeDomain,ids:ids.join(",")}:
          {domain:activeDomain,limit:"3"}).toString());
      if(stamp===generation.current)setBulkCheck(result.data);
    }catch(e){
      if(stamp===generation.current)setBulkError(e instanceof CmsError?e.message:
        "بررسی دسته‌ای پرونده‌ها تکمیل نشد. نتیجهٔ قبلی قابل‌اتکا نیست.");
    }finally{if(stamp===generation.current)setBulkBusy(false);}
  }
  useEffect(()=>{
    if(!canSelect){setInbox(undefined);return;}
    let active=true;setInbox(undefined);setInboxError("");
    const query=new URLSearchParams({domain:activeDomain,page:"1",page_size:"10"});
    void cms<PreparationInbox>("/publication/preparations/?"+query.toString())
      .then(r=>{if(active)setInbox(r.data);})
      .catch(e=>{if(active)setInboxError(e instanceof CmsError?e.message:"فهرست پرونده‌های پیشین در دسترس نیست.");});
    return ()=>{active=false;};
  },[canSelect,activeDomain,inboxVersion]);
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
    setPreparation(undefined);setPreparationError("");setPreparing(false);
    setPreparationCheck(undefined);setPreparationCheckError("");setCheckingPreparation(false);
    setCandidatePreview(undefined);setCandidatePreviewError("");setCandidatePreviewLoading(false);
    setPreviousDossierId("");setPreviousError("");setLoadingPrevious(false);
    setBulkCheck(undefined);setBulkError("");setBulkBusy(false);
    setSelectedDossierIds([]);
    preparationRetryRef.current=retryRef.current=undefined;
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
        <div className="card stack" aria-label="بازیابی پروندهٔ آماده‌سازی قبلی">
          <h3>بازکردن پروندهٔ آماده‌سازی قبلی</h3>
          <p className="muted">شناسهٔ پروندهٔ ثابت را وارد کنید تا رسید ذخیره‌شده و وضعیت زندهٔ همان بسته با مجوز فعلی خوانده شوند. هیچ پرونده یا تأیید تازه‌ای ساخته نمی‌شود.</p>
          <section className="stack" aria-label="پرونده‌های آماده‌سازی اخیر">
            <p>پرونده‌های ثبت‌شدهٔ خودتان در این حوزه: {inbox?inbox.count.toLocaleString("fa-IR"):"در حال خواندن…"}</p>
            {inboxError&&<p role="alert">{inboxError}</p>}
            {inbox&&inbox.count===0&&<p className="muted">هنوز پروندهٔ آماده‌سازی ثبت نشده است.</p>}
            {inbox&&inbox.results.length>0&&<ul className="stack">{inbox.results.map(item=>
              <li key={item.id}>
                <button type="button" className="button secondary" disabled={loadingPrevious}
                  onClick={()=>void loadPreviousPreparation(item.id)}>
                  بازکردن پرونده {item.id.slice(0,8)}، {item.item_count.toLocaleString("fa-IR")} مورد
                </button>
                <label>
                  <input type="checkbox"
                    checked={selectedDossierIds.includes(item.id)}
                    disabled={bulkBusy||(!selectedDossierIds.includes(item.id)&&selectedDossierIds.length>=5)}
                    onChange={e=>{
                      setSelectedDossierIds(prev=>e.target.checked?[...prev,item.id]:prev.filter(id=>id!==item.id));
                      setBulkCheck(undefined);setBulkError("");
                    }}/>
                  انتخاب برای تطبیق دسته‌ای پرونده {item.id.slice(0,8)}
                </label>
              </li>)}</ul>}
            {inbox&&inbox.count>inbox.page_size&&<p className="muted">ده پروندهٔ اخیر نمایش داده شده‌اند. برای موارد قدیمی‌تر از UUID استفاده کنید.</p>}
            <button type="button" className="button secondary" disabled={bulkBusy||!inbox||inbox.count===0}
              onClick={()=>void checkRecentPreparations()}>
              {bulkBusy?"در حال تطبیق دسته‌ای…":"بررسی دسته‌ای سه پروندهٔ اخیر"}
            </button>
            <button type="button" className="button secondary"
              disabled={bulkBusy||selectedDossierIds.length===0}
              onClick={()=>void checkRecentPreparations(selectedDossierIds)}>
              {bulkBusy?"در حال تطبیق…":
                "بررسی دقیق "+selectedDossierIds.length.toLocaleString("fa-IR")+" پروندهٔ انتخابی"}
            </button>
            <p className="muted">می‌توانید حداکثر پنج پروندهٔ دلخواه را هم‌زمان بررسی کنید؛ حتی اگر جزو سه پروندهٔ آخر نباشند. این کار صرفاً خواندن شواهد زنده است.</p>
            {bulkError&&<p role="alert">{bulkError}</p>}
            {bulkCheck&&<section className="stack" aria-label="نتیجهٔ بررسی دسته‌ای پرونده‌ها">
              <p role="status">نسخه‌های مطابق: {bulkCheck.current_count.toLocaleString("fa-IR")}؛
                نسخه‌های قدیمی یا نامنطبق: {bulkCheck.stale_count.toLocaleString("fa-IR")}؛
                بررسی‌شده: {bulkCheck.checked_count.toLocaleString("fa-IR")}</p>
              <ul>{bulkCheck.results.map(item=><li key={item.id}>
                <code dir="ltr">{item.id.slice(0,8)}</code>:
                {item.snapshot_current?" نسخه و شواهد مطابق‌اند":" پرونده نیازمند بازبینی تازه است"}
              </li>)}</ul>
              <p className="muted">مطابقت فقط به نسخه‌ها و شواهد این پرونده مربوط است، نه تأیید علمی، حقوق نشر یا مجوز انتشار.</p>
            </section>}
            <p className="muted">این فهرست تاریخی است و تازگی مدارک یا مجوز انتشار را اثبات نمی‌کند.</p>
          </section>
          <label>شناسه پروندهٔ آماده‌سازی قبلی
            <input type="text" value={previousDossierId} disabled={loadingPrevious}
              placeholder="UUID" autoComplete="off" spellCheck={false} dir="ltr"
              onChange={e=>setPreviousDossierId(e.target.value)}/>
          </label>
          <button type="button" className="button secondary" onClick={()=>void loadPreviousPreparation()}
            disabled={loadingPrevious||!previousDossierId.trim()}>
            {loadingPrevious?"در حال بازخوانی…":"بازکردن پروندهٔ ثبت‌شده"}
          </button>
          {previousError&&<p role="alert">{previousError}</p>}
        </div>
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
          {verification&&!preparation&&<section className="card stack" aria-label="بستن پروندهٔ آماده‌سازی ثابت">
            <h3>پروندهٔ ثابت برای تحویل به بازبین‌های مستقل</h3>
            <p className="muted">این پرونده فقط عکسِ ثابتِ نسخه‌ها، وابستگی‌ها و موانع فعلی را نگه می‌دارد. حتی پس از ثبت آن، تأیید علمی و حقوقی، Freeze انتشار و Apply وجود ندارند.</p>
            <button type="button" className="button secondary" onClick={()=>void createPreparation()}
              disabled={preparing||!verification.all_snapshots_current||
                verification.recheck_summary.content_issue_items>0||
                verification.recheck_summary.dependency_issue_items>0}>
              {preparing?"در حال ثبت پرونده…":"ثبت پروندهٔ آماده‌سازی بدون انتشار"}
            </button>
            {(!verification.all_snapshots_current||
              verification.recheck_summary.content_issue_items>0||
              verification.recheck_summary.dependency_issue_items>0)&&
              <p className="muted">پیش از ثبت پرونده، باید نسخه‌ها، وابستگی‌ها و ساختار محتوا معتبر باشند. بستهٔ تازه را بازبینی کنید.</p>}
            {preparationError&&<p role="alert">{preparationError}</p>}
          </section>}
          {preparation&&<section className="card stack" aria-label="رسید پروندهٔ آماده‌سازی ثابت">
            <h3>پروندهٔ آماده‌سازی ثابت ثبت شد</h3>
            <p role="status">این پرونده در دیتابیس به شکل تغییرناپذیر نگهداری می‌شود؛ نه تأیید محتواست و نه اجازهٔ انتشار. {preparation.recovered?"همان پاسخ درخواست قبلی بازیابی شد.":""}</p>
            <p>شناسه: <code dir="ltr" style={{overflowWrap:"anywhere"}}>{preparation.id}</code></p>
            <p>اثر انگشت پرونده: <code dir="ltr" style={{overflowWrap:"anywhere"}}>{preparation.dossier_digest}</code></p>
            <button type="button" className="button secondary" disabled={checkingPreparation}
              onClick={()=>void verifyPreparation()}>
              {checkingPreparation?"در حال تطبیق پرونده…":"تطبیق پروندهٔ ثابت با وضعیت زنده"}
            </button>
            {canPreview&&<button type="button" className="button secondary"
              disabled={candidatePreviewLoading} onClick={()=>void previewExactCandidate()}>
              {candidatePreviewLoading?"در حال تطبیق…":"پیش‌نمایش خصوصی دقیق همین کاندیدا"}
            </button>}
            {candidatePreviewError&&<p role="alert">{candidatePreviewError}</p>}
            {candidatePreviewLoading&&<p role="status">در حال اعتبارسنجی نسخه و دسترسی…</p>}
            {candidatePreview&&<div role="region" className="stack" aria-label="پیش‌نمایش خصوصی کاندیدای منتخب">
              <h4>نمای خصوصی موارد انتخاب‌شده</h4>
              <p role="status">این محتوا تنها در پنل مجاز نمایش داده می‌شود؛ نه تأیید علمی است و نه مجوز انتشار.</p>
              <ul>{candidatePreview.items.map(item=><li key={item.kind+":"+item.resource_id}>
                <strong>{item.kind} #{item.resource_id}</strong>
                <p>{Object.values(item.display).join(" | ")||"فقط شناسهٔ این رکورد قابل نمایش است."}</p>
                <p className="muted">نسخه: {item.version??"ثبت‌نشده"}؛ صرفاً خصوصی</p>
              </li>)}</ul>
              <p className="muted">نمای عمومی به‌دلیل نیاز به تأیید علمی و حقوق نشر و Manifest مستقل مسدود است.</p>
              <h5>نقشهٔ محدود مصرف‌کنندگان عمومی، بدون اعمال تغییر</h5>
              <p className="muted">این فهرست فقط نشان می‌دهد هر نوع رکورد ممکن است کدام بخش عمومی را تحت تأثیر قرار دهد. پیش‌بینی خروجی نهایی، مجوز نشر یا تغییر در سایت نیست.</p>
              <ul>{candidatePreview.impact_preview.items.map(item=><li key={item.kind+":"+item.resource_id}>
                <span>{item.kind} #{item.resource_id}</span>
                <p className="muted">وضعیت مصرف‌کنندگان با مسیرهای واقعی API تطبیق داده شده است. وجود مسیر به معنی انتشار این کاندیدا نیست.</p>
                <ul>{(["list","detail","search","graph","compare"] as const).map(surface=>{
                  const target=item.public_reader_contract.surfaces[surface];
                  const names={list:"فهرست",detail:"جزئیات",search:"جست‌وجو",graph:"گراف",compare:"مقایسه"};
                  return <li key={surface}>{names[surface]}: {target.status==="existing_reader"?
                    <code dir="ltr">{target.route}</code>:
                    <span className="muted">برای این نوع، مسیر عمومی مستقلی وجود ندارد</span>}</li>;
                })}</ul>
                <p className="muted">نوع تغییر مشروط: {item.change_intent==="create"?"ایجاد":item.change_intent==="update"?"ویرایش":"فعال‌سازی احتمالی"}؛ مشاهده‌پذیری عمومی خودِ نسخهٔ انتخابی: خصوصی و منتشرنشده.</p>
                <p className="muted">ریشه‌های عمومی موجود، از همان فیلتر عمومی سایت: {item.current_public_anchor.visible_count.toLocaleString("fa-IR")} از {item.current_public_anchor.root_count.toLocaleString("fa-IR")} قابل مشاهده‌اند؛
                  {item.current_public_anchor.status==="root_unresolved"||item.current_public_anchor.status==="indirect_root_unmapped"?" ریشهٔ این رابطه هنوز قابل استنتاج قطعی نیست.":
                  " این شمارش فقط دربارهٔ والد یا رکورد قبلی است، نه مجوز نشرِ کاندیدای خصوصی."}</p>
                <p className="muted">فیلدهای قابل‌ردیابی و تغییرکرده: {item.change_footprint.changed_public_fields.join("، ")||"بدون نام فیلد عمومی قابل‌اعلام"}؛ تعداد فیلدهای خصوصی یا نامشخص: {item.change_footprint.unmapped_or_private_changed_count.toLocaleString("fa-IR")}</p>
              </li>)}</ul>
            </div>}
            {preparationCheckError&&<p role="alert">{preparationCheckError}</p>}
            {preparationCheck&&<p role="status">{preparationCheck.snapshot_current?
              "نسخه و شواهدِ بررسی‌شده با پروندهٔ ثابت مطابق‌اند. هنوز مجوز انتشار وجود ندارد.":
              "نسخه، سیاست یا شواهد از زمان ثبت پرونده تغییر کرده‌اند. پرونده باید مجدداً آماده شود."}</p>}
            <FrozenManifestPanel key={preparation.id}
              domain={activeDomain} dossierId={preparation.id}
              dossierDigest={preparation.dossier_digest}
              valid={preparationCheck?.snapshot_current===true}/>
            <p className="muted">این رسید مجوز نشر عمومی یا تأیید مستقل انسانی نیست. مانیفست بررسی ثابت نیز مجوز Apply نیست.</p>
          </section>}
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
