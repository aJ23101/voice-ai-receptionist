"""Google Calendar integration for the receptionist agent."""

import datetime
import logging
import os.path
import re
import zoneinfo

from dotenv import load_dotenv
load_dotenv(".env.local")

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build

logger = logging.getLogger("calendar")

SCOPES = ["https://www.googleapis.com/auth/calendar"]
TIMEZONE = zoneinfo.ZoneInfo("Asia/Kolkata")

OPENING_HOUR = 10
CLOSING_HOUR = 19
SLOT_MINUTES = 30

WEEKDAYS = [
    "monday", "tuesday", "wednesday", "thursday",
    "friday", "saturday", "sunday",
]


def get_service():
    """Authenticate and return a Google Calendar API client."""
    creds = None

    if os.path.exists("token.json"):
        creds = Credentials.from_authorized_user_file("token.json", SCOPES)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file("credentials.json", SCOPES)
            creds = flow.run_local_server(port=0)

        with open("token.json", "w") as token:
            token.write(creds.to_json())

    return build("calendar", "v3", credentials=creds)


def get_busy_periods(service, date: datetime.date):
    """Return a list of (start, end) datetimes that are already booked on this date."""
    day_start = datetime.datetime.combine(
        date, datetime.time(0, 0), tzinfo=TIMEZONE
    )
    day_end = day_start + datetime.timedelta(days=1)

    result = (
        service.freebusy()
        .query(
            body={
                "timeMin": day_start.isoformat(),
                "timeMax": day_end.isoformat(),
                "timeZone": "Asia/Kolkata",
                "items": [{"id": "primary"}],
            }
        )
        .execute()
    )

    busy = result["calendars"]["primary"]["busy"]
    return [
        (
            datetime.datetime.fromisoformat(b["start"]).astimezone(TIMEZONE),
            datetime.datetime.fromisoformat(b["end"]).astimezone(TIMEZONE),
        )
        for b in busy
    ]


def get_free_slots(date: datetime.date):
    """Return a list of free slot start times as strings, e.g. ['10:00 AM', '2:30 PM']."""
    service = get_service()
    busy = get_busy_periods(service, date)

    free = []
    cursor = datetime.datetime.combine(
        date, datetime.time(OPENING_HOUR, 0), tzinfo=TIMEZONE
    )
    closing = datetime.datetime.combine(
        date, datetime.time(CLOSING_HOUR, 0), tzinfo=TIMEZONE
    )

    while cursor + datetime.timedelta(minutes=SLOT_MINUTES) <= closing:
        slot_end = cursor + datetime.timedelta(minutes=SLOT_MINUTES)

        overlaps = any(
            cursor < busy_end and slot_end > busy_start
            for busy_start, busy_end in busy
        )

        if not overlaps:
            free.append(cursor.strftime("%I:%M %p").lstrip("0"))

        cursor = slot_end

    return free


def parse_day(text: str) -> datetime.date | None:
    """Turn a spoken day like 'tomorrow' or 'thursday' into a date.

    Only resolves today through the next seven days. Returns None if the
    text isn't understood.
    """
    text = text.strip().lower()
    today = datetime.datetime.now(TIMEZONE).date()

    if text in ("today", "now"):
        return today

    if text in ("tomorrow", "tmrw"):
        return today + datetime.timedelta(days=1)

    for offset in range(7):
        candidate = today + datetime.timedelta(days=offset)
        name = WEEKDAYS[candidate.weekday()]
        if name in text:
            return candidate

    return None

def parse_time(text: str) -> datetime.time | None:
    """Turn a spoken time like '10 AM' or '2:30 pm' into a time object.

    Returns None if it can't be understood or isn't a valid slot start.
    """
    text = text.strip().lower().replace(".", "")

    match = re.search(r"(\d{1,2})[:\s]?(\d{2})?\s*(am|pm)?", text)
    if not match:
        return None

    hour = int(match.group(1))
    minute = int(match.group(2) or 0)
    meridiem = match.group(3)

    if meridiem == "pm" and hour != 12:
        hour += 12
    elif meridiem == "am" and hour == 12:
        hour = 0
    elif meridiem is None and hour < OPENING_HOUR:
        # "book me at 3" during clinic hours means 3 PM, not 3 AM
        hour += 12

    if not (0 <= hour <= 23) or minute not in (0, 30):
        return None

    return datetime.time(hour, minute)


def book_appointment(date: datetime.date, time: datetime.time, name: str, service: str):
    """Create a 30-minute appointment. Returns (success: bool, message: str)."""
    service_client = get_service()

    start = datetime.datetime.combine(date, time, tzinfo=TIMEZONE)
    end = start + datetime.timedelta(minutes=SLOT_MINUTES)

    # Re-check immediately before writing, in case the slot was taken meanwhile
    busy = get_busy_periods(service_client, date)
    taken = any(start < busy_end and end > busy_start for busy_start, busy_end in busy)

    if taken:
        free = get_free_slots(date)
        if free:
            return False, f"That slot was just taken. Still free: {', '.join(free[:3])}"
        return False, "That slot was just taken, and nothing else is free that day."

    event = {
        "summary": f"{name} - {service}",
        "start": {"dateTime": start.isoformat(), "timeZone": "Asia/Kolkata"},
        "end": {"dateTime": end.isoformat(), "timeZone": "Asia/Kolkata"},
    }

    created = service_client.events().insert(calendarId="primary", body=event).execute()
    logger.info(f"Booked {name} on {start} (event {created['id']})")

    return True, f"Booked {name} for {service} on {date} at {start.strftime('%I:%M %p').lstrip('0')}"


if __name__ == "__main__":
    import sys

    if len(sys.argv) > 1 and sys.argv[1] == "test-parse":
        today = datetime.datetime.now(TIMEZONE).date()
        print(f"Today is {today} ({WEEKDAYS[today.weekday()]})\n")
        for phrase in [
            "today", "tomorrow", "monday", "tuesday", "wednesday",
            "thursday", "friday", "saturday", "sunday",
            "next friday", "on Saturday please", "the 24th",
        ]:
            print(f"  {phrase!r:22} -> {parse_day(phrase)}")
        sys.exit()

    if len(sys.argv) > 1:
        check_date = datetime.date.fromisoformat(sys.argv[1])
    else:
        check_date = datetime.date.today()

    service = get_service()

    print(f"Busy periods on {check_date}:")
    for start, end in get_busy_periods(service, check_date):
        print(f"  {start} to {end}")

    print(f"\nFree slots on {check_date}:")
    for slot in get_free_slots(check_date):
        print(" ", slot)