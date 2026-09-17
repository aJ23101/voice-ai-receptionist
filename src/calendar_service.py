"""Google Calendar integration for the receptionist agent."""

import datetime
import logging
import os.path
import zoneinfo

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


if __name__ == "__main__":
    service = get_service()

    check_date = datetime.date(2026, 9, 17)   # Thursday, has two events

    print(f"Busy periods on {check_date}:")
    for start, end in get_busy_periods(service, check_date):
        print(f"  {start} to {end}")

    print(f"\nFree slots on {check_date}:")
    for slot in get_free_slots(check_date):
        print(" ", slot)