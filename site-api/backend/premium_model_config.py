"""FinLit v3.6.1 configuration supplied by the project owner.
Group fill values are the supplied 13–14 October 2026 snapshot, not live medians.
"""
MODEL_VERSION = "3.6.10"
BASELINE_VERSION = "3.6.1-simple"
FILL_VERSION = "2026-10-14"
QUARTERS_JUDGED = 10
QUARTERS_STORED = 14
PART_WEIGHTS = {"fundamental": 0.40, "valuation": 0.30, "quality": 0.20, "risk": 0.10}

RISK_W = {"VOLATILITY": 30, "BIGGEST_FALL": 30, "TRADING_VALUE": 20, "PLEDGE": 20}
COMMON_LIMITS = {
    "VOLATILITY": (55, 20), "BIGGEST_FALL": (50, 15), "PLEDGE": (30, 0), "CASH_CONVERSION": (0.4, 1.0),
    "PE_VS_INDUSTRY": (1.6, 0.6), "PE_VS_HISTORY": (1.6, 0.6), "PEG": (2.5, 0.5),
    "PB_VS_INDUSTRY": (1.6, 0.6), "PB_VS_HISTORY": (1.6, 0.6), "EV_EBITDA_VS_INDUSTRY": (1.6, 0.6),
    "DIVIDEND_YIELD": (0.5, 5.0),   # v3.4-U: kept for display; no group weights it any more
}


def group(fund_w, qual_w, val_w, limits):
    lim = dict(COMMON_LIMITS)
    lim.update(limits)
    lim["SALES_CAGR"], lim["PROFIT_CAGR"] = lim["SALES_GROWTH"], lim["PROFIT_GROWTH"]   # v3.4: same limits
    return {"weights": {"fundamental": fund_w, "quality": qual_w, "valuation": val_w, "risk": RISK_W},
            "limits": lim}


# v3.4: 7 Fundamental metrics. SALES_GROWTH / PROFIT_GROWTH = last 12 months; *_CAGR = up to 5 years.
F_STD = {"SALES_STREAK": 20, "PROFIT_STREAK": 20, "SALES_GROWTH": 8, "PROFIT_GROWTH": 10,
         "SALES_CAGR": 12, "PROFIT_CAGR": 15, "MARGIN_CHANGE": 15}
F_CYCLICAL = {"SALES_STREAK": 10, "PROFIT_STREAK": 10, "SALES_GROWTH": 10, "PROFIT_GROWTH": 15,
              "SALES_CAGR": 15, "PROFIT_CAGR": 20, "MARGIN_CHANGE": 20}
F_REALTY = {"SALES_STREAK": 10, "PROFIT_STREAK": 10, "SALES_GROWTH": 12, "PROFIT_GROWTH": 15,
            "SALES_CAGR": 18, "PROFIT_CAGR": 20, "MARGIN_CHANGE": 15}
F_LENDER = {"SALES_STREAK": 20, "PROFIT_STREAK": 20, "SALES_GROWTH": 6, "PROFIT_GROWTH": 10,
            "SALES_CAGR": 9, "PROFIT_CAGR": 15, "LOAN_GROWTH": 20}
F_INSURER = {"SALES_STREAK": 20, "PROFIT_STREAK": 20, "SALES_GROWTH": 8, "PROFIT_GROWTH": 8,
             "SALES_CAGR": 12, "PROFIT_CAGR": 12, "NETWORTH_GROWTH": 20}
V_STD = {"PE_VS_INDUSTRY": 40, "PE_VS_HISTORY": 30, "PEG": 30}
V_LENDER = {"PB_VS_INDUSTRY": 40, "PB_VS_HISTORY": 30, "PE_VS_INDUSTRY": 30, "PEG": 20}   # PEG optional
Q_LENDER = {"GROSS_NPA": 25, "NET_NPA": 25, "CAPITAL_ADEQUACY": 25, "ROA": 25}

