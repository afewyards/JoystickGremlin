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

import importlib
import logging
import os
import re
import sys
import threading
import time

from mako.template import Template
from PyQt5 import QtCore, QtWidgets
import sdl2

import gremlin
from gremlin import error, fsm


# Flag indicating that multiple physical devices with the same name exist
g_duplicate_devices = False


# Symbol used for the function that will compute the device id. This
# will change based on whether or not multiple devices of the same
# type are connected
device_id = None


# Table storing which modules have been imported already
g_loaded_modules = {}


class SingletonDecorator:

    """Decorator turning a class into a singleton."""

    def __init__(self, klass):
        self.klass = klass
        self.instance = None

    def __call__(self, *args, **kwargs):
        if self.instance is None:
            self.instance = self.klass(*args, **kwargs)
        return self.instance


class FileWatcher(QtCore.QObject):

    """Watches files for change."""

    # Signal emitted when the watched file is modified
    file_changed = QtCore.pyqtSignal(str)

    def __init__(self, file_names, parent=None):
        """Creates a new instance.

        :param file_names list of files to watch
        :param parent parent of this object
        """
        QtCore.QObject.__init__(self, parent)
        self._file_names = file_names
        self._last_size = {}
        for fname in self._file_names:
            self._last_size[fname] = 0

        self._is_running = True
        self._watch_thread = threading.Thread(target=self._monitor)
        self._watch_thread.start()

    def stop(self):
        """Terminates the thread monitoring files."""
        self._is_running = False
        if self._watch_thread.is_alive():
            self._watch_thread.join()

    def _monitor(self):
        """Continuously monitors files for change."""
        while self._is_running:
            for fname in self._file_names:
                stats = os.stat(fname)
                if stats.st_size != self._last_size[fname]:
                    self._last_size[fname] = stats.st_size
                    self.file_changed.emit(fname)
            time.sleep(1)


class JoystickDeviceData(object):

    """Represents data about a joystick like input device."""

    def __init__(self, device):
        """Initializes the device data based on the given device.

        :param device pyGame joystick object
        """
        self._hardware_id = get_device_guid(device)
        self._windows_id = sdl2.SDL_JoystickInstanceID(device)
        name_object = sdl2.SDL_JoystickName(device)
        if name_object is None:
            self._name = "Unknown device"
            logging.getLogger("system").error(
                "Encountered an invalid device name"
            )
        else:
            self._name = name_object.decode("utf-8")
        self._is_virtual = self._name == "vJoy Device"
        self._axes = sdl2.SDL_JoystickNumAxes(device)
        self._buttons = sdl2.SDL_JoystickNumButtons(device)
        self._hats = sdl2.SDL_JoystickNumHats(device)
        self._vjoy_id = 0

    @property
    def hardware_id(self):
        return self._hardware_id

    @property
    def windows_id(self):
        return self._windows_id

    @property
    def name(self):
        return self._name

    @property
    def is_virtual(self):
        return self._is_virtual

    @property
    def axes(self):
        return self._axes

    @property
    def buttons(self):
        return self._buttons

    @property
    def hats(self):
        return self._hats

    @property
    def vjoy_id(self):
        return self._vjoy_id


class AxisButton(object):

    def __init__(self, lower_limit, upper_limit):
        self._lower_limit = min(lower_limit, upper_limit)
        self._upper_limit = max(lower_limit, upper_limit)
        self.callback = None
        self._fsm = self._initialize_fsm()

    def _initialize_fsm(self):
        states = ["up", "down"]
        actions = ["press", "release"]
        transitions = {
            ("up", "press"): fsm.Transition(self._press, "down"),
            ("up", "release"): fsm.Transition(self._noop, "up"),
            ("down", "release"): fsm.Transition(self._release, "up"),
            ("down", "press"): fsm.Transition(self._noop, "down")
        }
        return fsm.FiniteStateMachine("up", states, actions, transitions)

    def process(self, value, callback):
        self.callback = callback
        if self._lower_limit <= value <= self._upper_limit:
            self._fsm.perform("press")
        else:
            self._fsm.perform("release")

    def _press(self):
        self.callback(True)

    def _release(self):
        self.callback(False)

    def _noop(self):
        pass

    @property
    def is_pressed(self):
        return self._fsm.current_state == "down"


