import pytz
from gi.repository import GObject, Gdk, Gtk

from abeluna.settings import settings
from abeluna.sync import Calendar, server
from abeluna.widgets import DropdownSelectWidget, ErrorDialog


class CalendarEditor(Gtk.Grid):
    __gsignals__ = {
        'updated-data': (GObject.SignalFlags.RUN_LAST, None, ()),
    }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.data = {}

        self.set_column_spacing(5)
        self.set_row_spacing(5)
        self.set_border_width(10)

        self._create_widgets()

    def set_data(self, data):
        self.data = data
        self.skip_validation_toggle.set_active(False)
        self.is_local_calendar.set_active(False)
        self.server_name_entry.get_buffer().set_text(self.data.get('name', ''), -1)
        self.server_url_entry.get_buffer().set_text(self.data.get('url', ''), -1)
        self.server_username_entry.get_buffer().set_text(self.data.get('username', ''), -1)
        self.server_password_entry.get_buffer().set_text(self.data.get('password', ''), -1)
        if not self.data.get('url'):
            self.is_local_calendar.set_active(True)
            self.update_server_fields()

    def update_server_fields(self):
        is_active = not self.is_local_calendar.get_active()
        for obj in (self.server_url_entry, self.server_username_entry, self.server_password_entry):
            if not is_active:
                obj.get_buffer().set_text('', -1)
            obj.set_sensitive(is_active)

    def get_data(self):
        return self.data

    def _create_widgets(self):
        self.server_name_label = Gtk.Label(label='Calendar Name')
        self.server_name_entry = Gtk.Entry()
        self.attach(self.server_name_label, 0, 0, 2, 1)
        self.attach_next_to(self.server_name_entry, self.server_name_label, Gtk.PositionType.RIGHT, 4, 1)

        self.is_local_calendar_label = Gtk.Label(label='Local Calendar')
        self.is_local_calendar = Gtk.CheckButton()
        self.is_local_calendar.connect('toggled', lambda button: self.update_server_fields())

        self.attach_next_to(self.is_local_calendar_label, self.server_name_label, Gtk.PositionType.BOTTOM, 2, 1)
        self.attach_next_to(self.is_local_calendar, self.is_local_calendar_label, Gtk.PositionType.RIGHT, 4, 1)

        self.server_url_label = Gtk.Label(label='Server URL')
        self.server_url_entry = Gtk.Entry()
        self.attach_next_to(self.server_url_label, self.is_local_calendar_label, Gtk.PositionType.BOTTOM, 2, 1)
        self.attach_next_to(self.server_url_entry, self.server_url_label, Gtk.PositionType.RIGHT, 4, 1)

        self.server_username_label = Gtk.Label(label='Server Username')
        self.server_username_entry = Gtk.Entry()
        self.attach_next_to(self.server_username_label, self.server_url_label, Gtk.PositionType.BOTTOM, 2, 1)
        self.attach_next_to(self.server_username_entry, self.server_username_label, Gtk.PositionType.RIGHT, 4, 1)

        self.server_password_label = Gtk.Label(label='Server Password')
        self.server_password_entry = Gtk.Entry()
        self.server_password_entry.set_visibility(False)
        self.attach_next_to(self.server_password_label, self.server_username_label, Gtk.PositionType.BOTTOM, 2, 1)
        self.attach_next_to(self.server_password_entry, self.server_password_label, Gtk.PositionType.RIGHT, 4, 1)

        self.skip_validation_toggle = Gtk.CheckButton(label='Skip Validation')
        self.attach(self.skip_validation_toggle, 0, 5, 3, 1)

        self.validation_spinner = Gtk.Spinner()
        self.validation_spinner.set_hexpand(False)
        self.validation_spinner.set_vexpand(True)
        self.validation_spinner.set_halign(Gtk.Align.END)
        self.attach_next_to(self.validation_spinner, self.skip_validation_toggle, Gtk.PositionType.RIGHT, 1, 1)

        def save_button_clicked(button):
            self.data['name'] = self.server_name_entry.get_buffer().get_text()
            self.data['url'] = self.server_url_entry.get_buffer().get_text()
            self.data['username'] = self.server_username_entry.get_buffer().get_text()
            self.data['password'] = self.server_password_entry.get_buffer().get_text()
            self.emit('updated-data')

        self.save_button = Gtk.Button('Save!')
        self.save_button.connect('clicked', save_button_clicked)

        self.attach_next_to(self.save_button, self.validation_spinner, Gtk.PositionType.RIGHT, 2, 1)


