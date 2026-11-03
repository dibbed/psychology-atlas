"use client";
import {useEffect,useRef,useState,type FormEvent} from "react";
import {type CmsPage} from "@/lib/cms";
import {mutationBlocked,versionHeaders} from "@/lib/cmsJobs";
import {CmsState} from "./CmsShell";
import {PrivateMutationError,usePrivateCms} from "./CmsJobsShared";

type Group={id:number;name:string;permissions:string[]};
export default function RoleGroups(){
  const {can,request,current,setDirty,leave}=usePrivateCms();
  const [groups,setGroups]=useState<CmsPage<Group>>(),[page,setPage]=useState(1),[reload,setReload]=useState(0);
  const [selected,setSelected]=useState<Group|null>(),[permissions,setPermissions]=useState<string[]>([]),[grants,setGrants]=useState<string[]>([]);
  const [name,setName]=useState(""),[tag,setTag]=useState<string|null>(null),[editorTag,setEditorTag]=useState<string|null>(null),[error,setError]=useState<unknown>();
  const [busy,setBusy]=useState(false),[intent,setIntent]=useState<"save"|"delete">();
  const [method,setMethod]=useState("totp"),[token,setToken]=useState("");
  const [permissionTerm,setPermissionTerm]=useState("");
  const lock=useRef(false),blocked=mutationBlocked(error);
  const editing=selected!==undefined;
  useEffect(()=>{setDirty(busy||editing);return()=>setDirty(false);},[busy,editing,setDirty]);
  useEffect(()=>{
    if(!can("cms_roles_view"))return;let active=true;const abort=new AbortController();setGroups(undefined);setError(undefined);
    void request<CmsPage<Group>>(`/roles/groups/?page=${page}&page_size=20`,{signal:abort.signal})
      .then(result=>{if(active&&current()){setGroups(result.data);setTag(result.etag);}})
      .catch(failure=>{if(active&&current())setError(failure);});
    if(can("cms_roles_edit"))void request<{permissions:string[]}>("/roles/permissions/",{signal:abort.signal})
      .then(result=>{if(active&&current())setGrants(result.data.permissions);})
      .catch(failure=>{if(active&&current())setError(failure);});
    return()=>{active=false;abort.abort();};
  },[can,request,current,page,reload]);
  function open(group:Group|null){leave(()=>{setSelected(group);setEditorTag(tag);setName(group?.name||"");setPermissions(group?.permissions||[]);setToken("");setIntent(undefined);});}
  function changePage(next:number){leave(()=>{setSelected(undefined);setEditorTag(null);setIntent(undefined);setToken("");setPage(next);});}
  async function commit(event:FormEvent<HTMLFormElement>){
    event.preventDefault();if(lock.current||!intent||!editorTag||!token.trim()||blocked||!can("cms_roles_edit"))return;
    const action=intent==="delete"?"delete_group":selected?"group":"create_group";
    const target=selected?.id||0,payload=intent==="delete"?{}:selected?{permissions}:{name:name.trim(),permissions};
    const path=selected?`/roles/groups/${selected.id}/${intent==="delete"?"delete/":""}`:"/roles/groups/";
    lock.current=true;setBusy(true);setError(undefined);
    try{
      await request("/auth/step-up/",{method:"POST",body:JSON.stringify({action,target_id:target,payload,method,token:token.trim()})});
      if(!current())return;setToken("");
      await request(path,{method:"POST",headers:versionHeaders(editorTag),body:JSON.stringify(payload)});
      if(current()){setSelected(undefined);setEditorTag(null);setIntent(undefined);setReload(value=>value+1);}
    }catch(failure){if(current())setError(failure);}
    finally{lock.current=false;if(current())setBusy(false);}
  }
  if(!can("cms_roles_view"))return null;
  return <section className="card stack" aria-label="مدیریت گروه‌های مجاز"><h2>گروه‌های نقش و سقف واگذاری</h2>
    <p>فقط گروه‌هایی نمایش داده می‌شوند که همهٔ مجوزهایشان در سقف واگذاری شما باشد. مجوز ایجادشده، تأیید علمی یا دسترسی به دادهٔ خصوصی بدون هدف ایجاد نمی‌کند.</p>
    <PrivateMutationError error={error} busy={busy} reload={()=>{setSelected(undefined);setIntent(undefined);setReload(value=>value+1);}}/>
    {!groups&&!error?<CmsState loading/>:groups&&<>
      <ul>{groups.results.map(group=><li key={group.id}><bdi>{group.name}</bdi> · #{group.id}{" "}
        <details><summary>مجوزهای گروه</summary><ul dir="ltr">{group.permissions.map(cap=><li key={cap}><code>{cap}</code></li>)}</ul></details>
        {can("cms_roles_edit")&&<button className="button secondary" type="button" disabled={busy||blocked} onClick={()=>open(group)}>ویرایش گروه</button>}
      </li>)}</ul>
      {groups.count>20&&<div className="cms-actions"><button className="button secondary" disabled={busy||page<=1} onClick={()=>changePage(page-1)}>قبل</button>
        <span>صفحهٔ {page}</span><button className="button secondary" disabled={busy||page*20>=groups.count} onClick={()=>changePage(page+1)}>بعد</button></div>}
    </>}
    {can("cms_roles_edit")&&<button className="button secondary" type="button" disabled={busy||blocked||!tag} onClick={()=>open(null)}>ساخت گروه نقش تازه</button>}
    {editing&&<div className="stack">
      <fieldset className="cms-fieldset stack" disabled={busy||blocked||!!intent}><legend>{selected?"ویرایش مجوز گروه":"گروه تازه"}</legend>
        {selected?<p>نام گروه: <bdi>{selected.name}</bdi></p>:<label>نام گروه تازه<input maxLength={150} value={name} onChange={event=>setName(event.target.value)}/></label>}
        <label>جست‌وجوی مجوز گروه<input type="search" maxLength={100} value={permissionTerm} onChange={event=>setPermissionTerm(event.target.value)}/></label>
        <p>مجوزهای انتخاب‌شده: {permissions.length}. فیلتر، انتخاب قبلی را پاک نمی‌کند.</p>
        {grants.filter(cap=>cap.includes(permissionTerm.trim())).map(cap=><label key={cap}><input type="checkbox" checked={permissions.includes(cap)} onChange={event=>
          setPermissions(old=>event.target.checked?[...old,cap]:old.filter(value=>value!==cap))}/><bdi>{cap}</bdi></label>)}
        <button className="button primary" type="button" disabled={!editorTag||(!selected&&!name.trim())} onClick={()=>setIntent("save")}>بررسی ذخیرهٔ گروه</button>
        {selected&&<button className="button secondary" type="button" onClick={()=>setIntent("delete")}>بررسی حذف گروه نقش</button>}
      </fieldset>
      {intent&&<form className="cms-conflict stack" onSubmit={commit}><h3>{intent==="delete"?"تأیید حذف گروه و قطع عضویت‌ها":"تأیید نسخهٔ جدید گروه"}</h3>
        <p>سیاست جاری، سقف واگذاری و باقی‌ماندن آخرین مالک روی سرور بررسی می‌شود. تغییر مجوز گروه بر همهٔ اعضا اثر دارد.</p>
        <fieldset className="cms-fieldset stack" disabled={busy||blocked}>
          <label>روش تأیید گروه<select value={method} onChange={event=>setMethod(event.target.value)}><option value="totp">TOTP</option><option value="recovery">کد بازیابی یک‌بارمصرف</option></select></label>
          <label>کد MFA گروه<input type="password" autoComplete="one-time-code" value={token} maxLength={32} onChange={event=>setToken(event.target.value)}/></label>
          <button className="button primary" disabled={!token.trim()} type="submit">اعمال تغییر تأییدشدهٔ گروه</button>
        </fieldset>
      </form>}
      <button className="button secondary" type="button" disabled={busy} onClick={()=>{setSelected(undefined);setEditorTag(null);setIntent(undefined);setToken("");}}>کنارگذاری تغییر گروه</button>
    </div>}
  </section>;
}
