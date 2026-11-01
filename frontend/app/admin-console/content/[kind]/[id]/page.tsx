import DomainRecord from '@/components/cms/DomainRecord';
export default async function ContentRecordPage({params}: {params: Promise<{kind: string; id: string}>}) {
  const {kind, id} = await params;
  return <DomainRecord key={`${kind}/${id}`} kind={kind} id={id}/>;
}
