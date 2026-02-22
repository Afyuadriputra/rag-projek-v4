import { useEffect, useRef } from "react";
import ChatBubble from "@/components/molecules/ChatBubble";
import type { ChatItem } from "@/components/molecules/ChatBubble";
import PlannerPanelRenderer, { type PlannerUiState } from "@/components/planner/PlannerPanelRenderer";
import type { PlannerHeaderMeta, PlannerProfileHintsSummary, PlannerWizardStep } from "@/lib/api";

export default function ChatThread({
  items,
  mode = "chat",
  activePlannerOptionMessageId,
  optionsLocked = false,
  onSelectPlannerOption,
  plannerPanelProps,
}: {
  items: ChatItem[];
  mode?: "chat" | "planner";
  activePlannerOptionMessageId?: string | null;
  optionsLocked?: boolean;
  onSelectPlannerOption?: (optionId: number, label: string) => void;
  plannerPanelProps?: {
    state: PlannerUiState;
    hasEmbeddedDocs: boolean;
    relevanceError?: string | null;
    majorSummary?: PlannerProfileHintsSummary | null;
    progressMessage: string;
    progressMode?: "start" | "branching" | "execute";
    wizardSteps: PlannerWizardStep[];
    wizardIndex: number;
    progressCurrent?: number;
    progressEstimatedTotal?: number;
    plannerHeader?: PlannerHeaderMeta | null;
    plannerMajorSource?: "user_override" | "inferred" | string;
    plannerStepHeader?: { path_label?: string; reason?: string } | null;
    wizardAnswers: Record<string, string>;
    plannerCanGenerateNow: boolean;
    plannerPathSummary: string;
    plannerDocs: Array<{ id: number; title: string }>;
    embeddedDocs: Array<{ id: number; title: string }>;
    selectedDocIds: number[];
    selectedDocTitles: string[];
    docPickerOpen: boolean;
    loading: boolean;
    deletingDocId: number | null;
    plannerWarning?: string | null;
    onUploadNew: () => void;
    onOpenDocPicker: () => void;
    onConfirmDocPicker: (ids: number[]) => void;
    onCloseDocPicker: () => void;
    onClearDocSelection: () => void;
    onSelectOption: (value: string) => void;
    onChangeManual: (value: string) => void;
    onNext: () => void;
    onBack: () => void;
    onEdit: (stepKey: string) => void;
    onExecute: () => void;
  };
}) {
  const bottomRef = useRef<HTMLDivElement>(null);

  // Auto-scroll ke pesan terakhir
  useEffect(() => {
    // Delay 100ms agar rendering elemen selesai sebelum scroll (fix untuk mobile)
    const timeout = setTimeout(() => {
      bottomRef.current?.scrollIntoView({ behavior: "smooth", block: "end" });
    }, 100);
    return () => clearTimeout(timeout);
  }, [items]);

  return (
    // Container Layout:
    // - w-full & mx-auto: Agar konten di tengah
    // - overflow-x-hidden: Mencegah tabel lebar merusak layout mobile
    // - px-4: Padding mobile
    <div
      data-testid="chat-thread"
      className="mx-auto w-full max-w-3xl min-w-0 overflow-x-hidden px-4 md:px-0"
    >
      <div className="flex flex-col gap-6 pb-2 md:gap-8 md:pb-4">
        {/* Date Badge */}
        <div className="pointer-events-none sticky top-0 z-10 flex justify-center py-6">
          <span className="inline-flex items-center rounded-full border border-zinc-200/50 bg-white/60 px-4 py-1.5 text-[10px] font-bold uppercase tracking-widest text-zinc-500 shadow-sm backdrop-blur-xl dark:border-zinc-700/70 dark:bg-zinc-900/75 dark:text-zinc-300">
            {new Date().toLocaleDateString("id-ID", {
              weekday: "long",
              day: "numeric",
              month: "short",
            })}
          </span>
        </div>

        {/* ✅ Pembaruan kompatibilitas:
            ChatItem sekarang boleh punya `sources?: [...]`.
            ChatBubble sudah handle itu, jadi di sini tidak perlu ubah desain/markup. */}
        {items.map((it) => {
          if (it.message_kind === "planner_panel" && plannerPanelProps) {
            return (
              <div key={it.id} data-testid="planner-inline-panel" className="w-full">
                <PlannerPanelRenderer {...plannerPanelProps} />
              </div>
            );
          }
          return (
            <ChatBubble
              key={it.id}
              item={it}
              showPlannerOptions={mode === "planner"}
              optionsEnabled={
                mode === "planner" &&
                !optionsLocked &&
                !!activePlannerOptionMessageId &&
                activePlannerOptionMessageId === it.id
              }
              onSelectOption={onSelectPlannerOption}
            />
          );
        })}

        {/* Dummy element scroll target */}
        <div ref={bottomRef} className="mt-2 h-12 w-full md:h-16" />
      </div>
    </div>
  );
}
