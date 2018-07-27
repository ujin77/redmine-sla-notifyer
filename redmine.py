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


DEFAULT_BATCH_LIMIT = 50

RM_DATE_FMT = '%Y-%m-%dT%H:%M:%SZ'


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


def delta_to_str(td):
    return re.match(r'(.*)\:\d+\.\d+$', str(td)).group(1)


def _debug_value(data, key=''):
    if data:
        if data.has_key(key):
            print "DEBUG:", key, '=', data[key]


def _debug_response(response, url=None):
    print 'DEBUG------------------------------'
    if url:
        print 'DEBUG: url:', url
    if response:
        try:
            resp = json.loads(response)
            _debug_value(resp, 'total_count')
            _debug_value(resp, 'limit')
            _debug_value(resp, 'offset')
            # print json.dumps(json.loads(response), indent=2, ensure_ascii=False)
        except ValueError:
            print 'DEBUG:', response
    print 'DEBUG------------------------------'


class Request(object):

    def __init__(self, base_url, resource='', params=None, offset=None, limit=None):
        super(Request, self).__init__()
        # print 'DEBUG Request __init__:', resource, params, offset, limit
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
        # print 'DEBUG Request url:', params
        return urljoin(self._base_url, params)


class RedmineClient(object):

    def __init__(self, config):
        super(RedmineClient, self).__init__()
        self._config = config
        self.on_init()

    def on_init(self):
        pass

    def _get_cfg(self, section, param):
        return self._config[section][param]

    def _do_request(self, resource, params=None, offset=None, limit=None):
        # print 'DEBUG _do_request:', resource, params, offset, limit
        _request = Request(self._get_cfg('redmine', 'url'), resource, params, offset, limit)
        req = urllib2.Request(url=_request.url())
        req.add_header('X-Redmine-API-Key', self._get_cfg('redmine', 'api-key'))
        try:
            response = urllib2.urlopen(req).read()
        except urllib2.HTTPError as e:
            print e
            return {}
        except urllib2.URLError as e:
            print e
            return {}
        # _debug_response(response, _request.url())
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



class SLA(object):

    @staticmethod
    def _time_percent(hours, percent):
        return int(hours * percent * 0.6)

    def __init__(self, config):
        super(SLA, self).__init__()
        self._config = config
        self._calc_persent()
        # logging.debug("Debug")
        # logging.info("Info")
        # logging.warn("Warn")
        # logging.error("Error")
        # logging.critical("Critical")

    def _calc_persent(self):
        for sla_name in self._config:
            for i in range(len(self._config[sla_name]['time_windows'])):
                self._config[sla_name]['time_windows'][i]['minutes'] = self._time_percent(
                    self._config[sla_name]['time_of_processing'],
                    self._config[sla_name]['time_windows'][i]['percent']
                )
        # print json.dumps(self._config, indent=2, ensure_ascii=False)

    def in_time_window(self, sla_name, minutes):
        current_time_window = None
        if sla_name in self._config:
            for time_window in self._config[sla_name]['time_windows']:
                if minutes >= time_window['minutes']:
                    current_time_window = time_window
                if minutes < time_window['minutes']:
                    return current_time_window
        return current_time_window

    def notified(self, sla_name, minutes):
        if sla_name in self._config:
            return self.in_time_window(sla_name, minutes)['notify']
        else:
            return None
