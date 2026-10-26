"""Market indices: live prices for every NSE and BSE index, and each index's valuation history (P/E, P/B, dividend yield).

Straight from the data providers, not through the site backend. Every index, its P/E, P/B and yield, and its history come from FinEdge.
When Dhan is set up (finlit/dhan.py), the level, day move and day range of each index in DHAN_INDEX come from Dhan instead while the
market is open (09:15 to 15:30 IST, weekdays); an index Dhan does not answer for, or answers for implausibly, keeps FinEdge's figures,
and outside market hours every index shows FinEdge's last close. Answers are kept in Redis and served at once: index prices are fresh
for a minute while the market is open (15 minutes otherwise), valuation history for six hours; past that the saved copy is still served
instantly while one background call refreshes it, so Dhan is asked at most once a minute however many people are reading. Prices are
public (the strip at the top of every page uses them); valuation history is a Gold tool.
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
import statistics
import time
from datetime import date, datetime, time as dtime, timedelta
from typing import Any, Dict, List, Optional, Tuple
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, Query, Request, Response

from .auth.routes import NO_STORE, Ctx, fail
from .finedge import FinEdgeClient, FinEdgeError
from .premium import premium_ctx
from .background import spawn
from .dhan import DhanClient, DhanError, plausible, to_quote

log = logging.getLogger("finlit.indices")
router = APIRouter(prefix="/api/indices")
IST = ZoneInfo("Asia/Kolkata")
CODE = re.compile(r"^[A-Z0-9]{2,24}$")
KEEP = 7 * 24 * 3600            # how long a saved answer may still be served while a refresh runs
HISTORY_YEARS = 5
# Shown first, in this order: the strip at the top of the site and the key tiles on the dashboard.
KEY = ["NIF50", "SNSXSENSEX", "NIFBAN", "NIFMID100", "NIFSMA100", "NIFIT", "INDVIX"]
DHAN_KEY, DHAN_IDS_KEY = "idx:dhan", "idx:dhan:ids"
DHAN_FRESH = 60                 # seconds between Dhan calls while the market is open
DHAN_MAX_AGE = 180              # a saved Dhan reading older than this is not shown (its refresh is failing): FinEdge's figures are
DHAN_LIMIT = 0.10               # a Dhan level further than this from the last one held is refused for that index
SESSION = (dtime(9, 15), dtime(15, 30))

# Our index (FinEdge code) -> (Dhan security id under IDX_I, Dhan SYMBOL_NAME, the name the site shows), read off Dhan's instrument file
# by hand, one by one: only where Dhan's row is unmistakably the same index. Not matched by similar names at run time, and an entry is used
# only while the stored instrument file still has that id with that symbol on the same exchange, and FinEdge still calls the code by that
# name. Left out on purpose: indices Dhan does not carry (BSE SmallCap, MidCap, LargeCap; NIFTY500 Healthcare ...), FinEdge's stale
# second SENSEX (SNSXBSE30), and BSE rows whose Dhan name differs from ours (Dhan's "BSE Basic Materials" for our "BSE Commodities",
# "BSE Finance" for "BSE Financial Services", "Consumer Discretionary Goods & Services", "BSE India Leaders", "BSE India Technology",
# "BSE Service Sector", "BSE Business Grps Ex Fin Services"), even where the symbol suggests a match.
DHAN_INDEX: Dict[str, Tuple[str, str, str]] = {
    "NIF50": ("13", "NIFTY", "Nifty 50"),   # Dhan: Nifty 50
    "NIFBAN": ("25", "BANKNIFTY", "Nifty Bank"),   # Dhan: Nifty Bank
    "NIFMID100": ("37", "NIFTY MID100 FREE", "NIFTY MIDCAP 100"),   # Dhan: NIFTY Midcap 100
    "NIFSMA100": ("5", "NIFTY SMALLCAP 100", "NIFTY Smallcap 100"),   # Dhan: NIFTY Smallcap 100
    "NIFIT": ("29", "NIFTYIT", "Nifty IT"),   # Dhan: Nifty IT
    "INDVIX": ("21", "INDIA VIX", "INDIA VIX"),   # Dhan: India VIX
    "NIFNEX50": ("38", "NIFTYNXT50", "Nifty Next 50"),   # Dhan: Nifty Next 50
    "NIF100": ("17", "NIFTY 100", "Nifty 100"),   # Dhan: NIFTY 100
    "NIF200": ("18", "NIFTY 200", "Nifty 200"),   # Dhan: NIFTY 200
    "NIF500": ("19", "NIFTY 500", "Nifty 500"),   # Dhan: NIFTY 500
    "NIFMID150": ("1", "NIFTY MIDCAP 150", "Nifty Midcap 150"),   # Dhan: NIFTY Midcap 150
    "NIFSMA250": ("3", "NIFTY SMALLCAP 250", "Nifty smallcap 250"),   # Dhan: NIFTY Smallcap 250
    "NIFSMA50": ("22", "NIFTY SMALLCAP 50", "NIFTY SMALLCAP 50"),   # Dhan: Nifty Smallcap 50
    "NIFMID50": ("20", "NIFTYMCAP50", "Nifty Midcap 50"),   # Dhan: Nifty Mid Cap 50
    "NIFLAR250": ("6", "NIFTY LARGEMID250", "NIFTY LargeMidcap 250"),   # Dhan: Nifty Largemid250
    "NIFMID400": ("7", "NIFTY MIDSMALLCAP 400", "Nifty MidSmallcap 400"),   # Dhan: Nifty MidSmallCap 400
    "NIFMIC250": ("444", "NIFTY MICROCAP250", "NIFTY MICROCAP 250"),   # Dhan: Nifty Microcap 250
    "NIFTOTMAR": ("443", "NIFTY TOTAL MKT", "NIFTY TOTAL MARKET"),   # Dhan: Nifty Total mkt
    "NIFMIDSEL2": ("442", "MIDCPNIFTY", "NIFTY MIDCAP SELECT"),   # Dhan: Nifty Midcap Select
    "NIFFINSER": ("27", "FINNIFTY", "Nifty Financial Services"),   # Dhan: Finnifty
    "NIFAUT": ("14", "NIFTY AUTO", "Nifty Auto"),   # Dhan: NIFTY Auto
    "NIFPRIBAN": ("15", "NIFTY PVT BANK", "Nifty Private Bank"),   # Dhan: NIFTY Private Bank
    "NIFFMC": ("28", "NIFTY FMCG", "Nifty FMCG"),   # Dhan: NIFTY FMCG
    "NIFMED": ("30", "NIFTY MEDIA", "Nifty Media"),   # Dhan: NIFTY Media
    "NIFMET": ("31", "NIFTY METAL", "Nifty Metal"),   # Dhan: NIFTY Metal
    "NIFPHA": ("32", "NIFTY PHARMA", "Nifty Pharma"),   # Dhan: NIFTY Pharma
    "NIFPSUBAN": ("33", "NIFTY PSU BANK", "Nifty PSU Bank"),   # Dhan: NIFTY PSU Bank
    "NIFREA": ("34", "NIFTY REALTY", "Nifty Realty"),   # Dhan: NIFTY Realty
    "NIFENE": ("42", "NIFTY ENERGY", "Nifty Energy"),   # Dhan: NIFTY Energy
    "NIFINF": ("43", "NIFTYINFRA", "Nifty Infrastructure"),   # Dhan: NIFTY Infra
    "NIFMNC": ("44", "NIFTY MNC", "Nifty MNC"),   # Dhan: NIFTY MNC
    "NIFCPS": ("45", "NIFTYCPSE", "Nifty CPSE"),   # Dhan: Nifty CPSE
    "NIFPSE": ("41", "NIFTYPSE", "Nifty PSE"),   # Dhan: Nifty PSE
    "NIFSERSEC": ("46", "NIFTY SERV SECTOR", "Nifty Services Sector"),   # Dhan: NIFTY Services Sector
    "NIFCOM": ("39", "NIFTY COMMODITIES", "Nifty Commodities"),   # Dhan: Nifty Commodities
    "NIFINDCON": ("40", "NIFTY CONSUMPTION", "Nifty India Consumption"),   # Dhan: NIFTY Consumption
    "NIFHEAIND": ("447", "NIFTY HEALTHCARE", "NIFTY HEALTHCARE INDEX"),   # Dhan: Nifty Healthcare
    "NIFCONDUR": ("466", "NIFTY CONSR DURBL", "NIFTY CONSUMER DURABLES"),   # Dhan: Nifty Consumer Durable
    "NIFOILGAS": ("470", "NIFTY OIL AND GAS", "NIFTY OIL & GAS"),   # Dhan: Nifty Oil and Gas
    "NIFMIDHEA": ("471", "NIFTY MIDSML HLTH", "Nifty MidSmall Healthcare"),   # Dhan: Nifty MidSmall Healthcare
    "NIFINDDIG2": ("473", "NIFTY IND DIGITAL", "NIFTY INDIA DIGITAL"),   # Dhan: Nifty India Digital
    "NIFINDMAN": ("474", "NIFTY INDIA MFG", "NIFTY INDIA MANUFACTURING"),   # Dhan: Nifty India Manufacturing
    "NIFINDCORGRO4": ("475", "NIFTY TATA 25 CAP", "Nifty India Corporate Group Index - Tata Group 25% Cap"),   # Dhan: Nifty India Corporate Group Index - Tata Group 25% Cap
    "NIFMULINDMAN": ("476", "NIFTY MULTI MFG", "Nifty500 Multicap India Manufacturing 50:30:20"),   # Dhan: Nifty 500 Multicap India Manufacturing 50:30:20
    "NIFMULINF503": ("477", "NIFTY MULTI INFRA", "Nifty500 Multicap Infrastructure 50:30:20"),   # Dhan: Nifty 500 Multicap Infrastructure 50:30:20
    "NIFESG": ("478", "NIFTY100 ESG", "NIFTY100 ESG"),   # Dhan: Nifty100 ESG
    "NIFESGSECLEA": ("479", "NIFTY100ESGSECLDR", "Nifty100 ESG Sector Leaders"),   # Dhan: Nifty100 ESG Sector Leaders
    "NIFENHESG": ("832", "Nifty100 Enh ESG", "NIFTY100 ENHANCED ESG"),   # Dhan: Nifty 100 Enhanced ESG
    "NIFMOM30": ("480", "NIFTY200MOMENTM30", "Nifty200 Momentum 30"),   # Dhan: Nifty 200 Momentum 30
    "NIFALP302": ("481", "NIFTY200 ALPHA 30", "NIFTY200 ALPHA 30"),   # Dhan: Nifty 200 Alpha 30
    "NIFALPLOWVOL": ("482", "NIFTY ALPHALOWVOL", "NIFTY ALPHA LOW-VOLATILITY 30"),   # Dhan: Nifty Alpha Low Volatility 30
    "NIFMIDMOM50": ("483", "NIFTYM150MOMNTM50", "Nifty Midcap150 Momentum 50"),   # Dhan: Nifty Midcap150 Momentum 50
    "NIFDIVPOI": ("484", "NIFTY50 DIV POINT", "NIFTY50 Dividend Points"),   # Dhan: Nifty 50 Dividend Points
    "NIFEQUWEI2": ("485", "NIFTY50 EQL WGT", "Nifty50 Equal Weight"),   # Dhan: Nifty 50 Equal Weight
    "NIFPR1XINV": ("486", "NIFTY50 PR 1X INV", "Nifty50 PR 1x Inverse"),   # Dhan: Nifty 50 PR 1x Inverse
    "NIFPR2XLEV": ("487", "NIFTY50 PR 2X LEV", "Nifty50 PR 2x Leverage"),   # Dhan: Nifty 50 PR 2x Leverage
    "NIFTR1XINV": ("488", "NIFTY50 TR 1X INV", "Nifty50 TR 1x Inverse"),   # Dhan: Nifty 50 TR 1x Inverse
    "NIFTR2XLEV": ("489", "NIFTY50 TR 2X LEV", "Nifty50 TR 2x Leverage"),   # Dhan: Nifty 50 TR 2x Leverage
    "NIFQUA30": ("490", "NIFTY200 QUALTY30", "NIFTY200 QUALITY 30"),   # Dhan: Nifty 200 Quality 30
    "NIFEVNEWAGEA": ("491", "NIFTY EV", "Nifty EV & New Age Automotive"),   # Dhan: Nifty EV and New Age Auto
    "NIFSMAMOMQUA": ("492", "NIFTYSML250MQ 100", "Nifty Smallcap250 Momentum Quality 100"),   # Dhan: Nifty Smallcap250 Momentum Quality 100
    "NIFINDDEF": ("493", "NIFTY IND DEFENCE", "NIFTY INDIA DEFENCE"),   # Dhan: Nifty India Defence
    "NIFTOP10EQUW": ("494", "NIFTY TOP 10 EW", "Nifty Top 10 Equal Weight"),   # Dhan: Nifty Top 10 Equal Weight
    "NIFFINSEREXB": ("495", "NIFTY FINSEREXBNK", "NIFTY FINANCIAL SERVICES EX-BANK"),   # Dhan: Nifty Financial Services Ex Bank
    "NIFVAL30": ("496", "NIFTY200 VALUE 30", "Nifty200 Value 30"),   # Dhan: Nifty 200 Value 30
    "NIFMULMOMQUA": ("497", "NIFTY MULTI MQ 50", "Nifty500 Multicap Momentum Quality 50"),   # Dhan: Nifty 500 Multicap Momentum Quality 50
    "NIFMOM50": ("498", "NIFTY500MOMENTM50", "Nifty500 Momentum 50"),   # Dhan: Nifty 500 Momentum 50
    "NIFALPQUALOW": ("801", "Nifty AQL 30", "NIFTY ALPHA QUALITY LOW-VOLATILITY 30"),   # Dhan: Nifty Alpha Quality Low Volatility 30
    "NIFALPQUAVAL": ("802", "Nifty AQLV 30", "NIFTY ALPHA QUALITY VALUE LOW-VOLATILITY 30"),   # Dhan: Nifty Alpha Quality Value Low Vol 30
    "NIFCAPMAR": ("803", "Nifty Capital Mkt", "Nifty Capital Markets"),   # Dhan: Nifty Capital Markets
    "NIFCORHOU": ("804", "Nifty CoreHousing", "Nifty Core Housing"),   # Dhan: Nifty Core Housing
    "NIFINDSEL5CO": ("805", "Nifty Corp MAATR", "NIFTY INDIA SELECT 5 CORPORATE GROUPS (MAATR)"),   # Dhan: Nifty India Select 5 Corp Grps (MAATR)
    "NIFHIGBET50": ("813", "Nifty HighBeta 50", "Nifty High Beta 50"),   # Dhan: Nifty High Beta 50
    "NIFHOU": ("814", "Nifty Housing", "NIFTY HOUSING"),   # Dhan: Nifty Housing
    "NIFINDTOU": ("815", "Nifty Ind Tourism", "Nifty India Tourism"),   # Dhan: Nifty India Tourism
    "NIFIPO": ("816", "Nifty IPO", "NIFTY IPO"),   # Dhan: Nifty IPO
    "NIFMOB": ("818", "Nifty Mobility", "NIFTY MOBILITY"),   # Dhan: Nifty Mobility
    "NIFMIDFINSER": ("819", "Nifty MS Fin Serv", "Nifty MidSmall Financial Services"),   # Dhan: Nifty Mid Small Financial Services
    "NIFMIDINDCON": ("820", "Nifty MS Ind Cons", "NIFTY MIDSMALL INDIA CONSUMPTION"),   # Dhan: Nifty Mid Small India Consumption
    "NIFMIDITTEL": ("821", "Nifty MS IT Telcm", "Nifty MidSmall IT & Telecom"),   # Dhan: Nifty Mid Small IT Telecom
    "NIFINDNEWAGE": ("822", "Nifty New Consump", "NIFTY INDIA NEW AGE CONSUMPTION"),   # Dhan: Nifty India New Age Consumption
    "NIFNONCYCCON": ("823", "Nifty NonCyc Cons", "NIFTY NON-CYCLICAL CONSUMER"),   # Dhan: Nifty Non Cyclical Consumer
    "NIFQUALOWVOL": ("824", "Nifty Qlty LV 30", "NIFTY QUALITY LOW-VOLATILITY 30"),   # Dhan: Nifty Quality Low Volatility 30
    "NIFRUR": ("825", "Nifty Rural", "NIFTY RURAL"),   # Dhan: Nifty Rural
    "NIFSHA25": ("826", "Nifty Shariah 25", "Nifty Shariah 25"),   # Dhan: Nifty Shariah 25
    "NIFSMAQUA50": ("827", "Nifty Sml250 Q50", "Nifty Smallcap250 Quality 50"),   # Dhan: Nifty Smallcap 250 Quality 50
    "NIFTOP15EQUW": ("828", "Nifty Top 15 EW", "NIFTY TOP 15 EQUAL WEIGHT"),   # Dhan: Nifty Top 15 Equal Weight
    "NIFTOP20EQUW": ("829", "Nifty Top 20 EW", "NIFTY TOP 20 EQUAL WEIGHT"),   # Dhan: Nifty Top 20 Equal Weight
    "NIFTRALOG": ("830", "Nifty Trans Logis", "NIFTY TRANSPORTATION & LOGISTICS"),   # Dhan: Nifty Transportation Logistics
    "NIFALP30": ("831", "Nifty100 Alpha 30", "NIFTY100 ALPHA 30"),   # Dhan: Nifty 100 Alpha 30
    "NIFSHA": ("833", "Nifty50 Shariah", "Nifty50 Shariah"),   # Dhan: Nifty 50 Shariah
    "NIFEQUWEI3": ("834", "Nifty500 EW", "Nifty500 Equal Weight"),   # Dhan: Nifty 500 Equal Weight
    "NIFLAREQUCAP": ("835", "Nifty500 LMS Eql", "Nifty500 LargeMidSmall Equal-Cap Weighted"),   # Dhan: Nifty 500 Lrg Mid Sml Equal Wtd
    "NIFLOWVOL502": ("836", "Nifty500 LowVol50", "NIFTY500 LOW VOLATILITY 50"),   # Dhan: Nifty 500 Low Volatility 50
    "NIFMULMQV50": ("837", "Nifty500 MQVLv50", "NIFTY500 MULTIFACTOR MQVLV 50"),   # Dhan: Nifty 500 Multifactor MQVLv 50
    "NIFQUA50": ("838", "Nifty500 Qlty50", "NIFTY500 QUALITY 50"),   # Dhan: Nifty 500 Quality 50
    "NIFSHA2": ("839", "Nifty500 Shariah", "NIFTY500 SHARIAH"),   # Dhan: Nifty 500 Shariah
    "NIFVAL50": ("840", "Nifty500 Value 50", "NIFTY500 VALUE 50"),   # Dhan: Nifty 500 Value 50
    "NIFMIDMOMQUA": ("841", "NiftyMS400 MQ 100", "Nifty MidSmallcap400 Momentum Quality 100"),   # Dhan: Nifty Mid Small 400 MQ 100
    "NIFEQUWEI": ("10", "NIFTY100 EQUAL WEIGHT", "NIFTY100 EQUAL WEIGHT"),   # Dhan: Nifty100 Equal Weight
    "NIFLOWVOL30": ("11", "NIFTY100 LOW VOLATILITY 30", "NIFTY100 LOW VOLATILITY 30"),   # Dhan: Nifty 100 Low Volatility 30
    "NIFALP50": ("12", "NIFTY ALPHA 50", "Nifty Alpha 50"),   # Dhan: NIFTY ALPHA 50
    "NIFMIDLIQ15": ("16", "NIFTY MID LIQ 15", "Nifty Midcap Liquid 15"),   # Dhan: Nifty Midcap Liquid 15
    "NIFLIQ15": ("35", "NIFTY100 LIQ 15", "Nifty100 Liquid 15"),   # Dhan: Nifty100 Liquid 15
    "NIFDIVOPP502": ("284", "NIFTY DIV OPPS 50", "NIFTY DIVIDEND OPPORTUNITIES 50"),   # Dhan: Nifty Dividend Opportunities 50
    "NIFGROSEC15": ("285", "NIFTY GROWSECT 15", "Nifty Growth Sectors 15"),   # Dhan: Nifty Growth Sectors 15
    "NIFVAL20": ("286", "NIFTY50 VALUE 20", "Nifty50 Value 20"),   # Dhan: Nifty50 Value 20 Index
    "NIFQUA302": ("287", "NIFTY100 QUALTY30", "NIFTY100 QUALITY 30"),   # Dhan: Nifty100 Qualty30
    "NIFMIDQUA50": ("446", "NIFTY M150 QLTY50", "NIFTY MIDCAP150 QUALITY 50"),   # Dhan: NIFTY Midcap150 Quality 50
    "NIFFINSER255": ("469", "NIFTY FINSRV25 50", "Nifty Financial Services 25/50"),   # Dhan: Nifty Financial Services 25/50
    "NIFMUL502": ("467", "NIFTY500 MULTICAP", "NIFTY500 MULTICAP 50:25:25"),   # Dhan: Nifty 500 Multicap 50:25:25
    "SNSXSENSEX": ("51", "SENSEX", "BSE SENSEX"),   # Dhan: Sensex
    "SNSXBANKEX": ("69", "BANKEX", "BSE BANKEX"),   # Dhan: BSE BANKEX
    "SNSXBSE100": ("65", "BSE100", "BSE 100"),   # Dhan: BSE 100
    "SNSXBSE200": ("66", "BSE200", "BSE 200"),   # Dhan: BSE 200
    "SNSXBSE500": ("67", "BSE500", "BSE 500"),   # Dhan: BSE 500
    "SNSX50": ("83", "SNSX50", "BSE SENSEX 50"),   # Dhan: BSE Sensex 50
    "SNSXSNSXT50": ("310", "SNXT50", "BSE SENSEX Next 50"),   # Dhan: Sensex Next 50 Index
    "SNSXSNSXN30": ("98", "SNXN30", "BSE SENSEX NEXT 30"),   # Dhan: BSE Sensex Next 30
    "SNSX60": ("860", "SNSX60", "BSE SENSEX SIXTY"),   # Dhan: BSE Sensex 60
    "SNSXSS6535": ("861", "SS6535", "BSE SENSEX SIXTY 65:35"),   # Dhan: BSE Sensex Sixty 65:35
    "SNSXSENEQW": ("859", "SENEQW", "BSE SENSEX EQUAL WEIGHT"),   # Dhan: BSE Sensex Equal Weight
    "SNSXAUTO": ("68", "AUTO", "BSE AUTO"),   # Dhan: BSE Auto
    "SNSXBSECD": ("70", "BSE CD", "BSE CONSUMER DURABLES"),   # Dhan: BSE Consumer Durables
    "SNSXBSECG": ("71", "BSE CG", "BSE CAPITAL GOODS"),   # Dhan: BSE Capital Goods
    "SNSXBSEFMCG": ("72", "BSEFMC", "BSE Fast Moving Consumer Goods"),   # Dhan: BSE FMCG
    "SNSXBSEHC": ("73", "BSE HC", "BSE Healthcare"),   # Dhan: BSE Healthcare
    "SNSXBSEIT": ("74", "BSE IT", "BSE Information Technology"),   # Dhan: BSE IT
    "SNSXMETAL": ("75", "METAL", "BSE METAL"),   # Dhan: BSE Metals
    "SNSXOILGAS": ("76", "OILGAS", "BSE OIL & GAS"),   # Dhan: BSE Oil and Gas
    "SNSXPOWER": ("77", "POWER", "BSE POWER"),   # Dhan: BSE Power
    "SNSXBSEPSU": ("78", "BSEPSU", "BSE PSU"),   # Dhan: BSE PSU
    "SNSXREALTY": ("79", "REALTY", "BSE REALTY"),   # Dhan: BSE Realty
    "SNSXTECK": ("80", "TECK", "BSE TECK"),   # Dhan: BSE TECk
    "SNSXBSEPBI": ("52", "BSEPBI", "BSE Private Banks Index"),   # Dhan: BSE Private Banks Index
    "SNSXESG100": ("53", "ESG100", "BSE 100 ESG Index"),   # Dhan: BSE 100 ESG
    "SNSXLCTMCI": ("54", "LCTMCI", "BSE 100 LargeCap TMC Index"),   # Dhan: BSE 100 LargeCap TMC Index
    "SNSXLMI250": ("55", "LMI250", "BSE 250 LargeMidCap Index"),   # Dhan: BSE 250 Large Mid
    "SNSXMID150": ("56", "MID150", "BSE 150 MidCap Index"),   # Dhan: BSE 150 MidCap
    "SNSXMSL400": ("57", "MSL400", "BSE 400 MidSmallCap Index"),   # Dhan: BSE 400 Mid Small
    "SNSXSML250": ("309", "SML250", "BSE 250 SmallCap Index"),   # Dhan: BSE 250 Small Cap
    "SNSXBSEDSI": ("2", "BSEDSI", "BSE Dividend Stability Index"),   # Dhan: BSE DSI
    "SNSXBSEEVI": ("4", "BSEEVI", "BSE Enhanced Value Index"),   # Dhan: BSE Enhanced Value Index
    "SNSXBSELVI": ("23", "BSELVI", "BSE Low Volatility Index"),   # Dhan: BSELVI
    "SNSXBSEMOI": ("36", "BSEMOI", "BSE Momentum Index"),   # Dhan: BSE Momentum Index
    "SNSXBSEQUI": ("81", "BSEQUI", "BSE Quality Index"),   # Dhan: BSEQUI
    "SNSXSPBSAIP": ("84", "ALLCAP", "BSE AllCap"),   # Dhan: BSE AllCap
    "SNSXINFRA": ("85", "INFRA", "BSE India Infrastructure Index"),   # Dhan: BSE India Infrastructure Index
    "SNSXCPSE": ("86", "CPSE", "BSE CPSE"),   # Dhan: BSE CPSE
    "SNSXMFG": ("87", "MFG", "BSE India Manufacturing Index"),   # Dhan: BSE India Mfg
    "SNSXUTILS": ("88", "UTILS", "BSE Utilities"),   # Dhan: BSE Utilities
    "SNSXTELCOM": ("89", "TELCOM", "BSE Telecommunication"),   # Dhan: BSE Telecom
    "SNSXSMLSEL": ("90", "SMLSEL", "BSE SmallCap Select Index"),   # Dhan: BSE SmallCap Select Index
    "SNSXMIDSEL": ("95", "MIDSEL", "BSE MidCap Select Index"),   # Dhan: BSE MidCap Select Index
    "SNSXENERGY": ("92", "ENERGY", "BSE Energy"),   # Dhan: BSE Energy
    "SNSXINDSTR": ("97", "INDSTR", "BSE Industrials"),   # Dhan: BSE Industrials
    "SNSXCAPINS": ("99", "CAPINS", "BSE CAPITAL MARKETS & INSURANCE"),   # Dhan: BSE Capital Markets & Insurance
    "SNSXBHRT22": ("301", "BHRT22", "BSE Bharat 22 Index"),   # Dhan: BSE Bharat 22 Index
    "SNSXBSEIPO": ("303", "BSEIPO", "BSE IPO"),   # Dhan: BSE IPO
    "SNSXSMEIPO": ("304", "SMEIPO", "BSE SME IPO"),   # Dhan: BSE SME IPO
    "SNSXDFRGRI": ("307", "DFRGRI", "BSE Diversified Financials Revenue Growth Index"),   # Dhan: DFRGRI
    "SNSX200EQW": ("842", "200EQW", "BSE 200 EQUAL WEIGHT INDEX"),   # Dhan: BSE 200 Equal Weight
    "SNSXBS1000": ("844", "BS1000", "BSE 1000"),   # Dhan: BSE 1000
    "SNSXFOCIT": ("850", "FOCIT", "BSE Focused IT"),   # Dhan: BSE Focused IT
    "SNSXFOCMID": ("851", "FOCMID", "BSE FOCUSED MIDCAP"),   # Dhan: BSE Focused Midcap
    "SNSXIND150": ("852", "IND150", "BSE India 150"),   # Dhan: BSE India 150
    "SNSXPOWENE": ("855", "POWENE", "BSE POWER & ENERGY"),   # Dhan: BSE Power Energy
    "SNSXPRECON": ("856", "PRECON", "BSE PREMIUM CONSUMPTION"),   # Dhan: BSE Premium Consumption
    "SNSXPSUBNK": ("857", "PSUBNK", "BSE PSU BANK"),   # Dhan: BSE PSU Bank
    "SNSXSELIPO": ("858", "SELIPO", "BSE SELECT IPO"),   # Dhan: BSE Select IPO
}

SECTOR = re.compile(r"\b(bank|it|pharma|auto|fmcg|metal|realty|energy|media|financial|fin serv|healthcare|oil|gas|consumer durables|chemicals|"
                    r"infra|commodit|capital goods|telecom|utilities|power|industrials|services sector|private bank|psu bank|insurance|"
                    r"cement|construction|textile|teck|tech|consumption|manufacturing|transport|logistics|defence|housing|rural|digital)\b", re.I)
BROAD = re.compile(r"^(nifty ?(50|100|200|500|next 50|midcap|smallcap|microcap|largemidcap|total market|midsmallcap|mid ?small)|"
                   r"bse (sensex|100|200|500|midcap|smallcap|largecap|allcap|large ?cap|mid ?cap|small ?cap|sensex next|150|250|400|1000)|"
                   r"nifty mid|nifty small|nifty large|nifty500|nifty total)", re.I)


def market_open(now: Optional[datetime] = None) -> bool:
    """Pre-open to the end of the closing session: how often FinEdge's figures are refreshed."""
    t = now or datetime.now(IST)
    return t.weekday() < 5 and (9, 0) <= (t.hour, t.minute) <= (15, 45)


