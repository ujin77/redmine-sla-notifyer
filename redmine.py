#!/usr/bin/python
# -*- coding: utf-8
#
import urllib2
from urlparse import urljoin
import json
from datetime import datetime, timedelta
import time
import re
import os
import logging
import io


DEFAULT_BATCH_LIMIT = 100

RM_DATE_FMT = '%Y-%m-%dT%H:%M:%SZ'

DEFAULT_PRIORITY = {
    'time_of_processing': 0,
    'business_time': False,
    'time_windows': []
}


def log_debug(name, msg):
    logging.debug('%s: %s' % (name, msg))


def utc_to_local(dt):
    if time.localtime().tm_isdst:
        return dt - timedelta(seconds=time.altzone)
    else:
        return dt - timedelta(seconds=time.timezone)


def local_to_utc(dt):
    if time.localtime().tm_isdst:
        return dt + timedelta(seconds=time.altzone)
    else:
        return dt + timedelta(seconds=time.timezone)


def date_from_redmine(str_date, to_local=False):
    if to_local:
        return utc_to_local(datetime.strptime(str_date, RM_DATE_FMT))
    else:
        return datetime.strptime(str_date, RM_DATE_FMT)


def time_diff(date_string, minutes=True):
    td = datetime.now() - utc_to_local(datetime.strptime(date_string, RM_DATE_FMT))
    if minutes:
        return int(td.total_seconds()/60)
    else:
        return delta_to_str(td)


def time_percent(hours, percent):
    return int(hours * percent * 0.6)


def delta_to_str(td):
    return re.match(r'(.*):\d+\.\d+$', str(td)).group(1)
    # return re.match(r'(.*)\:\d+\.\d+$', str(td)).group(1)


def json_to_file(filename, obj):
    with io.open(filename, 'w', encoding='utf8') as json_file:
        json_file.write(unicode(json.dumps(obj, ensure_ascii=False, indent=2)))
        json_file.close()


def _debug_value(data, key=''):
    if data:
        if key in data:
            logging.debug('response: %s=%s' % (key, data[key]))


def _debug_response(response, url=None):
    if url:
        logging.debug('url: %s' % url)
    if response:
        try:
            resp = json.loads(response)
            _debug_value(resp, 'total_count')
            _debug_value(resp, 'limit')
            _debug_value(resp, 'offset')
            # print json.dumps(json.loads(response), indent=2, ensure_ascii=False)
        except ValueError:
            logging.error(response)


class Request(object):

    def __init__(self, base_url, resource='', params=None, offset=None, limit=None):
        super(Request, self).__init__()
        self._base_url = base_url
        self._resource = resource
        self._params = {}
        if params:
            for key in params:
                self.add(key, params[key])
        if limit:
            self.add('limit', limit)
        if offset:
            self.add('offset', offset)

    def add(self, name, value):
        self._params[name] = value

    def url(self):
        params = self._resource + '.json?' + '&'.join(str('%s=%s' % item) for item in self._params.items())
        return urljoin(self._base_url, params)


class RedmineClient(object):

    def __init__(self, config, debug=False):
        super(RedmineClient, self).__init__()
        self._config = config
        self._debug = debug
        self.on_init()

    def on_init(self):
        pass

    def _get_cfg(self, section, param):
        return self._config[section][param]

    def _do_request(self, resource, params=None, offset=None, limit=None):
        _request = Request(self._get_cfg('redmine', 'url'), resource, params, offset, limit)
        # logging.debug('_do_request: %s' % _request.url())
        req = urllib2.Request(url=_request.url())
        req.add_header('X-Redmine-API-Key', self._get_cfg('redmine', 'api-key'))
        try:
            response = urllib2.urlopen(req).read()
        except urllib2.HTTPError as e:
            logging.error(e)
            return {}
        except urllib2.URLError as e:
            logging.error(e)
            return {}
        if self._debug:
            _debug_response(response, _request.url())
        return json.loads(response)

    def _get_data(self, resource, params=None):
        record_count = 0
        total_count = 1
        offset = 0
        limit = None
        data = []
        response_name = os.path.basename(resource)
        while record_count < total_count:
            res = self._do_request(resource, params, offset, limit)
            if res and response_name in res:
                record_count = res['offset'] + res['limit']
                total_count = res['total_count']
                offset = record_count
                limit = total_count - record_count
                if limit > DEFAULT_BATCH_LIMIT:
                    limit = DEFAULT_BATCH_LIMIT
                data += res[response_name]
            else:
                record_count = total_count + 1
        return data

    def get(self, resource, params=None):
        return self._get_data(resource, params)