def joystick_devices():
    """Returns the list of joystick like devices.

    :return list containing information about all joystick like devices
    """
    devices = []
    # Get all connected devices
    for i in range(sdl2.SDL_NumJoysticks()):
        joy = sdl2.SDL_JoystickOpen(i)
        if joy is None:
            logging.getLogger("system").error(
                "Invalid joystick device at id {}".format(i)
            )
        else:
            devices.append(JoystickDeviceData(joy))
    # Create hashes based on number of inputs for each virtual device. As we
    # absolutely need to be able to assign the SDL device to the correct
    # vJoy device we will not proceed if this mapping cannot be made without
    # ambiguity.
    vjoy_lookup = {}
    for i, dev in enumerate(devices):
        if not dev.is_virtual:
            continue
        hash_value = (dev.axes, dev.buttons, dev.hats)
        if hash_value in vjoy_lookup:
            raise gremlin.error.GremlinError(
                "Indistinguishable vJoy devices present"
            )
        vjoy_lookup[hash_value] = i

    # For virtual joysticks query them id by id until we have found all active
    # devices
    vjoy_proxy = gremlin.input_devices.VJoyProxy()

    # Try each possible vJoy device and if it exists find the matching device
    # as detected by SDL
    for i in range(1, 17):
        try:
            vjoy_dev = vjoy_proxy[i]
            hash_value = (
                # This is needed as we have two names for each axis
                int(vjoy_dev.axis_count / 2),
                vjoy_dev.button_count,
                vjoy_dev.hat_count
            )
            if hash_value in vjoy_lookup:
                devices[vjoy_lookup[hash_value]]._vjoy_id = vjoy_dev.vjoy_id

            if hash_value not in vjoy_lookup:
                raise gremlin.error.GremlinError(
                    "Unable to match vJoy device to windows device data"
                )
        except gremlin.error.VJoyError:
            pass

    # Reset all devices so we don't hog the ones we aren't actually using
    gremlin.input_devices.VJoyProxy.reset()

    return devices


def axis_calibration(value, minimum, center, maximum):
    """Returns the calibrated value for a normal style axis.

    :param value the raw value to process
    :param minimum the minimum value of the axis
    :param center the center value of the axis
    :param maximum the maximum value of the axis
    :return the calibrated value in [-1, 1] corresponding to the
        provided raw value
    """
    value = clamp(value, minimum, maximum)
    if value < center:
        return (value - center) / float(center - minimum)
    else:
        return (value - center) / float(maximum - center)


def slider_calibration(value, minimum, maximum):
    """Returns the calibrated value for a slider type axis.

    :param value the raw value to process
    :param minimum the minimum value of the axis
    :param maximum the maximum value of the axis
    :return the calibrated value in [-1, 1] corresponding to the
        provided raw value
    """
    value = clamp(value, minimum, maximum)
    return (value - minimum) / float(maximum - minimum) * 2.0 - 1.0


def create_calibration_function(minimum, center, maximum):
    """Returns a calibration function appropriate for the provided data.

    :param minimum the minimal value ever reported
    :param center the value in the neutral position
    :param maximum the maximal value ever reported
    :return function which returns a value in [-1, 1] corresponding
        to the provided raw input value
    """
    if minimum == center or maximum == center:
        return lambda x: slider_calibration(x, minimum, maximum)
    else:
        return lambda x: axis_calibration(x, minimum, center, maximum)


def script_path():
    """Returns the path to the scripts location.

    :return path to the scripts location
    """
    return os.path.dirname(os.path.realpath(sys.argv[0]))


def display_error(msg):
    """Displays the provided error message to the user.

    :param msg the error message to display
    """
    box = QtWidgets.QMessageBox(
        QtWidgets.QMessageBox.Critical,
        "Error",
        msg,
        QtWidgets.QMessageBox.Ok
    )
    box.exec()


def log(msg):
    """Logs the provided message to the user log file.

    :param msg the message to log
    """
    logging.getLogger("user").debug(str(msg))


def format_name(name):
    """Returns the name formatted as valid python variable name.

    :param name the name to format
    :return name formatted to be suitable as a python variable name
    """
    return re.sub("[^A-Za-z]", "", name.lower()[0]) + \
        re.sub("[^A-Za-z0-9]", "", name.lower()[1:])


def valid_python_identifier(name):
    """Returns whether a given name is a valid python identifier.

    :param name the name to check for validity
    :return True if the name is a valid identifier, False otherwise
    """
    return re.match("^[^\d\W]\w*\Z", name) is not None


def clamp(value, min_val, max_val):
    """Returns the value clamped to the provided range.

    :param value the input value
    :param min_val minimum value
    :param max_val maximum value
    :return the input value clamped to the provided range
    """
    if min_val > max_val:
        min_val, max_val = max_val, min_val
    return min(max_val, max(min_val, value))


def get_device_guid(device):
    """Returns the GUID of the provided device.

    :param device SDL2 joystick device for which to get the GUID
    :return GUID for the provided device
    """
    vendor_id = sdl2.SDL_JoystickGetVendor(device)
    product_id = sdl2.SDL_JoystickGetProduct(device)

    return (vendor_id << 16) + product_id


