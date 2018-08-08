# -*- coding: utf-8 -*-
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.header import Header


def _is_ascii(s):
    """
    Checks if the given string is in ascii format
    """
    try:
        s.encode('ascii')
    except UnicodeError:
        return False
    return True


def _encode_header(header):
    """
    If header is non-ascii, encode it in utf-8
    """
    if not _is_ascii(header):
        try:
            h = Header(header, 'utf-8')
            return h
        except Exception as e:
            print e
    return header


class Message(object):
    """
    Email Message
    """

    mail_from = ''

    def __init__(self, _to, subject, _from, **opts):
        """
        Constructs Message object

        Args:
            mail_from: From address, email "example@example.com" or tuple ("example@example.com", "John, Doe")
            subject: Email subject
            text: Email content, plain text
            html: Email content, html

        Returns:
            self

        Raises:
            ValueError: on invalid arguments
        """
        self.mail_to = []
        self._message = MIMEMultipart('alternative')
        self.attach(opts.get('text'), 'plain')
        self.attach(opts.get('html'), 'html')
        self._important = opts.get('important', False)
        self._from(_from)
        self._to(_to)
        self._subject(subject)

        # self.reply_to = ''
        # self.to = []
        # self.cc = []
        # self.bcc = []
        # self.headers = {}
        # self.attachments = []

    def attach(self, _text, _subtype='plain'):
        if _text:
            self._message.attach(MIMEText(_text, _subtype, 'utf-8'))

    def _from(self, mail_from):
        if mail_from:
            self.add_header('From', mail_from)
            self.mail_from = mail_from

    def _subject(self, subject):
        if subject:
            self.add_header('Subject', _encode_header(subject))

    def _to(self, recipients):
        """
        Add recipient

        Args:
            recipients: recipient, accepts string, list or dict
                if dict is passed, "To" field will be ignored and batch sending with substitution triggered

        Returns:
            self
        """
        if not recipients:
            raise ValueError('No recipients')
        if isinstance(recipients, (str, unicode)):
            for recipient in recipients.split(','):
                self.mail_to.append(recipient.strip())
        elif isinstance(recipients, dict):
            for k in recipients:
                self.mail_to.append(k)
        elif isinstance(recipients, tuple):
            for recipient in recipients:
                self.mail_to.append(recipient)
        elif isinstance(recipients, list):
            self.mail_to = recipients
        self.add_header('To', ', '.join(self.mail_to))

    def add_header(self, name, value):
        self._message[name] = value

    def as_string(self):
        if self._important:
            self.add_header("Importance", "High")
            self.add_header("X-MSMail-Priority", "High")
            self.add_header("X-Priority", "1 (Highest)")
        return self._message.as_string()
