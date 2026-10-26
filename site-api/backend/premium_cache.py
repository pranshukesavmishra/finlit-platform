"""What a premium report keeps between calculations, packed small for the trip to and from the research API.

Two things are worth keeping, and neither changes a number:
  * the model inputs: the exact provider data a calculation was fed (statements, prices, ratios, ownership filings, the industry list), so that
    calculating the same company again within INPUT_MAX_AGE_SECONDS needs no provider call at all;
  * the peer observations: the one price-ratio row per peer that the industry median used, shared by every company of that industry on the
    same day (a report otherwise looks up some 140 of them).
This module only packs, unpacks and checks them; the research API (backend/finlit/prism.py) stores them. Nothing here is a report."""
import base64
import json
import zlib
from datetime import datetime, timezone

INPUT_MAX_AGE_SECONDS = 24 * 3600      # financial statements change quarterly; a day-old copy of the inputs is far inside that
PACKED_LIMIT = 4_000_000               # bytes of base64 text accepted
UNPACKED_LIMIT = 24_000_000            # bytes after inflating: a zip bomb is refused
OBSERVATION_LIMIT = 4000               # peer observations accepted in one request


def pack(value) -> str:
    return base64.b64encode(zlib.compress(json.dumps(value, separators=(",", ":"), allow_nan=False).encode(), 6)).decode("ascii")


def unpack(text):
    """The packed value, or None when it is missing, too large, damaged or not what pack() produced."""
    if not isinstance(text, str) or not text or len(text) > PACKED_LIMIT:
        return None
    try:
        inflater = zlib.decompressobj()
        raw = inflater.decompress(base64.b64decode(text, validate=True), UNPACKED_LIMIT)
        if inflater.unconsumed_tail:
            return None
        return json.loads(raw)
    except (ValueError, zlib.error, TypeError):
        return None


def usable_inputs(packed, symbol, statement, now=None):
    """Previously kept model inputs for exactly this company and requested statement basis and young enough, else None."""
    kept = unpack(packed)
    if not isinstance(kept, dict) or kept.get("symbol") != symbol or kept.get("requested") != statement:
        return None
    if not all(key in kept for key in ("raw", "sources", "effective", "sourcing", "fetchedAt")):
        return None
    try:
        fetched = datetime.fromisoformat(str(kept["fetchedAt"]))
    except ValueError:
        return None
    fetched = fetched if fetched.tzinfo else fetched.replace(tzinfo=timezone.utc)
    age = ((now or datetime.now(timezone.utc)) - fetched).total_seconds()
    if not 0 <= age <= INPUT_MAX_AGE_SECONDS or not isinstance(kept["raw"], dict):
        return None
    return kept


def observation_key(key) -> str:
    """('consolidated', '2026-10-26', 'pr:pb,pe', 'TCS') -> 'consolidated|2026-10-26|pr:pb,pe|TCS' (JSON object keys are strings)."""
    return "|".join(key)


def parse_observation_key(text):
    parts = str(text).split("|", 3)
    return tuple(parts) if len(parts) == 4 and parts[0] in ("consolidated", "standalone") else None


def preload(flat):
    """{'consolidated|2026-10-26|pr:pb,pe|TCS': row} -> the tuple-keyed dict ObservationCache takes. Anything malformed is dropped."""
    out = {}
    if not isinstance(flat, dict):
        return out
    for text, value in list(flat.items())[:OBSERVATION_LIMIT]:
        key = parse_observation_key(text)
        if key and isinstance(value, (dict, int, float)) and not isinstance(value, bool):
            out[key] = value
    return out


KEPT_ROW_FIELDS = ("pe", "pb", "source")    # the only fields of a peer's row the median reads


def _trim(value):
    if isinstance(value, dict) and value.get("none") is True:
        return value                                # "answered, nothing usable"
    return {name: value[name] for name in KEPT_ROW_FIELDS if name in value} if isinstance(value, dict) else value


def flatten(rows):
    """The observations for transport: a peer's row is cut to the fields the industry median reads (the rest is the provider's other ratios)."""
    return {observation_key(key): _trim(value) for key, value in rows.items()}
