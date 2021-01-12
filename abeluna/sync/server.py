import datetime
import queue
import threading
import time
import uuid
from collections import defaultdict
from functools import wraps

import caldav
import icalendar

from abeluna.settings import settings
from abeluna.sync.calendar import Calendar
from abeluna.util import generate_vtimezone


class Task:
    def __init__(self, progress=0):
        self.uid = uuid.uuid4().hex
        self._progress = progress

    def __str__(self):
        return self.uid

    @property
    def progress(self):
        return self._progress

    @progress.setter
    def progress(self, value):
        self._progress = value

    @property
    def completed(self):
        return self._progress == 100

    @completed.setter
    def completed(self, value):
        self._progress = 100 if value else 0


def background_task(method):
    @wraps(method)
    def wrapper(self, *args, **kwargs):
        try:
            task = kwargs.pop('task', Task())
            delay_abs = kwargs.pop('delay', -1) + self.timefunc()
            self.task_queue.put_nowait((delay_abs, method, task, (self, task) + args, kwargs))
        except queue.Full:
            return None
        else:
            return task
    return wrapper


class SynchronizationServer:
    def __init__(self):
        self.task_queue = queue.PriorityQueue()

        self.todolist = defaultdict(list)

        self._stop_lock = threading.RLock()

        self._worker_stop = threading.Event()
        self._worker_thread = threading.Thread(target=self.worker_run)
        self._worker_thread.start()
        self._general_lock = threading.RLock()
        self._update_todo_skip = {}
        self.timefunc = time.time

        self._autosync_stop = threading.Event()
        self._autosync_thread = None
        self.restart_autosync_thread()
        self.last_sync = None
        self._sync_lock = threading.RLock()
        self._sync_callbacks = []

        self.calendars = {}

    def stop_all(self):
        with self._stop_lock:
            self._worker_stop.set()
            self._autosync_stop.set()
        self._worker_thread.join()
        self._autosync_thread.join()

    def worker_run(self):
        timeout = 0
        while not self._worker_stop.wait(timeout=timeout):
            try:
                delay_abs, method, task, args, kwargs = self.task_queue.get_nowait()
                if delay_abs > self.timefunc():
                    self.task_queue.put_nowait((delay_abs, method, task, args, kwargs))
                    raise queue.Empty()
            except queue.Empty:
                timeout = 0.25
            else:
                timeout = 0
                try:
                    task.completed = method(*args, **kwargs)
                except KeyboardInterrupt:
                    break
                except Exception:  # catch all
                    task.completed = False
                    import traceback
                    traceback.print_exc()

                # print('Process background task:', method, task)
                self.task_queue.task_done()

    def restart_autosync_thread(self):
        with self._stop_lock:
            if self._autosync_stop.is_set():
                return
            self._autosync_stop.set()
            if self._autosync_thread is not None:
                self._autosync_thread.join()
            self._autosync_stop.clear()

            self._autosync_thread = threading.Thread(target=self.autosync_run)
            self._autosync_thread.start()

    def autosync_run(self):
        if settings.AUTOSYNC_INTERVAL == '-1':
            return
        while not self._autosync_stop.wait(timeout=int(settings.AUTOSYNC_INTERVAL)):
            try:
                self._synchronize_todolist()
            except KeyboardInterrupt:
                break
            except Exception:  # catch all
                import traceback
                traceback.print_exc()

    def sync_connect(self, callback, *args, **kwargs):
        self._sync_callbacks.append((callback, args, kwargs))

    def _merge_todo(self, uid, local_copy_of_local, local_copy_of_remote, remote_copy_of_remote):
        # Nothing changed, don't touch anything.
        if local_copy_of_local.to_ical() == remote_copy_of_remote.to_ical():
            return False, remote_copy_of_remote
        # Nothing changed server side, so use the client todo if there are any updates.
        elif local_copy_of_remote.to_ical() == remote_copy_of_remote.to_ical():
            # print(uid, 'was changed locally but not changed on remote. Pushing to remote...')
            return True, local_copy_of_local
        # Something changed server side and client side, so we will prioritize the server.
        elif local_copy_of_remote.to_ical() != remote_copy_of_remote.to_ical():
            # print(uid, 'was changed both locally and on remote. Merging...')

            # User prioritizes server.
            for key, value in local_copy_of_local.items():
                try:
                    remote_copy_of_remote_value = remote_copy_of_remote[key].to_ical()
                except KeyError:
                    remote_copy_of_remote_value = None
                try:
                    local_copy_of_remote_value = local_copy_of_remote[key].to_ical()
                except KeyError:
                    local_copy_of_remote_value = None
                try:
                    local_copy_of_local_value = local_copy_of_local[key].to_ical()
                except KeyError:
                    local_copy_of_local_value = None

                # Nothing changed server side, so use client value.
                if (
                    settings.PRIORITIZE_ON_CONFLICT == 'SERVER' and
                    local_copy_of_remote_value == remote_copy_of_remote_value
                ):
                    remote_copy_of_remote[key] = value
                # Something changed client side, so use client value.
                elif (
                    settings.PRIORITIZE_ON_CONFLICT == 'CLIENT' and
                    local_copy_of_remote_value != local_copy_of_local_value
                ):
                    remote_copy_of_remote[key] = value
            return True, remote_copy_of_remote
        # How did we get here...
        else:
            assert False

    def _synchronize_todolist(self):
        with self._sync_lock:
            for cb, args, kwargs in self._sync_callbacks:
                cb(*args, mode='PRE_SYNC', **kwargs)

            for cal in self.calendars.values():
                try:
                    if cal.is_local:
                        continue
                    remote_todos = cal.calendar.todos(include_completed=True)
                    local_todos = cal.local_server.todos(include_deleted=True)

                    remote_uids = set()
                    for remote_todo in remote_todos:
                        remote_ical = remote_todo.icalendar_instance
                        new_cal = remote_ical.copy()
                        has_todo_component = False
                        updated_todo_component = False
                        for remote_item in remote_todo.icalendar_instance.subcomponents:
                            # Keep all non-todo items unconditionally in case there are any.
                            if not isinstance(remote_item, icalendar.Todo):
                                new_cal.add_component(remote_item)
                                continue

                            uid = str(remote_item['UID'])
                            remote_uids.add(uid)
                            try:
                                local_item = local_todos[local_todos.index(uid)]
                            except ValueError:
                                # print(uid, 'does not exist locally. Creating...')
                                # Item exists on the server but does not exist locally AND was not deleted locally.
                                has_todo_component = True
                                new_cal.add_component(remote_item)
                                cal.local_server.update_todo_from_server(remote_item)
                            else:
                                # Item exists on the server but does not exist locally AND was deleted locally.
                                if local_item.local_vtodo is None:
                                    # print(uid, 'was deleted locally. Deleting from server...')
                                    updated_todo_component = True
                                    cal.local_server.delete_todo_from_server(remote_item)
                                # Item exists on both the server and the client, compare the todos
                                else:
                                    has_todo_component = True
                                    updated, item_to_use = self._merge_todo(
                                        uid,
                                        local_item.local_vtodo,
                                        local_item.remote_vtodo,
                                        remote_item,
                                    )
                                    updated_todo_component |= updated

                                    new_cal.add_component(item_to_use)
                                    cal.local_server.update_todo_from_server(item_to_use)

                        if not has_todo_component:
                            remote_todo.delete()
                        elif updated_todo_component:
                            remote_todo.icalendar_instance = new_cal
                            remote_todo.save()

                    for local_item in local_todos:
                        # Item existed on server, so it was already processed.
                        if local_item.uid in remote_uids:
                            continue

                        # Item has a record of being on the server, but it doesn't exist on the server anymore.
                        # We can only assume it was deleted server-side.
                        if local_item.remote_vtodo is not None:
                            # print(local_item.uid, 'was deleted on remote. Deleting locally...')
                            cal.local_server.delete_todo_from_server(local_item.remote_vtodo)
                        # Item exists on client, has never existed on server, so create and push to the server.
                        else:
                            # print(local_item.uid, 'was created locally. Pushing to remote...')
                            vcal = icalendar.Calendar()
                            vcal.add('VERSION', '2.0')
                            vcal.add('PRODID', '-//Abeluna//NONSGML v1.0//EN')
                            vcal.add('CALSCALE', 'GREGORIAN')
                            vcal.add_component(generate_vtimezone())
                            vcal.add_component(local_item.local_vtodo)
                            caldav.Todo(cal.client, data=vcal, parent=cal.calendar, id=local_item.uid).save()
                            cal.local_server.update_todo_from_server(local_item.local_vtodo)
                except Exception:
                    import traceback
                    traceback.print_exc()

            self.initialize_todolist()
            self.last_sync = datetime.datetime.now()
            for cb, args, kwargs in self._sync_callbacks:
                cb(*args, mode='POST_SYNC', **kwargs)

    @background_task
    def synchronize_todolist(self, task):
        self._synchronize_todolist()
        return True

    def initialize_todolist(self, uid=None):
        with self._sync_lock:
            if uid is not None:
                try:
                    calendar = self.calendars[uid]
                except KeyError:
                    pass
                else:
                    self.todolist[uid] = [item.local_vtodo for item in calendar.local_server.todos()]
            else:
                self.todolist.clear()
                for uid, cal in self.calendars.items():
                    self.todolist[uid] = [item.local_vtodo for item in cal.local_server.todos()]

    def refresh_calendars(self):
        new_calendars = {}
        for uid, cal_dict in settings.CALENDARS.items():
            cal = Calendar.from_dict(cal_dict)
            new_calendars[uid] = cal

        with self._sync_lock:
            self.calendars = new_calendars
            self.initialize_todolist()

    @background_task
    def update_todo(self, task, vtodo, cal_uid, postpone=True):
        uid = str(vtodo['UID'])
        _time = self.timefunc()
        with self._general_lock:
            # Some sketchy logic to "batch" saves together.
            # E.g when the user is editting a textbox, don't save after every keystroke.
            if postpone:
                if uid not in self._update_todo_skip:
                    self.update_todo(vtodo, cal_uid, task=task, postpone=False)
                self._update_todo_skip[uid] = _time
                return False
            else:
                time_diff = int(settings.SAVE_INTERVAL) - (_time - self._update_todo_skip.get(uid, 0))
                if time_diff > 0:
                    self.update_todo(vtodo, cal_uid, task=task, postpone=False, delay=time_diff)
                    return False
                else:
                    try:
                        self._update_todo_skip.pop(uid)
                    except KeyError:
                        pass

        with self._sync_lock:
            self.calendars[cal_uid].local_server.update_todo_from_client(vtodo)
            self.initialize_todolist(uid=cal_uid)
        return True

    @background_task
    def delete_todo(self, task, vtodo, cal_uid):
        with self._sync_lock:
            self.calendars[cal_uid].local_server.delete_todo_from_client(vtodo)
            self.initialize_todolist(uid=cal_uid)
        return True


server = SynchronizationServer()
