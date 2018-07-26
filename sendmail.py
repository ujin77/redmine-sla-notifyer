#!/usr/bin/python
# -*- coding: utf-8 -*-
#
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from jinja2 import Template

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
<h1>Задача <a href="{{ url }}/issues/{{ issue_id }}">#{{ issue_id }}</a>: <a href="{{ url }}/issues/{{ issue_id }}">{{ issue_name }}</a></h1>
<ul class="details">
    <li><strong>Проект: </strong>{{ project }}</li>
    <li><strong>Уровень обслуживания: </strong>{{ sla }}</li>
    <li><strong>Время с момента добавления: </strong>{{ time_after_creation }}</li>
    <li><strong>Эскалация: </strong>{{ time_window }}</li>
    <li><strong>Уведомления отосланы: </strong>{{ notify_roles }}</li>
</ul>
<hr>
<span class="footer">
    <p><a class="external" href="{{ url }}">{{ url }}</a></p>
</span>
</body>
</html>
"""


class Sendmail(object):

    def __init__(self, config):
        super(Sendmail, self).__init__()
        self._config = config
        self.template = Template(TEMPLATE, trim_blocks=True)

    def _send(self, rcpt, html, subject=None):
        _msg = MIMEMultipart('alternative', None, [MIMEText(html, 'html', 'utf-8')])
        _msg['Subject'] = self._config['subject'] + subject
        _msg['From'] = self._config['from']
        _msg['To'] = rcpt
        server = None
        try:
            server = smtplib.SMTP_SSL(self._config['host'], self._config['port'])
            # if self._debug:
            # server.set_debuglevel(1)
            server.login(self._config['user'], self._config['password'])
            server.sendmail(self._config['from'], rcpt.split(','), _msg.as_string())
            server.quit()
        except smtplib.SMTPAuthenticationError as e:
            print 'Send mail [SMTPAuthenticationError]:', e.smtp_code, e.smtp_error
            server.quit()
            return False
        except smtplib.SMTPRecipientsRefused as e:
            print 'Send mail [SMTPRecipientsRefused]:'
            for (k, v) in e.recipients.items():
                print k, v[0], v[1]
            server.quit()
            return False
        except Exception as e:
            print 'Send mail error:', e
            return False
        return True

    def send(self, rcpt, issue_id, issue_name, project, sla, time_after_creation, time_window, notify_roles):
        return self._send(rcpt, self.template.render(
            url=self._config['url'],
            issue_id=issue_id,
            issue_name=issue_name,
            project=project,
            sla=sla,
            time_after_creation=time_after_creation,
            time_window=time_window,
            notify_roles=notify_roles),
                          ' ' + issue_name
        )
