#!/usr/bin/python
# -*- coding: utf-8 -*-
#
# import smtplib
# from email.mime.multipart import MIMEMultipart
# from email.mime.text import MIMEText
from jinja2 import Environment, FileSystemLoader
# import logging
# import json
import os
from smtp import SMTP
from smtp.message import Message


TEMPLATE_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'templates')
MAIL_HEADERS = {
    'X-Mailer': 'Redmine',
    'X-Auto-Response-Suppress': 'All',
    'Auto-Submitted': 'auto-generated'
}


class Sendmail(object):

    def __init__(self, config, template_report=False, debug=False):
        super(Sendmail, self).__init__()
        self._config = config
        self._debug = debug
        self._report = template_report
        env = Environment(loader=FileSystemLoader(TEMPLATE_PATH))
        if template_report:
            self.template = env.get_template('report.html')
        else:
            self.template = env.get_template('issue.html')
        self._smtp = SMTP(self._config['host'], self._config['user'], self._config['password'], ssl=True)

    def _send(self, rcpt, html, _subject=None, _headers=None, important=False):
        if _subject:
            _subject = '%s %s' % (self._config['subject'], _subject)
        else:
            _subject = self._config['subject']
        _msg = Message(rcpt, _subject, self._config['from'], html=html, important=important, headers=MAIL_HEADERS)
        # print _msg.as_string()
        # return True
        return self._smtp.send(_msg)

    def send(self, issue, important=False):
        return self.send_issue(issue, important=important)

    def send_issue(self, issue, important=False):
        if self._report:
            return False
        return self._send(issue['rcpt'], self.template.render(
            url=self._config['url'],
            issue=issue),
                          issue['subject'],
                          issue['time_window']['mail_headers'] if 'mail_headers' in issue['time_window'] else None,
                          important=important
                          )

    def send_report(self, rcpt, data, important=False):
        if not self._report:
            return False
        return self._send(rcpt, self.template.render(
            projects=data,
            url=self._config['url']),
                          important=important
                          )
