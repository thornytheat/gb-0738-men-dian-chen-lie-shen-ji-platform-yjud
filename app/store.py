import json
import sqlite3
from contextlib import contextmanager

from app.errors import AuditError
from app.manifest import canonical

DDL = (
    '''CREATE TABLE IF NOT EXISTS runs (
        run_id TEXT PRIMARY KEY, snapshot TEXT NOT NULL
    )''',
    '''CREATE TABLE IF NOT EXISTS appeal_events (
        seq INTEGER PRIMARY KEY,
        run_id TEXT NOT NULL REFERENCES runs(run_id),
        shelf_key TEXT NOT NULL,
        version INTEGER NOT NULL CHECK (version > 0),
        request_id TEXT NOT NULL,
        payload TEXT NOT NULL,
        event TEXT NOT NULL,
        UNIQUE (run_id, shelf_key, version),
        UNIQUE (run_id, request_id)
    )''',
)


class Store:
    def __init__(self, database):
        self.database = database

    @contextmanager
    def connection(self, write=False):
        connection = sqlite3.connect(self.database, timeout=15, isolation_level=None)
        connection.row_factory = sqlite3.Row
        try:
            connection.execute('PRAGMA foreign_keys = ON')
            connection.execute('BEGIN IMMEDIATE' if write else 'BEGIN')
            with connection:
                yield connection
        finally:
            connection.close()

    def initialize(self):
        self.database.parent.mkdir(parents=True, exist_ok=True)
        with self.connection(write=True) as connection:
            for statement in DDL:
                connection.execute(statement)

    @staticmethod
    def read(connection, run_id, required=True):
        found = connection.execute('SELECT snapshot FROM runs WHERE run_id = ?', (run_id,)).fetchone()
        if found is None:
            if required:
                raise AuditError('RUN_NOT_FOUND', '未找到该巡检批次', 404)
            return None
        events = connection.execute('SELECT event FROM appeal_events WHERE run_id = ? ORDER BY seq', (run_id,))
        return {**json.loads(found['snapshot']), 'events': [json.loads(event['event']) for event in events]}

    def get(self, run_id, required=True):
        with self.connection() as connection:
            return self.read(connection, run_id, required)

    def save(self, snapshot):
        run_id = snapshot['manifest']['run_id']
        record = canonical(snapshot)
        with self.connection(write=True) as connection:
            inserted = connection.execute('INSERT INTO runs VALUES (?, ?) ON CONFLICT(run_id) DO NOTHING', (run_id, record))
            return self.read(connection, run_id), inserted.rowcount == 0

    def append_event(self, run_id, payload, build):
        with self.connection(write=True) as connection:
            snapshot = self.read(connection, run_id)
            raw = canonical(payload)
            old = connection.execute('SELECT payload, event FROM appeal_events WHERE run_id = ? AND request_id = ?',
                                     (run_id, payload['request_id'])).fetchone()
            if old:
                if old['payload'] != raw:
                    raise AuditError('REQUEST_CONFLICT', '提交编号已用于其他内容', 409)
                return json.loads(old['event']), True
            event = build(snapshot, payload)
            connection.execute('''INSERT INTO appeal_events
                (run_id, shelf_key, version, request_id, payload, event) VALUES (?, ?, ?, ?, ?, ?)''',
                (run_id, event['key'], event['version'], payload['request_id'], raw, canonical(event)))
            return event, False
