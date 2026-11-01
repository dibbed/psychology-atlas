import DomainList from '@/components/cms/DomainList';
export default async function ContentListPage({params}: {params: Promise<{kind: string}>}) {
  return <DomainList kind={(await params).kind}/>;
}
