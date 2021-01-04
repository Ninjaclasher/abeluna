# Abeluna
A simple GUI to-do/task manager with CalDAV support. In theory, Abeluna should support any CalDAV server, but currently only [Nextcloud](https://apps.nextcloud.com/apps/tasks) and [https://radicale.org/3.0.html](Radicale) are tested.

## Screenshots

![Main window](https://i.imgur.com/8WP2OPj.png)

![Settings window](https://i.imgur.com/d29WsE2.png)

![Custom theme main window](https://i.imgur.com/rZWjWt2.png)

## Installation

### From PyPI
First, install two packages, `libnotify` and `gobject-introspection`. On other distributions besides Arch Linux, these names may be different. For example, on Debian-based systems, `gobject-introspection` is `libgirepository1.0-dev`.

```sh
$ pip install abeluna
$ abeluna
```