def session_open(now: Optional[datetime] = None) -> bool:
    """The normal market, 09:15 to 15:30 IST on weekdays: when Dhan is asked, and what "market open" means on the site."""
    t = (now or datetime.now(IST)).astimezone(IST)
    return t.weekday() < 5 and SESSION[0] <= t.time() <= SESSION[1]


def exchange_of(code: str) -> str:
    return "BSE" if code.startswith("SNSX") else "NSE"


def group_of(name: str, code: str) -> str:
    if code == "INDVIX" or "vix" in name.lower():
        return "Volatility"
    if BROAD.match(name.strip()) and not SECTOR.search(name):
        return "Broad market"
    if SECTOR.search(name):
        return "Sector"
    return "Strategy & theme"


def _num(v: Any, zero_is_none: bool = False) -> Optional[float]:
    if v is None or isinstance(v, bool):
        return None
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    if f != f or (zero_is_none and f == 0):
        return None
    return f


def shape_feed(payload: Any) -> Dict[str, Any]:
    rows = payload if isinstance(payload, list) else next((v for v in (payload or {}).values() if isinstance(v, list)), [])
    items = []
    for r in rows:
        if not isinstance(r, dict):
            continue
        code, name = str(r.get("index_symbol") or "").strip().upper(), " ".join(str(r.get("index_name") or "").split())
        if not code or not name:
            continue
        items.append({"code": code, "name": name, "group": group_of(name, code), "exchange": exchange_of(code),
                      "close": _num(r.get("close_price")), "changePct": _num(r.get("change_pct")), "points": _num(r.get("points_change")),
                      "open": _num(r.get("open_price")), "high": _num(r.get("high_price")), "low": _num(r.get("low_price")),
                      "pe": _num(r.get("pe"), True), "pb": _num(r.get("pb"), True), "divYield": _num(r.get("div_yield"), True),
                      "date": str(r.get("quote_date") or "")[:10] or None})
    order = {c: i for i, c in enumerate(KEY)}
    items.sort(key=lambda x: (order.get(x["code"], len(KEY)), x["exchange"] != "NSE", x["name"].lower()))
    as_of = max((x["date"] for x in items if x["date"]), default=None)
    return {"items": items, "key": [c for c in KEY if c in {x["code"] for x in items}], "asOf": as_of}


