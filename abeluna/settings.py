import configparser
import hashlib
import os
import threading
import sys

import keyring
import pytz
from gi.repository import GLib


def nonnegative_integer_validator(val):
    try:
        assert int(val) >= 0
    except (ValueError, AssertionError):
        return False


class Settings:
    DEFAULT_GENERAL_CONFIG = {
        'TIMEZONE': 'UTC',
        'AUTOSYNC_INTERVAL': '600',  # seconds
        'SAVE_INTERVAL': '1',  # seconds
        'PRIORITIZE_ON_CONFLICT': 'SERVER',
        'HIDE_COMPLETED': '0',
        'ALL_DAY_DUE_TIME': '00:00',
    }
    VALID_GENERAL_CONFIG_VALUES = {
        'TIMEZONE': pytz.all_timezones,
        'AUTOSYNC_INTERVAL': [
            '-1', '10', '30', '60', '600', '1800', '3600', '21600', '86400', '604800', '2419200', '1036800',
        ],
        'SAVE_INTERVAL': nonnegative_integer_validator,
        'PRIORITIZE_ON_CONFLICT': ['SERVER', 'CLIENT'],
        'HIDE_COMPLETED': ['0', '1'],
        'ALL_DAY_DUE_TIME': ['{:02}:{:02}'.format(x, y) for x in range(24) for y in range(60)],
    }

    def __init__(self):
        self.TASK_STORAGE_LOCATION = os.path.join(GLib.get_user_data_dir(), 'abeluna', 'todolists')
        self.CONFIG_FILE = os.path.join(GLib.get_user_config_dir(), 'abeluna', 'config.ini')
        os.makedirs(os.path.dirname(self.CONFIG_FILE), mode=0o755, exist_ok=True)
        os.makedirs(self.TASK_STORAGE_LOCATION, mode=0o755, exist_ok=True)

        self._lock = threading.RLock()

        self.config = configparser.ConfigParser()
        self.config.read(self.CONFIG_FILE)

        self.CALENDARS = {}

        for section in self.config.sections():
            if section.startswith('calendar '):
                calendar = dict(self.config[section])

                if 'password' not in calendar and calendar['url']:
                    try:
                        calendar['password'] = keyring.get_password("abeluna", calendar['uid'])
                    except keyring.errors.KeyringLocked as e:
                        print('Error: keyring locked. Unlock keyring to proceed')
                        sys.exit(1)
                    except (RuntimeError, keyring.errors.KeyringError) as e:
                        print('Error getting password for calendar "{}" from keyring'.format(calendar['name']))

                self.add_or_update_calendar(calendar)
        self.commit()

    @property
    def ordered_calendars(self):
        _calendars = {}
        for key, value in sorted(self.CALENDARS.items(), key=lambda x: int(x[1]['order'] or -1)):
            _calendars[key] = value
        return _calendars

    def commit(self):
        with self._lock:
            for section in self.config.sections():
                if section.startswith('calendar '):
                    calendar = dict(self.config[section])
                    if calendar['url'] and 'password' not in calendar:
                        try:
                            keyring.delete_password("abeluna", calendar['uid'])
                        except (RuntimeError, keyring.errors.KeyringError) as e:
                            pass
                    self.config.remove_section(section)
            for uid, calendar in self.CALENDARS.items():
                section_name = 'calendar {}'.format(uid)
                self.config.add_section(section_name)
                _calendar = calendar.copy()

                if _calendar['url'] and _calendar['password']:
                    try:
                        keyring.set_password("abeluna", uid, bytes(_calendar['password'], 'utf-8'))
                        del _calendar['password']
                    except (RuntimeError, keyring.errors.KeyringError) as e:
                        pass

                self.config[section_name].update(_calendar)

            with open(self.CONFIG_FILE, 'w') as f:
                self.config.write(f)

    def add_or_update_calendar(self, data):
        data.setdefault('local_storage', self.TASK_STORAGE_LOCATION)
        with self._lock:
            data.setdefault('order', str(len(self.CALENDARS) + 1))

            _old_uid = data.get('uid')
            hash_value = data.get('url', '').rstrip('/') or data['name']
            data['uid'] = _new_uid = hashlib.sha256(hash_value.encode()).hexdigest()
            if _old_uid is not None and _old_uid != _new_uid:
                # We're moving from a local todo list to a synced todo list, or vice versa
                _old_data = self.CALENDARS[_old_uid]
                if bool(_old_data['url']) ^ bool(data['url']):
                    filename = '{}.db'
                    try:
                        os.rename(
                            os.path.join(_old_data['local_storage'], filename.format(_old_uid)),
                            os.path.join(data['local_storage'], filename.format(_new_uid)),
                        )
                    except FileNotFoundError:
                        pass
                self.CALENDARS.pop(_old_uid)

            self.CALENDARS[_new_uid] = data

    def set_calendar_order(self, ordered_uids):
        with self._lock:
            if set(ordered_uids) != set(self.CALENDARS.keys()):
                return
            for order, uid in enumerate(ordered_uids, 1):
                self.CALENDARS[uid]['order'] = str(order)

    def delete_calendar(self, uid):
        with self._lock:
            try:
                self.CALENDARS.pop(uid)
            except KeyError:
                pass

    def __getattr__(self, field):
        if field in self.DEFAULT_GENERAL_CONFIG:
            with self._lock:
                try:
                    value = self.config['General'][field]
                except KeyError:
                    return self.DEFAULT_GENERAL_CONFIG[field]

            iterable_or_callable = self.VALID_GENERAL_CONFIG_VALUES[field]
            if callable(iterable_or_callable):
                valid = iterable_or_callable(value)
            else:
                valid = value in iterable_or_callable
            # if not valid:
            #    print('Invalid setting "{}": {}'.format(field, value))
            return value if valid else self.DEFAULT_GENERAL_CONFIG[field]
        raise AttributeError()

    def __setattr__(self, field, value):
        if field in self.DEFAULT_GENERAL_CONFIG:
            with self._lock:
                if not self.config.has_section('General'):
                    self.config.add_section('General')
                self.config['General'][field] = value
        else:
            super().__setattr__(field, value)

    def __getitem__(self, field):
        return getattr(self, field)

    def __setitem__(self, field, value):
        setattr(self, field, value)


settings = Settings()
