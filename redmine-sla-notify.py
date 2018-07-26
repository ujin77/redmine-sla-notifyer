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

PATH = os.path.dirname(os.path.abspath(__file__))

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
    },
}


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
            print e
        except Exception as e:
            print e


def load_json(fname):
    if os.path.isfile(fname):
        try:
            return json.load(open(fname), encoding='utf-8')
        except Exception as e:
            print e

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

    conf_file = PATH + '/test.conf'
    sla_file = PATH + '/sla.json'
    db_file = PATH + '/history.db'
    # print conf_file
    # print sla_file
    # print db_file
    # sys.exit()

    load_config(conf_file)
    sendmail = Sendmail(CONFIG['mail'])
    sla = SLA(load_json(sla_file))
    history = HistoryDB(db_file)
    # history.reset()
    rm = Redmine(CONFIG)

    for project in rm.get_projects_with_sla():
        roles = rm.get_memberships(project['id'])
        for issue in rm.get_issues(project['id']):
            time_window = sla.in_time_window(project['sla'], time_diff(issue['created_on']))
            if time_window:
                # print json.dumps(time_window, indent=2, ensure_ascii=False)
                if history.not_sent(issue['id'], time_window['name']):
                    notify_roles = ', '.join(str('%s' % item.encode('utf-8')) for item in time_window['notify'])
                    emails = {}
                    for notify_role in time_window['notify']:
                        if notify_role in roles:
                            users = roles[notify_role]['users']
                            for mail in users:
                                emails[mail] = ''
                    rcpt = ', '.join(str('%s' % item) for item in emails)

                    print '======================================'
                    print 'Id:', issue['id']
                    print 'Issue:', issue['subject'].encode('utf-8')
                    print 'Project:', project['name'].encode('utf-8')
                    print 'SLA:', project['sla']
                    print 'Time since creation:', time_diff(issue['created_on'], False)
                    print 'Time:', time_window['name']
                    print 'Notify roles:', notify_roles
                    print 'Notify emails:', rcpt

                    if sendmail.send(
                            rcpt=rcpt,
                            issue_id=issue['id'],
                            issue_name=issue['subject'],
                            project=project['name'],
                            sla=project['sla'],
                            time_after_creation=time_diff(issue['created_on'], False),
                            time_window=time_window['name'],
                            notify_roles=notify_roles.decode('utf-8')
                                 ):
                        history.sent(issue['id'], time_window['name'])
                # else:
                #     print 'Issue:', issue['id'], '-', issue['subject'], 'Project:', project['name'], '-', time_window['name']
