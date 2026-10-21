"""The forum's content rules, as pure functions (no database, no network), so every rule is easy to test.

FinLit is a research site, not an advisory service, so the forum is for information and opinion only. The rules below are
deliberately blunt heuristics, not a legal judgement:

* REJECT (the member is told why and can rewrite): contact details, invitations to private groups, explicit buy/sell calls with a
  time or a price, stop-losses, "guaranteed" or "risk free" promises, promises of returns, and links to shorteners, chat groups
  or social profiles.
* HOLD for a moderator (the post is saved but not shown to others until approved): hype words that often come with pump-and-dump
  campaigns, all-capitals shouting, rocket emojis, and links from a member who has not yet had posts approved.

A heuristic never replaces a moderator; it only decides what a human has to look at first.
"""

from __future__ import annotations

import hashlib
import re
import unicodedata
from dataclasses import dataclass, field
from typing import List, Optional, Tuple
from urllib.parse import urlsplit

TITLE_MIN, TITLE_MAX = 8, 140
BODY_MIN, BODY_MAX = 20, 4000
REPLY_MIN, REPLY_MAX = 2, 2000
MAX_LINKS = 2
HANDLE_RE = re.compile(r"^[A-Za-z][A-Za-z0-9_]{2,19}$")
RESERVED_HANDLE_PARTS = ("admin", "moderator", "finlit", "official", "sebi", "support", "staff")
RESERVED_HANDLES = {"mod", "team", "system", "help", "deleted", "removed", "nse", "bse", "anonymous", "everyone"}

# Zero-width, bidirectional-override and other invisible characters: used to hide words from filters or to spoof text order.
_INVISIBLE = dict.fromkeys(list(range(0x200B, 0x2010)) + list(range(0x202A, 0x202F)) + list(range(0x2060, 0x2065)) + list(range(0x2066, 0x206A)) + [0xFEFF, 0x00AD], None)
URL_RE = re.compile(r"(?:https?://|www\.)[^\s<>\"'`]+", re.I)
BARE_DOMAIN_RE = re.compile(r"\b[a-z0-9][a-z0-9-]{0,40}(?:\.[a-z0-9-]{1,40})*\.(?:com|in|net|org|io|co|me|ly|gl|gg|app|xyz|info|biz|ws|link|page|live|site|online|club|top|tk|cc|st)\b(?:/\S*)?", re.I)
BLOCKED_HOSTS = ("bit.ly", "tinyurl.com", "t.co", "goo.gl", "is.gd", "cutt.ly", "rb.gy", "ow.ly", "shorturl.at", "t.me", "telegram.me", "telegram.org", "wa.me", "whatsapp.com",
                 "discord.gg", "discord.com", "signal.group", "linktr.ee", "instagram.com", "facebook.com", "fb.me", "youtu.be", "youtube.com", "tiktok.com")

EMAIL_RE = re.compile(r"[\w.+\-]+\s*(?:@|\[at\]|\(at\)|\{at\})\s*[\w\-]+\s*(?:\.|\[dot\]|\(dot\)|\{dot\})\s*[a-z]{2,}", re.I)
PHONE_RES = (
    re.compile(r"(?<![\d,.])(?:\+?91[\s\-]?)?0?[6-9]\d{4}[\s\-]?\d{5}(?![\d,])"),           # an Indian mobile number, with or without +91 and one space
    re.compile(r"(?<!\d)\+\d{1,3}[\s\-]?\(?\d{2,5}\)?[\s\-]?\d{3,5}[\s\-]?\d{3,5}(?!\d)"),    # any number written with a country code
    re.compile(r"(?<![\d,.])\d{10,}(?![\d,])"),                                              # a run of ten or more digits
)
HANDLE_AT_RE = re.compile(r"(?<![\w@])@[A-Za-z][A-Za-z0-9_]{3,}")
CONTACT_WORDS = re.compile(r"\b(?:whats\s*app|telegram|signal\s+group|dm\s+me|pm\s+me|inbox\s+me|message\s+me|call\s+me|ping\s+me|contact\s+me|reach\s+me|my\s+(?:number|phone|mobile|email))\b", re.I)

