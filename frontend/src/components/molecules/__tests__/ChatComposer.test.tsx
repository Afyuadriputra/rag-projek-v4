import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import ChatComposer from "../ChatComposer";

describe("ChatComposer", () => {
  it("menampilkan planner lock reason spesifik saat loading", () => {
    render(
      <ChatComposer
        onSend={vi.fn()}
        onUploadClick={vi.fn()}
        loading
        plannerLockReason="Selesaikan langkah planner atau klik Analisis Sekarang."
      />
    );

    expect(screen.getAllByText("Selesaikan langkah planner atau klik Analisis Sekarang.").length).toBeGreaterThan(0);
  });
});
