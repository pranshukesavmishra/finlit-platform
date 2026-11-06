// @vitest-environment jsdom
import { cleanup, fireEvent, render } from "@testing-library/react";
import { MemoryRouter } from "react-router";
import { afterEach, expect, it } from "vitest";
import { FeatureBucket } from "./FeatureBucket";

afterEach(cleanup);
it("filter pills hide other groups visually but keep every card in the page", () => {
  const { container, getByRole } = render(<MemoryRouter><FeatureBucket /></MemoryRouter>);
  fireEvent.click(getByRole("button", { name: "Quant Lab" }));
  const groups = [...container.querySelectorAll<HTMLElement>(".fb-group")];
  expect(groups.filter((g) => !g.hidden).map((g) => g.dataset.group)).toEqual(["quantlab"]);
  expect(container.querySelectorAll(".fb-card")).toHaveLength(22);
  fireEvent.click(getByRole("button", { name: "All" }));
  expect(groups.every((g) => !g.hidden)).toBe(true);
});

it("the plan filter shows only the tools that open on that plan, hides empty groups and keeps every card in the page", () => {
  const { container, getByRole } = render(<MemoryRouter><FeatureBucket /></MemoryRouter>);
  fireEvent.click(getByRole("button", { name: "Silver" }));
  const cards = [...container.querySelectorAll<HTMLElement>(".fb-card")];
  expect(cards).toHaveLength(22);
  const shown = cards.filter((c) => !c.hidden);
  expect(shown.length).toBeGreaterThan(0);
  expect(shown.every((c) => c.dataset.tier === "silver")).toBe(true);
  const groups = [...container.querySelectorAll<HTMLElement>(".fb-group")];
  for (const g of groups) expect(g.hidden).toBe(!g.querySelector(".fb-card:not([hidden])"));
  fireEvent.click(getByRole("button", { name: "Any plan" }));
  expect(cards.every((c) => !c.hidden)).toBe(true);
});

it("every plan chip leads to that plan on the Plans page", () => {
  const { container } = render(<MemoryRouter><FeatureBucket /></MemoryRouter>);
  const hrefs = [...container.querySelectorAll<HTMLAnchorElement>("a.fb-chip")].map((a) => a.getAttribute("href"));
  expect(hrefs).toHaveLength(22);
  expect(new Set(hrefs)).toEqual(new Set(["/plans#basic", "/plans#silver", "/plans#gold"]));
});

it("Gold adds 'Plus all features of Silver' and of Free, Silver adds Free, Free and Any plan add nothing", () => {
  const { container, getByRole, queryByLabelText } = render(<MemoryRouter><FeatureBucket /></MemoryRouter>);
  fireEvent.click(getByRole("button", { name: "Gold" }));
  const rows = [...container.querySelectorAll(".fb-plus-row p b")].map((b) => b.textContent);
  expect(rows).toEqual(["Plus all features of Silver", "Plus all features of Free"]);
  expect(container.querySelectorAll(".fb-plus-silver li")).toHaveLength(2);
  fireEvent.click(getByRole("button", { name: "Silver" }));
  expect([...container.querySelectorAll(".fb-plus-row p b")].map((b) => b.textContent)).toEqual(["Plus all features of Free"]);
  fireEvent.click(getByRole("button", { name: "Free" }));
  expect(container.querySelector(".fb-plus")).toBeNull();
  fireEvent.click(getByRole("button", { name: "Any plan" }));
  expect(queryByLabelText(/Also included/)).toBeNull();
});
