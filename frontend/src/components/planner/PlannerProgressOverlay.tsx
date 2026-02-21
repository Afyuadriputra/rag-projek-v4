import GlassCard from "@/components/atoms/GlassCard";
import InlineProgress from "@/components/atoms/InlineProgress";

export default function PlannerProgressOverlay({ message }: { message: string }) {
  return (
    <GlassCard className="mx-auto w-[min(900px,92%)]">
      <InlineProgress message={message} />
    </GlassCard>
  );
}