GROUPS = {
    "LIGHT": group(F_STD, {"DEBT_TO_EQUITY": 20, "INTEREST_COVER": 20, "ROE": 35, "CASH_CONVERSION": 25}, V_STD,
                   {"SALES_GROWTH": (0, 18), "PROFIT_GROWTH": (0, 20), "MARGIN_CHANGE": (-3, 3),
                    "DEBT_TO_EQUITY": (1.0, 0.1), "INTEREST_COVER": (3, 15), "ROE": (10, 30)}),
    "MFG": group(F_STD, {"DEBT_TO_EQUITY": 25, "INTEREST_COVER": 25, "ROE": 30, "CASH_CONVERSION": 20}, V_STD,
                 {"SALES_GROWTH": (0, 20), "PROFIT_GROWTH": (0, 25), "MARGIN_CHANGE": (-3, 3),
                  "DEBT_TO_EQUITY": (1.5, 0.3), "INTEREST_COVER": (2, 8), "ROE": (8, 22)}),
    "HEAVY": group(F_CYCLICAL, {"DEBT_TO_EQUITY": 30, "INTEREST_COVER": 30, "ROE": 20, "CASH_CONVERSION": 20},
                   {"EV_EBITDA_VS_INDUSTRY": 40, "PB_VS_INDUSTRY": 30, "PE_VS_HISTORY": 30, "PEG": 20},
                   {"SALES_GROWTH": (-5, 15), "PROFIT_GROWTH": (-10, 25), "MARGIN_CHANGE": (-5, 5),
                    "DEBT_TO_EQUITY": (2.0, 0.5), "INTEREST_COVER": (1.5, 6), "ROE": (6, 18)}),
    "UTILITY": group(F_STD, {"DEBT_TO_EQUITY": 25, "INTEREST_COVER": 35, "ROE": 20, "CASH_CONVERSION": 20},
                     {"PB_VS_INDUSTRY": 35, "EV_EBITDA_VS_INDUSTRY": 35, "PE_VS_INDUSTRY": 30, "PEG": 20},  # v3.4-U
                     {"SALES_GROWTH": (0, 15), "PROFIT_GROWTH": (0, 18), "MARGIN_CHANGE": (-3, 3),
                      "DEBT_TO_EQUITY": (3.0, 1.0), "INTEREST_COVER": (1.3, 4), "ROE": (6, 16)}),
    "REALTY": group(F_REALTY, {"DEBT_TO_EQUITY": 35, "INTEREST_COVER": 25, "ROE": 20, "CASH_CONVERSION": 20},
                    {"PB_VS_INDUSTRY": 60, "PE_VS_INDUSTRY": 40, "PEG": 20},
                    {"SALES_GROWTH": (-5, 25), "PROFIT_GROWTH": (-10, 30), "MARGIN_CHANGE": (-5, 5),
                     "DEBT_TO_EQUITY": (1.5, 0.3), "INTEREST_COVER": (1.5, 5), "ROE": (5, 15)}),
    "BANK": group(F_LENDER, Q_LENDER, V_LENDER,
                  {"SALES_GROWTH": (5, 20), "PROFIT_GROWTH": (0, 25), "LOAN_GROWTH": (5, 20),
                   "GROSS_NPA": (6, 1.5), "NET_NPA": (2.5, 0.3), "CAPITAL_ADEQUACY": (12, 18), "ROA": (0.5, 1.8),
                   # Used only when capital adequacy is unavailable.
                   "INTEREST_COVER": (2, 8),
                   # Proposed financial-sector ROE scale for the industry-P/B fallback.
                   "ROE": (8, 18)}),
    "NBFC": group(F_LENDER, Q_LENDER, V_LENDER,
                  {"SALES_GROWTH": (5, 25), "PROFIT_GROWTH": (0, 25), "LOAN_GROWTH": (5, 25),
                   "GROSS_NPA": (6, 1.5), "NET_NPA": (3, 0.5), "CAPITAL_ADEQUACY": (15, 25), "INTEREST_COVER": (2, 8), "ROA": (1.0, 3.5)}),
    "INSURANCE": group(F_INSURER, {"FINANCIAL_LEVERAGE": 50, "ROE": 50},
                       {"PB_VS_INDUSTRY": 50, "PE_VS_INDUSTRY": 25, "PB_VS_HISTORY": 25, "PEG": 20},
                       {"SALES_GROWTH": (5, 20), "PROFIT_GROWTH": (0, 20), "NETWORTH_GROWTH": (5, 20),
                        "SOLVENCY": (1.5, 2.2), "FINANCIAL_LEVERAGE": (20, 5), "ROE": (8, 18)}),
}