class BusinessTime(object):

    def __init__(self, start_time, worktiming=None, weekends=None):
        super(BusinessTime, self).__init__()
        if worktiming is None:
            worktiming = [9, 18]
        if weekends is None:
            weekends = [6, 7]
        self.weekends = weekends
        self.begin_work = worktiming[0]
        self.end_work = worktiming[1]
        self.datetime_start = start_time
        self.datetime_end = datetime.now()
        self.day_hours = (self.end_work - self.begin_work)
        self.day_minutes = self.day_hours * 60  # minutes in a work day

    def getdays(self, start_time=None):
        return int(self.getminutes(start_time) / self.day_minutes)

    def gethours(self, start_time=None):
        return int(self.getminutes(start_time) / 60)

    def getminutes(self, start_time=None):
        if start_time:
            self.datetime_start = start_time
        return self._getminutes()

    def _getminutes(self):
        """
        Return the difference in minutes.
        """
        # Set initial default variables
        dt_start = self.datetime_start  # datetime of start
        dt_end = self.datetime_end  # datetime of end
        worktime_in_seconds = 0

        if dt_start.date() == dt_end.date():
            # starts and ends on same workday
            if self.is_weekend(dt_start):
                return 0
            else:
                if dt_start.hour < self.begin_work:
                    # set start time to opening hour
                    dt_start = datetime(
                        year=dt_start.year,
                        month=dt_start.month,
                        day=dt_start.day,
                        hour=self.begin_work,
                        minute=0)
                if dt_start.hour >= self.end_work or \
                        dt_end.hour < self.begin_work:
                    return 0
                if dt_end.hour >= self.end_work:
                    dt_end = datetime(
                        year=dt_end.year,
                        month=dt_end.month,
                        day=dt_end.day,
                        hour=self.end_work,
                        minute=0)
                worktime_in_seconds = (dt_end - dt_start).total_seconds()
        elif (dt_end - dt_start).days < 0:
            # ends before start
            return 0
        else:
            # start and ends on different days
            current_day = dt_start  # marker for counting workdays
            while not current_day.date() == dt_end.date():
                if not self.is_weekend(current_day):
                    if current_day == dt_start:
                        # increment hours of first day
                        if current_day.hour < self.begin_work:
                            # starts before the work day
                            worktime_in_seconds += self.day_minutes * 60  # add 1 full work day
                        elif current_day.hour >= self.end_work:
                            pass  # no time on first day
                        else:
                            # starts during the working day
                            dt_currentday_close = datetime(
                                year=dt_start.year,
                                month=dt_start.month,
                                day=dt_start.day,
                                hour=self.end_work,
                                minute=0)
                            worktime_in_seconds += (dt_currentday_close
                                                    - dt_start).total_seconds()
                    else:
                        # increment one full day
                        worktime_in_seconds += self.day_minutes * 60
                current_day += timedelta(days=1)  # next day
            # Time on the last day
            if not self.is_weekend(dt_end):
                if dt_end.hour >= self.end_work:  # finish after close
                    # Add a full day
                    worktime_in_seconds += self.day_minutes * 60
                elif dt_end.hour < self.begin_work:  # close before opening
                    pass  # no time added
                else:
                    # Add time since opening
                    dt_end_open = datetime(
                        year=dt_end.year,
                        month=dt_end.month,
                        day=dt_end.day,
                        hour=self.begin_work,
                        minute=0)
                    worktime_in_seconds += (dt_end - dt_end_open).total_seconds()
        return int(worktime_in_seconds / 60)

    def is_weekend(self, _datetime):
        """
        Returns True if datetime lands on a weekend.
        """
        for weekend in self.weekends:
            if _datetime.isoweekday() == weekend:
                return True
        return False


class SLA(object):

    @staticmethod
    def _time_percent(hours, percent):
        return int(hours * percent * 0.6)

    def __init__(self, config):
        super(SLA, self).__init__()
        self._config = config
        self._calc_persent()
        self.business_time = BusinessTime(None)

    def _calc_persent(self):
        for sla_name in self._config:
            for priority in self._config[sla_name]:
                for i in range(len(self._config[sla_name][priority]['time_windows'])):
                    self._config[sla_name][priority]['time_windows'][i]['minutes'] = self._time_percent(
                        self._config[sla_name][priority]['time_of_processing'],
                        self._config[sla_name][priority]['time_windows'][i]['percent']
                    )
        # print json.dumps(self._config, indent=2, ensure_ascii=False)

    def _get_sla(self, name):
        if name in self._config:
            return self._config[name]
        return None

    def _get_priority(self, sla_name, name):
        if sla_name in self._config:
            if name in self._config[sla_name]:
                return self._config[sla_name][name]
            else:
                if 'default' in self._config[sla_name]:
                    return self._config[sla_name]['default']
        return DEFAULT_PRIORITY

    def _get_time_windows(self, sla_name, priority):
        return self._get_priority(sla_name, priority)['time_windows']

    def _get_business_time(self, sla_name, priority):
        return self._get_priority(sla_name, priority)['business_time']

    def _get_time_of_processing(self, sla_name, priority):
        return self._get_priority(sla_name, priority)['time_of_processing']

    def in_time_window(self, sla_name, priority, start_date):
        if self._get_business_time(sla_name, priority):
            minutes = self.business_time.getminutes(date_from_redmine(start_date, True))
        else:
            minutes = time_diff(start_date)
        return self._in_time_window(sla_name, priority, minutes)

    def _in_time_window(self, sla_name, priority, minutes):
        current_time_window = None
        if sla_name in self._config:
            for time_window in self._get_time_windows(sla_name, priority):
                if minutes >= time_window['minutes']:
                    current_time_window = time_window
                if minutes < time_window['minutes']:
                    return current_time_window
        return current_time_window

    # def notified(self, sla_name, minutes):
    #     if sla_name in self._config:
    #         return self.in_time_window(sla_name, minutes)['notify']
    #     else:
    #         return None