def _stats(values: List[float]) -> Optional[Dict[str, float]]:
    if len(values) < 2:
        return None
    now = values[-1]
    return {"now": now, "median": statistics.median(values), "mean": statistics.fmean(values), "sd": statistics.pstdev(values),
            "min": min(values), "max": max(values), "pctile": round(100 * sum(v <= now for v in values) / len(values), 1), "n": len(values)}


def shape_history(payload: Any, years: int) -> Dict[str, Any]:
    rows = (payload or {}).get("rows") if isinstance(payload, dict) else payload
    out = []
    for r in rows or []:
        d = str((r or {}).get("quote_date") or "")[:10]
        if len(d) != 10:
            continue
        out.append({"d": d, "pe": _num(r.get("pe"), True), "pb": _num(r.get("pb"), True), "dy": _num(r.get("div_yield"), True)})
    out.sort(key=lambda x: x["d"])
    if out:
        cut = (date.fromisoformat(out[-1]["d"]) - timedelta(days=round(365.25 * years))).isoformat()
        out = [x for x in out if x["d"] >= cut]
    stats = {k: _stats([x[k] for x in out if x[k] is not None]) for k in ("pe", "pb", "dy")}
    return {"rows": out, "stats": stats, "from": out[0]["d"] if out else None, "to": out[-1]["d"] if out else None}


