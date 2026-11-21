import DomainRecord from "@/components/cms/DomainRecord";
export default async function CategoryDetail({ params }: { params: Promise<{ id: string }> }) {
  return <DomainRecord kind="category" id={(await params).id} />;
}
