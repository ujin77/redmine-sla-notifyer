# -*- coding: utf-8 -*-
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.audio import MIMEAudio
from email.mime.base import MIMEBase
from email.mime.image import MIMEImage
from email.header import Header
from email import encoders


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
        # self._headers = {}
        self._headers = opts.get('headers', {})
        self.attachments = []
        # self._message = MIMEMultipart('alternative')
        # self._message = MIMEMultipart()
        # self.attach(opts.get('text'), 'plain')
        # self.attach(opts.get('html'), 'html')
        # self.attachments.append({'file': 'data.html', 'data': opts.get('html')})
        self._html = opts.get('html')
        self._text = opts.get('text')
        self._important = opts.get('important', False)
        self._from(_from)
        self._to(_to)
        self._subject(subject)

        # self.reply_to = ''
        # self.to = []
        # self.cc = []
        # self.bcc = []

    # def attach(self, _text, _subtype='plain'):
    #     if _text:
    #         self._message.attach(MIMEText(_text, _subtype, 'utf-8'))

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
            for k, v in recipients.iteritems():
                self.mail_to.append('%s <%s>' % (_encode_header(v), k))
        elif isinstance(recipients, tuple):
            for recipient in recipients:
                self.mail_to.append(recipient)
        elif isinstance(recipients, list):
            self.mail_to = recipients
        self.add_header('To', ', '.join(self.mail_to))

    def add_header(self, name, value):
        self._headers[name] = value

    def add_headers(self, headers):
        if isinstance(headers, dict):
            self._headers.update(headers)

    def _get_attach_mime(self, attach):
        """
        Get a MIME part from the given file uploaded
        """
        filename = attach['file']
        data = attach['data']
        ctype = attach['ctype']
        encoding = attach['encoding'] if 'encoding' in attach else 'utf-8'
        maintype, subtype = ctype.split('/', 1)
        if maintype == 'text':
            msg = MIMEText(data, _subtype=subtype, _charset=encoding)
        elif maintype == 'image':
            msg = MIMEImage(data, _subtype=subtype)
        elif maintype == 'audio':
            msg = MIMEAudio(data, _subtype=subtype)
        else:
            msg = MIMEBase(maintype, subtype)
            msg.set_payload(data)
            encoders.encode_base64(msg)

        if attach.get('cid', False):
            msg.add_header('Content-ID', '<%s>' % attach['cid'])
        else:
            msg.add_header('Content-Disposition', 'attachment', filename=filename)

        return msg

    def add_attachment(self, filename, data, ctype='text/plain', cid=None):
        """
        Add attachment to email

        Args:
            filename: name of the file as seen in email
            data: data string
            ctype: Content-Type
            cid: Content-ID header, optional

        Returns:
            self
        """
        self.attachments.append({'file': filename, 'data': data, 'ctype': ctype, 'cid': cid})

    def as_string(self):
        _message = MIMEMultipart()
        if self._important:
            self.add_header("Importance", "High")
            self.add_header("X-MSMail-Priority", "High")
            self.add_header("X-Priority", "1 (Highest)")
        for _header in sorted(self._headers):
            _message[_header] = _encode_header(self._headers[_header])
        if self._html:
            _message.attach(MIMEText(self._html, 'html', 'utf-8'))
        if self._text:
            _message.attach(MIMEText(self._text, 'plain', 'utf-8'))
        if self.attachments:
            for attach in self.attachments:
                f = self._get_attach_mime(attach)
                if f:
                    _message.attach(f)
        return _message.as_string()
