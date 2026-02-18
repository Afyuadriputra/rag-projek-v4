import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import type { ChatResponse } from "@/lib/api";
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
}));

vi.mock("@/components/organisms/KnowledgeSidebar", () => ({
  default: () => <div data-testid="knowledge-sidebar">Sidebar</div>,
}));

const basePageProps = {
  user: { id: 1, username: "tester", email: "tester@example.com" },
  activeSessionId: 10,
  sessions: [],
  initialHistory: [],
  documents: [],
  storage: {
    used_bytes: 0,
    quota_bytes: 1024,
    used_pct: 0,
    used_human: "0 B",
    quota_human: "1 KB",
  },
};

const plannerStartResponse: ChatResponse = {
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
};

type SendPayload = {
  mode?: "chat" | "planner";
  message?: string;
  option_id?: number;
  session_id?: number;
};

describe("Phase 4 frontend interactions", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    usePageMock.mockReturnValue({ props: basePageProps });
    getSessionsMock.mockResolvedValue({
      sessions: [],
      pagination: { page: 1, page_size: 20, total: 0, has_next: false },
    });
    getDocumentsMock.mockResolvedValue({
      documents: [],
      storage: basePageProps.storage,
    });
    getSessionTimelineMock.mockResolvedValue({
      timeline: [],
      pagination: { page: 1, page_size: 100, total: 0, has_next: false },
    });
    uploadDocumentsMock.mockResolvedValue({ status: "success", msg: "ok" });
    sendChatMock.mockImplementation(async (payloadRaw: unknown) => {
      const payload = (payloadRaw ?? {}) as SendPayload;
      if (payload?.mode === "planner") {
        if (payload?.option_id === 1) {
          return {
            type: "planner_step",
            answer: "Lanjut ke profile",
            options: [{ id: 1, label: "Teknik Informatika", value: "Teknik Informatika" }],
            allow_custom: true,
            planner_step: "profile_jurusan",
            session_state: { current_step: "profile_jurusan" },
          } as ChatResponse;
        }
        return plannerStartResponse;
      }
      return {
        type: "chat",
        answer: "OK chat",
        sources: [],
        session_id: 10,
      } as ChatResponse;
    });
  });

  it("toggle ke Plan mengirim payload mode planner start", async () => {
    render(<Index />);
    await userEvent.click(await screen.findByTestId("mode-planner"));

    await waitFor(() => {
      expect(sendChatMock).toHaveBeenCalled();
    });

    const firstPayload = sendChatMock.mock.calls[0][0];
    expect(firstPayload).toMatchObject({
      mode: "planner",
      message: "",
      session_id: 10,
    });
    expect(firstPayload.option_id).toBeUndefined();
  });

  it("klik planner option mengirim option_id", async () => {
    render(<Index />);
    await userEvent.click(await screen.findByTestId("mode-planner"));
    await screen.findByText("Pilih strategi data");

    const optionButton = await screen.findByTestId("planner-option-1");
    await userEvent.click(optionButton);

    await waitFor(() => {
      expect(sendChatMock).toHaveBeenCalledTimes(2);
    });
    const secondPayload = sendChatMock.mock.calls[1][0];
    expect(secondPayload).toMatchObject({
      mode: "planner",
      option_id: 1,
      session_id: 10,
    });
  });

  it("planner menampilkan label terdeteksi dari dokumen untuk pertanyaan dan opsi", async () => {
    sendChatMock.mockResolvedValueOnce({
      type: "planner_step",
      answer: "Kami mendeteksi jurusan kamu kemungkinan Teknik Informatika. Benar?",
      options: [{ id: 1, label: "Teknik Informatika", value: "Teknik Informatika", detected: true }],
      allow_custom: true,
      planner_step: "profile_jurusan",
      profile_hints: {
        question_candidates: [
          {
            step: "profile_jurusan",
            question: "Kami mendeteksi jurusan kamu kemungkinan Teknik Informatika. Benar?",
            mode: "confirm",
          },
        ],
      },
      session_state: { current_step: "profile_jurusan" },
    } as ChatResponse);

    render(<Index />);
    await userEvent.click(await screen.findByTestId("mode-planner"));

    expect(await screen.findByTestId("planner-doc-detected-question")).toBeInTheDocument();
    expect(await screen.findByTestId("planner-option-detected-1")).toHaveTextContent("Terdeteksi dari dokumen");
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

  it("mode chat menyembunyikan planner option", async () => {
    render(<Index />);
    await userEvent.click(await screen.findByTestId("mode-planner"));
    await screen.findByTestId("planner-option-1");

    await userEvent.click(await screen.findByTestId("mode-chat"));
    expect(screen.queryByTestId("planner-option-1")).not.toBeInTheDocument();
  });

  it("switch mode berulang tidak menambah planner start response", async () => {
    render(<Index />);
    await userEvent.click(await screen.findByTestId("mode-planner"));
    await screen.findByText("Pilih strategi data");

    await userEvent.click(await screen.findByTestId("mode-chat"));
    await userEvent.click(await screen.findByTestId("mode-planner"));

    await waitFor(() => {
      const plannerStartCalls = sendChatMock.mock.calls.filter((c) => c?.[0]?.mode === "planner" && c?.[0]?.message === "");
      expect(plannerStartCalls).toHaveLength(1);
    });
  });

  it("menampilkan planner warning banner saat payload berisi planner_warning", async () => {
    render(<Index />);
    await userEvent.click(await screen.findByTestId("mode-planner"));

    const banner = await screen.findByTestId("planner-warning-banner");
    expect(banner).toBeInTheDocument();
    expect(banner).toHaveTextContent("Upload sumber dengan data yang relevan agar jawaban konsisten.");
  });

  it("load timeline session menampilkan planner milestone secara ringkas", async () => {
    getSessionTimelineMock.mockResolvedValueOnce({
      timeline: [
        {
          id: "planner-1",
          kind: "planner_milestone",
          text: "Pilih opsi 2: Manual",
          time: "10:10",
          date: "2026-02-18",
          meta: { planner_step: "data", event_type: "option_select" },
        },
      ],
      pagination: { page: 1, page_size: 100, total: 1, has_next: false },
    });

    render(<Index />);
    expect(await screen.findByText("Pilih opsi 2: Manual")).toBeInTheDocument();
    expect(await screen.findByText("Milestone Planner · data")).toBeInTheDocument();
  });
});