def shape_levels(payload: Any, years: int) -> Dict[str, Any]:
    """Daily closing level of an index (points), oldest first, for up to `years` back from its latest day."""
    rows = (payload or {}).get("rows") if isinstance(payload, dict) else payload
    out = []
    for r in rows or []:
        d = str((r or {}).get("quote_date") or "")[:10]
        c = _num((r or {}).get("close_price"), True)
        if len(d) == 10 and c is not None:
            out.append({"d": d, "c": c})
    out.sort(key=lambda x: x["d"])
    if out:
        cut = (date.fromisoformat(out[-1]["d"]) - timedelta(days=round(365.25 * years))).isoformat()
        out = [x for x in out if x["d"] >= cut]
    return {"rows": out, "from": out[0]["d"] if out else None, "to": out[-1]["d"] if out else None}


# ---------------------------------------------------------------- provider + cache

def _client(app) -> FinEdgeClient:
    c = getattr(app.state, "index_client", None)
    if c is None:
        c = app.state.index_client = FinEdgeClient(app.state.settings)
    return c


async def _fetch_feed(app) -> Dict[str, Any]:
    return shape_feed(await _client(app).get("/index/market-price/daily-feed", {}, timeout=20, retries=1))


async def _fetch_history(app, code: str) -> Any:
    today = datetime.now(IST).date()
    return await _client(app).get("/index/valuation/historical", {"index_symbol": code, "from_date": (today - timedelta(days=round(365.25 * HISTORY_YEARS) + 7)).isoformat(),
                                                                   "to_date": today.isoformat()}, timeout=25, retries=1)


