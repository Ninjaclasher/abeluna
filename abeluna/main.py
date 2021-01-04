import gi

gi.require_version('Gtk', '3.0')
gi.require_version('Gdk', '3.0')
gi.require_version('Notify', '0.7')

import os
import sys

import humanize
from gi.repository import GLib, GObject, Gio, Gtk, Notify

from abeluna.sync import server
from abeluna.util import colour_text
from abeluna.windows import SettingsWindow, TodoListWindow


UI_LOCATION = os.path.join(os.path.dirname(__file__), 'ui')


class MainWindow(Gtk.ApplicationWindow):
    def __init__(self, app):
        Gtk.Window.__init__(self, title='Abeluna', application=app)
        self.set_default_size(1200, 600)

        self.todolist_window = TodoListWindow()

        self.connect('button-press-event', self.todolist_window.reset_action_popover)
        self.connect('configure-event', self.todolist_window.reset_action_popover)

        self.new_todo_action = Gio.SimpleAction.new('new-todo', None)
        self.new_todo_action.connect('activate', lambda action, parameter: self.todolist_window.new_todo())
        self.add_action(self.new_todo_action)
        self.sync_todo_action = Gio.SimpleAction.new('sync-todo', None)
        self.sync_todo_action.connect('activate', lambda action, parameter: server.synchronize_todolist())
        self.add_action(self.sync_todo_action)
        self.general_settings_action = Gio.SimpleAction.new('general-settings', None)
        self.general_settings_action.connect(
            'activate',
            lambda action, parameter: SettingsWindow(parent=self, active_child='General'),
        )
        self.add_action(self.general_settings_action)
        self.calendar_settings_action = Gio.SimpleAction.new('calendar-settings', None)
        self.calendar_settings_action.connect(
            'activate',
            lambda action, parameter: SettingsWindow(parent=self, active_child='Calendars'),
        )
        self.add_action(self.calendar_settings_action)

        self.main_grid = Gtk.Grid()
        self.main_grid.set_column_homogeneous(True)
        self.main_grid.set_column_spacing(5)
        self.main_grid.set_row_homogeneous(True)
        self.main_grid.set_row_spacing(5)
        self.main_grid.set_border_width(10)
        self.add(self.main_grid)

        self.calendar_store = Gtk.ListStore(str, str)
        self.calendar_uid_to_iter = {}
        self.calendar_tree_view = Gtk.TreeView(model=self.calendar_store)
        self.calendar_tree_view.append_column(Gtk.TreeViewColumn('Calendars', Gtk.CellRendererText(), text=0))
        self.calendar_tree_view.get_selection().connect('changed', self.calendar_tree_selection_changed)
        self.calendar_tree_view.set_enable_search(False)
        self.calendar_tree_view.set_search_column(-1)
        self.calendar_tree_view.set_tooltip_column(0)

        self.calendar_scrollable_view = Gtk.ScrolledWindow(vexpand=True)
        self.calendar_scrollable_view.set_propagate_natural_width(True)
        self.calendar_scrollable_view.set_shadow_type(type=Gtk.ShadowType.ETCHED_OUT)
        self.calendar_scrollable_view.add(self.calendar_tree_view)

        self.main_grid.attach(self.calendar_scrollable_view, 0, 0, 4, 19)

        self.status_view = Gtk.Grid()
        self.status_view.set_column_spacing(5)
        self.status_view.set_hexpand(True)
        self.status_view.set_border_width(5)
        self.sync_spinner = Gtk.Spinner()
        self.sync_spinner.set_halign(Gtk.Align.START)
        self.sync_spinner.set_hexpand(False)
        self.status_view.add(self.sync_spinner)
        self.sync_label = Gtk.Label(label=' ')
        self.sync_label.set_halign(Gtk.Align.END)
        self.sync_label.set_hexpand(True)
        self.sync_label.set_property('use-markup', True)
        self.status_view.add(self.sync_label)
        self.main_grid.attach_next_to(
            self.status_view, self.calendar_scrollable_view, Gtk.PositionType.BOTTOM, 4, 1,
        )

        self.main_grid.attach_next_to(
            self.todolist_window, self.calendar_scrollable_view, Gtk.PositionType.RIGHT, 13, 20,
        )

        self.main_grid.show_all()

        GObject.timeout_add_seconds(30, self.update_natural_dates)
        server.refresh_calendars()
        self.rebuild_calendarlist()
        server.sync_connect(self.on_todo_sync)

    def on_todo_sync_watcher(self):
        if self._syncing:
            self.sync_spinner.start()
            return True
        self.todolist_window.rebuild_todolist()
        self.sync_spinner.stop()
        self.update_natural_dates()
        return False

    def on_todo_sync(self, mode):
        if mode == 'PRE_SYNC':
            self._syncing = True
            GObject.timeout_add(200, self.on_todo_sync_watcher)
        elif mode == 'POST_SYNC':
            self._syncing = False

    def update_natural_dates(self):
        last_sync = server.last_sync
        if last_sync is None:
            self.sync_label.set_label(' ')
            self.sync_label.set_tooltip_text('')
        else:
            self.sync_label.set_label(colour_text('Last synced {}.'.format(humanize.naturaltime(last_sync)), '#666'))
            self.sync_label.set_tooltip_text(last_sync.strftime('%c'))
        return True

    def rebuild_calendarlist(self):
        path_iter = self.calendar_tree_view.get_selection().get_selected()[1]
        if path_iter is None:
            _currently_selected_uid = None
        else:
            _currently_selected_uid = self.calendar_store[path_iter][1]
        self.calendar_store.clear()
        self.calendar_uid_to_iter.clear()

        for uid, calendar in server.calendars.items():
            self.calendar_uid_to_iter[uid] = self.calendar_store.append([calendar.name, uid])

        try:
            self.calendar_tree_view.get_selection().select_iter(
                self.calendar_uid_to_iter[_currently_selected_uid],
            )
        except KeyError:
            self.calendar_tree_selection_changed()

    def calendar_tree_selection_changed(self, calendar_tree_selection=None):
        self.todolist_window.reset_action_popover()
        if calendar_tree_selection is None:
            calendar_tree_selection = self.calendar_tree_view.get_selection()

        path_iter = calendar_tree_selection.get_selected()[1]
        if path_iter is None:
            self.new_todo_action.set_enabled(False)
            self.todolist_window.current_calendar = None
        else:
            self.new_todo_action.set_enabled(True)
            self.todolist_window.current_calendar = self.calendar_store[path_iter][1]


class Abeluna(Gtk.Application):
    def __init__(self):
        Gtk.Application.__init__(self)

    def do_activate(self):
        win = MainWindow(self)
        win.show()

    def do_startup(self):
        Gtk.Application.do_startup(self)
        builder = Gtk.Builder()
        Notify.init('Abeluna')
        try:
            builder.add_from_file(os.path.join(UI_LOCATION, 'menubar.ui'))
        except GLib.Error:
            self.quit()

        self.set_menubar(builder.get_object('menubar'))

        quit_action = Gio.SimpleAction.new('quit', None)
        quit_action.connect('activate', lambda action, parameter: self.quit())
        self.add_action(quit_action)

        self.add_accelerator('<Ctrl>N', 'win.new-todo', None)
        self.add_accelerator('<Ctrl>R', 'win.sync-todo', None)
        self.add_accelerator('<Ctrl>W', 'app.quit', None)


def main():
    app = Abeluna()
    try:
        exit_code = app.run(sys.argv)
    except KeyboardInterrupt:
        exit_code = 1
    server.stop_all()
    return exit_code


if __name__ == '__main__':
    main()
