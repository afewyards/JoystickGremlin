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


import os
from PyQt5 import QtCore, QtGui, QtWidgets
from xml.etree import ElementTree

from action_plugins.common import AbstractAction, AbstractActionWidget, \
    NoKeyboardPushButton, parse_bool
from gremlin.common import UiInputType
import gremlin.macro


class MacroListModel(QtCore.QAbstractListModel):

    """Model representing a Macro.

    This model supports model modification.
    """

    def __init__(self, parent=None):
        """Creates a new instance.

        :param parent parent widget
        """
        QtCore.QAbstractListModel.__init__(self, parent)

        self.entries = []

    def rowCount(self, parent=None):
        """Returns the number of rows in the model.

        :param parent the parent of the model
        :return number of rows in the model
        """
        return len(self.entries)

    def data(self, index, role):
        """Return the data of the index for the specified role.

        :param index the index into the model which is queried
        :param role the role for which the data is to be formatted
        :return data formatted for the given role at the given index
        """
        idx = index.row()
        if role == QtCore.Qt.DisplayRole and idx < len(self.entries):
            entry = self.entries[idx]
            if isinstance(entry, gremlin.macro.Macro.Pause):
                return "Pause for {:.4f} s".format(entry.duration)
            elif isinstance(entry, gremlin.macro.Macro.KeyAction):
                return "{} key {}".format(
                    "Press" if entry.is_pressed else "Release",
                    entry.key.name
                )
            else:
                return entry

    def setData(self, index, value, role):
        """"Sets the data at the given index and role to the provided value.

        :param index the index at which to set the new value
        :param value the value to set
        :param role the role for which to set the data
        """
        if index.isValid and role == QtCore.Qt.EditRole:
            idx = index.row()
            entry = self.entries[idx]
            if isinstance(entry, gremlin.macro.Macro.Pause):
                try:
                    entry.duration = float(value)
                except ValueError:
                    pass
            self.dataChanged.emit(index, index)
            return True
        return False

    def flags(self, index):
        """Returns the flags of an item.

        Only Macro.Pause items are editable currently

        :param index the index of the item for which to return the flags
        :return flags of an item
        """
        if not index.isValid():
            return QtCore.Qt.ItemIsEnabled

        if len(self.entries) == 0:
            return QtCore.QAbstractItemModel.flags(self, index)

        entry = self.entries[index.row()]
        if isinstance(entry, gremlin.macro.Macro.Pause):
            return QtCore.QAbstractItemModel.flags(self, index) | \
                QtCore.Qt.ItemIsEditable
        return QtCore.QAbstractItemModel.flags(self, index)

    def remove_entry(self, index):
        """Removes the entry at the provided index.

        If the index is invalid nothing happens.

        :param index the index of the entry to remove
        """
        if 0 <= index < len(self.entries):
            self.beginRemoveRows(self.index(0, 0), index, index)
            del self.entries[index]
            self.endRemoveRows()

    def add_entry(self, index, entry):
        """Adds the given entry at the provided index.

        :param index the index at which to insert the new entry
        :param entry the entry to insert
        """
        self.beginInsertRows(QtCore.QModelIndex(), index, index)
        self.entries.insert(index + 1, entry)
        self.endInsertRows()

    def swap(self, id1, id2):
        """Swaps the entries pointed to by the two indices.

        If either of the indices is invalid nothing happens.

        :param id1 first index
        :param id2 second index
        """
        if -1 < id1 < len(self.entries) and -1 < id2 < len(self.entries):
            self.entries[id1], self.entries[id2] = \
                self.entries[id2], self.entries[id1]
            self.dataChanged.emit(self.index(id1, 0), self.index(id2, 0))