async def _fetch_levels(app, code: str, years: int = HISTORY_YEARS) -> Any:
    today = datetime.now(IST).date()
    return await _client(app).get("/index/market-price/historical", {"index_symbol": code, "from_date": (today - timedelta(days=round(365.25 * years) + 7)).isoformat(),
                                                                      "to_date": today.isoformat()}, timeout=25, retries=1)


async def _cached(app, key: str, fresh: float, fetch, wait: bool = True) -> Optional[Dict[str, Any]]:
    """Saved copy at once (refreshed behind the scenes once it is older than `fresh` seconds); the provider is asked only when nothing is saved,
    and then waited for unless `wait` is false (the first visitor gets None while the copy is made)."""
    redis = app.state.store.redis
    try:
        raw = await redis.get(key)
    except Exception:
        raw = None
    if raw:
        hit = json.loads(raw)
        if time.time() - hit["t"] > fresh:
            spawn(_refresh(app, key, fetch))
        return hit["v"]
    if not wait:
        spawn(_refresh(app, key, fetch))
        return None
    return await _refresh(app, key, fetch, wait=True)


async def _refresh(app, key: str, fetch, wait: bool = False) -> Optional[Dict[str, Any]]:
    redis = app.state.store.redis
    try:
        if not await redis.set(key + ":lock", "1", nx=True, ex=30):
            if not wait:
                return None
            for _ in range(60):   # another request is already asking the provider: use its answer
                await asyncio.sleep(0.25)
                raw = await redis.get(key)
                if raw:
                    return json.loads(raw)["v"]
    except Exception:
        pass
    try:
        value = await fetch()
    except FinEdgeError as exc:
        log.warning("index data not refreshed (%s): %s", key, exc)
        value = None
    try:
        if value is not None:
            await redis.set(key, json.dumps({"t": time.time(), "v": value}), ex=KEEP)
        await redis.delete(key + ":lock")
    except Exception:
        pass
    return value


