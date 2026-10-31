// @vitest-environment jsdom
import { describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach } from "vitest";
import { ProfitabilityRatios } from "./ProfitabilityRatios";

const periods = ["FY22", "FY23", "FY24", "FY25", "FY26"];
const rows = {
  operating_margin: [10, 11, 12, 13, 16.1],
  net_margin: [null, 5, 6, 7, 8],
  effective_tax_rate: [20, 22, 25, 24, 30],
  roe: [15, 14, 13, 12, 9],
};

vi.stubGlobal("ResizeObserver", class { observe() {} unobserve() {} disconnect() {} });
afterEach(cleanup);

describe("ProfitabilityRatios CHANGE column", () => {
  it("adds a CHANGE header after the last year, saying what it compares", () => {
    render(<ProfitabilityRatios periods={periods} rows={rows} />);
    const heads = screen.getAllByRole("columnheader").map((h) => h.textContent);
    expect(heads[heads.length - 1]).toBe("CHANGEMar 2022 to Mar 2026");
    expect(heads[heads.length - 2]).toBe("Mar 2026");
  });
  it("shows signed points, a dash with a reason for a gap, and no tone for tax", () => {
    const { container } = render(<ProfitabilityRatios periods={periods} rows={rows} />);
    const cell = (label: string) => [...container.querySelectorAll("tbody tr")].find((r) => r.firstElementChild?.textContent === label)!.lastElementChild as HTMLElement;
    expect(cell("Operating margin").textContent).toBe("▲ +6.1 pts");
    expect(cell("Operating margin").className).toContain("up");
    expect(cell("Return on equity").textContent).toBe("▼ −6.0 pts");
    expect(cell("Return on equity").className).toContain("down");
    expect(cell("Net margin").textContent).toBe("—");
    expect(cell("Net margin").getAttribute("title")).toBe("No Mar 2022 figure");
    expect(cell("Effective tax rate").textContent).toBe("▲ +10.0 pts");
    expect(cell("Effective tax rate").className).not.toMatch(/up|down/);
  });
});

describe("ProfitabilityRatios upgrades", () => {
  it("sorts by CHANGE within groups, gaps last, and exposes aria-sort", () => {
    const { container } = render(<ProfitabilityRatios periods={periods} rows={rows} />);
    const btn = screen.getByRole("button", { name: /CHANGE/ });
    const names = () => [...container.querySelectorAll("tbody tr:not(.pr-g)")].map((r) => r.firstElementChild?.textContent);
    expect(names().slice(0, 2)).toEqual(["Operating margin", "Net margin"]);
    fireEvent.click(btn);
    expect(btn.closest("th")!.getAttribute("aria-sort")).toBe("descending");
    expect(names().slice(0, 2)).toEqual(["Operating margin", "Net margin"]);
    fireEvent.click(btn);
    expect(btn.closest("th")!.getAttribute("aria-sort")).toBe("ascending");
    expect(names().slice(0, 2)).toEqual(["Operating margin", "Net margin"]);
  });
  it("explains CHANGE and marks below/above median beyond colour", () => {
    const { container } = render(<ProfitabilityRatios periods={periods} rows={rows} />);
    expect(screen.getByRole("button", { name: /CHANGE/ }).getAttribute("title")).toMatch(/percentage points/);
    expect(container.querySelector("td.pr-ab")).not.toBeNull();
    expect(container.querySelector("td.pr-be")).not.toBeNull();
  });
});
