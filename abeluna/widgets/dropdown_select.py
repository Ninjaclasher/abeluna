from gi.repository import Gtk


class DropdownSelectWidget(Gtk.ComboBox):
    def __init__(self, *args, **kwargs):
        options = kwargs.pop('options')

        if len(options) < 1:
            raise ValueError('no options')

        self.id_index = kwargs.pop('id_index', 0)
        self.value_index = kwargs.pop('value_index', 1)

        if not isinstance(options[0][self.id_index], str):
            raise ValueError('id must be of type string')

        self.store = Gtk.ListStore(*[type(idx) for idx in options[0]])
        for option in options:
            self.store.append(option)
        kwargs['model'] = self.store

        super().__init__(*args, **kwargs)

        renderer_text = Gtk.CellRendererText()
        self.pack_start(renderer_text, True)
        self.add_attribute(renderer_text, 'text', self.value_index)

        self.set_id_column(self.id_index)
