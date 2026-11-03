import PrivacyConsole from "@/components/cms/PrivacyConsole";

export default async function PrivacyPage({params}:{params:Promise<{id:string}>}){
  const {id}=await params,userId=Number(id);
  if(!/^[1-9]\d*$/.test(id)||!Number.isSafeInteger(userId))return <p>شناسهٔ حساب معتبر نیست.</p>;
  return <PrivacyConsole key={id} userId={userId}/>;
}