# ---------------------------------------------------------------- Dhan: live levels for the mapped indices

def _dhan(app) -> Optional[DhanClient]:
    c = getattr(app.state, "index_dhan", None)
    if c is None:
        if not getattr(app.state.settings, "dhan_client_id", ""):
            return None
        c = app.state.index_dhan = DhanClient(app.state.settings, app.state.store.redis)
    return c if c.configured else None


def confirm(rows) -> Tuple[Dict[str, str], List[str]]:
    """The DHAN_INDEX entries the stored instrument file confirms ({our code: security id}), and the codes it does not: the id must be
    there once, on the index's own exchange, with the same Dhan symbol (an id Dhan has given to another index is not followed)."""
    by_id: Dict[str, List[Tuple[str, str]]] = {}
    for r in rows:
        by_id.setdefault(str(r["security_id"]), []).append((r["exch"], r["symbol"]))
    ok: Dict[str, str] = {}
    off: List[str] = []
    for code, (sid, sym, _) in DHAN_INDEX.items():
        if by_id.get(sid) == [(exchange_of(code), sym)]:
            ok[code] = sid
        else:
            off.append(code)
    return ok, off


async def _dhan_ids(app) -> Dict[str, Any]:
    """{"ids": confirmed mapping, "probe": RELIANCE's NSE security id}, kept in Redis for six hours so the database is not asked each minute
    (the daily instrument load clears it)."""
    redis = app.state.store.redis
    try:
        raw = await redis.get(DHAN_IDS_KEY)
        if raw:
            return json.loads(raw)
    except Exception:
        pass
    async with app.state.store.pool.acquire() as conn:
        rows = await conn.fetch("SELECT exch, security_id, symbol FROM dhan_indices")
        probe = await conn.fetchval("SELECT security_id FROM dhan_instruments WHERE exch = 'NSE' AND symbol = 'RELIANCE' AND series = 'EQ' LIMIT 1")
    ids, off = confirm(rows)
    if rows and off:
        log.warning("Dhan's instrument file does not confirm %d mapped indices (%s): they keep FinEdge's figures", len(off), ", ".join(off[:20]))
    out = {"ids": ids, "probe": probe}
    try:
        await redis.set(DHAN_IDS_KEY, json.dumps(out), ex=6 * 3600 if rows else 600)
    except Exception:
        pass
    return out


