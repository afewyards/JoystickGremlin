# -*- coding: utf-8; -*-

# Copyright (C) 2015 - 2016 Lionel Ott
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.

import json
import time
import os

from PyQt5 import QtCore

import gremlin.util


@gremlin.util.SingletonDecorator
class Configuration(object):

    """Responsible for loading and saving configuration data."""

    def __init__(self):
        """Creates a new instance, loading the current configuration."""
        self._data = {}
        self._last_reload = None
        self.reload()

        self.watcher = QtCore.QFileSystemWatcher([
            os.path.join(gremlin.util.userprofile_path(), "config.json")
        ])
        self.watcher.fileChanged.connect(self.reload)

    def reload(self):
        """Loads the configuration file's content."""
        if self._last_reload is not None and \
                time.time() - self._last_reload < 1:
            return

        fname = os.path.join(gremlin.util.userprofile_path(), "config.json")
        # Attempt to load the configuration file if this fails set
        # default empty values.
        load_successful = False
        if os.path.isfile(fname):
            with open(fname) as hdl:
                try:
                    decoder = json.JSONDecoder()
                    self._data = decoder.decode(hdl.read())
                    load_successful = True
                except ValueError:
                    pass
        if not load_successful:
            self._data = {
                "calibration": {},
                "profiles": {},
                "last_mode": {}
            }

        # Ensure required fields are present and if they are missing
        # add empty ones.
        for field in ["calibration", "profiles", "last_mode"]:
            if field not in self._data:
                self._data[field] = {}

        # Save all data
        self._last_reload = time.time()
        self.save()

    def save(self):
        """Writes the configuration file to disk."""
        fname = os.path.join(gremlin.util.userprofile_path(), "config.json")
        with open(fname, "w") as hdl:
            encoder = json.JSONEncoder(
                sort_keys=True,
                indent=4
            )
            hdl.write(encoder.encode(self._data))

    def set_calibration(self, dev_id, limits):
        """Sets the calibration data for all axes of a device.

        :param dev_id the id of the device
        :param limits the calibration data for each of the axes
        """
        hid, wid = gremlin.util.extract_ids(dev_id)
        identifier = str(hid) if wid == -1 else "{}_{}".format(hid, wid)
        if identifier in self._data["calibration"]:
            del self._data["calibration"][identifier]
        self._data["calibration"][identifier] = {}

        for i, limit in enumerate(limits):
            if limit[2] - limit[0] == 0:
                continue
            axis_name = "axis_{}".format(i)
            self._data["calibration"][identifier][axis_name] = [
                limit[0], limit[1], limit[2]
            ]
        self.save()

    def get_calibration(self, dev_id, axis_id):
        """Returns the calibration data for the desired axis.

        :param dev_id the id of the device
        :param axis_id the id of the desired axis
        :return the calibration data for the desired axis
        """
        hid, wid = gremlin.util.extract_ids(dev_id)
        identifier = str(hid) if wid == -1 else "{}_{}".format(hid, wid)
        axis_name = "axis_{}".format(axis_id)
        if identifier not in self._data["calibration"]:
            return [-32768, 0, 32767]
        if axis_name not in self._data["calibration"][identifier]:
            return [-32768, 0, 32767]

        return self._data["calibration"][identifier][axis_name]

    def get_executable_list(self):
        """Returns a list of all executables with associated profiles.

        :return list of executable paths
        """
        return list(self._data["profiles"].keys())

    def remove_profile(self, exec_path):
        """Removes the executable from the configuration.

        :param exec_path the path to the executable to remove
        """
        if self._has_profile(exec_path):
            del self._data["profiles"][exec_path]
            self.save()

    def get_profile(self, exec_path):
        """Returns the path to the profile associated with the given
        executable.

        :param exec_path the path to the executable for which to
            return the profile
        :return profile associated with the given executable
        """
        return self._data["profiles"].get(exec_path, None)

    def set_profile(self, exec_path, profile_path):
        """Stores the executable and profile combination.

        :param exec_path the path to the executable
        :param profile_path the path to the associated profile
        """
        self._data["profiles"][exec_path] = profile_path
        self.save()

    def set_last_mode(self, profile_path, mode_name):
        """Stores the last active mode of the given profile.

        :param profile_path profile path for which to store the mode
        :param mode_name name of the active mode
        """
        if profile_path is None or mode_name is None:
            return
        self._data["last_mode"][profile_path] = mode_name
        self.save()

    def get_last_mode(self, profile_path):
        """Returns the last active mode of the given profile.

        :param profile_path profile path for which to return the mode
        :return name of the mode if present, None otherwise
        """
        return self._data["last_mode"].get(profile_path, None)

    def _has_profile(self, exec_path):
        """Returns whether or not a profile exists for a given executable.

        :param exec_path the path to the executable
        :return True if a profile exists, False otherwise
        """
        return exec_path in self._data["profiles"]

    @property
    def last_profile(self):
        return self._data.get("last_profile", None)

    @last_profile.setter
    def last_profile(self, value):
        self._data["last_profile"] = value
        self.save()

    @property
    def autoload_profiles(self):
        return self._data.get("autoload_profiles", False)

    @autoload_profiles.setter
    def autoload_profiles(self, value):
        if type(value) == bool:
            self._data["autoload_profiles"] = value
            self.save()

    @property
    def highlight_input(self):
        return self._data.get("highlight_input", True)

    @highlight_input.setter
    def highlight_input(self, value):
        if type(value) == bool:
            self._data["highlight_input"] = value
            self.save()

    @property
    def mode_change_message(self):
        return self._data.get("mode_change_message", False)

    @mode_change_message.setter
    def mode_change_message(self, value):
        self._data["mode_change_message"] = bool(value)

    @property
    def close_to_tray(self):
        return self._data.get("close_to_tray", False)

    @close_to_tray.setter
    def close_to_tray(self, value):
        self._data["close_to_tray"] = bool(value)

    @property
    def start_minimized(self):
        return self._data.get("start_minimized", False)

    @start_minimized.setter
    def start_minimized(self, value):
        self._data["start_minimized"] = bool(value)
