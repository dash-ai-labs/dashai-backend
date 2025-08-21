from abc import ABC, abstractmethod
from datetime import datetime
import re


def email_date_converter(email_date):
    if not isinstance(email_date, str):
        return None
    if email_date[:1] == "\xa0":
        email_date = email_date.replace("\xa0", "")
    if email_date.count(",") >= 2:
        email_date = ", ".join(email_date.split(", ")[-2:])
    if email_date[-3:-2].isalpha():
        email_date = " ".join(email_date.split()[:-1])
    if email_date[-1].isalpha():
        email_date = email_date[:-1]
    if " . " in email_date:
        email_date = email_date.split(" . ")[0]

    # Normalize invalid numeric timezone offsets (e.g., +4865) to +0000
    # RFC-valid offsets are within ±14 hours and minutes 00-59. Anything outside is coerced to UTC.
    tz_match = re.search(r"([+-])(\d{2})(\d{2})(?!\d)", email_date)
    if tz_match:
        sign, hours_str, minutes_str = tz_match.groups()
        try:
            hours = int(hours_str)
            minutes = int(minutes_str)
            if hours > 14 or minutes > 59:
                email_date = email_date[: tz_match.start()] + "+0000" + email_date[tz_match.end() :]
        except ValueError:
            # If parsing fails for any reason, coerce to UTC as a safe default
            email_date = email_date[: tz_match.start()] + "+0000" + email_date[tz_match.end() :]
    if email_date[:3].isalpha() and email_date[-3] != ":" and email_date[-6] == "_":
        return datetime.strptime(email_date.split(".")[0], "%a, %d %b %Y %H:%M:%S %z")
    elif email_date[:3].isalpha() and email_date[-3] != ":" and "(" in email_date:
        return datetime.strptime(email_date.split(" (")[0], "%a, %d %b %Y %H:%M:%S %z")
    elif email_date[:3].isalpha() and email_date[-3] != ":":
        # Handle microseconds by trying with and without them
        try:
            return datetime.strptime(email_date, "%a, %d %b %Y %H:%M:%S %z")
        except ValueError:
            # Try with microseconds
            try:
                return datetime.strptime(email_date, "%a, %d %b %Y %H:%M:%S.%f %z")
            except ValueError:
                # If there's extra data after microseconds, try to extract just the valid part
                # Remove anything after the timezone offset
                tz_pattern = r"([+-]\d{4})"
                tz_match = re.search(tz_pattern, email_date)
                if tz_match:
                    clean_date = email_date[: tz_match.end()]
                    try:
                        return datetime.strptime(clean_date, "%a, %d %b %Y %H:%M:%S.%f %z")
                    except ValueError:
                        return datetime.strptime(clean_date, "%a, %d %b %Y %H:%M:%S %z")
                raise
    elif email_date[-3] == ":":
        # Handle microseconds for timezone-less format
        try:
            return datetime.strptime(email_date, "%a, %d %b %Y %H:%M:%S")
        except ValueError:
            try:
                return datetime.strptime(email_date, "%a, %d %b %Y %H:%M:%S.%f")
            except ValueError:
                # Extract just the datetime part if there's extra data
                if "." in email_date:
                    # Find the seconds part and keep up to 6 digits for microseconds
                    parts = email_date.split(".")
                    if len(parts) > 1:
                        microsec_part = parts[1][:6]  # Take only first 6 digits for microseconds
                        clean_date = parts[0] + "." + microsec_part
                        return datetime.strptime(clean_date, "%a, %d %b %Y %H:%M:%S.%f")
                raise
    elif email_date.count("-") == 2:
        return datetime.strptime(email_date, "%d-%m-%Y")
    else:
        # Handle microseconds for fallback format
        try:
            return datetime.strptime(email_date, "%d %b %Y %H:%M:%S %z")
        except ValueError:
            try:
                return datetime.strptime(email_date, "%d %b %Y %H:%M:%S.%f %z")
            except ValueError:
                # Remove extra data after timezone if present
                tz_pattern = r"([+-]\d{4})"
                tz_match = re.search(tz_pattern, email_date)
                if tz_match:
                    clean_date = email_date[: tz_match.end()]
                    try:
                        return datetime.strptime(clean_date, "%d %b %Y %H:%M:%S.%f %z")
                    except ValueError:
                        return datetime.strptime(clean_date, "%d %b %Y %H:%M:%S %z")
                raise


class AbstractMessage(ABC):
    def __init__(self, message_dict):
        self._message_dict = message_dict

    @abstractmethod
    def get_from(self):
        pass

    @abstractmethod
    def get_from_name(self):
        pass

    @abstractmethod
    def get_to(self):
        pass

    @abstractmethod
    def get_cc(self):
        pass

    def get_label_ids(self):
        pass

    @abstractmethod
    def get_subject(self):
        pass

    @abstractmethod
    def get_date(self):
        pass

    @abstractmethod
    def get_content(self):
        pass

    @abstractmethod
    def get_raw_content(self):
        pass

    @abstractmethod
    def get_attachments(self):
        pass

    def get_thread_id(self):
        pass

    @abstractmethod
    def get_email_id(self):
        pass

    def get_snippet(self):
        pass

    def to_dict(self):
        return {
            "_id": self.get_email_id(),
            "threads": self.get_thread_id(),
            "labels": self.get_label_ids(),
            "to": self.get_to(),
            "sender": self.get_from(),
            "sender_name": self.get_from_name(),
            "cc": self.get_cc(),
            "snippet": self.get_snippet(),
            "subject": self.get_subject(),
            "content": self.get_content(),
            "raw_content": self.get_raw_content(),
            "date": self.get_date(),
            "attachments": self.get_attachments(),
        }