CALL_PATTERNS: List[Tuple[re.Pattern, str]] = [
    (re.compile(r"\b(?:buy|sell|accumulate|book\s+profits?|exit|go\s+long)\b[\s,:\-]*(?:now|today|tomorrow|immediately|asap|on\s+dips?|below|above|this\s+week)\b", re.I), "a buy or sell call"),
    (re.compile(r"\b(?:target\s+price|price\s+target)\b[^.\n]{0,25}\d|\btgt\b|\btargets?\s*(?:of|is|are|:|=|-|at)?\s*(?:₹|rs\.?\s*|inr\s*)\d", re.I), "a price target"),
    (re.compile(r"\b(?:stop\s*-?\s*loss|stoploss|sl)\s*(?:of|is|at|:|=|-)?\s*(?:₹|rs\.?\s*|inr\s*)?\d", re.I), "a stop-loss level"),
    (re.compile(r"\b(?:sure\s*-?\s*shot|guaranteed?|assured\s+(?:returns?|profits?)|risk\s*-?\s*free|no\s+risk|100\s*%\s*(?:sure|safe|profit|returns?)|double\s+your\s+money|easy\s+money|jackpot)\b", re.I), "a promise of gains or safety"),
    (re.compile(r"\b\d{1,4}\s*x\b[\s\w]{0,20}\b(?:in|within)\s+\d+\s*(?:days?|weeks?|months?)", re.I), "a promise of returns"),
    (re.compile(r"\b(?:intraday|btst|stbt|swing|positional|option|options|nifty|banknifty)\s+(?:calls?|tips?)\b|\b(?:paid|premium|vip)\s+(?:tips?|calls?|group|channel|service)\b|\bstock\s+tips?\b", re.I), "tips or a paid service"),
    (re.compile(r"\b(?:join|follow|subscribe(?:\s+to)?)\s+(?:my|our|the|this)\s+(?:group|channel|community|course|webinar|telegram)\b", re.I), "an invitation to a private group or service"),
    (re.compile(r"\b(?:i|we)\s+(?:recommend|suggest|advise)\s+(?:you\s+)?(?:to\s+)?(?:buy|sell|hold|accumulate|avoid)\b|\byou\s+should\s+(?:buy|sell)\b|\b(?:strong\s+buy|must\s+buy|must\s+sell)\b", re.I), "advice to buy or sell"),
]
HOLD_PATTERNS: List[Tuple[re.Pattern, str]] = [
    (re.compile(r"\b(?:multi\s*-?\s*bagger|moon\s*shot|to\s+the\s+moon|rocket(?:ship)?|next\s+big\s+thing|hot\s+(?:stock|tip)|insider\s+(?:info|tip|news)|operator\s+(?:driven|played|stock)|pump(?:ing|ed)?|dump(?:ing|ed)?|penny\s+stock|load\s+up|all\s*-?\s*in|don'?t\s+miss|last\s+chance|once\s+in\s+a\s+lifetime)\b", re.I), "hype words often seen in pump-and-dump campaigns"),
    (re.compile(r"\b(?:5|10|20|50|100)\s*x\b", re.I), "a multiple-of-your-money claim"),
    (re.compile("[\U0001F680\U0001F4B0\U0001F911\U0001F4B8]"), "hype emoji"),
    (re.compile(r"!{4,}"), "shouting"),
]


@dataclass
class Verdict:
    """What the rules say about one piece of text."""
    ok: bool = True
    code: str = ""                                    # machine-readable reason when rejected
    message: str = ""                                 # plain-words explanation shown to the member
    hold: List[str] = field(default_factory=list)     # reasons for a moderator to look first (post is saved but not shown)


def clean_text(raw: str) -> str:
    """Plain text only: normalised, invisible and control characters removed, blank lines capped, trailing space trimmed. HTML is never interpreted
    anywhere (the website renders text), so angle brackets are kept as typed: "P/E < 10" must stay readable."""
    text = unicodedata.normalize("NFKC", raw or "").translate(_INVISIBLE).replace("\r\n", "\n").replace("\r", "\n")
    text = "".join(ch for ch in text if ch in "\n\t" or unicodedata.category(ch)[0] != "C")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return "\n".join(line.strip() for line in text.split("\n")).strip()


