import calendar
import datetime

import pytz
from gi.repository import GObject, Gtk

from abeluna.settings import settings
from abeluna.widgets.dropdown_select import DropdownSelectWidget


class DateTimePickerWidget(Gtk.Grid):
    __gsignals__ = {
        'updated-date': (GObject.SignalFlags.RUN_LAST, None, ()),
    }

    def __init__(self, *args, **kwargs):
        self.date_only = kwargs.pop('date_only', True)
        selected_date = kwargs.pop('selected_date', None)
        self._tz = kwargs.pop('timezone', None)

        super().__init__(*args, **kwargs)
        self.set_column_spacing(10)
        self.set_row_spacing(10)
        self.set_border_width(5)

        self._create_widgets()

        self.set_selected_date(selected_date)
        self.set_date_only(self.date_only)

    @property
    def now(self):
        return datetime.datetime.now(tz=self.tz) + datetime.timedelta(minutes=1)

    @property
    def tz(self):
        if self._tz is not None:
            return self._tz
        return pytz.timezone(settings.TIMEZONE)

    def get_date_only(self):
        return self.date_only

    def set_date_only(self, date_only):
        self.date_only = date_only
        for child in self.get_children():
            self.remove(child)

        if not self.date_only:
            self.attach(self.hour_selector, 0, 0, 2, 3)
            self.attach_next_to(self.time_colon, self.hour_selector, Gtk.PositionType.RIGHT, 1, 3)
            self.attach_next_to(self.minute_selector, self.time_colon, Gtk.PositionType.RIGHT, 2, 3)
        self.attach(self.year_selector, 6, 0, 3, 1)
        self.attach_next_to(self.month_selector, self.year_selector, Gtk.PositionType.BOTTOM, 3, 1)
        self.attach_next_to(self.day_selector, self.month_selector, Gtk.PositionType.BOTTOM, 3, 1)

        self.attach(self.set_button, 7, 4, 2, 1)

        # self.emit('updated-date')

    def get_selected_date(self):
        return self.selected_date

    def set_selected_date(self, selected_date):
        self.selected_date = selected_date
        if self.selected_date is not None:
            date = self.selected_date = self.selected_date.astimezone(tz=self.tz)
        else:
            date = self.now

        self.hour_selector.set_value(date.hour)
        self.minute_selector.set_value(date.minute)
        self.year_selector.set_value(date.year)
        self.month_selector.set_active(date.month - 1)
        self.day_selector.set_value(date.day)

        # self.emit('updated-date')

    def _create_widgets(self):
        self.hour_selector = Gtk.SpinButton(
            adjustment=Gtk.Adjustment(
                value=0,
                lower=0,
                upper=23,
                step_increment=1,
                page_increment=0,
                page_size=0,
            ),
        )
        self.hour_selector.set_wrap(True)
        self.hour_selector.set_orientation(Gtk.Orientation.VERTICAL)

        self.time_colon = Gtk.Label(label=':')

        self.minute_selector = Gtk.SpinButton(
            adjustment=Gtk.Adjustment(
                value=0,
                lower=0,
                upper=59,
                step_increment=1,
                page_increment=5,
                page_size=0,
            ),
        )
        self.minute_selector.set_wrap(True)
        self.minute_selector.set_orientation(Gtk.Orientation.VERTICAL)
        self.minute_selector.set_margin_end(20)

        self.year_selector = Gtk.SpinButton(
            adjustment=Gtk.Adjustment(
                value=self.now.year,
                lower=datetime.MINYEAR,
                upper=datetime.MAXYEAR,
                step_increment=1,
                page_increment=0,
                page_size=0,
            ),
        )
        self.year_selector.set_wrap(True)

        months = []
        for month_index in range(1, 13):
            months.append([str(month_index), datetime.date(1970, month_index, 1).strftime('%B')])
        self.month_selector = DropdownSelectWidget(options=months)
        self.month_selector.set_active(0)

        day_adjustment = Gtk.Adjustment(
            value=1,
            lower=1,
            upper=31,
            step_increment=1,
            page_increment=5,
            page_size=0,
        )
        self.day_selector = Gtk.SpinButton(adjustment=day_adjustment)
        self.day_selector.set_wrap(True)
        self.day_selector.set_hexpand(True)

        def on_changed(*args, **kwargs):
            month = self.month_selector.get_active_id()
            if month is None:
                return
            month = int(month)
            year = self.year_selector.get_value_as_int()
            weekday, num_days = calendar.monthrange(year, month)
            day_adjustment.set_upper(num_days)
            self.day_selector.update()
        self.month_selector.connect('changed', on_changed)
        self.year_selector.connect('value-changed', on_changed)

        self.set_button = Gtk.Button(label='Set!')

        def on_set_button_clicked(button):
            self.selected_date = datetime.datetime(
                year=self.year_selector.get_value_as_int(),
                month=int(self.month_selector.get_active_id()),
                day=self.day_selector.get_value_as_int(),
                hour=self.hour_selector.get_value_as_int(),
                minute=self.minute_selector.get_value_as_int(),
            ).astimezone(tz=self.tz)
            self.emit('updated-date')
        self.set_button.connect('clicked', on_set_button_clicked)
        self.set_button.set_margin_top(20)
