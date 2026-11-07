// @vitest-environment jsdom
// The DCF calculator's slider fields: the slider and the number box are one value, the range widens for a bigger number, and nothing is lost while typing.
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { useState } from "react";
import { afterEach, describe, expect, it, vi } from "vitest";
vi.mock("../components/Info", () => ({ Info: () => null }));
import { SliderField } from "./Dcf";

afterEach(cleanup);
function Harness(p: { start: string; min: number; max: number; step?: number; unit?: string; error?: string }) {
  const [v, setV] = useState(p.start);
  return <SliderField id="t" label="Discount rate" value={v} onChange={setV} unit={p.unit} min={p.min} max={p.max} step={p.step} error={p.error} />;
}
const slider = () => screen.getByRole("slider", { name: "Discount rate, slider" }) as HTMLInputElement;
const box = () => screen.getByRole("textbox", { name: /Discount rate/ }) as HTMLInputElement;

describe("DCF SliderField", () => {
  it("moving the slider writes the number into the box, rounded to the step", () => {
    render(<Harness start="12" min={1} max={30} step={0.1} unit="%" />);
    fireEvent.change(slider(), { target: { value: "13.7" } });
    expect(box().value).toBe("13.7");
    fireEvent.change(slider(), { target: { value: "14.0000001" } });
    expect(box().value).toBe("14");
  });
  it("typing a number moves the slider, and a half-typed or empty box leaves the slider at the start without losing the text", () => {
    render(<Harness start="12" min={1} max={30} step={0.1} />);
    fireEvent.change(box(), { target: { value: "20" } });
    expect(slider().value).toBe("20");
    fireEvent.change(box(), { target: { value: "2." } });
    expect(box().value).toBe("2.");
    fireEvent.change(box(), { target: { value: "" } });
    expect(box().value).toBe("");
    expect(Number(slider().value)).toBe(1);
  });
  it("a typed or loaded number beyond the range widens the slider instead of being cut off", () => {
    render(<Harness start="12500" min={0} max={1000} />);
    expect(Number(slider().max)).toBeGreaterThanOrEqual(12500);
    expect(Number(slider().value)).toBe(12500);
    fireEvent.change(box(), { target: { value: "-30" } });
    expect(Number(slider().min)).toBeLessThanOrEqual(-30);
  });
  it("the range ends are shown with a real minus sign, and the units follow", () => {
    const { container } = render(<Harness start="10" min={-10} max={50} step={0.5} unit="%" />);
    const ends = [...container.querySelectorAll(".dcf-range-ends span")].map((e) => e.textContent);
    expect(ends).toEqual(["−10.0%", "50.0%"]);
  });
  it("an error is shown under the field and flagged on the box", () => {
    render(<Harness start="12" min={1} max={30} error="Enter a number." />);
    expect(screen.getByText("Enter a number.")).toBeTruthy();
    expect(box().getAttribute("aria-invalid")).toBe("true");
  });
});