class SettingsWindow(Gtk.Window):
    def __init__(self, parent, active_child=None):
        Gtk.Window.__init__(self, title='Abeluna Settings')
        self.set_default_size(900, 400)
        self.parent = parent
        self.set_modal(True)
        self.set_transient_for(self.parent)
        self.set_destroy_with_parent(True)
        self.set_position(Gtk.WindowPosition.CENTER_ON_PARENT)
        self.connect('delete-event', lambda obj, event: self.destroy())

        self.main_grid = Gtk.Grid()
        self.main_grid.set_column_spacing(5)
        self.main_grid.set_row_spacing(5)
        self.main_grid.set_border_width(10)
        self.add(self.main_grid)

        self.main_stack = Gtk.Stack()
        self.main_stack_switcher = Gtk.StackSwitcher()
        self.main_stack_switcher.set_stack(self.main_stack)
        self.main_stack_switcher.set_orientation(Gtk.Orientation.VERTICAL)

        self.general_page_grid = Gtk.Grid()
        self.general_page_grid.set_column_homogeneous(True)
        self.general_page_grid.set_column_spacing(5)
        self.general_page_grid.set_row_spacing(5)
        self.general_page_grid.set_vexpand(True)
        self.general_page_grid.set_hexpand(True)

        self.timezone_label = Gtk.Label(label='Timezone')
        timezone_todo_store = Gtk.ListStore(str)
        for tz in pytz.common_timezones:
            timezone_todo_store.append([tz])
        self.timezone_combo = Gtk.ComboBox.new_with_model_and_entry(model=timezone_todo_store)
        self.timezone_combo.set_entry_text_column(0)
        self.timezone_combo.set_id_column(0)

        timezone_completion = Gtk.EntryCompletion()
        timezone_completion.set_model(timezone_todo_store)
        timezone_completion.set_text_column(0)
        timezone_completion.set_minimum_key_length(2)

        def match_timezone_selected(completion, todo_store, it):
            self.timezone_combo.set_active_id(todo_store[it][0])
        timezone_completion.connect('match-selected', match_timezone_selected)

        def match_timezone(completion, string, it):
            to_match = timezone_todo_store[it][0].lower()
            return all(word in to_match for word in string.lower().split())
        timezone_completion.set_match_func(match_timezone)
        self.timezone_combo.get_child().set_completion(timezone_completion)
        self.timezone_combo.set_active_id(settings.TIMEZONE)

        self.general_page_grid.attach(self.timezone_label, 0, 0, 2, 1)
        self.general_page_grid.attach_next_to(self.timezone_combo, self.timezone_label, Gtk.PositionType.RIGHT, 4, 1)

        self.autosync_label = Gtk.Label(label='Autosync Interval')
        self.autosync_selector = DropdownSelectWidget(options=[
            ('-1', 'Never'),
            ('10', 'Every 10 seconds'),
            ('30', 'Every 30 seconds'),
            ('60', 'Every minute'),
            ('600', 'Every 10 minutes'),
            ('1800', 'Every 30 minutes'),
            ('3600', 'Every hour'),
            ('21600', 'Every 6 hours'),
            ('86400', 'Every day'),
            ('604800', 'Every week'),
            ('2419200', 'Every 4 weeks'),
            ('1036800', 'Every year'),
        ])
        self.autosync_selector.set_active_id(settings.AUTOSYNC_INTERVAL)
        self.general_page_grid.attach_next_to(self.autosync_label, self.timezone_label, Gtk.PositionType.BOTTOM, 2, 1)
        self.general_page_grid.attach_next_to(self.autosync_selector, self.autosync_label, Gtk.PositionType.RIGHT, 4, 1)

        self.priority_label = Gtk.Label(label='On conflict')
        self.priority_selector = DropdownSelectWidget(options=[
            ('SERVER', 'Prioritize server'),
            ('CLIENT', 'Prioritize client'),
        ])
        self.priority_selector.set_active_id(settings.PRIORITIZE_ON_CONFLICT)
        self.general_page_grid.attach_next_to(self.priority_label, self.autosync_label, Gtk.PositionType.BOTTOM, 2, 1)
        self.general_page_grid.attach_next_to(self.priority_selector, self.priority_label, Gtk.PositionType.RIGHT, 4, 1)

        self.saved_label = Gtk.Label(label=' ')
        self.saved_label.set_xalign(0.95)
        self.saved_label.set_yalign(0.75)

        def clear_saved_label():
            self.saved_label.set_label(' ')
            return False

        def save_button_clicked(button):
            timezone = self.timezone_combo.get_active_id()
            autosync_interval = self.autosync_selector.get_active_id()
            priority = self.priority_selector.get_active_id()

            failed_settings = []
            for obj, name in (
                (timezone, 'timezone'),
                (autosync_interval, 'autosync interval'),
                (priority, 'priority'),
            ):
                if obj is None:
                    failed_settings.append(name)

            if failed_settings:
                ErrorDialog(
                    self,
                    'Setting for {} is invalid. Please try again.'.format(', '.join(failed_settings)),
                ).run_and_wait()
            else:
                if settings.TIMEZONE != timezone:
                    settings.TIMEZONE = timezone
                    self.parent.todolist_window.rebuild_todolist()
                if settings.AUTOSYNC_INTERVAL != autosync_interval:
                    settings.AUTOSYNC_INTERVAL = autosync_interval
                    server.restart_autosync_thread()
                settings.PRIORITIZE_ON_CONFLICT = priority
                settings.commit()
                self.saved_label.set_label('Saved!')
                GObject.timeout_add_seconds(5, clear_saved_label)

        self.save_button = Gtk.Button('Save!')
        self.save_button.set_margin_top(20)
        self.save_button.connect('clicked', save_button_clicked)

        self.general_page_grid.attach(self.save_button, 4, 4, 2, 1)
        self.general_page_grid.attach_next_to(self.saved_label, self.save_button, Gtk.PositionType.LEFT, 2, 1)

        padding = Gtk.Box()
        padding.set_hexpand(True)
        padding.set_vexpand(True)

        self.general_page_grid.attach_next_to(padding, self.save_button, Gtk.PositionType.TOP, 2, 1)

        self.main_stack.add_titled(self.general_page_grid, 'General', 'General settings')

        self.servers_page_grid = Gtk.Grid()
        self.servers_page_grid.set_column_homogeneous(True)
        self.servers_page_grid.set_column_spacing(5)
        self.servers_page_grid.set_row_spacing(5)

        self.server_todo_store = Gtk.ListStore(str, str, str, str)

        def rebuild_server_todo_store():
            self.server_todo_store.clear()
            for calendar in settings.CALENDARS.values():
                self.server_todo_store.append([
                    calendar['name'],
                    calendar['url'] or 'Local Calendar',
                    calendar['username'] or 'Local Calendar',
                    calendar['uid'],
                ])
        rebuild_server_todo_store()

        self.server_view = Gtk.TreeView(model=self.server_todo_store)
        self.server_view.set_hexpand(True)
        self.server_view.set_headers_clickable(False)
        self.server_view.set_search_column(0)
        for idx, name in enumerate(('Calendar Name', 'URL', 'Username')):
            self.server_view.append_column(Gtk.TreeViewColumn(name, Gtk.CellRendererText(), text=idx))

        self.server_editor_popover = Gtk.Popover()
        self.server_editor = CalendarEditor()

        def server_validation_checker(calendar, data):
            if hasattr(calendar, '_validated'):
                self.server_editor.save_button.set_sensitive(True)
                self.server_editor.validation_spinner.stop()
                if calendar._validated:
                    settings.add_or_update_calendar(data)
                    settings.commit()
                    rebuild_server_todo_store()
                    server.refresh_calendars()
                    self.parent.rebuild_calendarlist()
                    self.server_editor_popover.popdown()
                else:
                    ErrorDialog(
                        self,
                        'Could not connect to server. Please check your settings are correct.',
                    ).run_and_wait()
                return False
            return True

        def on_data_updated(obj):
            data = self.server_editor.get_data()
            if not data['name']:
                ErrorDialog(self, 'Name cannot be empty.').run_and_wait()
                return
            elif (
                not self.server_editor.is_local_calendar.get_active() and
                not all(data[field] for field in ('url', 'username', 'password'))
            ):
                ErrorDialog(self, 'Please enter the URL and credentials for the remote server.').run_and_wait()
                return

            self.server_editor.save_button.set_sensitive(False)
            calendar = Calendar.from_dict(data)
            if self.server_editor.skip_validation_toggle.get_active():
                calendar._validated = True
            else:
                self.server_editor.validation_spinner.start()
                import threading
                threading.Thread(target=calendar.validate).start()
            GObject.timeout_add(100, server_validation_checker, calendar, data)

        self.server_editor.connect('updated-data', on_data_updated)
        self.server_editor_popover.add(self.server_editor)

        def _show_editor_on_row(path):
            uid = self.server_todo_store[path][3]
            self.server_editor.set_data(settings.CALENDARS[uid].copy())

            pos = self.server_view.get_cell_area(path, self.server_view.get_column(0))
            rect = Gdk.Rectangle()
            pos_x, pos_y = self.server_view.convert_bin_window_to_widget_coords(pos.x, pos.y)

            rect.x = 0
            rect.width = self.server_view.get_allocation().width
            rect.y = pos_y
            rect.height = pos.height
            self.server_editor_popover.set_relative_to(self.server_view)
            self.server_editor_popover.set_pointing_to(rect)
            self.server_editor_popover.set_position(Gtk.PositionType.BOTTOM)
            self.server_editor_popover.show_all()
            self.server_editor_popover.popup()

        def on_row_activated(todo_tree_view, path, column):
            _show_editor_on_row(path)

        self.server_view.connect('row-activated', on_row_activated)

        self.scrollable_server_view = Gtk.ScrolledWindow(vexpand=True)
        self.scrollable_server_view.set_propagate_natural_width(True)
        self.scrollable_server_view.set_shadow_type(type=Gtk.ShadowType.ETCHED_OUT)
        self.scrollable_server_view.add(self.server_view)
        self.servers_page_grid.attach(self.scrollable_server_view, 0, 0, 8, 6)

        self.server_add_button = Gtk.Button(label='Add')
        self.server_clone_button = Gtk.Button(label='Clone')
        self.server_edit_button = Gtk.Button(label='Modify')
        self.server_delete_button = Gtk.Button(label='Delete')

        self.server_clone_button.set_sensitive(False)
        self.server_edit_button.set_sensitive(False)
        self.server_delete_button.set_sensitive(False)

        def on_todo_tree_selection_changed(todo_tree_selection):
            current_it = todo_tree_selection.get_selected()[1]
            if current_it is None:
                self.server_clone_button.set_sensitive(False)
                self.server_edit_button.set_sensitive(False)
                self.server_delete_button.set_sensitive(False)
            else:
                self.server_clone_button.set_sensitive(True)
                self.server_edit_button.set_sensitive(True)
                self.server_delete_button.set_sensitive(True)
        self.server_view.get_selection().connect('changed', on_todo_tree_selection_changed)

        def on_server_create(button, clone_selected):
            if clone_selected:
                it = self.server_view.get_selection().get_selected()[1]
                if it is None:
                    return
                uid = self.server_todo_store[it][3]
                data = settings.CALENDARS[uid].copy()
                data.pop('uid')
            else:
                data = {}

            self.server_editor.set_data(data)
            rect = Gdk.Rectangle()
            rect.width = button.get_allocation().width
            rect.height = button.get_allocation().height

            self.server_editor_popover.set_relative_to(button)
            self.server_editor_popover.set_pointing_to(rect)
            self.server_editor_popover.set_position(Gtk.PositionType.TOP)
            self.server_editor_popover.show_all()
            self.server_editor_popover.popup()
        self.server_add_button.connect('clicked', on_server_create, False)
        self.server_clone_button.connect('clicked', on_server_create, True)

        def on_server_edit(button):
            it = self.server_view.get_selection().get_selected()[1]
            if it is None:
                return
            _show_editor_on_row(self.server_todo_store.get_path(it))
        self.server_edit_button.connect('clicked', on_server_edit)

        def on_server_delete(button):
            it = self.server_view.get_selection().get_selected()[1]
            if it is None:
                return
            settings.delete_calendar(self.server_todo_store[it][3])
            settings.commit()
            rebuild_server_todo_store()
            server.refresh_calendars()
            self.parent.rebuild_calendarlist()

        self.server_delete_button.connect('clicked', on_server_delete)

        self.servers_page_grid.attach_next_to(
            self.server_add_button, self.scrollable_server_view, Gtk.PositionType.BOTTOM, 2, 1,
        )
        self.servers_page_grid.attach_next_to(
            self.server_clone_button, self.server_add_button, Gtk.PositionType.RIGHT, 2, 1,
        )
        self.servers_page_grid.attach_next_to(
            self.server_edit_button, self.server_clone_button, Gtk.PositionType.RIGHT, 2, 1,
        )
        self.servers_page_grid.attach_next_to(
            self.server_delete_button, self.server_edit_button, Gtk.PositionType.RIGHT, 2, 1,
        )

        self.main_stack.add_titled(self.servers_page_grid, 'Calendars', 'Calendar settings')

        def on_close_window(button):
            self.destroy()

        self.close_button = Gtk.Button(label='Close')
        self.close_button.connect('clicked', on_close_window)

        padding = Gtk.Box()
        padding.set_vexpand(True)
        self.main_grid.attach(self.main_stack_switcher, 0, 0, 3, 2)
        self.main_grid.attach_next_to(padding, self.main_stack_switcher, Gtk.PositionType.BOTTOM, 3, 1)
        self.main_grid.attach_next_to(self.close_button, padding, Gtk.PositionType.BOTTOM, 3, 1)
        self.main_grid.attach(self.main_stack, 3, 0, 5, 4)

        self.show_all()

        if active_child is not None:
            self.main_stack.set_visible_child_name(active_child)
