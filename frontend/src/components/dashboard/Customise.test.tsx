// @vitest-environment jsdom
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router";
import { afterEach, describe, expect, it, vi } from "vitest";
import { Customise } from "./Customise";
import { normaliseLayout } from "../../lib/prefs";

afterEach(cleanup);
const setup = () => {
  const onChange = vi.fn(), onReset = vi.fn(), layout = normaliseLayout(null);
  render(<MemoryRouter><Customise layout={layout} plan="gold" onChange={onChange} onReset={onReset} onDone={() => {}} /></MemoryRouter>);
  return { onChange, onReset, layout };
};

describe("Customise", () => {
  it("lists every block, including the market ones, with a switch each", () => {
    const { layout } = setup();
    expect(screen.getAllByRole("checkbox")).toHaveLength(layout.length);
    expect(screen.getByLabelText("Market today width")).toBeTruthy();
  });
  it("hides a market block", () => {
    const { onChange } = setup();
    fireEvent.click(screen.getByLabelText(/Market today/, { selector: "input" }));
    expect(onChange.mock.calls[0][0].find((w: { id: string }) => w.id === "market").on).toBe(false);
  });
  it("moves a block with the arrows and keeps the first block's up button off", () => {
    const { onChange } = setup();
    expect((screen.getByLabelText("Move Your stocks today up") as HTMLButtonElement).disabled).toBe(true);
    fireEvent.click(screen.getByLabelText("Move Market today up"));
    expect(onChange.mock.calls[0][0].slice(0, 2).map((w: { id: string }) => w.id)).toEqual(["market", "mystocks"]);
  });
  it("moves a block by dragging it onto another", () => {
    const { onChange } = setup();
    const items = screen.getAllByRole("listitem");
    fireEvent.dragStart(items[0], { dataTransfer: { setData() {}, effectAllowed: "" } });
    fireEvent.drop(items[2], { dataTransfer: {} });
    expect(onChange.mock.calls[0][0].map((w: { id: string }) => w.id).slice(0, 3)).toEqual(["market", "snapshot", "mystocks"]);
  });
  it("sets the width and resets the layout", () => {
    const { onChange, onReset } = setup();
    fireEvent.click(screen.getAllByText("Full")[2]);   // the third block (Market snapshot, half) becomes full width
    expect(onChange.mock.calls[0][0].find((w: { id: string }) => w.id === "snapshot").size).toBe("full");
    expect(onChange).toHaveBeenCalled();
    fireEvent.click(screen.getByText("Reset layout"));
    expect(onReset).toHaveBeenCalled();
  });
});