POINTS_PER_GOOD_QUARTER = 10
MISS_PENALTY = 5
STREAK_MAGNITUDE_SHARE = 0.20   # v3.2: share of streak points that depends on growth size (0 = v3.1)
TRADING_VALUE_STEPS = [(25, 100), (10, 80), (2, 60), (0.5, 30), (0, 0)]
CAGR_MAX_YEARS = 5
CAGR_PREFERRED_YEARS = (5, 3)   # Owner preference: 5 years, then 3, then available.
CAGR_MIN_YEARS = 1              # At least two consecutive annual observations.
PROFIT_TURNAROUND_POINTS = 70   # v3.6: only when the latest figure is a profit
LOSS_NARROWED_POINTS = 30       # v3.6: still a loss, but smaller than before
CASH_LOSS_POINTS = {"cash_positive": 50, "cash_negative": 0}   # v3.6: cash conversion when 3-year profit <= 0
IC_NOT_APPLICABLE_DE = 0.1      # v3.6: interest cover is dropped when debt/equity is below this
PEG_CORE_GROUPS = ("LIGHT", "MFG", "BANK")    # PEG always used (when P/E exists). BANK added at the owner's request (October 2026): banks such as Kotak lost PEG to the six-quarter rule
# v3.6 fill for a metric with no data: the lower of the group median and 50 (FILL_DEFAULT).
# Medians of actual points across 1,146 NSE stocks (m-cap >= Rs 2,000 Cr), 13-14 Oct 2026; only those below 50 listed.
FILL_DEFAULT = 50.0
FILL_OVERRIDES = {
    "LIGHT": {"PROFIT_STREAK": 34.6, "ROE": 14.5, "PE_VS_INDUSTRY": 26.0, "PEG": 0.0, "BIGGEST_FALL": 48.7},
    "MFG": {"PROFIT_STREAK": 36.1, "ROE": 36.8, "PE_VS_INDUSTRY": 28.3, "PEG": 12.1, "VOLATILITY": 44.0},
    "HEAVY": {"SALES_STREAK": 47.4, "PROFIT_STREAK": 37.6, "ROE": 48.5, "PEG": 25.9, "PB_VS_INDUSTRY": 48.0,
              "EV_EBITDA_VS_INDUSTRY": 47.2},
    "UTILITY": {"SALES_STREAK": 40.0, "PROFIT_STREAK": 16.8, "MARGIN_CHANGE": 45.1, "ROE": 40.7, "PE_VS_INDUSTRY": 11.6,
                "PEG": 0.0, "PB_VS_INDUSTRY": 11.7, "EV_EBITDA_VS_INDUSTRY": 12.8, "VOLATILITY": 47.9, "BIGGEST_FALL": 38.2},
    "REALTY": {"SALES_STREAK": 40.0, "PROFIT_STREAK": 35.0, "MARGIN_CHANGE": 36.1, "INTEREST_COVER": 34.6, "ROE": 30.4,
               "CASH_CONVERSION": 17.6, "PE_VS_INDUSTRY": 33.2, "PEG": 0.0, "PB_VS_INDUSTRY": 22.9, "BIGGEST_FALL": 35.3},
    "BANK": {"SALES_GROWTH": 6.3, "SALES_CAGR": 45.8, "ROA": 39.5},
    "NBFC": {"ROA": 48.5, "PE_VS_INDUSTRY": 46.3},
    "INSURANCE": {"SALES_GROWTH": 31.3, "PROFIT_GROWTH": 27.4, "NETWORTH_GROWTH": 31.7, "ROE": 15.4, "PEG": 0.0},
}
PROVISIONAL_BELOW = 0.80        # data confidence below this -> PROVISIONAL (label at most HEALTHY)
NOT_RATED_BELOW = 0.50          # data confidence below this -> NOT RATED
PROVISIONAL_MIN_QUARTERS = 6    # fewer comparable quarters than this -> PROVISIONAL
PEG_MIN_PROFIT_STREAK = 6             # other groups: PEG only for proven growers (ACTUAL good quarters)
PEG_GROWTH_CAP = 40                   # % growth used in PEG is capped here
FLAG_RED, FLAG_GREEN = 40, 70         # metric points: < 40 red flag, 40-69 amber, >= 70 strength
PLEDGE_ALERT = 25                     # % pledged that triggers a hard alert
VALUE_TRAP = {"limit": 35, "cap": 60}
RATING_BANDS = ((80, "STRONG"), (65, "HEALTHY"), (50, "AVERAGE"), (35, "WEAK"), (0, "POOR"))

# Owner's v3.6.1 loss adjustment, applied before the weak-business cap.
LOSS_ADJUSTED_FUNDAMENTAL = True
LOSS_FAMILY = {"LIGHT": "STANDARD", "MFG": "STANDARD", "UTILITY": "STANDARD",
               "HEAVY": "CYCLICAL", "REALTY": "CYCLICAL",
               "BANK": "FINANCIAL", "NBFC": "FINANCIAL", "INSURANCE": "FINANCIAL"}
LOSS_CAPS = {
    "STANDARD": {"recovering": 55, "loss": 40, "persistent": 30, "chronic": 20},
    "CYCLICAL": {"recovering": 60, "loss": 45, "persistent": 30, "chronic": 20},
    "FINANCIAL": {"recovering": 50, "loss": 35, "persistent": 25, "chronic": 15},
}
DEEP_LOSS_MARGIN = 10
DEEP_LOSS_EXTRA = 10
LOSS_CAP_FLOOR = 10
