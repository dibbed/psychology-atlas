import ResearchRecords from "@/components/cms/ResearchRecords";
export default async function ResearchDatasetPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  return <ResearchRecords key={id} id={id} />;
}
