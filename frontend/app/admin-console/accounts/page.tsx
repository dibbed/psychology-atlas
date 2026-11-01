"use client";
import {useEffect,useState,type FormEvent} from "react";
import {cms,CmsError,type CmsPage} from "@/lib/cms";
import {CmsState,useCms} from "@/components/cms/CmsShell";

type Account={id:number;username:string;is_active:boolean;is_staff:boolean;
  effective_permissions?:string[]};
type SessionSummary={id:string;created_at:string;last_seen:string;expires_at:string;revoked_at:string|null};
const message=(e:unknown)=>e instanceof CmsError?e.message:"دادهٔ حساب دریافت نشد.";
export default function AccountsDirectory(){
  const {can}=useCms();const allowed=can("cms_user_view");
  const [term,setTerm]=useState("");const [query,setQuery]=useState("");
  const [page,setPage]=useState(1);const [rows,setRows]=useState<CmsPage<Account>>();
  const [detail,setDetail]=useState<Account>();
  const [sessions,setSessions]=useState<CmsPage<SessionSummary>>();
  const [sessionsError,setSessionsError]=useState("");
  const [loading,setLoading]=useState(true);const [busy,setBusy]=useState(false);
  const [error,setError]=useState("");
  useEffect(()=>{
    if(!allowed)return;
    let valid=true;
    const params=new URLSearchParams({q:query,page:String(page),page_size:"30"});
    void cms<CmsPage<Account>>("/users/?"+params.toString())
      .then(r=>{if(valid){setRows(r.data);setLoading(false);setError("");}})
      .catch(e=>{if(valid){setError(message(e));setLoading(false);}});
    return ()=>{valid=false;};
  },[allowed,page,query]);
  const search=(event:FormEvent<HTMLFormElement>)=>{
    event.preventDefault();setDetail(undefined);setPage(1);setLoading(true);
    setQuery(term.trim());
  };
  const open=async(id:number)=>{
    setBusy(true);setError("");setDetail(undefined);setSessions(undefined);setSessionsError("");
    try{
      const res=await cms<Account>("/users/"+id+"/");
      setDetail(res.data);
    }catch(e){setError(message(e));}
    finally{setBusy(false);}
  };
  const showSessions=async(userId:number)=>{
    setSessions(undefined);setSessionsError("");setBusy(true);
    try{const response=await cms<CmsPage<SessionSummary>>("/sessions/?user_id="+userId+"&page=1&page_size=30");
      setSessions(response.data);}
    catch(e){setSessionsError(message(e));}
    finally{setBusy(false);}
  };
  if(!allowed)return <CmsState empty="برای دسترسی به فهرست کاربران به مجوز cms_user_view نیاز است."/>;
  return <div className="stack" dir="rtl">
    <a className="cms-link" href="/admin-console">بازگشت به خانهٔ مدیریت</a>
    <div className="cms-title">
      <p className="eyebrow">P14 | Accounts</p><h1>فهرست امن حساب‌ها</h1>
      <p className="muted">این صفحه فقط هویت عمومی مدیریت (شناسه و نام کاربری)، فعال‌بودن و سطح دسترسی مجاز را نمایش می‌دهد؛ ایمیل، یادداشت‌ها، نتایج آزمون، رمزها و توکن‌های کاربران خوانده نمی‌شوند.</p>
    </div>
    {error&&<p role="alert">{error}</p>}
    <section className="card stack">
      <h2>جست‌وجوی حساب</h2>
      <form className="cms-filters" onSubmit={search}>
        <label>نام کاربری یا شناسه
          <input type="search" value={term} maxLength={200}
            onChange={e=>setTerm(e.target.value)}/>
        </label>
        <button type="submit" className="button secondary">جست‌وجو</button>
      </form>
      {loading?<CmsState loading/>:rows?.count===0?
        <CmsState empty="حسابی مطابق جست‌وجو پیدا نشد."/>:
        <ul className="stack">{rows?.results.map(user=><li key={user.id}>
          <strong><bdi>{user.username}</bdi></strong>
          <span> شناسه {user.id} | {user.is_active?"فعال":"غیرفعال"} | {user.is_staff?"پرسنل":"کاربر معمولی"}</span>
          <button type="button" className="button secondary" disabled={busy}
            onClick={()=>void open(user.id)}>جزئیات مجاز</button>
        </li>)}</ul>}
      {rows&&rows.count>rows.page_size&&<div className="cms-filters">
        <button className="button secondary" type="button" disabled={page<=1||loading}
          onClick={()=>{setPage(page-1);setLoading(true);}}>قبل</button>
        <span>صفحهٔ {page} از {Math.ceil(rows.count/rows.page_size)}</span>
        <button className="button secondary" type="button" disabled={page*rows.page_size>=rows.count||loading}
          onClick={()=>{setPage(page+1);setLoading(true);}}>بعد</button>
      </div>}
    </section>
    {detail&&<section className="card stack" aria-labelledby="account-detail-title">
      <h2 id="account-detail-title">جزئیات حساب <bdi>{detail.username}</bdi></h2>
      <p>شناسه {detail.id} | {detail.is_active?"فعال":"غیرفعال"} |
        {detail.is_staff?"پرسنل":"کاربر معمولی"}</p>
      {can("cms_roles_view")&&detail.effective_permissions&&<>
        <h3>دسترسی‌های مؤثر، فقط برای نقش مجاز</h3>
        {detail.effective_permissions.length===0?
          <p>هیچ مجوز CMS فعالی ندارد.</p>:
          <ul dir="ltr">{detail.effective_permissions.map(cap=>
            <li key={cap}><code>{cap}</code></li>)}</ul>}
      </>}
      {can("cms_user_revoke_sessions")&&<div className="stack">
        <h3>نمای محدود نشست‌های مدیریت</h3>
        <button type="button" className="button secondary" disabled={busy}
          onClick={()=>void showSessions(detail.id)}>نمایش نشست‌های مجاز</button>
        {sessionsError&&<p role="alert">{sessionsError}</p>}
        {sessions&&<ul>{sessions.results.map(item=><li key={item.id}>
          ساخته‌شده: <time dateTime={item.created_at}>{item.created_at}</time> |
          انقضا: <time dateTime={item.expires_at}>{item.expires_at}</time> |
          {item.revoked_at?" باطل‌شده":" ثبت‌شده"}
        </li>)}</ul>}
      </div>}
      <p className="muted">تغییر وضعیت، بازیابی حساب یا خواندن دادهٔ خصوصی از این بخش مجاز نیست. عملیات حساس باید از گردش‌کار دارای MFA، علت و audit انجام شوند.</p>
    </section>}
  </div>;
}
