#!/usr/bin/python
# -*- coding: utf-8
#
import sqlite3


class HistoryDB(object):

    def __init__(self, db_file):
        super(HistoryDB, self).__init__()
        self._cn = sqlite3.connect(db_file)
        self.cur = self._cn.cursor()
        self.cur.execute('''CREATE TABLE IF NOT EXISTS history
             (issue_id INTEGER, time_window TEXT)''')
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
