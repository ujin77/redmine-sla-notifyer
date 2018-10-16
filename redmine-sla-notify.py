#!/usr/bin/python
# -*- coding: utf-8
#

import os
import sys
import json
import ConfigParser
from redmine import RedmineClient, time_diff, time_percent, date_from_redmine, BusinessTime
from db import HistoryDB
from sendmail import Sendmail
import logging
from logging.config import fileConfig as logfileConfig
import argparse
import io
import copy

PATH = os.path.dirname(os.path.abspath(__file__))
PROGRAM = os.path.splitext(os.path.basename(__file__))[0]
CONFIG = {
    'main': {
        'sla-file': 'sla.json',
        'cache_time': 3600
    },
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


def save_json(data, name):
    with io.open(name, 'w', encoding='utf-8') as f:
        f.write(json.dumps(data, ensure_ascii=False, indent=2))


def print_json(js, name=''):
    print u'--------------------\n{}'.format(name)
    print json.dumps(js, ensure_ascii=False, indent=2)


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


def issue_get_notify_roles(_time_window):
    return ', '.join(unicode(u'%s' % item) for item in _time_window['notify'])


def issue_log_info(_issue):
    # print json.dumps(_issue, indent=2, ensure_ascii=False)
    for k, v in _issue.iteritems():
        if isinstance(v, dict):
            info = ', '.join(unicode(u'%s (%s)' % (item, val)) for item, val in v.iteritems())
            v = info
        logging.info(u'[%i] %s: %s' % (_issue['id'], k, v))


def issue_log_debug(_issue, _msg=''):
    # print json.dumps(_issue, indent=2, ensure_ascii=False)
    for k, v in _issue.iteritems():
        logging.debug(u'[%i] %s: %s' % (_issue['id'], k, v))
    logging.debug(u'[%i] %s' % (_issue['id'], _msg))


class Redmine(RedmineClient):

    business_time = BusinessTime(None)
    projects = None
    hdb = None

    def on_init(self):
        self.hdb = HistoryDB(file_path('history.db'))

    def _calc_sla_persent(self):
        for sla_name, sla_val in self._config['sla'].items():
            for priority_name, priority_val in sla_val.items():
                for time_window in priority_val['time_windows']:
                    time_window['minutes'] = time_percent(priority_val['time_of_processing'], time_window['percent'])
                    # print sla_name, priority_name, priority_val['time_of_processing'],
                    #    time_window['percent'], time_window['minutes']

    def in_time_window(self, _project, _issue):
        current_time_window = None

        if 'nbd' in _project['priority'][_issue['priority']] and _project['priority'][_issue['priority']]['nbd']:
            # "NBD", _issue['priority']
            minutes = self.business_time.getminutes(date_from_redmine(_issue['created_on'], True))
        else:
            # "###", _issue['priority']
            minutes = time_diff(_issue['created_on'])
        for time_window in _project['priority'][_issue['priority']]['time_windows']:
            if minutes >= time_window['minutes']:
                current_time_window = time_window
            if minutes < time_window['minutes']:
                return current_time_window
        return current_time_window

    def _get_projects_with_sla(self):
        self.projects = {}
        for project in self.get('projects'):
            if 'custom_fields' in project:
                for custom_field in project['custom_fields']:
                    if custom_field['name'] == 'SLA' and custom_field['value']:
                        self.projects[project['identifier']] = {
                                'id': project['id'],
                                'identifier': project['identifier'],
                                'name': project['name'],
                                'sla': custom_field['value']
                            }

    def get_issues(self, project_id):
        opened_issues = []
        for _issue in self.get('issues', {'project_id': project_id, 'status_id': 'open'}):
            if _issue['project']['id'] == project_id:
                opened_issues.append({
                    'id': _issue['id'],
                    'project_id': _issue['project']['id'],
                    'project_name': _issue['project']['name'],
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
                        _roles[role['name']] = {}
                    _roles[role['name']][self.get_user_mail(member_user_id)] = member_user_name
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

    def _get_priorities(self, sla_name):
        return self._config['sla'][sla_name]

    def _update_projects(self):
        for project_identifier, project in self.projects.iteritems():
            project["roles"] = self.get_memberships(project['id'])
            project['priority'] = copy.deepcopy(self._get_priorities(project['sla']))
            for priority_name, priority in project['priority'].items():
                for time_window in priority['time_windows']:
                    time_window['rcpt'] = {}
                    for notify_role in time_window['notify']:
                        if notify_role in project["roles"]:
                            logging.debug(
                                u'{}, {}, {}, {}: {}'.format(
                                    project['identifier'],
                                    priority_name,
                                    time_window['name'],
                                    notify_role,
                                    ','.join(project["roles"][notify_role].keys())
                                )
                            )
                            time_window['rcpt'].update(project["roles"][notify_role])
                    logging.debug(
                        u'{}, {}, {}, rcpt: {}'.format(
                            project['identifier'],
                            priority_name,
                            time_window['name'],
                            ','.join(time_window['rcpt'].keys())
                        )
                    )
        # save_json(self.projects, 'test/projects.json')

    def get_cache(self):
        return self.hdb.get_cache(int(self._config['main']['cache_time']))

    def write_cache(self):
        self.hdb.write_cache(self.projects)

    def get_projects(self):
        self.projects = self.get_cache()
        if not self.projects:
            self.projects = {}
            logging.debug("Update cache")
            self._calc_sla_persent()
            self._get_users()
            self._get_projects_with_sla()
            self._update_projects()
            self.write_cache()

    def run_notify(self, reset_history=False, test_mail=False):
        mail = Sendmail(self._config['mail'])
        if reset_history:
            logging.info("Reset history")
            self.hdb.reset()
        self.get_projects()
        for project_identifier, project in self.projects.items():
            for issue in rm.get_issues(project['id']):
                time_window = rm.in_time_window(project, issue)
                if time_window:
                    if self.hdb.not_sent(issue['id'], time_window['name']):
                        if time_window['rcpt']:
                            issue['rcpt'] = time_window['rcpt']
                            issue['project_identifier'] = project_identifier
                            issue['project_sla'] = project['sla']
                            issue['time_window'] = time_window['name']
                            issue['time_after_creation'] = time_diff(issue['created_on'], False)
                            issue['created_on_local'] = str(date_from_redmine(issue['created_on'], True))
                            issue['notify_roles'] = issue_get_notify_roles(time_window)
                            issue['important'] = time_window['important'] if 'important' in time_window else False
                            if test_mail:
                                issue['rcpt_origin'] = copy.deepcopy(issue['rcpt'])
                                issue['rcpt'] = self._config['main']['test_email']
                            issue_log_info(issue)
                            if mail.send_issue(issue=issue, important=issue['important']):
                                self.hdb.sent(issue['id'], issue['time_window'])
                        else:
                            issue_log_debug(issue, 'No notify roles!')
                    else:
                        issue_log_debug(issue, 'In history!')

    def run_report(self, full_report=False, test_mail=False):
        mail = Sendmail(self._config['mail'], template_report=True)
        self.get_projects()
        report = []
        for project_identifier, project in self.projects.items():
            project_report = {
                'id': project['id'],
                'identifier': project['identifier'],
                'name': project['name'],
                'sla': project['sla'],
                'issues': []
            }
            for issue in rm.get_issues(project['id']):
                time_window = rm.in_time_window(project, issue)
                if time_window:
                    if time_window['percent'] == 100 or full_report:
                        issue['project_sla'] = project['sla']
                        issue['time_window'] = time_window['name']
                        issue['time_after_creation'] = time_diff(issue['created_on'], False)
                        issue['created_on_local'] = str(date_from_redmine(issue['created_on'], True))
                        issue['important'] = time_window['important'] if 'important' in time_window else False
                        project_report['issues'].append(issue)
            if project_report['issues']:
                report.append(project_report)
        rcpt = self._config['main']['report_email']
        if test_mail:
            rcpt = self._config['main']['test_email']
        if report:
            logging.info("Send report to %s" % rcpt)
            mail.send_report(rcpt, report)
        else:
            logging.info("Nothing to report")


def print_history():
    hdb = HistoryDB(file_path('history.db'))
    print "| id | sla"
    for (i, s) in hdb.get_history():
        print '| %2i | %s' % (i, s)


def print_cache():
    hdb = HistoryDB(file_path('history.db'))
    print json.dumps(hdb.get_cache_dump(), ensure_ascii=False, indent=2)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument('-c', '--conf-file', default=os.path.join(PATH, PROGRAM + '.conf'))
    parser.add_argument('-s', '--sla-file')
    parser.add_argument('-l', '--log-conf-file', default=os.path.join(PATH, 'logging.conf'))
    parser.add_argument('-r', '--reset-history', action='store_true', help="Reset(delete) history")
    parser.add_argument('--report', action='store_true', help="Report")
    parser.add_argument('--full-report', action='store_true', help="Full Report")
    parser.add_argument('--test', action='store_true', help="Send test mail")
    parser.add_argument('--history', action='store_true', help="Print hisory")
    parser.add_argument('--view-cache', action='store_true', help="View cache")

    args = parser.parse_args()

    if os.path.isfile(args.log_conf_file):
        logfileConfig(args.log_conf_file)
    else:
        logging.basicConfig(level=logging.INFO)

    logging.debug("START")
    logging.debug('Config file: %s' % args.conf_file)
    load_config(args.conf_file)

    logging.debug('SLA config file: %s' % args.sla_file)
    logging.debug('Log config file: %s' % args.log_conf_file)
    if args.sla_file:
        CONFIG['main']['sla-file'] = args.sla_file

    if not os.path.isfile(CONFIG['main']['sla-file']):
        logging.error("The SLA configuration is not specified")
        parser.print_help()
        sys.exit(0)

    CONFIG['sla'] = load_json(CONFIG['main']['sla-file'])

    rm = Redmine(CONFIG)
    if args.report or args.full_report:
        rm.run_report(full_report=args.full_report, test_mail=args.test)
    elif args.view_cache:
        print_cache()
    elif args.history:
        print_history()
    else:
        rm.run_notify(args.reset_history, args.test)
    logging.debug("END")
