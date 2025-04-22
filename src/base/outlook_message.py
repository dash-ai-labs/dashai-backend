from msgraph.generated.models.message import Message

from src.base.message import AbstractMessage


class OutlookMessage(AbstractMessage):
    def __init__(self, message: Message):
        self.message = message

    def get_from(self):
        return [self.message.sender.email_address.address]

    def get_from_name(self):
        return [self.message.sender.email_address.name]

    def get_to(self):
        return [recipient.email_address.address for recipient in self.message.to_recipients]

    def get_cc(self):
        return [recipient.email_address.address for recipient in self.message.cc_recipients]

    def get_subject(self):
        return self.message.subject

    def get_date(self):
        return self.message.received_date_time

    def get_content(self):
        return self.message.body.content

    def get_raw_content(self):
        return self.message.body.content

    def get_email_id(self):
        return self.message.id

    def get_is_read(self):
        return self.message.is_read
