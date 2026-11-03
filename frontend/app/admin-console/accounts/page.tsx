"use client";
import {useEffect,useState,type FormEvent} from "react";
import {CmsError,type CmsPage} from "@/lib/cms";
import {CmsState} from "@/components/cms/CmsShell";
import {usePrivateCms} from "@/components/cms/CmsJobsShared";
import AccountAccess from "@/components/cms/AccountAccess";
import RoleGroups from "@/components/cms/RoleGroups";

type Account={id:number;username:string;is_active:boolean;is_staff:boolean;
  effective_permissions?:string[]};
const message=(e:unknown)=>e instanceof CmsError?e.message:"دادهٔ حساب دریافت نشد.";
export default function AccountsDirectory(){
  const {can,request,current,leave}=usePrivateCms();const allowed=can("cms_user_view");
  const [term,setTerm]=useState("");const [query,setQuery]=useState("");
  const [page,setPage]=useState(1);const [rows,setRows]=useState<CmsPage<Account>>();
  const [detail,setDetail]=useState<Account>();
  const [loading,setLoading]=useState(true);const [busy,setBusy]=useState(false);
  const [error,setError]=useState("");
  useEffect(()=>{
    if(!allowed)return;
    let valid=true;
    const params=new URLSearchParams({q:query,page:String(page),page_size:"30"});
    void request<CmsPage<Account>>("/users/?"+params.toString())
      .then(r=>{if(valid&&current()){setRows(r.data);setLoading(false);setError("");}})
      .catch(e=>{if(valid&&current()){setError(message(e));setLoading(false);}});
    return ()=>{valid=false;};
  },[allowed,page,query,request,current]);
  const search=(event:FormEvent<HTMLFormElement>)=>{
    event.preventDefault();leave(()=>{setDetail(undefined);setPage(1);setLoading(true);setQuery(term.trim());});
  };
  const open=async(id:number)=>{
    setBusy(true);setError("");setDetail(undefined);
    try{
      const res=await request<Account>("/users/"+id+"/");
      if(current())setDetail(res.data);
    }catch(e){if(current())setError(message(e));}
    finally{if(current())setBusy(false);}
  };
  const refreshDetail=async()=>{
    if(!detail)return;
    const response=await request<Account>("/users/"+detail.id+"/");
    if(current()){setDetail(response.data);setRows(old=>old?{...old,results:old.results.map(row=>row.id===response.data.id?response.data:row)}:old);}
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
            onClick={()=>leave(()=>void open(user.id))}>جزئیات مجاز</button>
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
      <AccountAccess key={detail.id} userId={detail.id} onChanged={refreshDetail}/>
      <p className="muted">خواندن یا انتقال دادهٔ خصوصی به مجوز و هدف مستقل نیاز دارد. تصمیم retention و حذف باید جداگانه تأیید شود.</p>
    </section>}
    {!detail&&<RoleGroups/>}
  </div>;
}