def readings(raw: Dict[Tuple[str, str], dict], ids: Dict[str, str], probe: Optional[str], feed: Optional[Dict[str, Any]],
             prev: Optional[Dict[str, Any]], now: datetime) -> Dict[str, dict]:
    """Dhan's answer, index by index, as the figures to show, keeping only what passes every check:
      * FinEdge still names the code as the mapping does (and so holds a value to compare with);
      * a level above zero, from today's session: its own update time if Dhan sends one, else RELIANCE's last trade must be today
        (an exchange holiday on a weekday, or a feed stuck on yesterday, falls back);
      * within 10% of the last level we hold: today's earlier Dhan reading, else FinEdge's.
    The day's move is Dhan's net change (level minus the previous close), as for stocks (dhan.to_quote)."""
    today = now.date().isoformat()
    held = {x["code"]: x for x in (feed or {}).get("items") or []}
    last = (prev or {}).get("q") or {} if str((prev or {}).get("t") or "")[:10] == today else {}
    p = to_quote(raw.get(("NSE_EQ", str(probe))) or {}) if probe else {}
    trading = bool(p.get("asOf")) and p["asOf"][:10] == today
    out: Dict[str, dict] = {}
    skipped: Dict[str, List[str]] = {}
    for code, sid in ids.items():
        row, q = held.get(code), to_quote(raw.get(("IDX_I", sid)) or {})
        why = None
        if row is None or row["name"].casefold() != DHAN_INDEX[code][2].casefold():
            why = "name"
        elif not q:
            why = "no level"
        elif (q["asOf"][:10] != today) if q["asOf"] else not trading:
            why = "not today"
        else:
            ref = (last.get(code) or {}).get("close") or row.get("close")
            if ref and not plausible({"price": q["price"]}, {"price": ref}, DHAN_LIMIT):
                log.warning("Dhan's %s for %s is more than 10%% from the %s held; FinEdge's figures are shown", q["price"], code, ref)
                why = "implausible"
        if why:
            skipped.setdefault(why, []).append(code)
            continue
        out[code] = {"close": q["price"], "points": q["change"], "changePct": q["changePct"], "open": q["open"], "high": q["high"], "low": q["low"],
                     "time": q["asOf"] or now.isoformat(timespec="seconds"), "date": today}
    if skipped:
        log.info("Dhan index levels not used: %s", "; ".join(f"{k} {len(v)} ({', '.join(v[:8])})" for k, v in skipped.items()))
    return out


