import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import type { ChatResponse, DocumentDto } from "@/lib/api";
import Index from "../Index";

const usePageMock = vi.fn();

const sendChatMock = vi.fn();
const uploadDocumentsMock = vi.fn();
const getDocumentsMock = vi.fn();
const getSessionsMock = vi.fn();
const createSessionMock = vi.fn();
const deleteSessionMock = vi.fn();
const getSessionTimelineMock = vi.fn();
const renameSessionMock = vi.fn();
const deleteDocumentMock = vi.fn();
const plannerStartV3Mock = vi.fn();
const plannerNextStepV3Mock = vi.fn();
const plannerExecuteV3Mock = vi.fn();
const plannerCancelV3Mock = vi.fn();

vi.mock("@inertiajs/react", () => ({
  usePage: () => usePageMock(),
}));

vi.mock("@/lib/api", () => ({
  sendChat: (...args: unknown[]) => sendChatMock(...args),
  uploadDocuments: (...args: unknown[]) => uploadDocumentsMock(...args),
  getDocuments: (...args: unknown[]) => getDocumentsMock(...args),
  getSessions: (...args: unknown[]) => getSessionsMock(...args),
  createSession: (...args: unknown[]) => createSessionMock(...args),
  deleteSession: (...args: unknown[]) => deleteSessionMock(...args),
  getSessionTimeline: (...args: unknown[]) => getSessionTimelineMock(...args),
  renameSession: (...args: unknown[]) => renameSessionMock(...args),
  deleteDocument: (...args: unknown[]) => deleteDocumentMock(...args),
  plannerStartV3: (...args: unknown[]) => plannerStartV3Mock(...args),
  plannerNextStepV3: (...args: unknown[]) => plannerNextStepV3Mock(...args),
  plannerExecuteV3: (...args: unknown[]) => plannerExecuteV3Mock(...args),
  plannerCancelV3: (...args: unknown[]) => plannerCancelV3Mock(...args),
}));

vi.mock("@/components/organisms/KnowledgeSidebar", () => ({
  default: () => <div data-testid="knowledge-sidebar">Sidebar</div>,
}));

type SendPayload = {
  mode?: "chat" | "planner";
  message?: string;
  option_id?: number;
  session_id?: number;
};

const storage = {
  used_bytes: 0,
  quota_bytes: 1024,
  used_pct: 0,
  used_human: "0 B",
  quota_human: "1 KB",
};

const embeddedDocs: DocumentDto[] = [
  {
    id: 1,
    title: "KHS Semester 1.pdf",
    is_embedded: true,
    uploaded_at: "2026-01-10 10:00",
    size_bytes: 1024,
  },
  {
    id: 2,
    title: "KRS Semester 2.pdf",
    is_embedded: true,
    uploaded_at: "2026-01-11 10:00",
    size_bytes: 1024,
  },
  {
    id: 3,
    title: "Draft belum embedded.pdf",
    is_embedded: false,
    uploaded_at: "2026-01-12 10:00",
    size_bytes: 1024,
  },
];

function makePageProps(docs: DocumentDto[] = embeddedDocs) {
  return {
    user: { id: 1, username: "tester", email: "tester@example.com" },
    activeSessionId: 10,
    sessions: [],
    initialHistory: [],
    documents: docs,
    storage,
  };
}

describe("Phase 4 frontend interactions", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    usePageMock.mockReturnValue({ props: makePageProps() });
    getSessionsMock.mockResolvedValue({
      sessions: [],
      pagination: { page: 1, page_size: 20, total: 0, has_next: false },
    });
    getDocumentsMock.mockResolvedValue({
      documents: embeddedDocs,
      storage,
    });
    getSessionTimelineMock.mockResolvedValue({
      timeline: [],
      pagination: { page: 1, page_size: 100, total: 0, has_next: false },
    });
    uploadDocumentsMock.mockResolvedValue({ status: "success", msg: "ok" });
    plannerStartV3Mock.mockResolvedValue({
      status: "success",
      planner_run_id: "run-1",
      wizard_blueprint: { version: "3", steps: [] },
      intent_candidates: [{ id: 1, label: "Rekap IPK", value: "rekap_ipk" }],
      documents_summary: embeddedDocs.filter((d) => d.is_embedded).map((d) => ({ id: d.id, title: d.title })),
      progress: { current: 1, estimated_total: 4 },
    });
    plannerNextStepV3Mock.mockResolvedValue({ status: "success", can_generate_now: false, path_taken: [] });
    plannerExecuteV3Mock.mockResolvedValue({ status: "success", answer: "OK", sources: [] });
    plannerCancelV3Mock.mockResolvedValue({ status: "success" });

    sendChatMock.mockImplementation(async (payloadRaw: unknown) => {
      const payload = (payloadRaw ?? {}) as SendPayload;
      if (payload?.mode === "planner") {
        return {
          type: "planner_step",
          answer: "Pilih strategi data",
          options: [
            { id: 1, label: "📎 Ya, saya mau upload file", value: "upload" },
            { id: 2, label: "✍️ Tidak, saya isi manual", value: "manual" },
          ],
          allow_custom: false,
          planner_step: "data",
          planner_warning: "Upload sumber dengan data yang relevan agar jawaban konsisten.",
          profile_hints: { confidence_summary: "low", has_relevant_docs: false },
          planner_meta: { origin: "start_auto" },
          session_state: { current_step: "data", collected_data: {}, data_level: { level: 0 } },
        } as ChatResponse;
      }
      return {
        type: "chat",
        answer: "OK chat",
        sources: [],
        session_id: 10,
      } as ChatResponse;
    });
  });

  it("masuk mode planner menampilkan onboarding dan lock reason composer", async () => {
    render(<Index />);
    await userEvent.click(await screen.findByTestId("mode-planner"));

    expect(await screen.findByText("Setup Dokumen Planner")).toBeInTheDocument();
    expect(await screen.findByText("Selesaikan langkah planner atau klik Analisis Sekarang.")).toBeInTheDocument();
  });

  it("doc-picker reuse existing hanya mengirim doc ids terpilih", async () => {
    render(<Index />);
    await userEvent.click(await screen.findByTestId("mode-planner"));

    await userEvent.click(await screen.findByTestId("planner-open-doc-picker"));
    expect(await screen.findByTestId("planner-doc-picker-sheet")).toBeInTheDocument();

    await userEvent.click(await screen.findByTestId("planner-doc-checkbox-1"));
    await userEvent.click(await screen.findByTestId("planner-doc-picker-confirm"));

    await waitFor(() => {
      expect(plannerStartV3Mock).toHaveBeenCalledTimes(1);
    });
    expect(plannerStartV3Mock.mock.calls[0][0]).toMatchObject({
      sessionId: 10,
      reuseDocIds: [1],
    });
  });

  it("drag-drop upload memanggil uploadDocuments", async () => {
    render(<Index />);
    const dropTarget = await screen.findByTestId("chat-drop-target");

    const file = new File(["hello"], "drag.txt", { type: "text/plain" });
    const dataTransfer = {
      files: [file],
    } as unknown as DataTransfer;

    fireEvent.dragOver(dropTarget, { dataTransfer });
    expect(await screen.findByTestId("chat-drop-overlay")).toBeInTheDocument();

    fireEvent.drop(dropTarget, { dataTransfer });

    await waitFor(() => {
      expect(uploadDocumentsMock).toHaveBeenCalledTimes(1);
    });
  });
});
