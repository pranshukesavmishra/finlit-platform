// What each Profit & loss line means on FinLit, in one place. The same definitions apply on the stock page, the quarter results,
// the screener, the ratios and the exports (backend/finlit/normalize/statements.py states them in code).
import type { Glossary } from "../lib/api";
import { cr, num } from "../lib/format";

const g = (key: string, label: string, what: string, read?: string, formula?: string): Glossary => ({ key, label, what, read, formula });

export const PL_INFO: Record<string, Glossary> = {
  revenue: g("pl_revenue", "Revenue", "Money earned from the company's main business (sales of products and services). A bank or lender shows interest earned plus fees.", "Other income is not included.", "Revenue from operations"),
  other_income: g("pl_other_income", "Other income", "Money earned outside the main business, such as interest on deposits or gains on investments.", "It is not part of operating profit. It is added back below, before profit before tax."),
  expenses: g("pl_expenses", "Total expenses", "Every cost the company reports for the period, including interest and depreciation, exactly as in its results. Interest and depreciation are also listed on their own lines below.", "Costs are shown as positive amounts.", "Operating costs + interest + depreciation"),
  operating_profit: g("pl_operating_profit", "Operating profit (EBITDA)", "What the core business earned before interest, depreciation and other income. Same definition on the stock page, quarter results, screener and ratios. For a bank it is income less operating costs, before provisions.", "A company can have a positive operating profit and still lose money after interest and depreciation: compare it with profit before tax.", "Revenue − (Total expenses − Interest − Depreciation)"),
  finance_costs: g("pl_finance_costs", "Interest", "Interest the company paid on its borrowings. Shown as a positive cost."),
  depreciation: g("pl_depreciation", "Depreciation", "The yearly cost of wear on machines, buildings and other assets, and amortisation of intangibles. Shown as a positive cost."),
  profit_before_tax: g("pl_pbt", "Profit before tax", "Profit after every cost and one-off item, before tax. A minus sign means a loss.", undefined, "Operating profit + Other income − Interest − Depreciation + Exceptional items"),
  tax: g("pl_tax", "Tax", "Income tax expense for the period. A minus sign means a tax credit (tax income), for example on past losses."),
  net_profit: g("pl_net_profit", "Net profit", "Profit that belongs to the company's own shareholders, after tax and after the share that belongs to minority holders. A minus sign means a loss.", "EPS is worked out on this same profit.", "Profit before tax − Tax (± share of associates, discontinued operations, minorities)"),
  eps: g("pl_eps", "EPS (₹)", "Net profit for each share. It has the same sign as net profit: a loss gives a negative EPS.", undefined, "Net profit ÷ number of shares"),
};

/** Label shown for a Profit & loss line (the key is stable, the label is the plain-language name). */
export const PL_LABEL: Record<string, string> = { expenses: "Total expenses", operating_profit: "Operating profit (EBITDA)" };

/** One table cell: crore amounts without decimals, EPS with two; both keep their true minus sign. */
export const plCell = (key: string, v: number | null | undefined): string => (v == null ? "—" : key === "eps" ? num(v, 2) : cr(v));
