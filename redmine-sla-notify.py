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
PROGRAM = os.path.splitext(os.path.basename(__file__))[0]


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


def _debug(data):
    if isinstance(data, dict):
        for item in data:
            logging.debug('%s: %s' % (item, data[item]))


def load_config(f_name):
    if os.path.isfile(f_name):
        config = ConfigParser.ConfigParser(allow_no_value=True)
        try:
            config.readfp(open(f_name))
            for section in config.sections():
                for (name, value) in config.items(section):
                    if not CONFIG.get(section):
                        CONFIG[section] = {}
                    CONFIG[section][name] = value.strip("'\"")
        except ConfigParser.MissingSectionHeaderError as e:
            logging.error(e)
        except Exception as e:
            logging.error(e)


def load_json(f_name):
    if os.path.isfile(f_name):
        try:
            return json.load(open(f_name), encoding='utf-8')
        except Exception as e:
            logging.error(e)


class Redmine(RedmineClient):

    def on_init(self):
        self._get_users()

    def get_projects_with_sla(self):
        project_sla = []
        for _project in self.get('projects'):
            if 'custom_fields' in _project:
                for custom_field in _project['custom_fields']:
                    if custom_field['name'] == 'SLA' and custom_field['value']:
                        project_sla.append({
                            'id': _project['id'],
                            'identifier': _project['identifier'],
                            'name': _project['name'],
                            'sla': custom_field['value']
                        })
        return project_sla

    def get_issues(self, project_id):
        opened_issues = []
        for _issue in self.get('issues', {'project_id': project_id, 'status_id': 'open'}):
            # print json.dumps(issue, indent=2, ensure_ascii=False)
            opened_issues.append({
                'id': _issue['id'],
                'project_id': _issue['project']['id'],
                'subject': _issue['subject'],
                'status': _issue['status']['name'],
                'priority': _issue['priority']['name'],
                'author': _issue['author']['name'],
                'assigned_to': _issue['assigned_to']['name'] if 'assigned_to' in _issue else None,
                'created_on': _issue['created_on']
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


def issue_get_rcpt(_issue, _roles):
    emails = {}
    for notify_role in _issue['time_window']['notify']:
        if notify_role in _roles:
            for _mail in _roles[notify_role]['users']:
                emails[_mail] = ''
    return ', '.join(str('%s' % item) for item in emails)


def issue_get_notify_roles(_issue):
    return ', '.join(unicode(u'%s' % item) for item in _issue['time_window']['notify'])


def issue_log_info(_issue):
    # print json.dumps(_issue, indent=2, ensure_ascii=False)
    logging.info(u'[%i] %s' % (_issue['id'], _issue['subject']))
    logging.info(u'[%i] Created: %s' % (_issue['id'], _issue['created_on']))
    logging.info(u'[%i] Priority: %s' % (_issue['id'], _issue['priority']))
    logging.info(u'[%i] Project: %s' % (_issue['id'], _issue['project']['name']))
    logging.info(u'[%i] SLA: %s' % (_issue['id'], _issue['project']['sla']))
    logging.info(
        u'[%i] Time after creation: %s' % (_issue['id'], _issue['time_after_creation']))
    logging.info(u'[%i] Time window: %s' % (_issue['id'], _issue['time_window']['name']))
    logging.info(u'[%i] Notify roles: %s' % (_issue['id'], _issue['notify_roles']))
    logging.info(u'[%i] Rcpt: %s' % (_issue['id'], _issue['rcpt']))


def issue_log_debug(_issue, _msg=''):
    # print json.dumps(_issue, indent=2, ensure_ascii=False)
    logging.debug(u'[%i] %s' % (_issue['id'], _issue['subject']))
    logging.debug(u'[%i] Created: %s' % (_issue['id'], _issue['created_on']))
    logging.debug(u'[%i] Priority: %s' % (_issue['id'], _issue['priority']))
    logging.debug(u'[%i] Project: %s' % (_issue['id'], _issue['project']['name']))
    logging.debug(u'[%i] SLA: %s' % (_issue['id'], _issue['project']['sla']))
    if 'time_after_creation' in _issue:
        logging.debug(u'[%i] Time after creation: %s' % (_issue['id'], _issue['time_after_creation']))
    logging.debug(u'[%i] Time window: %s' % (_issue['id'], _issue['time_window']['name']))
    if 'notify_roles' in _issue:
        logging.debug(u'[%i] Notify roles: %s' % (_issue['id'], _issue['notify_roles']))
    if 'rcpt' in _issue:
        logging.debug(u'[%i] Rcpt: %s' % (_issue['id'], _issue['rcpt']))
    logging.debug(u'[%i] %s' % (_issue['id'], _msg))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument('-c', '--conf-file', default=os.path.join(PATH, PROGRAM + '.conf'))
    parser.add_argument('-s', '--sla-file', default=os.path.join(PATH, 'sla.json'))
    parser.add_argument('-l', '--log-conf-file', default=os.path.join(PATH, 'logging.conf'))
    parser.add_argument('-r', '--reset-history', action='store_true', help="Reset history")
    args = parser.parse_args()

    if os.path.isfile(args.log_conf_file):
        logfileConfig(args.log_conf_file)
    else:
        logging.basicConfig(level=logging.INFO)

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
    # history.reset()
    mail = Sendmail(CONFIG['mail'])

    rm = Redmine(CONFIG)

    for project in rm.get_projects_with_sla():
        roles = rm.get_memberships(project['id'])
        logging.debug('Project: #%i %s ###' % (project['id'], project['name']))
        for issue in rm.get_issues(project['id']):
            if issue['project_id'] == project['id']:
                issue['time_window'] = sla.in_time_window(project['sla'], issue['priority'], issue['created_on'])
                if issue['time_window']:
                    issue['project'] = project
                    if history.not_sent(issue['id'], issue['time_window']['name']):
                        issue['notify_roles'] = issue_get_notify_roles(issue)
                        if issue['notify_roles']:
                            issue['rcpt'] = issue_get_rcpt(issue, roles)
                            issue['time_after_creation'] = time_diff(issue['created_on'], False)
                            issue_log_info(issue)
                            if mail.send(issue=issue):
                                history.sent(issue['id'], issue['time_window']['name'])
                        else:
                            issue_log_debug(issue, 'no notify roles')
                    else:
                        issue_log_debug(issue, 'in history')
    logging.debug("END")
