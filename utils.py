import json
import os
import smtplib
from collections.abc import Sequence
from datetime import timedelta
from email.message import EmailMessage
from pathlib import Path
from re import Pattern
from typing import Any

import httpx

from logger import DEBUG, LOGGER

SMTP_SERVER = os.environ["SMTP_SERVER"]
EMAIL_USER = os.environ["EMAIL_USER"]
EMAIL_PASSWORD = os.environ["EMAIL_PASSWORD"]
PHONE = os.environ["PHONE"]
EMAIL_RECIPIENT = os.environ["EMAIL_RECIPIENT"]
SMTP_PORT = 587


def write_out(data: dict[str, str | dict[str, str]], file: Path) -> None:
    """Write the last video to disk."""
    with file.open("w", encoding="utf8") as out:
        json.dump(data, out, indent=2)


def read_data(file: Path) -> dict[str, str | dict[str, str]]:
    """
    Read stored data.

    Returns
    -------
    Current file information.

    """
    with file.open("r", encoding="utf8") as fp:
        return json.load(fp)


def send_email(
    subject: str | None, message: str, caller: str, receiver: str = EMAIL_RECIPIENT
) -> None:
    """Send an email with the latest video information."""
    msg = EmailMessage()
    if subject:
        msg["Subject"] = subject
    msg["From"] = EMAIL_USER
    msg["To"] = receiver
    msg.set_content(message)

    smtp = smtplib.SMTP(SMTP_SERVER, 587)
    smtp.ehlo()
    smtp.starttls()
    smtp.login(EMAIL_USER, EMAIL_PASSWORD)
    if DEBUG == "Debug":
        message = f"send_email called from {caller} - Sent {msg}"
        LOGGER.debug(message)
        return
    smtp.send_message(msg)


def contains_keyword(target: str, keywords: Sequence[str]) -> bool:
    """Return whether any of the keywords are in the target string."""
    for word in keywords:
        if word in target:
            return True
    return False


def get_time(time: str, pattern: Pattern[str]) -> timedelta:
    """
    Convert the runtime string into a struct_time.

    Returns
    -------
    Video runtime.

    """
    time_delta = timedelta(seconds=0)
    ma = pattern.match(time)
    if ma is None:
        return time_delta
    if (hours := ma.group(1)) is not None:
        time_delta += timedelta(hours=int(hours))
    if (minutes := ma.group(2)) is not None:
        time_delta += timedelta(minutes=int(minutes))
    if (seconds := ma.group(3)) is not None:
        time_delta += timedelta(seconds=int(seconds))
    return time_delta


async def get_data(payload: str) -> dict[str, Any]:
    """
    Gather the useful information from the JSON object as a dictionary.

    Returns
    -------
    JSON data for the information.

    """
    async with httpx.AsyncClient() as client:
        response = await client.get(payload, timeout=5)
    try:
        return json.loads(response.text)["items"][0]
    except IndexError:
        raise BadVideoError


class BadVideoError(Exception):
    pass