async def _fetch_dhan(app) -> Dict[str, Any]:
    """One /marketfeed/quote call for every confirmed index (segment IDX_I) and RELIANCE, then readings(). Never raises: a failure is saved
    as no readings, so every index shows FinEdge's figures until the next try a minute later."""
    now = datetime.now(IST)
    out: Dict[str, Any] = {"t": now.isoformat(timespec="seconds"), "q": {}}
    redis = app.state.store.redis
    try:
        prev = json.loads(raw)["v"] if (raw := await redis.get(DHAN_KEY)) else None
        if (prev or {}).get("closed") == now.date().isoformat():
            return prev                                               # the exchange is shut today: no more calls until tomorrow
        dc, m = _dhan(app), await _dhan_ids(app)
        if dc is None or not m["ids"]:
            return {**out, "error": "no confirmed index mapping (instrument file not loaded yet?)"}
        feed = json.loads(raw)["v"] if (raw := await redis.get("idx:feed")) else None
        keys = [("IDX_I", sid) for sid in sorted(set(m["ids"].values()), key=int)] + ([("NSE_EQ", str(m["probe"]))] if m["probe"] else [])
        got = await dc.quotes(keys)                                   # about 170 instruments: one call
    except DhanError as e:
        log.warning("Dhan index levels unavailable, FinEdge's are shown: %s", e)
        return {**out, "error": str(e)}
    except Exception as e:
        log.exception("Dhan index levels failed, FinEdge's are shown")
        return {**out, "error": type(e).__name__}
    out["q"] = readings(got, m["ids"], m["probe"], feed, prev, now)
    p = to_quote(got.get(("NSE_EQ", str(m["probe"]))) or {}) if m["probe"] else {}
    if not out["q"] and p.get("asOf") and p["asOf"][:10] < out["t"][:10] and now.time() >= dtime(9, 30):
        out["closed"] = out["t"][:10]                                 # nothing traded by 09:30: a weekday holiday
    return out


def overlay(feed: Dict[str, Any], dh: Optional[Dict[str, Any]], now: datetime) -> Dict[str, Any]:
    """The FinEdge feed with Dhan's level, move and day range in place for each index that has a reading (only during the session, and only
    from a reading at most three minutes old). P/E, P/B and yield stay FinEdge's, dated by valDate; `source` says which provider each
    row's level is from and `time` when Dhan last updated it."""
    fresh = dh and session_open(now) and (now - datetime.fromisoformat(dh["t"])).total_seconds() <= DHAN_MAX_AGE
    q = (dh.get("q") or {}) if fresh else {}
    items = []
    for x in feed["items"]:
        r = q.get(x["code"])
        if r:
            items.append({**x, "close": r["close"], "points": r["points"], "changePct": r["changePct"], "open": r["open"], "high": r["high"],
                          "low": r["low"], "date": r["date"], "time": r["time"], "valDate": x["date"], "source": "dhan"})
        else:
            items.append({**x, "time": None, "valDate": x["date"], "source": "finedge"})
    live = [x for x in items if x["code"] in feed["key"] and x["source"] == "dhan"]
    return {**feed, "items": items, "asOf": max((x["date"] for x in items if x["date"]), default=None), "live": bool(live)}


@router.get("")
async def indices(request: Request) -> Response:
    """Every index with today's level, move and valuation; the key indices first. Dhan's live levels where it has them during the session."""
    app = request.app
    fresh = 60 if market_open() else 900
    data = await _cached(app, "idx:feed", fresh, lambda: _fetch_feed(app))
    if data is None:
        raise fail(502, "provider_unavailable", "Index prices are not available right now. Please try again in a moment.")
    dh = await _cached(app, DHAN_KEY, DHAN_FRESH, lambda: _fetch_dhan(app), wait=False) if session_open() and _dhan(app) is not None else None
    return Response(json.dumps({**overlay(data, dh, datetime.now(IST)), "marketOpen": session_open()}), media_type="application/json",
                    headers={"Cache-Control": "public, max-age=30"})


@router.get("/{code}/history")
async def history(request: Request, code: str, years: int = Query(5, ge=1, le=HISTORY_YEARS)) -> Response:
    """Daily closing level of one index in points for up to five years. Public, like the index prices; one saved copy per index serves every viewer."""
    code = code.strip().upper()
    if not CODE.match(code):
        raise fail(400, "bad_request", "Unknown index.")
    raw = await _cached(request.app, f"idx:px:{code}", 3600 if market_open() else 6 * 3600, lambda: _fetch_levels(request.app, code))
    if raw is None:
        raise fail(502, "provider_unavailable", "The index history is not available right now. Please try again in a moment.")
    out = shape_levels(raw, years)
    if not out["rows"]:
        raise fail(404, "not_found", "There is no price history for this index.")
    feed = await _cached(request.app, "idx:feed", 900, lambda: _fetch_feed(request.app)) or {"items": []}
    name = next((x["name"] for x in feed["items"] if x["code"] == code), code)
    return Response(json.dumps({"code": code, "name": name, "years": years, "unit": "points", **out}), media_type="application/json",
                    headers={"Cache-Control": "public, max-age=300"})


@router.get("/{code}/valuation")
async def valuation(request: Request, code: str, years: int = Query(5, ge=1, le=HISTORY_YEARS), ctx: Ctx = Depends(premium_ctx)) -> Response:
    """Daily P/E, P/B and dividend yield of one index for up to five years, with where today sits against that history."""
    code = code.strip().upper()
    if not CODE.match(code):
        raise fail(400, "bad_request", "Unknown index.")
    raw = await _cached(request.app, f"idx:val:{code}", 6 * 3600, lambda: _fetch_history(request.app, code))
    if raw is None:
        raise fail(502, "provider_unavailable", "The valuation history is not available right now. Please try again in a moment.")
    out = shape_history(raw, years)
    if not out["rows"]:
        raise fail(404, "not_found", "There is no valuation history for this index.")
    feed = await _cached(request.app, "idx:feed", 900, lambda: _fetch_feed(request.app)) or {"items": []}
    name = next((x["name"] for x in feed["items"] if x["code"] == code), code)
    return Response(json.dumps({"code": code, "name": name, "years": years, **out}), media_type="application/json", headers=NO_STORE)


async def warm(app) -> None:
    """Index prices for the strip, and NIFTY 50's history, ready before the first visitor asks."""
    try:
        await _cached(app, "idx:feed", 60, lambda: _fetch_feed(app))
        await _cached(app, "idx:val:NIF50", 6 * 3600, lambda: _fetch_history(app, "NIF50"))
    except Exception:
        log.exception("index warm-up failed")
