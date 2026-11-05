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
