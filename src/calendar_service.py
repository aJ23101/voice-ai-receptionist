"""Google Calendar integration for the receptionist agent."""

import datetime
import json
import logging
import os
import re
import zoneinfo

from dotenv import load_dotenv
from google.auth.exceptions import RefreshError
from google.auth.transport.requests import Request
from google.oauth2 import service_account
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build

load_dotenv(".env.local")

logger = logging.getLogger("calendar")

SCOPES = ["https://www.googleapis.com/auth/calendar"]
DEFAULT_SERVICE_ACCOUNT_FILE = "/etc/secrets/smilecare-receptionist-8587a082c9e6.json"

# The calendar to read and write. Point CALENDAR_ID at a throwaway calendar
# when running simulations, so test bookings stay out of the real one.
CALENDAR_ID = os.environ.get("CALENDAR_ID", "primary")
TIMEZONE = zoneinfo.ZoneInfo("Asia/Kolkata")

OPENING_HOUR = 10
CLOSING_HOUR = 19
SLOT_MINUTES = 30

WEEKDAYS = [
    "monday",
    "tuesday",
    "wednesday",
    "thursday",
    "friday",
    "saturday",
    "sunday",
]


def get_service():
    """Authenticate and return a Google Calendar API client."""
    service_account_json = os.environ.get("GOOGLE_SERVICE_ACCOUNT_JSON")
    service_account_file = os.environ.get("GOOGLE_SERVICE_ACCOUNT_FILE")
    if not service_account_json and service_account_file:
        try:
            with open(service_account_file, encoding="utf-8") as secret_file:
                service_account_json = secret_file.read()
        except OSError as error:
            raise RuntimeError(
                "Could not read the GOOGLE_SERVICE_ACCOUNT_FILE secret."
            ) from error
    elif not service_account_json and os.path.isfile(DEFAULT_SERVICE_ACCOUNT_FILE):
        with open(DEFAULT_SERVICE_ACCOUNT_FILE, encoding="utf-8") as secret_file:
            service_account_json = secret_file.read()

    if service_account_json:
        try:
            service_account_info = json.loads(service_account_json)
        except json.JSONDecodeError as error:
            raise ValueError(
                "GOOGLE_SERVICE_ACCOUNT_JSON must contain valid JSON."
            ) from error

        creds = service_account.Credentials.from_service_account_info(
            service_account_info,
            scopes=SCOPES,
        )
        return build("calendar", "v3", credentials=creds)

    creds = None

    if os.path.exists("token.json"):
        creds = Credentials.from_authorized_user_file("token.json", SCOPES)

    if creds and creds.expired and creds.refresh_token:
        try:
            creds.refresh(Request())
        except RefreshError:
            logger.warning(
                "Saved Google OAuth grant is invalid or revoked; requesting consent."
            )
            creds = None

    if not creds or not creds.valid:
        flow = InstalledAppFlow.from_client_secrets_file("credentials.json", SCOPES)
        creds = flow.run_local_server(port=0)

        with open("token.json", "w") as token:
            token.write(creds.to_json())

    return build("calendar", "v3", credentials=creds)


def get_busy_periods(service, date: datetime.date):
    """Return a list of (start, end) datetimes that are already booked on this date."""
    day_start = datetime.datetime.combine(date, datetime.time(0, 0), tzinfo=TIMEZONE)
    day_end = day_start + datetime.timedelta(days=1)

    result = (
        service.freebusy()
        .query(
            body={
                "timeMin": day_start.isoformat(),
                "timeMax": day_end.isoformat(),
                "timeZone": "Asia/Kolkata",
                "items": [{"id": CALENDAR_ID}],
            }
        )
        .execute()
    )

    busy = result["calendars"][CALENDAR_ID]["busy"]
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
            cursor < busy_end and slot_end > busy_start for busy_start, busy_end in busy
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

    if "today" in text or "now" in text:
        return today

    if "tomorrow" in text or "tmrw" in text:
        return today + datetime.timedelta(days=1)

    for offset in range(7):
        candidate = today + datetime.timedelta(days=offset)
        name = WEEKDAYS[candidate.weekday()]
        if name in text:
            return candidate

    return None


NUMBER_WORDS = {
    "one": 1,
    "two": 2,
    "three": 3,
    "four": 4,
    "five": 5,
    "six": 6,
    "seven": 7,
    "eight": 8,
    "nine": 9,
    "ten": 10,
    "eleven": 11,
    "twelve": 12,
    "fifteen": 15,
    "twenty": 20,
    "thirty": 30,
    "forty five": 45,
    "forty": 40,
}


def parse_time(text: str) -> datetime.time | None:
    """Turn a spoken time like '10 AM', '2:30 pm' or 'twelve thirty' into a time.

    Returns None if it can't be understood or isn't a valid slot start.
    """
    text = text.strip().lower().replace(".", "")

    # "half past two" -> 2:30, "quarter to five" -> 4:45 (rejected below as
    # an invalid slot start). Strip the qualifier first, then read the hour.
    offset = 0
    qualifier = re.match(r"(half|quarter)\s+(past|to)\s+(.+)", text)
    if qualifier:
        minutes = 30 if qualifier.group(1) == "half" else 15
        offset = minutes if qualifier.group(2) == "past" else -minutes
        text = qualifier.group(3)

    # Convert spoken numbers to digits: "twelve thirty" -> "12 30"
    for word in sorted(NUMBER_WORDS, key=len, reverse=True):
        text = text.replace(word, str(NUMBER_WORDS[word]))

    text = text.replace("o'clock", ":00").replace("oclock", ":00")
    text = text.replace("noon", "12 pm").replace("midday", "12 pm")

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

    if offset:
        shifted = datetime.datetime(2000, 1, 1, hour, minute) + datetime.timedelta(
            minutes=offset
        )
        hour, minute = shifted.hour, shifted.minute

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

    created = (
        service_client.events().insert(calendarId=CALENDAR_ID, body=event).execute()
    )
    logger.info(f"Booked {name} on {start} (event {created['id']})")

    return (
        True,
        f"Booked {name} for {service} on {date} at {start.strftime('%I:%M %p').lstrip('0')}",
    )


def create_callback_request(name: str, reason: str):
    """Log a callback request as an all-day event. Returns (success, message)."""
    service_client = get_service()

    today = datetime.datetime.now(TIMEZONE).date()

    event = {
        "summary": f"CALLBACK: {name} - {reason}",
        "description": (
            f"Callback requested by {name}.\n"
            f"Reason: {reason}\n"
            f"Logged by the voice receptionist."
        ),
        "start": {"date": today.isoformat()},
        "end": {"date": (today + datetime.timedelta(days=1)).isoformat()},
    }

    created = (
        service_client.events().insert(calendarId=CALENDAR_ID, body=event).execute()
    )
    logger.info(f"Callback request logged for {name} (event {created['id']})")

    return True, f"Callback request logged for {name}"


if __name__ == "__main__":
    import sys

    if len(sys.argv) > 1 and sys.argv[1] == "test-parse":
        today = datetime.datetime.now(TIMEZONE).date()
        print(f"Today is {today} ({WEEKDAYS[today.weekday()]})\n")
        for phrase in [
            "today",
            "tomorrow",
            "monday",
            "tuesday",
            "wednesday",
            "thursday",
            "friday",
            "saturday",
            "sunday",
            "next friday",
            "on Saturday please",
            "the 24th",
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
