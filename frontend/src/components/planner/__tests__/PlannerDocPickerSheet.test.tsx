import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import PlannerDocPickerSheet from "../PlannerDocPickerSheet";

describe("PlannerDocPickerSheet", () => {
  it("submit disabled saat tidak ada dokumen dipilih lalu aktif saat dipilih", async () => {
    const onClose = vi.fn();
    const onConfirm = vi.fn();
    const onClear = vi.fn();

    render(
      <PlannerDocPickerSheet
        open
        docs={[
          { id: 11, title: "KHS TI" },
          { id: 12, title: "KRS TI" },
        ]}
        selectedIds={[]}
        onClose={onClose}
        onConfirm={onConfirm}
        onClear={onClear}
      />
    );

    const confirmBtn = screen.getByTestId("planner-doc-picker-confirm");
    expect(confirmBtn).toBeDisabled();

    await userEvent.click(screen.getByTestId("planner-doc-checkbox-11"));
    expect(confirmBtn).not.toBeDisabled();

    await userEvent.click(confirmBtn);
    expect(onConfirm).toHaveBeenCalledWith([11]);
  });
});
