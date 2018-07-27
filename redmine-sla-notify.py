#!/usr/bin/python
# -*- coding: utf-8
#

import os
import sys
import json
import ConfigParser
from redmine import SLA, RedmineClient, time_diff
from db import HistoryDB
from sendmail import Sendmail
import logging
from logging.config import fileConfig as logfileConfig
import argparse

PATH = os.path.dirname(os.path.abspath(__file__))
PROG = os.path.splitext(os.path.basename(__file__))[0]


CONFIG = {
    'mail': {
        'to': 'test@domain.local',
        'from': 'test@domain.local',
        'host': 'smtp.domain.local',
        'user': 'test@domain.local',
        'password': 'password',
        'port': 465,
        'subject': 'TEST'
    },
    'redmine': {
        'url': 'http://localhost',
        'api-key': 'key',
    }
}


def file_path(filename):
    return os.path.join(PATH, filename)


def load_config(fname):
    if os.path.isfile(fname):
        config = ConfigParser.ConfigParser(allow_no_value=True)
        try:
            config.readfp(open(fname))
            for section in config.sections():
                for (name, value) in config.items(section):
                    if not CONFIG.get(section): CONFIG[section] = {}
                    CONFIG[section][name] = value.strip("'\"")
        except ConfigParser.MissingSectionHeaderError as e:
            logging.error(e)
        except Exception as e:
            logging.error(e)


def load_json(fname):
    if os.path.isfile(fname):
        try:
            return json.load(open(fname), encoding='utf-8')
        except Exception as e:
            logging.error(e)


class Redmine(RedmineClient):

    def on_init(self):
        self._get_users()

    def get_projects_with_sla(self):
        project_sla = []
        for project in self.get('projects'):
            if 'custom_fields' in project:
                for custom_field in project['custom_fields']:
                    if custom_field['name'] == 'SLA' and custom_field['value']:
                        project_sla.append({
                            'id': project['id'],
                            'identifier': project['identifier'],
                            'name': project['name'],
                            'sla': custom_field['value']
                        })
        return project_sla

    def get_issues(self, project_id):
        opened_issues = []
        for issue in self.get('issues', {'project_id': project_id, 'status_id': 'open'}):
            # print json.dumps(issue, indent=2, ensure_ascii=False)
            opened_issues.append({
                'id': issue['id'],
                'subject': issue['subject'],
                'status': issue['status']['name'],
                'priority': issue['priority']['name'],
                'author': issue['author']['name'],
                'assigned_to': issue['assigned_to']['name'] if 'assigned_to' in issue else None,
                'created_on': issue['created_on']
            })
        return opened_issues

    def get_memberships(self, project_id):
        _roles = {}
        memberships = self.get('projects/{}/memberships'.format(project_id))
        for membership in memberships:
            if 'user' in membership:
                member_user_id = membership['user']['id']
                member_user_name = membership['user']['name']
                for role in membership['roles']:
                    if role['name'] not in _roles:
                        _roles[role['name']] = {'users': {}}
                    _roles[role['name']]['users'][self.get_user_mail(member_user_id)] = member_user_name
        return _roles

    def get_user_mail(self, user_id):
        return self.users[user_id]['mail']

    def _get_users(self):
        self.users = {}
        _users = self.get('users', {'status': 1})
        for _user in _users:
            self.users[_user['id']] = {
                'mail': _user['mail']
            }

    def get_users(self):
        return self.users


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument('-c', '--conf-file', default=os.path.join(PATH, PROG +'.conf'))
    parser.add_argument('-s', '--sla-file', default=os.path.join(PATH, 'sla.json'))
    parser.add_argument('-l', '--log-conf-file', default=os.path.join(PATH, 'logging.conf'))
    parser.add_argument('-r', '--reset-history', action='store_true', help="Reset history")
    args = parser.parse_args()

    if os.path.isfile(args.log_conf_file):
        logfileConfig(args.log_conf_file)
    else:
        logging.basicConfig(level=logging.DEBUG)

    logging.debug("START")
    logging.debug('Config file: %s' % args.conf_file)
    logging.debug('SLA config file: %s' % args.sla_file)
    logging.debug('Log config file: %s' % args.log_conf_file)

    load_config(args.conf_file)
    if not os.path.isfile(args.sla_file):
        logging.error("The SLA configuration is not specified")
        parser.print_help()
        sys.exit(0)

    sla = SLA(load_json(args.sla_file))
    history = HistoryDB(file_path('history.db'))
    if args.reset_history:
        history.reset()
    sendmail = Sendmail(CONFIG['mail'])

    rm = Redmine(CONFIG)

    for project in rm.get_projects_with_sla():
        roles = rm.get_memberships(project['id'])
        for issue in rm.get_issues(project['id']):
            time_window = sla.in_time_window(project['sla'], time_diff(issue['created_on']))
            if time_window:
                if history.not_sent(issue['id'], time_window['name']):
                    notify_roles = ', '.join(unicode(u'%s' % item) for item in time_window['notify'])
                    if notify_roles:
                        emails = {}
                        for notify_role in time_window['notify']:
                            if notify_role in roles:
                                users = roles[notify_role]['users']
                                for mail in users:
                                    emails[mail] = ''
                        rcpt = ', '.join(str('%s' % item) for item in emails)

                        logging.info(u'[%i] %s' % (issue['id'], issue['subject']))
                        logging.info(u'[%i] Project: %s' % (issue['id'], project['name']))
                        logging.info(u'[%i] SLA: %s' % (issue['id'], project['sla']))
                        logging.info(
                            u'[%i] Time after creation: %s' % (issue['id'], time_diff(issue['created_on'], False)))
                        logging.info(u'[%i] Time window: %s' % (issue['id'], time_window['name']))
                        logging.info(u'[%i] Notify roles: %s' % (issue['id'], notify_roles))
                        logging.info(u'[%i] Notify emails: %s' % (issue['id'], rcpt))
                        if sendmail.send(
                                rcpt=rcpt,
                                issue_id=issue['id'],
                                issue_name=issue['subject'],
                                project=project['name'],
                                sla=project['sla'],
                                time_after_creation=time_diff(issue['created_on'], False),
                                time_window=time_window['name'],
                                notify_roles=notify_roles
                                     ):
                            history.sent(issue['id'], time_window['name'])
                            logging.info('[%i] Mails are sent' % issue['id'])
    logging.debug("END")