def content_hash(text: str) -> str:
    """Same for copies that differ only in case, spacing or punctuation."""
    norm = re.sub(r"[^a-z0-9]+", " ", text.lower()).strip()
    return hashlib.sha256(norm.encode()).hexdigest()


def find_urls(text: str) -> List[str]:
    return [u.rstrip(".,;:!?)]}'\"") for u in URL_RE.findall(text)]


def _host(url: str) -> str:
    try:
        return (urlsplit(url if "//" in url else "http://" + url).hostname or "").lower().removeprefix("www.")
    except ValueError:
        return ""


def _blocked(host: str) -> bool:
    return any(host == b or host.endswith("." + b) for b in BLOCKED_HOSTS)


def check_links(text: str) -> Verdict:
    urls = find_urls(text)
    if len(urls) > MAX_LINKS:
        return Verdict(False, "too_many_links", f"Please keep to {MAX_LINKS} links or fewer in one post.")
    refusal = Verdict(False, "blocked_link", "Links to shorteners, chat groups and social profiles cannot be posted. Link to the original source (filing, annual report, news article).")
    for url in urls:
        parts = urlsplit(url if "//" in url else "http://" + url)
        host = _host(url)
        if not host or "@" in (parts.netloc or "") or re.fullmatch(r"[\d.]+|[\da-f:]+", host):
            return Verdict(False, "bad_link", "That link cannot be posted. Use a normal web address (no login details or raw IP addresses).")
        if _blocked(host):
            return refusal
    # A bare domain such as "t.me/somegroup" is a link too.
    rest = EMAIL_RE.sub(" ", URL_RE.sub(" ", text))
    if any(_blocked(_host(m.group(0))) for m in BARE_DOMAIN_RE.finditer(rest)):
        return refusal
    return Verdict()


def check_text(text: str, *, trusted: bool = True) -> Verdict:
    """Apply every rule to one cleaned text. `trusted` = the member already has posts standing."""
    if EMAIL_RE.search(text) or any(r.search(text) for r in PHONE_RES) or HANDLE_AT_RE.search(text) or CONTACT_WORDS.search(text):
        return Verdict(False, "contact_details", "Contact details (phone numbers, email addresses, WhatsApp or Telegram handles) cannot be posted. Keep the conversation here.")
    for pattern, what in CALL_PATTERNS:
        if pattern.search(text):
            return Verdict(False, "advice_or_call", f"This looks like {what}. The forum is for information and opinion only: share your reasoning and the numbers behind it, "
                                                    "not what others should buy or sell, at what price, or by when.")
    links = check_links(text)
    if not links.ok:
        return links
    hold = [what for pattern, what in HOLD_PATTERNS if pattern.search(text)]
    letters = [c for c in text if c.isalpha()]
    if len(letters) >= 30 and sum(c.isupper() for c in letters) / len(letters) > 0.6:
        hold.append("mostly capital letters")
    if re.search(r"(.)\1{9,}", text):
        hold.append("repeated characters")
    if find_urls(text) and not trusted:
        hold.append("a link from a member with no approved posts yet")
    return Verdict(True, hold=hold)


def check_handle(handle: str) -> str:
    """'' when acceptable, else the reason."""
    if not HANDLE_RE.match(handle or ""):
        return "Use 3 to 20 letters, numbers or underscores, starting with a letter."
    low = handle.lower()
    if low in RESERVED_HANDLES or any(p in low for p in RESERVED_HANDLE_PARTS):
        return "That name is reserved. Please choose another."
    if re.search(r"\d{6,}", handle) or CONTACT_WORDS.search(handle.replace("_", " ")):
        return "Please choose a name that does not look like contact details."
    return ""


def check_lengths(kind: str, title: Optional[str], body: str) -> str:
    """'' when the lengths are fine, else the message."""
    if kind == "thread":
        if not title or not (TITLE_MIN <= len(title) <= TITLE_MAX):
            return f"The title needs {TITLE_MIN} to {TITLE_MAX} characters."
        if not (BODY_MIN <= len(body) <= BODY_MAX):
            return f"Write {BODY_MIN} to {BODY_MAX} characters in the opening post, so others have something to respond to."
    elif not (REPLY_MIN <= len(body) <= REPLY_MAX):
        return f"A reply needs {REPLY_MIN} to {REPLY_MAX} characters."
    return ""
