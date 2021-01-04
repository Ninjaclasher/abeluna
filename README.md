Abeluna [![Build Status](https://github.com/Ninjaclasher/abeluna/workflows/build/badge.svg)](https://github.com/Ninjaclasher/abeluna/actions/)
=====

A simple GUI to-do/task manager with CalDAV support. In theory, Abeluna should support any CalDAV server, but currently only [Nextcloud](https://apps.nextcloud.com/apps/tasks) and [Radicale](https://radicale.org/3.0.html) are tested.

The goal of this application is to become a desktop version of Nextcloud's Tasks app. As such, not all functionality in the [icalendar's VTODO](https://icalendar.org/iCalendar-RFC-5545/3-6-2-to-do-component.html) are supported, only those that are used by Nextcloud. On the other hand, there some non-standard fields used by Nextcloud that are supported by Abeluna, such as the ability to hide subtasks.

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

### AUR
There are plans to add Abeluna to the AUR, but it has not been added yet.

## Usage
```sh
$ abeluna
```

In the GUI, calendars can be added through `Settings > Calendar settings`. General settings, such as the timezone and synchronization schedule can be accessed through `Settings > General settings`.

## Future Plans
 - Support for desktop notifications.
 - Support for recurring tasks.
 - Add common keyboard shortcuts.
