import datetime
import uuid
from collections import defaultdict

import humanize
import icalendar
import pytz
from gi.repository import GObject, Gdk, Gtk

from abeluna.settings import settings
from abeluna.sync import server
from abeluna.util import colour_text
from abeluna.widgets import DateTimePickerWidget, DropdownSelectWidget


DEFAULT_DATA = {
    'uid': '',
    'summary': 'Task Name',
    'start_date': None,
    'end_date': None,
    'all_day': False,
    'classification': 'PUBLIC',
    'status': 'NEEDS-ACTION',
    'progress': 0,
    'priority': 0,
    'categories': [],
    'description': '',
    # Backend
    'sequence': 0,
    'created_date': None,
    'completed_date': None,
    'dtstamp': None,
    'last_modified_date': None,
    'related_to': None,
    'hide_subtasks': 0,
}


class Todo:
    FIELDS = list(DEFAULT_DATA.keys())
    CLASS_OPTIONS = [
        ('PUBLIC', 'Show full event'),
        ('CONFIDENTIAL', 'Show only busy'),
        ('PRIVATE', 'Hide this task'),
    ]

    STATUS_OPTIONS = [
        ('NEEDS-ACTION', 'Needs Action'),
        ('COMPLETED', 'Completed'),
        ('IN-PROCESS', 'In Process'),
        ('CANCELLED', 'Cancelled'),
    ]

    DO_NOT_TRACK = ('last_modified_date', 'sequence', 'completed_date', 'dtstamp', 'created_date')
    DO_NOT_LOAD = ('uid', 'sequence', 'created_date', 'dtstamp', 'last_modified_date', 'hide_subtasks')

    UTC_DATE_FIELDS = ('created_date', 'completed_date', 'dtstamp', 'last_modified_date')
    LOCAL_DATE_FIELDS = ('start_date', 'end_date')
    DATE_FIELDS = UTC_DATE_FIELDS + LOCAL_DATE_FIELDS

    VTODO_MAPPING = (
        ('uid', 'UID'),
        ('summary', 'SUMMARY'),
        ('start_date', 'DTSTART'),
        ('end_date', 'DUE'),
        ('classification', 'CLASS'),
        ('status', 'STATUS'),
        ('progress', 'PERCENT-COMPLETE'),
        ('priority', 'PRIORITY'),
        ('categories', 'CATEGORIES'),
        ('description', 'DESCRIPTION'),
        ('sequence', 'SEQUENCE'),
        ('created_date', 'CREATED'),
        ('completed_date', 'COMPLETED'),
        ('dtstamp', 'DTSTAMP'),
        ('last_modified_date', 'LAST-MODIFIED'),
        ('related_to', 'RELATED-TO'),
        ('hide_subtasks', 'X-OC-HIDESUBTASKS'),
    )

    @classmethod
    def load_from_vtodo(cls, vtodo, load_all=True):
        kwargs = {}

        def _sanitize(val):
            if isinstance(val, icalendar.vText):
                return str(val)
            elif isinstance(val, icalendar.prop.vCategory):
                _tmp_vals = []
                for cat in val.cats:
                    if isinstance(cat, icalendar.vText):
                        _tmp_vals.append(str(cat))
                    else:
                        _tmp_vals.append(cat)
                return _tmp_vals
            return val

        def _normalize_datetime(date):
            dt = date.dt
            if not isinstance(dt, datetime.datetime):
                dt = datetime.datetime(year=dt.year, month=dt.month, day=dt.day)
            return dt.astimezone(pytz.timezone(settings.TIMEZONE))

        for field_model, field_vtodo in cls.VTODO_MAPPING:
            if not load_all and field_model in cls.DO_NOT_LOAD:
                continue
            try:
                val = vtodo[field_vtodo]
            except KeyError:
                pass
            else:
                kwargs[field_model] = _sanitize(val)

        for dt in ('start_date', 'end_date'):
            if dt in kwargs and not isinstance(kwargs[dt].dt, datetime.datetime):
                kwargs['all_day'] = True
        for dt in cls.DATE_FIELDS:
            if dt in kwargs:
                kwargs[dt] = _normalize_datetime(kwargs[dt])

        return cls(vtodo=vtodo, **kwargs)

    def update_vtodo(self):
        _fields = self.fields.copy()

        def _sanitize(field, val):
            if field == 'categories':
                return icalendar.prop.vCategory(val)
            return val

        for field_list, timezone in (
            (self.UTC_DATE_FIELDS, pytz.UTC),
            (self.LOCAL_DATE_FIELDS, pytz.timezone(settings.TIMEZONE)),
        ):
            for dt_field in field_list:
                if _fields[dt_field] is not None:
                    _fields[dt_field] = _fields[dt_field].astimezone(timezone)

        if _fields['all_day']:
            for dt in ('start_date', 'end_date'):
                if _fields[dt] is not None:
                    _fields[dt] = _fields[dt].date()

        for field_model, field_vtodo in self.VTODO_MAPPING:
            val = _fields[field_model]
            try:
                self.vtodo.pop(field_vtodo)
            except KeyError:
                pass
            if val not in (None, '', []):
                self.vtodo.add(field_vtodo, _sanitize(field_model, val))

    def now(self, aware):
        if aware:
            return datetime.datetime.now(pytz.timezone(settings.TIMEZONE))
        else:
            return datetime.datetime.now()

    def __init__(self, **kwargs):
        self.vtodo = kwargs.pop('vtodo', None)
        self.callback_mapping = defaultdict(list)
        self.fields = DEFAULT_DATA.copy()
        self.fields['uid'] = uuid.uuid4().hex
        self.fields['created_date'] = self.fields['dtstamp'] = self.fields['last_modified_date'] = self.now(aware=True)
        self.fields.update(**kwargs)

        if self.vtodo is None:
            self.vtodo = icalendar.Todo()
        self.update_vtodo()

        def on_complete():
            if self.completed_date is not None and not self.completed:
                self.completed_date = None
            elif self.completed_date is None and self.completed:
                self.completed_date = self.now(aware=True)
        self.connect('progress', on_complete)
        self.connect('status', on_complete)

        def update():
            _now = self.now(aware=True)
            if (
                self.last_modified_date is not None and
                abs(self.last_modified_date - _now).total_seconds() > 60
            ):
                self.sequence += 1
            self.last_modified_date = _now

        self.connect_to_all(update)

    def connect(self, field, callback, *args, **kwargs):
        self.callback_mapping[field].append((callback, args, kwargs))

    def connect_to_all(self, callback, *args, **kwargs):
        for field in self.FIELDS:
            if field not in self.DO_NOT_TRACK:
                self.connect(field, callback, *args, **kwargs)

    def __getattr__(self, field):
        if field in self.FIELDS:
            return self.fields[field]
        raise AttributeError()

    def __setattr__(self, field, value):
        if field in self.FIELDS:
            if value != self.fields[field]:
                self.fields[field] = value
                self.update_vtodo()
                for cb, args, kwargs, in self.callback_mapping[field]:
                    cb(*args, **kwargs)
        else:
            super().__setattr__(field, value)

    def __getitem__(self, field):
        return getattr(self, field)

    def __setitem__(self, field, value):
        setattr(self, field, value)

    @property
    def completed(self):
        return self.status == 'COMPLETED' and self.progress == 100

    @completed.setter
    def completed(self, value):
        if value:
            self.status = 'COMPLETED'
            self.progress = 100
        else:
            self.status = 'NEEDS-ACTION'
            self.progress = 0

    @property
    def time_display(self):
        _now = self.now(aware=False)

        def _time_or_date_display(dt):
            if not self.all_day and abs(_now - dt) < datetime.timedelta(days=30):
                return humanize.naturaltime(dt)
            else:
                return humanize.naturaldate(dt)

        def _convert_datetime(dt):
            if dt is None:
                return None
            return dt.astimezone(pytz.timezone(settings.TIMEZONE)).replace(tzinfo=None)

        if self.completed:
            if self.completed_date is None:
                return ''

            return colour_text(
                'Completed {}'.format(_time_or_date_display(_convert_datetime(self.completed_date))),
                '#00c900',
            )
        if self.status == 'CANCELLED':
            return '<i>Cancelled</i>'

        if self.start_date is None and self.end_date is None:
            return ''

        _start = _convert_datetime(self.start_date)
        _end = _convert_datetime(self.end_date)
        if _start is not None and _start > _now:
            return 'Starts {}'.format(_time_or_date_display(_start))
        elif _end is not None:
            if _end < _now:
                return colour_text(
                    '<b>Ended {}</b>'.format(_time_or_date_display(_end)),
                    'red',
                )
            else:
                return colour_text(
                    'Ends {}'.format(_time_or_date_display(_end)),
                    'orange',
                )
        return ''

    @property
    def sort_value(self):
        _GAP = 2**34
        _MIN_BOUND = 0
        _COMPLETED_BOUND = _GAP
        _PRIORITY_BOUND = _GAP * 2
        _END_DATE_BOUND = _GAP * 3

        _now = self.now(aware=True)
        if self.completed:
            if self.completed_date is None:
                return _MIN_BOUND
            return _COMPLETED_BOUND - int((_now - self.completed_date).total_seconds() // 60)
        elif self.status == 'CANCELLED':
            return _COMPLETED_BOUND + 1
        elif self.status == 'IN-PROCESS':
            return _PRIORITY_BOUND + 1
        elif self.end_date is not None:
            return _END_DATE_BOUND - int((self.end_date - _now).total_seconds() // 60)
        elif self.priority:
            return _PRIORITY_BOUND - self.priority
        return _COMPLETED_BOUND + 2


CHAR_LONG_LIMIT = 2048
CHAR_SHORT_LIMIT = 48


class TodoEditor(Gtk.Grid):
    def __init__(self, *args, **kwargs):
        _data = kwargs.pop('data', None)
        _uid = kwargs.pop('uid', None)
        super().__init__(*args, **kwargs)
        self.data = None
        self.uid = None

        self.set_column_homogeneous(True)
        self.set_column_spacing(5)
        self.set_row_spacing(5)
        self.set_border_width(10)

        self._create_widgets()

        self.set_uid(_uid)
        self.set_data(_data)

    def set_data(self, _data):
        if _data is None:
            self.data = None
            self.uid = None
            for child in self.get_children():
                child.hide()
            return

        if self.uid != _data['uid']:
            return

        self.data = _data
        self._update_widgets(_data)
        self.show_all()

    def set_uid(self, uid):
        self.uid = uid

    def _update_widgets(self, _data):
        self.summary_label.set_text(_data['summary'])
        self.startdate_picker.set_selected_date(_data['start_date'])
        self.startdate_picker.set_date_only(_data['all_day'])
        self.enddate_picker.set_selected_date(_data['end_date'])
        self.enddate_picker.set_date_only(_data['all_day'])
        self.allday_toggle.set_active(_data['all_day'])
        self.classification_combobox.set_active_id(_data['classification'])
        self.status_combobox.set_active_id(_data['status'])
        self.progress_slider.set_value(_data['progress'])
        self.priority_slider.set_value(_data['priority'])
        self.category_view.set_text(', '.join(_data['categories']) or '-')
        self.description_view.get_buffer().set_text(_data['description'])
        self.update_datepicker_labels()

    def _get_label(self, widget):
        date = widget.get_selected_date()
        if date is None:
            return 'Unset'
        else:
            if widget.get_date_only():
                return date.strftime('%b %d, %Y')
            else:
                return date.strftime('%b %d, %Y %H:%M')

    def update_datepicker_labels(self):
        self.startdate_button.set_label(self._get_label(self.startdate_picker))
        self.enddate_button.set_label(self._get_label(self.enddate_picker))

    def _create_widgets(self):
        self.summary_label = Gtk.Entry()
        self.summary_label.get_buffer().set_max_length(CHAR_SHORT_LIMIT)
        self.summary_label.set_width_chars(CHAR_SHORT_LIMIT // 4)

        def on_edited_summary(obj):
            self.data['summary'] = obj.get_buffer().get_text()
        self.summary_label.connect('changed', on_edited_summary)

        self.attach(self.summary_label, 0, 0, 3, 1)

        self.startdate_label = Gtk.Label(label='Start date')
        self.startdate_popover = Gtk.Popover()
        self.startdate_picker = DateTimePickerWidget()
        self.startdate_popover.add(self.startdate_picker)

        self.startdate_button = Gtk.Button(label=self._get_label(self.startdate_picker))

        def on_clicked_startdate(obj):
            self.startdate_picker.set_selected_date(self.data['start_date'])
            self.startdate_popover.set_relative_to(self.startdate_button)
            self.startdate_popover.show_all()
            self.startdate_popover.popup()
        self.startdate_button.connect('clicked', on_clicked_startdate)

        def on_update_selected_startdate(obj):
            start_date = obj.get_selected_date()
            if start_date is not None and self.data['end_date'] is not None and start_date > self.data['end_date']:
                self.data['end_date'] = start_date
                self.enddate_picker.set_selected_date(self.data['end_date'])
            self.data['start_date'] = start_date
            self.startdate_popover.popdown()
            self.update_datepicker_labels()
        self.startdate_picker.connect('updated-date', on_update_selected_startdate)

        def on_delete_startdate(obj):
            self.data['start_date'] = None
            self.startdate_picker.set_selected_date(None)
            self.update_datepicker_labels()
        self.startdate_delete = Gtk.Button.new_from_icon_name('user-trash-symbolic', 4)
        self.startdate_delete.connect('clicked', on_delete_startdate)

        self.attach_next_to(self.startdate_label, self.summary_label, Gtk.PositionType.BOTTOM, 2, 1)
        self.attach_next_to(self.startdate_button, self.startdate_label, Gtk.PositionType.RIGHT, 3, 1)
        self.attach_next_to(self.startdate_delete, self.startdate_button, Gtk.PositionType.RIGHT, 1, 1)

        self.enddate_label = Gtk.Label(label='End date')
        self.enddate_popover = Gtk.Popover()
        self.enddate_picker = DateTimePickerWidget()
        self.enddate_popover.add(self.enddate_picker)

        self.enddate_button = Gtk.Button(label=self._get_label(self.enddate_picker))

        def on_clicked_enddate(obj):
            self.enddate_picker.set_selected_date(self.data['end_date'])
            self.enddate_popover.set_relative_to(self.enddate_button)
            self.enddate_popover.show_all()
            self.enddate_popover.popup()
        self.enddate_button.connect('clicked', on_clicked_enddate)

        def on_update_selected_enddate(obj):
            end_date = obj.get_selected_date()
            if end_date is not None and self.data['start_date'] is not None and end_date < self.data['start_date']:
                self.data['start_date'] = end_date
                self.startdate_picker.set_selected_date(self.data['start_date'])
            self.data['end_date'] = end_date
            self.enddate_popover.popdown()
            self.update_datepicker_labels()
        self.enddate_picker.connect('updated-date', on_update_selected_enddate)

        def on_delete_enddate(obj):
            self.data['end_date'] = None
            self.enddate_picker.set_selected_date(None)
            self.update_datepicker_labels()
        self.enddate_delete = Gtk.Button.new_from_icon_name('user-trash-symbolic', 4)
        self.enddate_delete.connect('clicked', on_delete_enddate)

        self.attach_next_to(self.enddate_label, self.startdate_label, Gtk.PositionType.BOTTOM, 2, 1)
        self.attach_next_to(self.enddate_button, self.enddate_label, Gtk.PositionType.RIGHT, 3, 1)
        self.attach_next_to(self.enddate_delete, self.enddate_button, Gtk.PositionType.RIGHT, 1, 1)

        self.allday_label = Gtk.Label(label='All day?')
        self.allday_toggle = Gtk.Switch()

        def on_activate_allday(obj, gparam):
            self.data['all_day'] = obj.get_active()
            self.enddate_picker.set_date_only(self.data['all_day'])
            self.startdate_picker.set_date_only(self.data['all_day'])
            self.update_datepicker_labels()
        self.allday_toggle.connect('notify::active', on_activate_allday)
        self.allday_toggle.set_halign(Gtk.Align.START)

        self.attach_next_to(self.allday_label, self.enddate_label, Gtk.PositionType.BOTTOM, 2, 1)
        self.attach_next_to(self.allday_toggle, self.allday_label, Gtk.PositionType.RIGHT, 1, 1)

        self.classification_label = Gtk.Label(label='Classification')
        self.classification_combobox = DropdownSelectWidget(options=Todo.CLASS_OPTIONS)

        def on_changed_classification(obj):
            self.data['classification'] = obj.get_active_id()
        self.classification_combobox.connect('changed', on_changed_classification)

        self.attach_next_to(self.classification_label, self.allday_label, Gtk.PositionType.BOTTOM, 2, 1)
        self.attach_next_to(self.classification_combobox, self.classification_label, Gtk.PositionType.RIGHT, 4, 1)

        self.status_label = Gtk.Label(label='Status')
        self.status_combobox = DropdownSelectWidget(options=Todo.STATUS_OPTIONS)

        def on_changed_status(obj):
            self.data['status'] = obj.get_active_id()
        self.status_combobox.connect('changed', on_changed_status)

        self.attach_next_to(self.status_label, self.classification_label, Gtk.PositionType.BOTTOM, 2, 1)
        self.attach_next_to(self.status_combobox, self.status_label, Gtk.PositionType.RIGHT, 4, 1)

        self.progress_label = Gtk.Label(label='Progress')
        self.progress_slider = Gtk.Scale(
            orientation=Gtk.Orientation.HORIZONTAL,
            adjustment=Gtk.Adjustment(
                value=0,
                lower=0,
                upper=100,
                step_increment=1,
                page_increment=10,
                page_size=0,
            ),
        )
        self.progress_slider.set_value_pos(Gtk.PositionType.LEFT)
        self.progress_slider.set_digits(0)
        self.progress_slider.set_hexpand(True)
        self.progress_slider.set_valign(Gtk.Align.START)

        def on_changed_progress(obj):
            self.data['progress'] = obj.get_value()
        self.progress_slider.connect('value-changed', on_changed_progress)
        self.attach_next_to(self.progress_label, self.status_label, Gtk.PositionType.BOTTOM, 2, 1)
        self.attach_next_to(self.progress_slider, self.progress_label, Gtk.PositionType.RIGHT, 4, 1)

        self.priority_label = Gtk.Label(label='Priority')
        self.priority_slider = Gtk.Scale(
            orientation=Gtk.Orientation.HORIZONTAL,
            adjustment=Gtk.Adjustment(
                value=0,
                lower=0,
                upper=9,
                step_increment=1,
                page_increment=0,
                page_size=0,
            ),
        )
        self.priority_slider.set_value_pos(Gtk.PositionType.LEFT)
        self.priority_slider.set_digits(0)
        self.priority_slider.set_hexpand(True)
        self.priority_slider.set_valign(Gtk.Align.START)

        def on_changed_priority(obj):
            self.data['priority'] = obj.get_value()
        self.priority_slider.connect('value-changed', on_changed_priority)
        self.attach_next_to(self.priority_label, self.progress_label, Gtk.PositionType.BOTTOM, 2, 1)
        self.attach_next_to(self.priority_slider, self.priority_label, Gtk.PositionType.RIGHT, 4, 1)

        self.category_label = Gtk.Label(label='Categories')
        self.category_label.set_margin_bottom(10)
        self.category_view = Gtk.Label()
        self.attach_next_to(self.category_label, self.priority_label, Gtk.PositionType.BOTTOM, 2, 1)
        self.attach_next_to(self.category_view, self.category_label, Gtk.PositionType.RIGHT, 4, 1)

        self.description_label = Gtk.Label(label='Summary')
        self.description_window = Gtk.ScrolledWindow()
        self.description_window.set_hexpand(True)
        self.description_window.set_vexpand(True)
        self.description_window.set_shadow_type(type=Gtk.ShadowType.ETCHED_IN)
        self.description_view = Gtk.TextView()
        self.description_view.set_border_width(5)
        self.description_view.set_wrap_mode(Gtk.WrapMode.WORD_CHAR)

        def on_changed_description(obj):
            self.data['description'] = obj.get_text(obj.get_start_iter(), obj.get_end_iter(), include_hidden_chars=True)

        def limit_text_before(obj, it, text, length):
            cnt = obj.get_char_count()
            if cnt == CHAR_LONG_LIMIT:
                obj.stop_emission_by_name('insert-text')

        def limit_text_after(obj, it, text, length):
            cnt = obj.get_char_count()
            if cnt > CHAR_LONG_LIMIT:
                totrim_begin = obj.get_iter_at_offset(CHAR_LONG_LIMIT)
                totrim_end = obj.get_end_iter()
                obj.delete(totrim_begin, totrim_end)
                it.assign(totrim_begin)
        self.description_view.get_buffer().connect('insert-text', limit_text_before)
        self.description_view.get_buffer().connect_after('insert-text', limit_text_after)
        self.description_view.get_buffer().connect('end-user-action', on_changed_description)

        self.description_window.add(self.description_view)
        self.attach_next_to(self.description_label, self.category_label, Gtk.PositionType.BOTTOM, 2, 1)
        self.attach_next_to(self.description_window, self.description_label, Gtk.PositionType.RIGHT, 4, 1)


class TodoListWindow(Gtk.Grid):
    def __init__(self):
        super().__init__()

        self.set_column_homogeneous(True)
        self.set_column_spacing(5)

        self.store = Gtk.TreeStore(str, str, bool, int, str, str, GObject.TYPE_UINT64)
        self.data = {}
        self.todo_uid_to_iter = {}
        self._reset_old_path = None
        self._current_calendar = None

        self.sorted_store = Gtk.TreeModelSort(model=self.store)
        self.sorted_store.set_sort_column_id(6, Gtk.SortType.DESCENDING)

        self.tree_view = Gtk.TreeView(model=self.sorted_store)
        self.tree_view.set_level_indentation(2)
        self.tree_view.set_headers_visible(False)

        column_summary = Gtk.TreeViewColumn('Task Name', Gtk.CellRendererText(), text=0)
        column_summary.set_sizing(Gtk.TreeViewColumnSizing.AUTOSIZE)
        column_summary.set_expand(True)
        self.tree_view.append_column(column_summary)

        column_display = Gtk.TreeViewColumn('Display', Gtk.CellRendererText(), markup=1)
        self.tree_view.append_column(column_display)

        renderer_completed = Gtk.CellRendererToggle()
        column_completed = Gtk.TreeViewColumn('Completed', renderer_completed, active=2)
        renderer_completed.connect('toggled', self.todo_completion_toggle)
        self.tree_view.append_column(column_completed)

        column_progress = Gtk.TreeViewColumn('Progress', Gtk.CellRendererProgress(text=''), value=3)
        self.tree_view.append_column(column_progress)

        column_pixbuf = Gtk.TreeViewColumn('Actions', Gtk.CellRendererPixbuf(), icon_name=4)
        self.tree_view.append_column(column_pixbuf)

        self.tree_view.connect('button-press-event', self.tree_view_button_press)
        self.tree_view.connect('row-activated', self.tree_view_row_activated)
        self.tree_view.connect('row-collapsed', self.tree_view_row_visibility_changed, True)
        self.tree_view.connect('row-expanded', self.tree_view_row_visibility_changed, False)
        self.tree_view.get_selection().connect('changed', self.tree_selection_changed)
        self.tree_view.set_enable_tree_lines(True)
        self.tree_view.set_enable_search(False)
        self.tree_view.set_search_column(-1)
        self.tree_view.set_tooltip_column(0)
        self.todo_scrollable_view = Gtk.ScrolledWindow(vexpand=True)
        self.todo_scrollable_view.set_propagate_natural_width(True)
        self.todo_scrollable_view.set_shadow_type(type=Gtk.ShadowType.ETCHED_OUT)
        self.todo_scrollable_view.add(self.tree_view)
        self.todo_scrollable_view.get_hadjustment().connect('value-changed', self.reset_action_popover)
        self.todo_scrollable_view.get_vadjustment().connect('value-changed', self.reset_action_popover)
        self.attach(self.todo_scrollable_view, 0, 0, 7, 1)

        self.editor_view = TodoEditor()
        self.attach_next_to(self.editor_view, self.todo_scrollable_view, Gtk.PositionType.RIGHT, 6, 1)

        self.popover = Gtk.Popover()
        self.popover_grid = Gtk.ListBox()
        button_delete = Gtk.Button(label='Delete')
        image_delete = Gtk.Image.new_from_icon_name('user-trash-symbolic', 4)
        button_delete.set_image(image_delete)
        button_delete.set_always_show_image(True)

        def on_todo_delete(obj):
            def propagate_delete(cur_iter):
                uid = self.store[cur_iter][5]

                server.delete_todo(self.data[uid].vtodo, self._current_calendar)
                del self.todo_uid_to_iter[uid]
                del self.data[uid]

                for child_iter in self.iterate_children(cur_iter):
                    propagate_delete(child_iter)

            uid = self.popover._attached_uid
            it = self.todo_uid_to_iter[uid]
            propagate_delete(it)
            self.store.remove(it)
            self.reset_action_popover()

        button_delete.connect('clicked', on_todo_delete)
        self.popover_grid.add(button_delete)

        button_clone_subtask = Gtk.Button(label='Clone')
        button_clone_subtask.set_image(Gtk.Image.new_from_icon_name('edit-copy-symbolic', 4))
        button_clone_subtask.set_always_show_image(True)

        def on_clone_subtask(obj):
            self.clone_todo(attached_uid=self.popover._attached_uid)
        button_clone_subtask.connect('clicked', on_clone_subtask)
        self.popover_grid.add(button_clone_subtask)

        button_add_subtask = Gtk.Button(label='Add subtask')
        button_add_subtask.set_image(Gtk.Image.new_from_icon_name('list-add-symbolic', 4))
        button_add_subtask.set_always_show_image(True)

        def on_add_subtask(obj):
            self.new_todo(parent_uid=self.popover._attached_uid)
        button_add_subtask.connect('clicked', on_add_subtask)
        self.popover_grid.add(button_add_subtask)

        self.popover.add(self.popover_grid)

        GObject.timeout_add_seconds(30, self.update_natural_dates)

    def update_natural_dates(self):
        for uid, it in self.todo_uid_to_iter.items():
            self.store[it][1] = self.data[uid].time_display
        return True

    def rebuild_todolist(self):
        path_iter = self.tree_view.get_selection().get_selected()[1]
        if path_iter is None:
            _currently_selected_uid = None
        else:
            _currently_selected_uid = self.sorted_store[path_iter][5]

        self.store.clear()
        self.data.clear()
        self.todo_uid_to_iter.clear()

        if self._current_calendar is not None:
            adjacency_list = defaultdict(list)

            for vtodo in server.todolist[self._current_calendar]:
                self.data[str(vtodo['UID'])] = Todo.load_from_vtodo(vtodo)

            for todo in self.data.values():
                parent = todo['related_to']
                if parent not in self.data:
                    parent = None
                adjacency_list[parent].append(todo.uid)

            def add_todos_to_store(current_todo=None):
                for todo in adjacency_list[current_todo]:
                    self.todo_uid_to_iter[todo] = self.attach_todo(self.todo_uid_to_iter.get(current_todo, None), todo)
                    add_todos_to_store(todo)
            add_todos_to_store()

            for todo_uid in adjacency_list[None]:
                self.update_tree_view_row_visibility(self.todo_uid_to_iter[todo_uid])

            for todo in self.data.values():
                self.connect_todo(todo)

        try:
            self.tree_view.get_selection().select_iter(
                self.sorted_store.convert_child_iter_to_iter(self.todo_uid_to_iter[_currently_selected_uid])[1],
            )
        except KeyError:
            self.tree_selection_changed()

    def attach_todo(self, parent, uid):
        _data = self.data[uid]
        return self.store.append(
            parent,
            [
                _data.summary,
                _data.time_display,
                _data.completed,
                _data.progress,
                'applications-system-symbolic',
                uid,
                _data.sort_value,
            ],
        )

    def new_todo(self, parent_uid=None, new_todo=None):
        if self._current_calendar is None:
            return

        if new_todo is None:
            new_todo = Todo(related_to=parent_uid)

        parent_it = self.todo_uid_to_iter.get(parent_uid, None)
        self.data[new_todo.uid] = new_todo
        todo_it = self.todo_uid_to_iter[new_todo.uid] = self.attach_todo(parent_it, new_todo.uid)

        server.update_todo(new_todo.vtodo, self._current_calendar)
        self.connect_todo(new_todo)

        path = self.sorted_store.convert_child_path_to_path(self.store.get_path(todo_it))
        self.tree_view.expand_to_path(path)
        self.tree_view.set_cursor(path, None, False)

    def clone_todo(self, attached_uid=None):
        try:
            data = self.data[attached_uid]
        except KeyError:
            return

        cloned_todo = Todo.load_from_vtodo(icalendar.Todo.from_ical(data.vtodo.to_ical()), load_all=False)
        self.new_todo(cloned_todo.related_to, new_todo=cloned_todo)

    def connect_todo(self, todo):
        path = self.store.get_path(self.todo_uid_to_iter[todo.uid])
        for field in ('progress', 'status', 'summary'):
            todo.connect(field, self.editor_view.set_data, todo)
        todo.connect('progress', self.tree_view_update_progress, path)
        todo.connect('progress', self.update_todo_completion, path)
        todo.connect('status', self.update_todo_completion, path)
        todo.connect('summary', self.tree_view_update_summary, path)
        todo.connect('start_date', self.tree_view_update_date, path)
        todo.connect('end_date', self.tree_view_update_date, path)
        todo.connect('all_day', self.tree_view_update_date, path)
        todo.connect('progress', self.tree_view_update_date, path)
        todo.connect('status', self.tree_view_update_date, path)
        todo.connect('progress', self.tree_view_update_sort, path)
        todo.connect('status', self.tree_view_update_sort, path)
        todo.connect('priority', self.tree_view_update_sort, path)
        todo.connect('start_date', self.tree_view_update_sort, path)
        todo.connect('end_date', self.tree_view_update_sort, path)
        todo.connect('all_day', self.tree_view_update_sort, path)
        todo.connect_to_all(server.update_todo, todo.vtodo, self._current_calendar)

    def reset_action_popover(self, *args):
        self.popover.popdown()

    @property
    def current_calendar(self):
        return self._current_calendar

    @current_calendar.setter
    def current_calendar(self, uid):
        self._current_calendar = uid
        self.rebuild_todolist()

    def iterate_children(self, it):
        child_iter = self.store.iter_children(it)
        while child_iter is not None:
            yield child_iter
            child_iter = self.store.iter_next(child_iter)

    def update_todo_completion(self, path):
        # Implicit recursion through signals
        value = self.store[path][2] = self.data[self.store[path][5]].completed
        for child_iter in self.iterate_children(self.store.get_iter(path)):
            self.store[child_iter][2] = self.data[self.store[child_iter][5]].completed = value

    def todo_completion_toggle(self, widget, path):
        if isinstance(path, str):
            path = Gtk.TreePath.new_from_string(path)
        path = self.sorted_store.convert_path_to_child_path(path)

        uid = self.store[path][5]
        self.data[uid].completed = not self.data[uid].completed
        self.update_todo_completion(path)
        self._reset_old_path = self.sorted_store.convert_child_path_to_path(path)

    def tree_selection_changed(self, tree_selection=None):
        if tree_selection is None:
            tree_selection = self.tree_view.get_selection()

        if self._reset_old_path is not None:
            tree_selection.select_path(self._reset_old_path)
            self._reset_old_path = None
            return

        path_iter = tree_selection.get_selected()[1]
        if path_iter is None:
            self.editor_view.set_data(None)
            return

        uid = self.sorted_store[path_iter][5]
        _data = self.data[uid]

        self.editor_view.set_uid(uid)
        self.editor_view.set_data(_data)

    def update_tree_view_row_visibility(self, it, show=True):
        show &= not int(self.data[self.store[it][5]]['hide_subtasks'])
        if not show:
            return

        self.tree_view.expand_row(
            self.sorted_store.convert_child_path_to_path(self.store.get_path(it)),
            open_all=False,
        )
        for child_iter in self.iterate_children(it):
            self.update_tree_view_row_visibility(child_iter, show)

    def tree_view_row_visibility_changed(self, tree_view, it, path, hide):
        _data = self.data[self.sorted_store[path][5]]
        _data.hide_subtasks = int(hide)
        self.update_tree_view_row_visibility(self.todo_uid_to_iter[_data.uid], not hide)

    def tree_view_update_summary(self, path):
        _data = self.data[self.store[path][5]]
        self.store[path][0] = _data.summary

    def tree_view_update_date(self, path):
        _data = self.data[self.store[path][5]]
        self.store[path][1] = _data.time_display

    def tree_view_update_progress(self, path):
        _data = self.data[self.store[path][5]]
        self.store[path][3] = _data.progress

    def tree_view_update_sort(self, path):
        _data = self.data[self.store[path][5]]
        self.store[path][6] = _data.sort_value

    def tree_view_row_activated(self, tree_view, path, column):
        if tree_view.row_expanded(path):
            tree_view.collapse_row(path)
        else:
            tree_view.expand_row(path, open_all=False)

    def tree_view_button_press(self, tree_view, event):
        if event.type == Gdk.EventType.BUTTON_PRESS:
            try:
                path, column, cell_x, cell_y = tree_view.get_path_at_pos(event.x, event.y)
            except Exception:
                self.reset_action_popover()
                return
            if column.get_title() != 'Actions' and event.button != 3:
                self.reset_action_popover()
            else:
                pos = tree_view.get_cell_area(path, column)
                rect = Gdk.Rectangle()
                pos_x, pos_y = tree_view.convert_bin_window_to_widget_coords(pos.x, pos.y)
                if column.get_title() == 'Actions':
                    rect.x = pos_x
                    rect.width = pos.width
                else:
                    rect.x = event.x

                rect.y = pos_y
                rect.height = pos.height // 2
                self.popover.set_position(Gtk.PositionType.BOTTOM)
                self.popover.set_relative_to(tree_view)
                self.popover.set_pointing_to(rect)
                self.popover.set_modal(False)

                self.popover._attached_uid = self.sorted_store[path][5]

                self.popover.show_all()
                self.popover.popup()
