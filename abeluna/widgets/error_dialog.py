from gi.repository import Gtk


class ErrorDialog:
    def __init__(self, parent, text):
        self.dialog = Gtk.MessageDialog(
            transient_for=parent,
            flags=0,
            message_type=Gtk.MessageType.ERROR,
            buttons=Gtk.ButtonsType.OK,
            text=text,
        )

    def run_and_wait(self):
        self.dialog.run()
        self.dialog.destroy()
