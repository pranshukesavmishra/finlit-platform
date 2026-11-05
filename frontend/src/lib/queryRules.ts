// The "Rules for writing a query" guide: its text lives in content/queryRules.json, which the backend tests (tests/test_ql_rules.py) check against the real
// parser, so every rule, example and error explanation here is one the language actually follows. This file only looks things up.
import rules from "../content/queryRules.json";
import type { Fix, Problem } from "./query";

export type ErrorRule = { rule: string; fix: string; bad?: string; good?: string };
export const RULES = rules as {
  golden: string[]; results: string[]; syntax: { op: string; meaning: string; example: string }[]; notSupported: string[];
  dos: { do: string; dont: string; why: string; code: string }[]; examples: { id: string; title: string; query: string }[];
  errors: Record<string, ErrorRule>; specials: Record<string, ErrorRule & { match: string }>;
};

/** The rule a problem broke, with how to fix it. A few mistakes the parser reports as an unknown ratio (NOT, sector) have a rule of their own. */
export function ruleFor(p: Pick<Problem, "code" | "text">): ErrorRule | null {
  if (p.code === "unknown_metric") {
    for (const s of Object.values(RULES.specials)) if (new RegExp(s.match, "i").test(p.text.trim())) return s;
  }
  return RULES.errors[p.code] ?? null;
}

/** The repair to offer as the main button: only when there is exactly one, so it is never a guess between several. */
export const onlyFix = (p: Pick<Problem, "fixes">): Fix | null => (p.fixes.length === 1 ? p.fixes[0] : null);
