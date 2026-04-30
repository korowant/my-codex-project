import asyncio
import re
from dataclasses import dataclass
from email import message_from_bytes, utils
from imaplib import IMAP4_SSL
from time import time

from bs4 import BeautifulSoup


class MailTimedOut(Exception):
    """Raised when the expected email does not arrive in time."""


@dataclass
class MailConfig:
    email_data: str
    imap_server: str | None = None
    imap_port: int = 993
    timeout_seconds: int = 180


class Mail:
    """Small IMAP helper adapted from the uploaded PudgyWorld mail module."""

    def __init__(self, config: MailConfig):
        self.config = config
        self.mail_login: str
        self.mail_pass: str
        self.alias: str | None = None
        self.imap: IMAP4_SSL | None = None
        self.authed = False
        self._parse_email_data(config.email_data)

    def _parse_email_data(self, email_data: str) -> None:
        parts = email_data.split(":")
        if len(parts) < 2:
            raise ValueError("FAIRGROUND_EMAIL_DATA must be login:password or login:password:alias")
        self.mail_login = parts[0]
        self.mail_pass = ":".join(parts[1:-1] if len(parts) > 2 else parts[1:])
        if len(parts) > 2:
            self.alias = parts[-1]

    @property
    def target_email(self) -> str:
        return self.alias or self.mail_login

    def _detect_imap_server(self) -> str:
        if self.config.imap_server:
            return self.config.imap_server

        domain = self.mail_login.split("@")[-1].lower()
        if "icloud" in domain or "me.com" in domain or "mac.com" in domain:
            return "imap.mail.me.com"
        if "rambler" in domain:
            return "imap.rambler.ru"
        if "gmx" in domain:
            return "imap.gmx.com"
        if "gmail" in domain or "googlemail" in domain:
            return "imap.gmail.com"
        if "outlook" in domain or "hotmail" in domain or "live.com" in domain:
            return "outlook.office365.com"
        if "yahoo" in domain:
            return "imap.mail.yahoo.com"

        return f"imap.{domain}"

    def login(self) -> None:
        self.close()
        self.imap = IMAP4_SSL(host=self._detect_imap_server(), port=self.config.imap_port)
        self.imap.login(self.mail_login, self.mail_pass)
        self.authed = True

    async def find_latest_html(
        self,
        senders: list[str] | None = None,
        subject_contains: str | None = None,
        min_timestamp: float | None = None,
    ) -> BeautifulSoup:
        self.login()
        if not self.imap:
            raise RuntimeError("IMAP connection was not established")

        start_time = time()
        folders = ["INBOX", "Spam", "Junk", "[Gmail]/Spam"]
        senders = senders or []

        while time() < start_time + self.config.timeout_seconds:
            candidates = []
            for folder in folders:
                try:
                    typ, _ = self.imap.select(folder, readonly=True)
                    if typ != "OK":
                        continue

                    ids: set[bytes] = set()
                    if senders:
                        for sender in senders:
                            typ, data = self.imap.search(None, "FROM", sender, "TO", self.target_email)
                            if typ == "OK" and data and data[0]:
                                ids.update(data[0].split())
                            typ, data = self.imap.search(None, "FROM", sender)
                            if typ == "OK" and data and data[0]:
                                ids.update(data[0].split())
                    else:
                        typ, data = self.imap.search(None, "ALL")
                        if typ == "OK" and data and data[0]:
                            ids.update(data[0].split()[-25:])

                    for msg_id in ids:
                        typ, fetched = self.imap.fetch(msg_id, "(BODY.PEEK[])")
                        if typ != "OK" or not fetched or not fetched[0]:
                            continue

                        msg = message_from_bytes(fetched[0][1])
                        subject = msg.get("Subject") or ""
                        if subject_contains and subject_contains.lower() not in subject.lower():
                            continue
                        try:
                            ts = utils.parsedate_to_datetime(msg.get("Date")).timestamp()
                        except Exception:
                            ts = 0.0
                        if min_timestamp is not None and ts < min_timestamp:
                            continue
                        candidates.append((ts, msg))
                except Exception:
                    continue

            if candidates:
                _, newest = max(candidates, key=lambda item: item[0])
                return self._format_mail(newest)

            await asyncio.sleep(5)

        raise MailTimedOut("Timed out waiting for verification email")

    async def wait_for_code(self, min_timestamp: float | None = None) -> str:
        html = await self.find_latest_html(min_timestamp=min_timestamp)
        text = html.get_text(" ", strip=True)

        code_patterns = [
            r"\b(\d{6})\b",
            r"\b(\d{5})\b",
            r"\b(\d{4})\b",
            r"\b([A-Z0-9]{6})\b",
        ]
        for pattern in code_patterns:
            match = re.search(pattern, text)
            if match:
                return match.group(1)
        raise ValueError("Could not find a verification code in the latest email")

    def _format_mail(self, mail) -> BeautifulSoup:
        if not mail.is_multipart():
            payload = mail.get_payload(decode=True)
            charset = mail.get_content_charset() or "utf-8"
            return BeautifulSoup(payload.decode(charset, errors="replace"), "html.parser")

        fallback = None
        for part in mail.walk():
            payload = part.get_payload(decode=True)
            if not payload:
                continue
            charset = part.get_content_charset() or "utf-8"
            if part.get_content_type() == "text/html":
                return BeautifulSoup(payload.decode(charset, errors="replace"), "html.parser")
            if part.get_content_type() == "text/plain":
                fallback = payload.decode(charset, errors="replace")

        if fallback is not None:
            return BeautifulSoup(fallback, "html.parser")
        raise ValueError("No readable content found in email")

    def close(self) -> None:
        if self.imap and self.authed:
            try:
                self.imap.logout()
            except Exception:
                pass
        self.imap = None
        self.authed = False

    def __del__(self):
        self.close()
