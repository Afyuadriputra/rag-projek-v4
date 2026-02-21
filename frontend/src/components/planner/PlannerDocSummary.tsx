export default function PlannerDocSummary({ docs }: { docs: Array<{ id: number; title: string }> }) {
  const text = docs.map((d) => d.title).join(", ") || "-";
  return <div className="text-xs text-zinc-500 dark:text-zinc-400">Dokumen: {text}</div>;
}