class MacroWidget(AbstractActionWidget):

    """Widget which allows creating and editing of macros."""

    def __init__(self, profile_data, vjoy_devices, change_cb, parent=None):
        AbstractActionWidget.__init__(
            self,
            profile_data,
            vjoy_devices,
            change_cb,
            parent
        )
        assert(isinstance(profile_data, Macro))

    def _setup_ui(self):
        self.model = MacroListModel()
        self._connect_signals()

        self.list_view = QtWidgets.QListView()
        self.list_view.setModel(self.model)
        self.list_view.setCurrentIndex(self.model.index(0, 0))

        gfx_path = os.path.join(
            os.path.dirname(os.path.realpath(__file__)),
            "gfx"
        )

        # Buttons
        self.button_layout = QtWidgets.QHBoxLayout()
        self.button_up = QtWidgets.QPushButton(
            QtGui.QIcon("gfx/list_up"), "Up"
        )
        self.button_up.clicked.connect(self._up_cb)
        self.button_down = QtWidgets.QPushButton(
            QtGui.QIcon("gfx/list_down"), "Down"
        )
        self.button_delete = QtWidgets.QPushButton(
            QtGui.QIcon("gfx/list_delete"), "Delete"
        )
        self.button_delete.clicked.connect(self._delete_cb)
        self.button_down.clicked.connect(self._down_cb)
        record_icon = QtGui.QIcon()
        record_icon.addPixmap(
            QtGui.QPixmap("{}/macro_record".format(gfx_path)),
            QtGui.QIcon.Normal
        )
        record_icon.addPixmap(
            QtGui.QPixmap("{}/macro_record_on".format(gfx_path)),
            QtGui.QIcon.Active,
            QtGui.QIcon.On
        )

        self.button_record = NoKeyboardPushButton(record_icon, "Record")
        self.button_record.setCheckable(True)
        self.button_record.clicked.connect(self._record_cb)
        self.button_pause = QtWidgets.QPushButton(
            QtGui.QIcon("{}/macro_add_pause".format(gfx_path)), "Add Pause"
        )
        self.button_pause.clicked.connect(self._pause_cb)
        self.button_layout.addWidget(self.button_up)
        self.button_layout.addWidget(self.button_down)
        self.button_layout.addWidget(self.button_delete)
        self.button_layout.addWidget(self.button_record)
        self.button_layout.addWidget(self.button_pause)

        self.main_layout.addWidget(self.list_view)
        self.main_layout.addLayout(self.button_layout)

    def key_event_cb(self, event):
        action = gremlin.macro.Macro.KeyAction(
            gremlin.macro.key_from_code(
                event.identifier[0],
                event.identifier[1]
            ),
            event.is_pressed
        )
        self._append_entry(action)

    def to_profile(self):
        self.action_data.sequence = self.model.entries
        self.action_data.is_valid = self.model.rowCount() > 0

    def initialize_from_profile(self, action_data):
        # Store profile data
        self.action_data = action_data

        # Disconnect from all update signals before we load a profile in
        # to prevent export spam
        self._disconnect_signals()

        # Replace existing model with an empty one which is filled from
        # the profile data.
        # This needs to stay otherwise the code breaks.
        self.model = MacroListModel()
        self.list_view.setModel(self.model)
        for i, entry in enumerate(action_data.sequence):
            self.model.add_entry(i, entry)
        self._connect_signals()

    def _up_cb(self):
        """Moves the currently selected entry upwards."""
        idx = self.list_view.currentIndex().row()
        if idx > 0:
            self._swap_entries(idx, idx-1)

    def _down_cb(self):
        """Moves the currently selected entry downwards."""
        idx = self.list_view.currentIndex().row()
        if idx < len(self.model.entries)-1:
            self._swap_entries(idx, idx+1)

    def _record_cb(self):
        """Starts the recording of key presses."""
        if self.button_record.isChecked():
            # Record keystrokes
            self._recording = True
            el = gremlin.event_handler.EventListener()
            el.keyboard_event.connect(self.key_event_cb)
        else:
            # Stop recording keystrokes
            self._recording = False
            el = gremlin.event_handler.EventListener()
            el.keyboard_event.disconnect(self.key_event_cb)

    def _pause_cb(self):
        """Adds a pause macro action to the list."""
        self._append_entry(gremlin.macro.Macro.Pause(0.01))

    def _delete_cb(self):
        """Callback executed when the delete button is pressed."""
        idx = self.list_view.currentIndex().row()
        self.model.remove_entry(idx)
        new_idx = min(len(self.model.entries), max(0, idx - 1))
        self.list_view.setCurrentIndex(self.model.index(new_idx, 0))

    def _swap_entries(self, id1, id2):
        """Swaps the two model items with the given indices.

        :param id1 the first index
        :param id2 the second index
        """
        self.model.swap(id1, id2)
        self.list_view.setCurrentIndex(self.model.index(id2, 0))

    def _append_entry(self, entry):
        """Adds the given entry after current selection.

        :param entry the entry to add to the model
        """
        cur_index = self.list_view.currentIndex().row()
        self.model.add_entry(
            cur_index,
            entry
        )
        self.list_view.setCurrentIndex(
            self.model.index(cur_index+1, 0)
        )

    def _connect_signals(self):
        """Connects model signals to the change callback."""
        self.model.dataChanged.connect(self.change_cb)
        self.model.rowsMoved.connect(self.change_cb)
        self.model.rowsInserted.connect(self.change_cb)
        self.model.rowsRemoved.connect(self.change_cb)

    def _disconnect_signals(self):
        """Disconnects model signals from the notify function."""
        self.model.dataChanged.disconnect()
        self.model.rowsMoved.disconnect()
        self.model.rowsInserted.disconnect()
        self.model.rowsRemoved.disconnect()


