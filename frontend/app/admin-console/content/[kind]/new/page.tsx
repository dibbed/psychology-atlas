import DomainRecord from '@/components/cms/DomainRecord';
export default async function NewContentPage({params}: {params: Promise<{kind: string}>}) {
  return <DomainRecord kind={(await params).kind}/>;
}
