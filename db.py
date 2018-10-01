#!/usr/bin/python
# -*- coding: utf-8
#
import sqlite3
import time
import json

DB_INIT = """
CREATE TABLE IF NOT EXISTS history (issue_id INTEGER, time_window TEXT);
CREATE TABLE IF NOT EXISTS cache (id INTEGER PRIMARY KEY, last_update INTEGER, js TEXT);
"""

DB_RESET = """
DROP TABLE IF EXISTS cache;
"""


class HistoryDB(object):

    def __init__(self, db_file):
        super(HistoryDB, self).__init__()
        self._cn = sqlite3.connect(db_file)
        self.cur = self._cn.cursor()
        # self.cur.executescript(DB_RESET)
        self.cur.executescript(DB_INIT)
        self.commit()

    def commit(self):
        self._cn.commit()

    def sent(self, issue_id, time_window):
        self.cur.execute('INSERT INTO history VALUES (?,?)', (issue_id, time_window))
        self.commit()

    def already_sent(self, issue_id, time_window):
        self.cur.execute('SELECT * FROM history WHERE issue_id=? AND time_window=?', (issue_id, time_window))
        return self.cur.fetchone()

    def not_sent(self, issue_id, time_window):
        return not self.already_sent(issue_id, time_window)

    def reset(self):
        self.cur.execute('DELETE FROM history')
        self.commit()

    def get_history(self):
        self.cur.execute('SELECT * FROM history ORDER BY issue_id;')
        return self.cur.fetchall()

    def write_cache(self, js):
        self.cur.execute('UPDATE cache SET last_update=?, js=?;', (time.time(), json.dumps(js)))
        self.commit()

    def get_cache(self, timeout=60):
        self.cur.execute('SELECT last_update, js FROM cache;')
        res = self.cur.fetchone()
        if res:
            if time.time()-res[0] > timeout:
                return None
            return json.loads(res[1])
        else:
            self.cur.execute('INSERT INTO cache VALUES (1, ?, "[]");', (time.time(),))
            self.commit()
            return None

    def get_cache_dump(self):
        self.cur.execute('SELECT last_update, js FROM cache;')
        res = self.cur.fetchone()
        if res:
            return json.loads(res[1])
        return None

