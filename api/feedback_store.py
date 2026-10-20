"""Public feedback submission, with idempotent private Google Sheets storage.

The API runtime identity is the same service account already authorized for
the private archive spreadsheet. No user-supplied text is formula-evaluated.
"""
import re
import uuid
from datetime import datetime
from zoneinfo import ZoneInfo

import google.auth
from googleapiclient.discovery import build

SHEET_ID = "1pLRILhu02VX1_KYDgEaRjOeL4WgBP_1Wmh-mm-iFcaY"
SHEET_NAME = "의견 보내기"
KST = ZoneInfo("Asia/Seoul")
MAX_MESSAGE = 3000


def clean_feedback(data):
    if not isinstance(data, dict):
        raise ValueError("의견 내용을 입력해주세요.")
    message = data.get("message")
    if not isinstance(message, str):
        raise ValueError("의견 내용을 입력해주세요.")
    message = message.strip()
    if not 2 <= len(message) <= MAX_MESSAGE:
        raise ValueError("의견은 2자 이상 3,000자 이하로 입력해주세요.")
    if "\x00" in message:
        raise ValueError("허용되지 않는 문자가 포함되어 있습니다.")
    try:
        ident = str(uuid.UUID(data["submission_id"]))
    except (ValueError, KeyError, TypeError, AttributeError) as exc:
        raise ValueError("전송 정보를 확인할 수 없습니다. 페이지를 새로고침해주세요.") from exc
    if not isinstance(data.get("website", ""), str) or len(data.get("website", "")) > 200:
        raise ValueError("잘못된 요청입니다.")
    return ident, message, bool(data.get("website", "").strip())


def sheet_row(ident, submitted_at, message):
    # values.append with RAW prevents spreadsheet formula injection.
    return [ident, submitted_at, message, "", ""]


def save_feedback_to_sheet(ident, submitted_at, message):
    credentials, _ = google.auth.default(
        scopes=["https://www.googleapis.com/auth/spreadsheets"])
    sheets = build("sheets", "v4", credentials=credentials, cache_discovery=False).spreadsheets()
    # The stable submission ID protects against client retries after a lost response.
    existing = sheets.values().get(
        spreadsheetId=SHEET_ID,
        range="'의견 보내기'!A2:A",
        valueRenderOption="UNFORMATTED_VALUE",
    ).execute()
    if any(row and row[0] == ident for row in existing.get("values", [])):
        return False
    sheets.values().append(
        spreadsheetId=SHEET_ID,
        range="'의견 보내기'!A:E",
        valueInputOption="RAW",
        insertDataOption="INSERT_ROWS",
        body={"values": [sheet_row(ident, submitted_at, message)]},
    ).execute()
    return True


def new_timestamp():
    return datetime.now(KST).strftime("%Y-%m-%d %H:%M:%S")
