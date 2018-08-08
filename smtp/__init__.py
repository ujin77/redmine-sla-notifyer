# -*- coding: utf-8 -*-
import smtplib
import logging

# import message


class SMTP(object):
    """
    Transport to send emails using smtp
    """

    def __init__(self, host, username, password, **opts):
        """
        Construct smtp transport object

        Args:
            host: host
            port: port
            username: username
            password: password
            tls: Use TLS
            ssl: Use SSL
            port: port number
        """
        self.username = username
        self.password = password
        self.host = host
        self.tls = opts.get('tls')
        self.ssl = opts.get('ssl')
        port = opts.get('port')
        if self.ssl and not port:
            port = smtplib.SMTP_SSL_PORT
        if self.tls and not port:
            port = 587
        if not port:
            port = smtplib.SMTP_PORT
        self.HOSTPORT = (self.host, port)

    def send(self, _message):
        if self.ssl:
            server = smtplib.SMTP_SSL(*self.HOSTPORT)
        else:
            server = smtplib.SMTP(*self.HOSTPORT)
            if self.tls:
                server.starttls()
        try:
            # server.set_debuglevel(1)
            if self.ssl or self.tls:
                server.login(self.username, self.password)
            server.sendmail(_message.mail_from,
                            _message.mail_to,
                            _message.as_string())
            server.quit()
        except smtplib.SMTPAuthenticationError as e:
            server.quit()
            logging.error('Send mail [SMTPAuthenticationError]: %i %s' % (e.smtp_code, e.smtp_error))
            return False
        except smtplib.SMTPRecipientsRefused as e:
            server.quit()
            for (k, v) in e.recipients.items():
                logging.error('RecipientsRefused: %s Reply: %s %s' % (k, v[0], v[1]))
            return False
        except Exception as e:
            logging.error('Send mail error: %s' % e)
            return False
        return True