def mode_list(node):
    """Returns a list of all modes based on the given node.

    :param node a node from a profile tree
    :return list of mode names
    """
    # Get profile root node
    parent = node
    while parent.parent is not None:
        parent = parent.parent
    assert(type(parent) == gremlin.profile.Profile)
    # Generate list of modes
    mode_names = []
    for device in parent.devices.values():
        mode_names.extend(device.modes.keys())

    return sorted(list(set(mode_names)), key=lambda x: x.lower())


def hat_tuple_to_index(direction):
    """Returns the numerical representation of the hat direction tuple.

    :param direction the direction represented via a tuple
    :return integer representing the direction
    """
    lookup = {
        ( 0,  0): 0,
        ( 0,  1): 1,
        ( 1,  1): 2,
        ( 1,  0): 3,
        ( 1, -1): 4,
        ( 0, -1): 5,
        (-1, -1): 6,
        (-1,  0): 7,
        (-1,  1): 8,
    }
    return lookup[direction]


def userprofile_path():
    """Returns the path to the user's profile folder, %userprofile%."""
    return os.path.abspath(os.path.join(
        os.getenv("userprofile"),
        "Joystick Gremlin")
    )


def setup_userprofile():
    """Initializes the data folder in the user's profile folder."""
    folder = userprofile_path()
    if not os.path.exists(folder):
        try:
            os.mkdir(folder)
        except Exception as e:
            raise error.GremlinError(
                "Unable to create data folder: {}".format(str(e))
            )
    elif not os.path.isdir(folder):
        raise error.GremlinError("Data folder exists but is not a folder")


def device_id_duplicates(device):
    """Returns a unique id for the provided device.

    This function is intended to be used when device of identical type
    are present.

    :param device the object with device related information
    :return unique identifier of this device
    """
    return device.hardware_id, device.windows_id


def device_id_unique(device):
    """Returns a unique id for the provided device.

    This function is intended to be used when all devices are
    distinguishable by their hardware id.

    :param device the object with device related information
    :return unique identifier of this device
    """
    return device.hardware_id


def setup_duplicate_joysticks():
    """Detects if multiple identical devices are connected and performs
    appropriate setup.
    """
    global g_duplicate_devices
    global device_id
    devices = joystick_devices()

    # Check if we have duplicate items
    entries = [dev.hardware_id for dev in devices]
    g_duplicate_devices = len(entries) != len(set(entries))

    # Create appropriate device_id generator
    if g_duplicate_devices:
        device_id = device_id_duplicates
    else:
        device_id = device_id_unique


def extract_ids(dev_id):
    """Returns hardware and windows id of a device_id.

    Only if g_duplicate_devices is true will there be a windows id
    present. If it is not present -1 will be returned

    :param dev_id the device_id from which to extract the individual
        ids
    :return hardware_id and windows_id
    """
    if g_duplicate_devices:
        return dev_id[0], dev_id[1]
    else:
        return dev_id, -1


def get_device_id(hardware_id, windows_id):
    """Returns the correct device id given both hardware and windows id.

    :param hardware_id the hardware id of the device
    :param windows_id the windows id of the device
    :return correct combination of hardware and windows id
    """
    if g_duplicate_devices:
        return hardware_id, windows_id
    else:
        return hardware_id


def clear_layout(layout):
    """Removes all items from the given layout.

    :param layout the layout from which to remove all items
    """
    while layout.count() > 0:
        child = layout.takeAt(0)
        if child.layout():
            clear_layout(child.layout())
        elif child.widget():
            child.widget().hide()
            child.widget().deleteLater()
        layout.removeItem(child)


def text_substitution(text):
    """Returns the provided text after running text substitution on it.

    :param text the text to substitute parts of
    :return original text with parts substituted
    """
    eh = gremlin.event_handler.EventHandler()
    tpl = Template(text)
    return tpl.render(
        current_mode=eh.active_mode
    )


def convert_sdl_hat(value):
    """Converts the SDL hat representation to the Gremlin one.

    :param value the hat state representation as used by SDL
    :return the hat representation corresponding to the SDL one
    """
    direction = [0, 0]
    if value & sdl2.SDL_HAT_UP:
        direction[1] = 1
    elif value & sdl2.SDL_HAT_DOWN:
        direction[1] = -1
    if value & sdl2.SDL_HAT_RIGHT:
        direction[0] = 1
    elif value & sdl2.SDL_HAT_LEFT:
        direction[0] = -1
    return tuple(direction)


def load_module(name):
    """Imports  the given module.

    :param name the name of the module
    :return the loaded module
    """
    global g_loaded_modules
    if name in g_loaded_modules:
        importlib.reload(g_loaded_modules[name])
    else:
        g_loaded_modules[name] = importlib.import_module(name)
    return g_loaded_modules[name]
