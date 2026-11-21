import {Suspense} from "react";
import PublicationAttestations from "@/components/cms/PublicationAttestations";

export default function PublicationAttestationsPage(){
  return <Suspense fallback={<main className="shell page"><p>در حال بارگذاری فرم بازبینی…</p></main>}>
    <PublicationAttestations/>
  </Suspense>;
}
