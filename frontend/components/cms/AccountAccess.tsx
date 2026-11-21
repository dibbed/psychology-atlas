"use client";
import {useEffect,useRef,useState,type FormEvent} from "react";
import {type CmsPage,cmsDate} from "@/lib/cms";
import {mutationBlocked,versionHeaders} from "@/lib/cmsJobs";
import {CmsState} from "./CmsShell";
import {PrivateMutationError,usePrivateCms} from "./CmsJobsShared";

type Access={id:number;username:string;is_active:boolean;is_staff:boolean;is_superuser:boolean;
  groups:number[];permissions:string[];direct_permissions:string[]};
type Session={id:string;created_at:string;last_seen:string;expires_at:string;revoked_at:string|null};
type Group={id:number;name:string;permissions:string[]};
type ProofAction="user"|"revoke_session"|"revoke_account"|"regenerate_recovery"|"revoke_mfa";
type Intent={action:ProofAction;target:number|string;payload:Record<string,unknown>;path:string;etag:string};

export default function AccountAccess({userId,onChanged}:{userId:number;onChanged?:()=>Promise<void>}){
  const {me,can,request,current,setDirty}=usePrivateCms();
  const [access,setAccess]=useState<Access>(),[tag,setTag]=useState<string|null>(null);
  const [grants,setGrants]=useState<string[]>([]),[selected,setSelected]=useState<string[]>([]);
  const [permissionTerm,setPermissionTerm]=useState(""),[groups,setGroups]=useState<CmsPage<Group>>(),[groupPage,setGroupPage]=useState(1);
  const [selectedGroups,setSelectedGroups]=useState<number[]>([]);
  const [flags,setFlags]=useState({is_active:true,is_staff:false,is_superuser:false});
  const [sessions,setSessions]=useState<CmsPage<Session>>(),[sessionTag,setSessionTag]=useState<string|null>(null);
  const [error,setError]=useState<unknown>(),[busy,setBusy]=useState(false),[reload,setReload]=useState(0);
  const [intent,setIntent]=useState<Intent>(),[method,setMethod]=useState("totp"),[token,setToken]=useState("");
  const lock=useRef(false),blocked=mutationBlocked(error);
  const ownSessionRevoke=intent?.action==="revoke_session"&&userId===me.user.id;
  const canEdit=can("cms_roles_view")&&can("cms_roles_edit");
  const changed=!!access&&(JSON.stringify([...selected].sort())!==JSON.stringify([...access.direct_permissions].sort())||
    JSON.stringify([...selectedGroups].sort())!==JSON.stringify([...access.groups].sort())||
    Object.entries(flags).some(([key,value])=>value!==access[key as keyof typeof flags]));
  useEffect(()=>{setDirty(busy||changed||!!intent);return()=>setDirty(false);},[busy,changed,intent,setDirty]);
  useEffect(()=>{
    let active=true;const abort=new AbortController();setAccess(undefined);setSessions(undefined);setError(undefined);setIntent(undefined);setToken("");
    if(can("cms_roles_view"))void request<Access>(`/roles/users/${userId}/`,{signal:abort.signal})
      .then(result=>{if(active&&current()){
        setAccess(result.data);setTag(result.etag);setSelected(result.data.direct_permissions);setSelectedGroups(result.data.groups);
        setFlags({is_active:result.data.is_active,is_staff:result.data.is_staff,is_superuser:result.data.is_superuser});
      }}).catch(failure=>{if(active&&current())setError(failure);});
    if(canEdit)void request<{permissions:string[]}>("/roles/permissions/",{signal:abort.signal})
      .then(result=>{if(active&&current())setGrants(result.data.permissions);})
      .catch(failure=>{if(active&&current())setError(failure);});
    if(me.user.id===userId)void request<CmsPage<Session>>(`/sessions/?user_id=${userId}&page=1&page_size=100`,{signal:abort.signal})
      .then(result=>{if(active&&current()){setSessions(result.data);setSessionTag(result.etag);}})
      .catch(failure=>{if(active&&current())setError(failure);});
    return()=>{active=false;abort.abort();};
  },[userId,reload,can,canEdit,request,current,me.user.id]);
  useEffect(()=>{
    if(!canEdit)return;let active=true;const abort=new AbortController();setGroups(undefined);
    void request<CmsPage<Group>>(`/roles/groups/?page=${groupPage}&page_size=20`,{signal:abort.signal})
      .then(result=>{if(active&&current())setGroups(result.data);})
      .catch(failure=>{if(active&&current())setError(failure);});
    return()=>{active=false;abort.abort();};
  },[userId,reload,groupPage,canEdit,request,current]);
  async function readSessions(){
    if(lock.current)return;lock.current=true;setBusy(true);setError(undefined);
    try{const result=await request<CmsPage<Session>>(`/sessions/?user_id=${userId}&page=1&page_size=100`);
      if(current()){setSessions(result.data);setSessionTag(result.etag);}}
    catch(failure){if(current())setError(failure);}finally{lock.current=false;if(current())setBusy(false);}
  }
  function prepareUser(){
    if(!access||!tag||!changed||!canEdit||blocked)return;
    const payload:Record<string,unknown>={};
    if(JSON.stringify([...selected].sort())!==JSON.stringify([...access.direct_permissions].sort()))payload.permissions=selected;
    if(JSON.stringify([...selectedGroups].sort())!==JSON.stringify([...access.groups].sort()))payload.groups=selectedGroups;
    for(const [key,value] of Object.entries(flags))if(value!==access[key as keyof typeof flags])payload[key]=value;
    setIntent({action:"user",target:userId,path:`/roles/users/${userId}/`,payload,etag:tag});
  }
  async function commit(event:FormEvent<HTMLFormElement>){
    event.preventDefault();if(!intent||(!ownSessionRevoke&&!token.trim())||lock.current||blocked)return;
    lock.current=true;setBusy(true);setError(undefined);
    try{
      if(!ownSessionRevoke)await request("/auth/step-up/",{method:"POST",body:JSON.stringify({action:intent.action,target_id:intent.target,
        payload:intent.payload,method,token:token.trim()})});
      if(!current())return;setToken("");
      if(intent.action==="regenerate_recovery"){
        setIntent(undefined);setDirty(false);window.location.assign("/account/two_factor/backup/tokens/");return;
      }
      await request(intent.path,{method:"POST",headers:versionHeaders(intent.etag),body:JSON.stringify(intent.payload)});
      if(intent.action==="revoke_mfa"||(ownSessionRevoke&&intent.target===me.session.id)||
          (intent.action==="revoke_account"&&userId===me.user.id)){window.dispatchEvent(new Event("cms-session-expired"));return;}
      if(current()){setIntent(undefined);setReload(value=>value+1);await onChanged?.();setSessions(undefined);}
    }catch(failure){if(current())setError(failure);}
    finally{lock.current=false;if(current())setBusy(false);}
  }
  return <section className="card stack" aria-label="کنترل دسترسی و نشست حساب">
    <h3>کنترل دسترسی و نشست حساب</h3>
    <PrivateMutationError error={error} busy={busy} reload={()=>{setError(undefined);setReload(value=>value+1);setSessionTag(null);}}/>
    {can("cms_roles_view")&&(!access&&!error?<CmsState loading/>:access&&<>
      <p>نسخهٔ سیاست: <bdi>{tag}</bdi>. مجوز مستقیم با دسترسی ارث‌برده از گروه‌ها متفاوت است؛ ذخیره، مجوز گروه را به مجوز مستقیم تبدیل نمی‌کند.</p>
      <p>گروه‌های موجود: <bdi>{access.groups.join(", ")||"—"}</bdi></p>
      {canEdit&&<fieldset className="cms-fieldset stack" disabled={busy||blocked||!!intent}>
        <legend>مجوزهای مستقیم قابل واگذاری</legend>
        <details><summary>فهرست مجوزهای مستقیم</summary>
        <label>جست‌وجوی مجوز مستقیم<input type="search" maxLength={100} value={permissionTerm} onChange={event=>setPermissionTerm(event.target.value)}/></label>
        <p>مجوزهای مستقیم انتخاب‌شده: {selected.length}. فیلتر فقط نمایش را تغییر می‌دهد.</p>
        {grants.filter(cap=>cap.includes(permissionTerm.trim())).map(cap=><label key={cap}><input type="checkbox" checked={selected.includes(cap)} onChange={event=>
          setSelected(old=>event.target.checked?[...old,cap]:old.filter(value=>value!==cap))}/><bdi>{cap}</bdi></label>)}
        </details>
        <h4>عضویت گروه‌های قابل واگذاری</h4>
        <p>گروه‌های خارج از سقف واگذاری در این فرم پنهان و بدون تغییر حفظ می‌شوند.</p>
        {!groups?<CmsState loading/>:groups.results.map(group=><label key={group.id}><input type="checkbox" checked={selectedGroups.includes(group.id)} onChange={event=>
          setSelectedGroups(old=>event.target.checked?[...old,group.id]:old.filter(value=>value!==group.id))}/><bdi>{group.name}</bdi></label>)}
        {groups&&groups.count>20&&<div className="cms-actions"><button className="button secondary" type="button" disabled={groupPage<=1} onClick={()=>setGroupPage(value=>value-1)}>گروه‌های قبل</button>
          <span>صفحهٔ گروه {groupPage}</span><button className="button secondary" type="button" disabled={groupPage*20>=groups.count} onClick={()=>setGroupPage(value=>value+1)}>گروه‌های بعد</button></div>}
        {can("cms_roles_grant_owner")&&<><h4>وضعیت حساس حساب</h4>
          <label><input type="checkbox" checked={flags.is_active} onChange={event=>setFlags(old=>({...old,is_active:event.target.checked}))}/>حساب فعال است</label>
          <label><input type="checkbox" checked={flags.is_staff} onChange={event=>setFlags(old=>({...old,is_staff:event.target.checked}))}/>دسترسی پرسنل دارد</label>
          <label><input type="checkbox" checked={flags.is_superuser} onChange={event=>setFlags(old=>({...old,is_superuser:event.target.checked}))}/>ابرکاربر است</label>
        </>}
        <button className="button primary" type="button" disabled={!changed||!tag} onClick={prepareUser}>بررسی تغییر دسترسی حساب</button>
      </fieldset>}
    </>)}
    {(can("cms_user_revoke_sessions")||me.user.id===userId)&&<>
      <button type="button" className="button secondary" disabled={busy||changed||!!intent||blocked} onClick={()=>void readSessions()}>بازخوانی نشست‌های حساب</button>
      {sessions&&<><p>نشست‌های ثبت‌شده: {sessions.count}؛ این صفحه حداکثر ۱۰۰ نشست تازه را نشان می‌دهد. لغو همه، تمام نشست‌ها و اعتبار توکن‌های قدیمی را می‌بندد.</p>
        <ul>{sessions.results.map(session=><li key={session.id}>
          <bdi>{session.id}</bdi><p>ایجاد: {cmsDate(session.created_at)}؛ آخرین حضور: {cmsDate(session.last_seen)}؛ انقضا: {cmsDate(session.expires_at)}</p>
          {session.revoked_at?<p>باطل شده</p>:<button className="button secondary" type="button" disabled={busy||changed||!!intent||blocked||!sessionTag}
            onClick={()=>setIntent({action:"revoke_session",target:session.id,path:`/sessions/${session.id}/revoke/`,payload:{},etag:sessionTag!})}>بررسی لغو این نشست</button>}
        </li>)}</ul>
        {can("cms_user_revoke_sessions")&&<button className="button secondary" type="button" disabled={busy||changed||!!intent||blocked||!sessionTag}
          onClick={()=>setIntent({action:"revoke_account",target:userId,path:`/users/${userId}/revoke-sessions/`,payload:{},etag:sessionTag!})}>بررسی لغو همهٔ نشست‌ها و توکن‌ها</button>}
      </>}
    </>}
    {me.user.id===userId&&<div className="stack"><h4>امنیت و بازیابی حساب خودم</h4>
      <p>کدهای تازه جای کدهای قبلی را می‌گیرند و فقط یک بار در صفحهٔ امن بستهٔ MFA نمایش داده می‌شوند. لغو MFA همهٔ دستگاه‌ها و نشست‌های خودتان را می‌بندد و تنظیم دوباره لازم دارد.</p>
      <button className="button secondary" type="button" disabled={busy||changed||!!intent||blocked} onClick={()=>
        setIntent({action:"regenerate_recovery",target:userId,path:"",payload:{},etag:""})}>بررسی ساخت کدهای بازیابی خودم</button>
      <button className="button secondary" type="button" disabled={busy||changed||!!intent||blocked||!(tag||sessionTag)} onClick={()=>
        setIntent({action:"revoke_mfa",target:userId,path:"/auth/mfa/revoke/",payload:{},etag:(tag||sessionTag)!})}>بررسی لغو MFA خودم</button>
    </div>}
    {intent&&<form className="cms-conflict stack" onSubmit={commit}><h4>{ownSessionRevoke?"تأیید لغو نشست خودم":"تأیید حساس با MFA تازه"}</h4>
      <p>{intent.action==="user"?"مجوزها یا وضعیت همین حساب تغییر می‌کند. سرور سقف واگذاری و باقی‌ماندن آخرین مالک را بررسی می‌کند.":intent.action==="regenerate_recovery"?
        "پس از تأیید، به صفحهٔ امن کدهای بازیابی می‌روید؛ ساخت مجموعهٔ تازه در همان صفحه جداگانه تأیید می‌شود.":intent.action==="revoke_mfa"?
        "دستگاه‌های MFA خودتان حذف و نشست‌ها باطل می‌شوند. پیش از تأیید، مسیر ورود و تنظیم مجدد را بررسی کنید.":"نشست انتخاب‌شده یا تمام نشست‌های این حساب بسته می‌شود؛ اگر متعلق به شما باشد، ورود دوباره لازم است."}</p>
      <fieldset disabled={busy||blocked} className="cms-fieldset stack">
        {!ownSessionRevoke&&<><label>روش تأیید تغییر حساب<select value={method} onChange={event=>setMethod(event.target.value)}><option value="totp">TOTP</option><option value="recovery">کد بازیابی یک‌بارمصرف</option></select></label>
          <label>کد MFA تغییر حساب<input type="password" value={token} autoComplete="one-time-code" maxLength={32} onChange={event=>setToken(event.target.value)}/></label></>}
        <button className="button primary" type="submit" disabled={!ownSessionRevoke&&!token.trim()}>اعمال تغییر تأییدشدهٔ حساب</button>
        <button className="button secondary" type="button" onClick={()=>{setIntent(undefined);setToken("");}}>انصراف از تغییر حساب</button>
      </fieldset>
    </form>}
    <p className="muted">بازیابی آفلاین مالک به اثبات هویت و عملیات مجاز محیط نیاز دارد. این بخش گذرواژه، رمز MFA یا نشست کاربر دیگری را نمایش نمی‌دهد.</p>
  </section>;
}
