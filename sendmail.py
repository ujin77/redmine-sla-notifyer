#!/usr/bin/python
# -*- coding: utf-8 -*-
#
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from jinja2 import Template
import logging

TEMPLATE = u"""
<html lang="en">
<head>
    <meta charset="UTF-8">
    <style>
        body{font-family:Verdana, sans-serif;font-size:14px;line-height:1.4em;color:#222}
        a:link{color:#169}
        a:visited{color:#169}
        a:hover{color:#c61a1a}
        a:active{color:#c61a1a}
        hr {width:100%;height:1px;background:#ccc;border:0;margin:1.2em 0}
        h1 {font-family:"Trebuchet MS", Verdana, sans-serif;margin:0px;font-size:1.3em;line-height:1.4em}
        pre {font-family:Consolas, Menlo, "Liberation Mono", Courier, monospace;
            margin:1em 1em 1em 1.6em;padding:8px;background-color:#fafafa;
            border:1px solid #e2e2e2;border-radius:3px;width:auto;overflow-x:auto;overflow-y:hidden'}
        code {font-family:Consolas, Menlo, "Liberation Mono", Courier, monospace}
        .footer{font-size:0.8em;font-style:italic}
        .external{color:#169}
        .journal_details{color:#959595;margin-bottom:1.5em}
        .details{color:#959595;margin-bottom:1.5em}
    </style>
</head>
<body>
<span class="header"><p>{{ subject }}</p></span>
<h1>Задача <a href="{{ url }}/issues/{{ issue_id }}">#{{ issue_id }}</a>:
 <a href="{{ url }}/issues/{{ issue_id }}">{{ issue_name }}</a></h1>
<ul class="details">
    <li><strong>Приоритет: </strong>{{ priority }}</li>
    <li><strong>Проект: </strong>{{ project }}</li>
    <li><strong>Уровень обслуживания: </strong>{{ sla }}</li>
    <li><strong>Время с момента добавления: </strong>{{ time_after_creation }}</li>
    <li><strong>Эскалация: </strong>{{ time_window }}</li>
    <li><strong>Уведомления отправлены: </strong>{{ notify_roles }}</li>
</ul>
<hr>
<span class="footer">
    <p><a class="external" href="{{ url }}">{{ url }}</a></p>
</span>
</body>
</html>
"""


class Sendmail(object):

    def __init__(self, config, debug=False):
        super(Sendmail, self).__init__()
        self._config = config
        self._debug = debug
        self.template = Template(TEMPLATE, trim_blocks=True)

    def _send(self, rcpt, html, _subject=None, _headers=None):
        _msg = MIMEMultipart('alternative', None, [MIMEText(html, 'html', 'utf-8')])
        _msg['From'] = self._config['from']
        _msg['To'] = rcpt
        if _subject:
            _msg['Subject'] = '%s %s' % (self._config['subject'], _subject)
        else:
            _msg['Subject'] = self._config['subject']
        if _headers:
            for k, v in _headers.iteritems():
                _msg[k] = v
        server = None
        try:
            server = smtplib.SMTP_SSL(self._config['host'], self._config['port'])
            if self._debug:
                server.set_debuglevel(1)
            server.login(self._config['user'], self._config['password'])
            server.sendmail(self._config['from'], rcpt.split(','), _msg.as_string())
            server.quit()
        except smtplib.SMTPAuthenticationError as e:
            logging.error('Send mail [SMTPAuthenticationError]: %i %s' % (e.smtp_code, e.smtp_error))
            server.quit()
            return False
        except smtplib.SMTPRecipientsRefused as e:
            logging.error('Send mail [SMTPRecipientsRefused]')
            for (k, v) in e.recipients.items():
                logging.error('%s %s %s' % (k, v[0], v[1]))
            server.quit()
            return False
        except Exception as e:
            logging.error('Send mail error: %s' % e)
            return False
        return True

    def send(self, issue):
        return self._send(issue['rcpt'], self.template.render(
                url=self._config['url'],
                issue_id=issue['id'],
                issue_name=issue['subject'],
                priority=issue['priority'],
                project=issue['project']['name'],
                sla=issue['project']['sla'],
                time_after_creation=issue['time_after_creation'],
                time_window=issue['time_window']['name'],
                notify_roles=issue['notify_roles']),
            issue['subject'],
            issue['time_window']['mail_headers'] if 'mail_headers' in issue['time_window'] else None
        )
