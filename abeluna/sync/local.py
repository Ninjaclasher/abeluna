import os
import sqlite3
from collections import namedtuple
from functools import partial

import icalendar


class LocalTodo(namedtuple('LocalTodo', 'uid local_vtodo remote_vtodo')):
    def __eq__(self, other):
        if isinstance(other, str):
            return self.uid == other
        return self.uid == other.uid

    def __hash__(self):
        return self.uid


class LocalServer:
    def __init__(self, path, calendar_name):
        self.path = path
        self.calendar = calendar_name
        self.conn = partial(sqlite3.connect, os.path.join(self.path, '{}.db'.format(self.calendar)))

        with self.conn() as c:
            c.execute('''
                CREATE TABLE IF NOT EXISTS todo
                (uid TEXT PRIMARY KEY, local_vtodo TEXT, remote_vtodo TEXT)
            ''')
            c.commit()

        self.todolist = []

    def _sanitize_uid(self, uid):
        return str(uid)

    def todos(self, include_deleted=False):
        def create_ical(val):
            if val is None:
                return val
            return icalendar.Calendar.from_ical(val)

        with self.conn() as c:
            data = c.execute(
                '''
                SELECT * FROM todo
                {where}
                '''.format(where='' if include_deleted else 'WHERE local_vtodo IS NOT NULL'),
            ).fetchall()

        return [
            LocalTodo(
                uid=item[0],
                local_vtodo=create_ical(item[1]),
                remote_vtodo=create_ical(item[2]),
            ) for item in data
        ]

    def update_todo_from_server(self, vtodo):
        ical = vtodo.to_ical().decode()
        uid = self._sanitize_uid(vtodo['UID'])
        with self.conn() as c:
            c.execute(
                '''
                INSERT OR IGNORE INTO todo
                VALUES (?, NULL, NULL)
                ''',
                (uid,),
            )
            c.execute(
                '''
                UPDATE todo
                SET local_vtodo=?, remote_vtodo=?
                WHERE uid=?
                ''',
                (ical, ical, uid),
            )
            c.commit()

    def update_todo_from_client(self, vtodo):  # also includes creating the todo
        ical = vtodo.to_ical().decode()
        uid = self._sanitize_uid(vtodo['UID'])
        with self.conn() as c:
            c.execute(
                '''
                INSERT OR IGNORE INTO todo
                VALUES (?, NULL, NULL)
                ''',
                (uid,),
            )
            c.execute(
                '''
                UPDATE todo
                SET local_vtodo=?
                WHERE uid=?
                ''',
                (ical, uid),
            )
            c.commit()

    def delete_todo_from_server(self, vtodo):
        with self.conn() as c:
            c.execute(
                '''
                DELETE FROM todo
                WHERE uid = ?
                ''',
                (self._sanitize_uid(vtodo['UID']),),
            )
            c.commit()

    def delete_todo_from_client(self, vtodo):
        uid = self._sanitize_uid(vtodo['UID'])
        with self.conn() as c:
            c.execute(
                '''
                DELETE FROM todo
                WHERE uid = ? and remote_vtodo IS NULL
                ''',
                (uid,),
            )
            c.execute(
                '''
                UPDATE todo
                SET local_vtodo = NULL
                WHERE uid = ? and remote_vtodo IS NOT NULL
                ''',
                (uid,),
            )
            c.commit()