class Macro(AbstractAction):

    """Represents a macro action."""

    name = "Macro"
    tag = "macro"
    widget = MacroWidget
    input_types = [
        UiInputType.JoystickAxis,
        UiInputType.JoystickButton,
        UiInputType.JoystickHat,
        UiInputType.Keyboard
    ]
    callback_params = []

    def __init__(self, parent):
        """Creates a new Macro instance.

        :param parent the parent profile.ItemAction of this macro action
        """
        AbstractAction.__init__(self, parent)
        self.sequence = []

    def icon(self):
        return "{}/icon.png".format(os.path.dirname(os.path.realpath(__file__)))

    def _parse_xml(self, node):
        """Parses the XML node corresponding to a macro action.

        :param node the XML node to parse.
        """
        self.sequence = []
        for child in node:
            if child.tag == "key":
                key_action = gremlin.macro.Macro.KeyAction(
                    gremlin.macro.key_from_code(
                        int(child.get("scan_code")),
                        parse_bool(child.get("extended"))
                    ),
                    parse_bool(child.get("press"))
                )
                self.sequence.append(key_action)
            elif child.tag == "pause":
                self.sequence.append(
                    gremlin.macro.Macro.Pause(float(child.get("duration")))
                )

    def _generate_xml(self):
        """Generates a XML node corresponding to this object.

        :return XML node representing the object's data
        """
        node = ElementTree.Element("macro")
        for entry in self.sequence:
            if isinstance(entry, gremlin.macro.Macro.KeyAction):
                action_node = ElementTree.Element("key")
                action_node.set("scan_code", str(entry.key.scan_code))
                action_node.set("extended", str(entry.key.is_extended))
                action_node.set("press", str(entry.is_pressed))
                node.append(action_node)
            elif isinstance(entry, gremlin.macro.Macro.Pause):
                pause_node = ElementTree.Element("pause")
                pause_node.set("duration", str(entry.duration))
                node.append(pause_node)
        return node

    def _generate_code(self):
        """Generates the python code corresponding to this instance.

        :return python code executing this object's contents.
        """
        return self._code_generation(
            "macro",
            {
                "entry": self,
                "macro_name": "macro_{:04d}".format(Macro.next_code_id),
                "gremlin": gremlin
            }
        )

version = 1
name = "macro"
create = Macro
