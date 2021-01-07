import caldav

from abeluna.sync.local import LocalServer


class Calendar:
    def __init__(self, uid, name, url, username, password, local_storage):
        self.uid = uid
        self.name = name
        self.url = url
        self.username = username
        self.password = password
        self.local_storage = local_storage

        if self.uid and self.local_storage:
            self.local_server = LocalServer(self.local_storage, self.uid)
        else:
            self.local_server = None

        if self.url:
            self.client = caldav.DAVClient(
                url=self.url,
                username=self.username,
                password=self.password,
            )
            self.calendar = caldav.Calendar(client=self.client, url=self.url)
        else:
            self.client = self.calendar = None

    @property
    def is_local(self):
        return self.client is None

    def validate(self):
        if self.is_local:
            self._validated = True
        else:
            try:
                response = self.client.propfind(self.url)
            except Exception:
                self._validated = False
            else:
                self._validated = response.status in (200, 207)
        return self._validated

    def to_dict(self):
        return {
            'uid': self.uid,
            'name': self.name,
            'url': self.url,
            'username': self.username,
            'password': self.password,
            'local_storage': self.local_storage,
        }

    @classmethod
    def from_dict(cls, d):
        return cls(
            d.get('uid', ''),
            d['name'],
            d['url'],
            d['username'],
            d['password'],
            d.get('local_storage', ''),
        )
