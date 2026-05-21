from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone
from typing import Any

SAME_RE = re.compile(
    r"ZCZC-"
    r"(?P<org>[A-Z]{3})-"
    r"(?P<event>[A-Z0-9]{3})-"
    r"(?P<counties>[\d-]+)\+"
    r"(?P<valid_hours>\d{2})"
    r"(?P<valid_mins>\d{2})-"
    r"(?P<issue_day>\d{3})"
    r"(?P<issue_hhmm>\d{4})-"
    r"(?P<wfo>.+)"
)


def normalize_multimon_line(line: str) -> str:
    return line.replace("EAS: ", "").replace("SAME: ", "").strip()


def parse_same(raw: str) -> dict[str, Any] | None:
    match = SAME_RE.search(raw)

    if not match:
        return None

    data = match.groupdict()

    counties = [c for c in data["counties"].split("-") if c]

    valid_hours = int(data["valid_hours"])
    valid_mins = int(data["valid_mins"])
    valid_seconds = valid_hours * 3600 + valid_mins * 60

    now_utc = datetime.now(timezone.utc)

    issue_utc = _parse_issue_time(
        now_utc=now_utc,
        julian_day=int(data["issue_day"]),
        hhmm=data["issue_hhmm"],
    )

    expires_utc = issue_utc + timedelta(seconds=valid_seconds)
    remaining = max(0, int((expires_utc - now_utc).total_seconds()))

    return {
        "event_code": data["event"],
        "org": data["org"],
        "counties": counties,
        "wfo": data["wfo"].strip(),
        "valid_hours": valid_hours,
        "valid_mins": valid_mins,
        "valid_seconds": valid_seconds,
        "issue_utc": issue_utc.isoformat(),
        "issue_expiry_utc": expires_utc.isoformat(),
        "true_remaining_secs": remaining,
        "received_utc": now_utc.isoformat(),
        "raw": raw.strip(),
    }


def _parse_issue_time(
    now_utc: datetime,
    julian_day: int,
    hhmm: str,
) -> datetime:
    hour = int(hhmm[:2])
    minute = int(hhmm[2:])
    year = now_utc.year

    candidate = datetime(
        year,
        1,
        1,
        hour,
        minute,
        tzinfo=timezone.utc,
    ) + timedelta(days=julian_day - 1)

    if (candidate - now_utc).total_seconds() > 43200:
        candidate = datetime(
            year - 1,
            1,
            1,
            hour,
            minute,
            tzinfo=timezone.utc,
        ) + timedelta(days=julian_day - 1)

    return candidate
