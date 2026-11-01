import GovernanceRecord from "@/components/cms/GovernanceRecord";
export default async function TerminologyRecordPage({ params }: { params: Promise<{ id: string }> }) { const { id } = await params; return <GovernanceRecord key={id} kind="terminology" id={id} />; }
