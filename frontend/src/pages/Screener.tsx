import { DEMO } from "../lib/demo";
import { ScreenerLite } from "./ScreenerLite";
import { ScreenerPro } from "./ScreenerPro";

/** The live site uses the server-side screener (160+ filters, plan-gated on the server); the static demo has no server, so it keeps the small client-side one. */
export function Screener() { return DEMO ? <ScreenerLite /> : <ScreenerPro />; }
