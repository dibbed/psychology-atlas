import JobDetail from "@/components/cms/JobDetail";
export default async function JobPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  return <JobDetail key={id} id={id} />;
}
