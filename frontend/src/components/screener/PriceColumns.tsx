// The optional 52-week and return columns of both score screeners: 3-month, 6-month and 1-year return, and how far below the 52-week high. Off by default; the choice is kept in this browser.
import { useState } from "react";
import { MINUS, nf } from "../../lib/format";
import type { Item, SortKey } from "../../lib/scoreScreen";
import { Dash } from "./cells";
import { SortTh } from "./ScreenerFrame";
import type { Screener } from "./useScreener";

const KEY = "finlit.screener.priceCols";
export const PRICE_COL_COUNT = 4;
export const PRICE_SORT: SortKey[] = ["ret_3m", "ret_6m", "return_1y", "pct_from_high"];

export function usePriceColumns(): [boolean, (on: boolean) => void] {
  const [on, set] = useState<boolean>(() => { try { return localStorage.getItem(KEY) === "1"; } catch { return false; } });
  return [on, (v) => { set(v); try { localStorage.setItem(KEY, v ? "1" : "0"); } catch { /* a private window: the choice lasts for this visit */ } }];
}

export function PriceColumnsToggle({ on, set }: { on: boolean; set: (on: boolean) => void }) {
  return (
    <div className="sx-colopt"><button type="button" className={"fgx-chip" + (on ? " is-on" : "")} aria-pressed={on} onClick={() => set(!on)}>{on && <i aria-hidden="true">&#10003;</i>}Add 52-week and return columns</button>
      <small>3-month, 6-month and 1-year return, and how far below the 52-week high.</small></div>);
}

export const PriceHeads = ({ s }: { s: Screener }) => (<>
  <SortTh s={s} k="ret_3m" label="3M return" of="Price" /><SortTh s={s} k="ret_6m" label="6M return" of="Price" /><SortTh s={s} k="return_1y" label="1Y return" of="Price" />
  <SortTh s={s} k="pct_from_high" label="Below 52-week high" of="Price" /></>);

const Pct = ({ v, why, signed = true }: { v: number | null | undefined; why: string; signed?: boolean }) =>
  v == null ? <td><Dash why={why} /></td> : <td>{signed && v > 0 ? "+" : v < 0 ? MINUS : ""}{nf(Math.abs(v), 1)}%</td>;

export const PriceCells = ({ r }: { r: Item }) => (<>
  <Pct v={r.ret_3m} why="not enough price history" /><Pct v={r.ret_6m} why="not enough price history" /><Pct v={r.return_1y} why="not enough price history" />
  <Pct v={r.pct_from_high} why="no 52-week high yet" signed={false} /></>);
