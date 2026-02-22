import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import PlannerOnboardingCard from "../PlannerOnboardingCard";

describe("PlannerOnboardingCard", () => {
  it("menampilkan ringkasan sumber aktif planner", () => {
    render(
      <PlannerOnboardingCard
        hasEmbeddedDocs
        onUploadNew={vi.fn()}
        onOpenDocPicker={vi.fn()}
        onClearDocSelection={vi.fn()}
        selectedDocCount={3}
        selectedDocTitles={["KHS Semester 1", "KHS Semester 2", "KRS Semester 3"]}
      />
    );

    expect(screen.getByText("Sumber aktif planner")).toBeInTheDocument();
    expect(screen.getByText("3 dokumen dipilih")).toBeInTheDocument();
    expect(screen.getByText(/KHS Semester 1, KHS Semester 2, KRS Semester 3/)).toBeInTheDocument();
  });
});
