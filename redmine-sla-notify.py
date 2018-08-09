#!/usr/bin/python
# -*- coding: utf-8
#

import os
import sys
import json
import ConfigParser
from redmine import RedmineClient, time_diff, time_percent, date_from_redmine, BusinessTime, CSV
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

    business_time = BusinessTime(None)

    def _calc_sla_persent(self):
        for _sla_name in self._config['sla']:
            for _priority_name in self._config['sla'][_sla_name]:
                for i in range(len(self._config['sla'][_sla_name][_priority_name]['time_windows'])):
                    self._config['sla'][_sla_name][_priority_name]['time_windows'][i]['minutes'] = time_percent(
                        self._config['sla'][_sla_name][_priority_name]['time_of_processing'],
                        self._config['sla'][_sla_name][_priority_name]['time_windows'][i]['percent']
                    )

    def in_time_window(self, _project, _issue):
        current_time_window = None

        if 'nbd' in _project['priority'][_issue['priority']] and _project['priority'][_issue['priority']]['nbd']:
            # print "NBD", _issue['priority']
            minutes = self.business_time.getminutes(date_from_redmine(_issue['created_on'], True))
        else:
            # print "###", _issue['priority']
            minutes = time_diff(_issue['created_on'])
        for time_window in _project['priority'][_issue['priority']]['time_windows']:
            if minutes >= time_window['minutes']:
                current_time_window = time_window
            if minutes < time_window['minutes']:
                return current_time_window
        return current_time_window

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

    def get_projects(self):
        _projects = hdb.get_cache(int(self._config['main']['cache_time']))
        if not _projects:
            logging.info("Update cache")
            self._calc_sla_persent()
            self._get_users()
            _projects = self.get_projects_with_sla()
            for _project in _projects:
                _roles = self.get_memberships(_project['id'])
                _project['priority'] = self._config['sla'][_project['sla']]
                for _priority_name in _project['priority']:
                    for time_window in _project['priority'][_priority_name]['time_windows']:
                        _notify_names = time_window['notify']
                        time_window['notify'] = {}
                        for _notify_name in _notify_names:
                            if _notify_name in _roles:
                                time_window['notify'][_notify_name] = _roles[_notify_name]['users']
            hdb.write_cache(_projects)
        return _projects


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


def run_notify(_conf, reset_history=False, test_mail=False):
    if reset_history:
        logging.debug("Reset history")
        hdb.reset()
    rm = Redmine(_conf)
    mail = Sendmail(_conf['mail'])
    for project in rm.get_projects():
        for issue in rm.get_issues(project['id']):
            time_window = rm.in_time_window(project, issue)
            if time_window:
                if hdb.not_sent(issue['id'], time_window['name']):
                    issue['rcpt'] = {}
                    for role_name in time_window['notify']:
                        for rcpt_to, rcpt_name in time_window['notify'][role_name].iteritems():
                            issue['rcpt'][rcpt_to] = rcpt_name
                    if issue['rcpt']:
                        issue['project_sla'] = project['sla']
                        issue['time_window'] = time_window['name']
                        issue['time_after_creation'] = time_diff(issue['created_on'], False)
                        issue['created_on_local'] = str(date_from_redmine(issue['created_on'], True))
                        issue['notify_roles'] = issue_get_notify_roles(time_window)
                        issue['important'] = time_window['important'] if 'important' in time_window else False
                        issue_log_info(issue)
                        if test_mail:
                            logging.debug("Send test to %s" % _conf['main']['test_email'])
                            issue['rcpt'] = _conf['main']['test_email']
                        if mail.send_issue(issue=issue, important=issue['important']):
                            hdb.sent(issue['id'], issue['time_window'])
                        # print "### ISSUE", json.dumps(issue, ensure_ascii=False, indent=2)
                    else:
                        issue_log_debug(issue, 'No notify roles!')
                else:
                    issue_log_debug(issue, 'In history!')


def generate_csv(data):
    # print json.dumps(data, ensure_ascii=False, indent=2)
    csv = CSV()
    for project in data:
        for issue in project['issues']:
            # print json.dumps(issue, ensure_ascii=False, indent=2)
            csv.add([
                issue['project_id'],
                issue['project_name'],
                issue['id'],
                issue['subject']
            ])
    return csv.get()


def run_report(_conf, test_mail=False, full_report=False):
    rm = Redmine(_conf)
    mail = Sendmail(_conf['mail'], template_report=True)
    projects = []
    for project in rm.get_projects():
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
            projects.append(project_report)
    rcpt = _conf['main']['report_email']
    if test_mail:
        rcpt = _conf['main']['test_email']
    if projects:
        logging.info("Send report to %s" % rcpt)
        mail.send_report(rcpt, projects)
        # print generate_csv(projects)
    else:
        logging.info("Nothing to report")
    # json_to_file('cache.json', rm.get_projects())


def print_history():
    # print hdb.get_last_update()
    print "| id | sla"
    for (i, s) in hdb.get_history():
        print '| %2i | %s' % (i, s)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument('-c', '--conf-file', default=os.path.join(PATH, PROGRAM + '.conf'))
    parser.add_argument('-s', '--sla-file', default=os.path.join(PATH, 'sla.json'))
    parser.add_argument('-l', '--log-conf-file', default=os.path.join(PATH, 'logging.conf'))
    parser.add_argument('-r', '--reset-history', action='store_true', help="Reset(delete) history")
    parser.add_argument('--report', action='store_true', help="Report")
    parser.add_argument('--full-report', action='store_true', help="Full Report")
    parser.add_argument('--test', action='store_true', help="Send test mail")
    parser.add_argument('--history', action='store_true', help="Print hisory")

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
    CONFIG['sla'] = load_json(args.sla_file)
    hdb = HistoryDB(file_path('history.db'))
    if args.report or args.full_report:
        run_report(CONFIG, test_mail=args.test, full_report=args.full_report)
    elif args.history:
        print_history()
    else:
        run_notify(CONFIG, args.reset_history, args.test)
    logging.debug("END")
