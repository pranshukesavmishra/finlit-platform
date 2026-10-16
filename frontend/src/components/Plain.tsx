import type { ReactNode } from "react";
import { Icon } from "../lib/icons";

/** A one-line plain-English reading of the section below it, so nobody has to interpret numbers alone. */
export function Plain({ children, tone = "info" }: { children: ReactNode; tone?: "info" | "good" | "warn" }) {
  return (
    <div className={"plain pl-" + tone}>
      <span className="plain-i"><Icon name="spark" /></span>
      <div><b>In simple words</b><p>{children}</p></div>
    </div>
  );
}
