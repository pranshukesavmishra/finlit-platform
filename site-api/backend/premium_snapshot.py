"""Signed current-report snapshots: no server instance affinity or report storage."""
import hashlib
import hmac
import json
from datetime import datetime, timezone, timedelta
import jwt

AUDIENCE = 'premium-report-snapshot'
TTL_SECONDS = 1800


def canonical(report):
    # JSON.parse/stringify turns 1.0 into 1. Normalise integral floats so an
    # unchanged browser round-trip retains the same authenticated digest.
    def normalise(value):
        if isinstance(value, float) and value.is_integer():
            return int(value)
        if isinstance(value, dict):
            return {key: normalise(item) for key, item in value.items()}
        if isinstance(value, list):
            return [normalise(item) for item in value]
        return value
    encoded = json.dumps(normalise(report), sort_keys=True, separators=(',', ':'), allow_nan=False).encode()
    if len(encoded) > 2_000_000:
        raise ValueError('Report snapshot is too large')
    return encoded


def issue(report, subject, secret):
    now = datetime.now(timezone.utc)
    snapshot = {**report, 'snapshotExpiresAt': (now + timedelta(seconds=TTL_SECONDS)).isoformat()}
    digest = hashlib.sha256(canonical(snapshot)).hexdigest()
    receipt = jwt.encode({'aud': AUDIENCE, 'sub': subject, 'iat': now, 'exp': now+timedelta(seconds=TTL_SECONDS), 'digest': digest}, secret, algorithm='HS256')
    return {**snapshot, 'snapshotReceipt': receipt}


def verify(report, receipt, subject, secret):
    claims = jwt.decode(receipt, secret, algorithms=['HS256'], audience=AUDIENCE,
                        options={'require':['aud','sub','iat','exp','digest']})
    if claims['sub'] != subject or not hmac.compare_digest(claims['digest'], hashlib.sha256(canonical(report)).hexdigest()):
        raise ValueError('Report snapshot does not match its receipt')
    if report.get('state') != 'ready':
        raise ValueError('Report is not ready')
    return report
