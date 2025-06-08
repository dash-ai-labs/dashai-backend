import base64
from html.parser import HTMLParser
from io import StringIO

from src.base.message import AbstractMessage, email_date_converter
from src.libs import clean_up_text


class MLStripper(HTMLParser):
    def __init__(self):
        super().__init__()
        self.reset()
        self.strict = False
        self.convert_charrefs = True
        self.text = StringIO()

    def handle_data(self, d):
        self.text.write(d)

    def get_data(self):
        return self.text.getvalue()


def get_email_dict(message):
    try:
        return Message(message_dict=message).to_dict()
    except ValueError as e:
        print(message, str(e))
        return None


class Message(AbstractMessage):
    def __init__(self, message_dict):
        self._message_dict = message_dict

    def get_from(self):
        return self._split_emails(email_lst=self.get_header_field_from_message(field="From"))

    def get_from_name(self):
        email_lst = self._split_names(email_list=self.get_header_field_from_message(field="From"))
        return email_lst

    def get_to(self):
        return self._split_emails(email_lst=self.get_header_field_from_message(field="To"))

    def get_cc(self):
        return self._split_emails(email_lst=self.get_header_field_from_message(field="Cc"))

    def get_label_ids(self):
        if "labelIds" in self._message_dict.keys():
            return self._message_dict["labelIds"]
        else:
            return []

    def get_attachments(self):
        attachment_ids = []
        if (
            "body" in self._message_dict["payload"].keys()
            and "attachmentId" in self._message_dict["payload"]["body"].keys()
        ):
            attachment_ids.append(
                {
                    "name": self._message_dict["payload"]["filename"],
                    "id": self._message_dict["payload"]["body"]["attachmentId"],
                }
            )
        if "parts" in self._message_dict["payload"].keys():
            attachment_ids.extend(
                Message._get_attachment_ids(payload=self._message_dict["payload"])
            )
        return attachment_ids

    def get_subject(self):
        return self.get_header_field_from_message(field="Subject")

    def get_date(self):
        if self.get_header_field_from_message(field="Date") is None:
            email_date = self.get_header_field_from_message(field="date")
        else:
            email_date = self.get_header_field_from_message(field="Date")
        return email_date_converter(email_date=email_date)

    def get_content(self):
        if "parts" in self._message_dict["payload"].keys():
            return self._get_parts_content(message_parts=self._message_dict["payload"]["parts"])
        else:
            return self._get_parts_content(message_parts=[self._message_dict["payload"]])

    def get_raw_content(self):
        if "parts" in self._message_dict["payload"].keys():
            return self._get_raw_parts_content(message_parts=self._message_dict["payload"]["parts"])
        else:
            return self._get_raw_parts_content(message_parts=[self._message_dict["payload"]])

    def get_thread_id(self):
        return self._message_dict["threadId"]

    def get_email_id(self):
        return self._message_dict["id"]

    def get_snippet(self):
        return self._message_dict["snippet"]

    def get_header_field_from_message(self, field):
        lst = [
            entry["value"]
            for entry in self._message_dict["payload"]["headers"]
            if entry["name"].lower() == field.lower()
        ]
        if len(lst) > 0:
            return lst[0]
        else:
            return None

    def _get_raw_parts_content(self, message_parts):
        content_types = [p["mimeType"] for p in message_parts if "mimeType" in p.keys()]
        if "text/html" in content_types:
            return self._get_email_body(
                message_parts=message_parts[content_types.index("text/html")]
            )
        elif "text/plain" in content_types:
            return self._get_email_body(
                message_parts=message_parts[content_types.index("text/plain")]
            )
        # Handle multipart types recursively
        elif any(mtype.startswith("multipart/") for mtype in content_types):
            # Find the first multipart type
            for mtype in ["multipart/alternative", "multipart/related", "multipart/mixed"]:
                if mtype in content_types:
                    multi_part_content = message_parts[content_types.index(mtype)]
                    if "parts" in multi_part_content:
                        return self._get_raw_parts_content(
                            message_parts=multi_part_content["parts"]
                        )
            return None
        else:
            return None

    def _get_parts_content(self, message_parts):
        content_types = [p["mimeType"] for p in message_parts if "mimeType" in p.keys()]
        content = None
        if "text/plain" in content_types:
            content = self._get_email_body(
                message_parts=message_parts[content_types.index("text/plain")]
            )
        elif "text/html" in content_types:
            content = self._strip_tags(
                html=self._get_email_body(
                    message_parts=message_parts[content_types.index("text/html")]
                )
            )
        # Handle multipart types recursively
        elif any(mtype.startswith("multipart/") for mtype in content_types):
            # Find the first multipart type
            for mtype in ["multipart/alternative", "multipart/related", "multipart/mixed"]:
                if mtype in content_types:
                    multi_part_content = message_parts[content_types.index(mtype)]
                    if "parts" in multi_part_content:
                        return self._get_parts_content(message_parts=multi_part_content["parts"])
            return None
        else:
            content = clean_up_text(self._get_raw_parts_content(message_parts=message_parts))

        if not content:
            content = clean_up_text(self._get_raw_parts_content(message_parts=message_parts))
        return content

    def _split_emails(self, email_lst):
        if email_lst is not None:
            email_split_lst = email_lst.split(", ")
            return [
                email_address
                for email in email_split_lst
                if "@" in email
                and (email_address := self._get_email_address(email=email)) is not None
            ]
        else:
            return []

    def _split_names(self, email_list):
        if email_list is not None:
            email_split_lst = email_list.split(", ")
            names = [self._get_email_name(email=email) for email in email_split_lst if "@" in email]
            return [name for name in names if name is not None]
        else:
            return []

    @staticmethod
    def _get_email_name(email):
        email_split = email.split("<")
        if len(email_split) == 1:
            return None
        else:
            return email_split[0].strip()

    @staticmethod
    def _get_email_body(message_parts):
        if "body" in message_parts.keys() and "data" in message_parts["body"].keys():
            return (
                base64.urlsafe_b64decode(message_parts["body"]["data"].encode("UTF-8"))
                .decode("UTF-8")
                .strip()
            )
        else:
            return ""

    @staticmethod
    def _get_attachment_ids(payload):
        attachment_ids = []
        if "parts" in payload.keys():
            for part in payload["parts"]:
                attachment_ids.extend(Message._get_attachment_ids(payload=part))
        if "body" in payload.keys() and "attachmentId" in payload["body"].keys():
            attachment_ids.append(
                {
                    "name": payload["filename"],
                    "id": payload["body"]["attachmentId"],
                }
            )
        return attachment_ids

    @staticmethod
    def _strip_tags(html):
        s = MLStripper()
        s.feed(html)
        return s.get_data()

    @staticmethod
    def _get_email_address(email):
        email_split = email.split("<")
        if len(email_split) == 1:
            return email.lower()
        else:
            return email_split[1].split(">")[0].lower()

    def get_is_read(self):
        return "UNREAD" not in self._message_dict["labelIds"]
