from PySide2 import QtWidgets, QtCore, QtGui
import re
import os
import hou
import webbrowser
import json

version = hou.applicationVersion()
icon_path = [hou.expandString("$HOME"),"houdini{}.{}".format(version[0], version[1]),"config","Icons","houdini_bookmarks_icons"]
icon_path = [hou.expandString("$HBM"),"config","Icons","houdini_bookmarks_icons"]
icon_path = os.path.join(*icon_path)

class MainView(QtWidgets.QFrame):
    def __init__(self, panel = None):
        super(MainView, self).__init__()
        self.panel = panel
        self.icons = self.load_icons(["add.svg", "jump.svg", "show_parms.svg", "file.svg", "delete.svg", "blank.svg", "internet.svg"])
        self.setup_widgets()
        self.setup_layouts()
        self.setup_scene_callbacks()
        self.load_bookmarks_from_session()


    def mousePressEvent(self, event):
        return False

    def setup_widgets(self):
        #splitter between top and bottom widgets
        self.splitter = QtWidgets.QSplitter(QtCore.Qt.Vertical)
        self.splitter.setHandleWidth(1)

        #top Widgets
        self.top_widget = QtWidgets.QWidget()
        self.tab_widget = QtWidgets.QTabWidget()
        self.tab_widget.currentChanged.connect(self.update_description)
        self.tab_bar = TabBar()
        self.tab_widget.setTabBar(self.tab_bar)

        #corner widget setup
        self.corner_widget = QtWidgets.QWidget()
        self.corner_widget.setContentsMargins(0, 0, 0, 0)
        self.add_tab_button = QtWidgets.QPushButton()
        self.add_tab_button.setIcon(QtGui.QPixmap(icon_path+"/add.svg"))
        self.add_tab_button.setIconSize(QtCore.QSize(13, 13))
        self.add_tab_button.setStyleSheet("QPushButton { border: none; }\
                                           QPushButton:pressed { border: 1px solid; }")
        self.add_tab_button.setMaximumWidth(20)
        self.add_tab_button.clicked.connect(lambda: self.add_tab())

        self.options_button = QtWidgets.QPushButton()
        self.options_button.setIcon(QtGui.QPixmap(icon_path+"/gear.svg"))
        self.options_button.setIconSize(QtCore.QSize(13, 13))
        self.options_button.setMaximumWidth(20)
        self.options_menu = QtWidgets.QMenu()
        self.options_button.setStyleSheet("QPushButton { border: none; }\
                                           QPushButton:pressed { border: 1px solid; }\
                                           QPushButton::menu-indicator { image: none; }")
        save_to_file_action = QtWidgets.QAction("Save to file", self.options_button)
        load_from_file_action = QtWidgets.QAction("Load from file", self.options_button)
        save_to_file_action.triggered.connect(self.save_to_file)
        load_from_file_action.triggered.connect(self.load_from_file)
        self.options_menu.addAction(save_to_file_action)
        self.options_menu.addAction(load_from_file_action)
        self.options_button.setMenu(self.options_menu)

        #default closable
        self.tab_widget.setTabsClosable(True)
        self.tab_widget.tabCloseRequested.connect(lambda index: self.close_tab(index))
        self.tab_bar.setStyleSheet("QTabBar::close-button { image: url("+(icon_path+"/delete.svg").replace("\\", "/")+"); }\
                                    QTabBar::close-button:hover { background: grey; }\
                                    QTabBar::close-button:pressed { border: 1px solid; }")

        self.tab_widget.setCornerWidget(self.corner_widget)

        #bottom widgets
        self.bottom_widget = QtWidgets.QWidget()
        self.item_path_label = QtWidgets.QLabel("")
        self.item_note = TextEdit()
        self.item_note.editingFinished.connect(self.update_item_note)
        self.copy_path_button = QtWidgets.QPushButton()
        self.copy_path_button.setIcon(QtGui.QPixmap(icon_path+"/copy.svg"))
        self.copy_path_button.setStyleSheet("QPushButton { border: none; }\
                                             QPushButton:pressed { border: 1px solid; }")
        self.copy_path_button.setFixedWidth(25)
        self.copy_path_button.clicked.connect(self.copy_to_clipboard)

        #add widgets to splitter
        self.splitter.addWidget(self.top_widget)
        self.splitter.addWidget(self.bottom_widget)
        self.splitter.setStretchFactor(0, 1)
        self.splitter.setStretchFactor(1, 0)

    def setup_layouts(self):
        #create layouts
        layout = QtWidgets.QVBoxLayout()
        layout.setContentsMargins(15,15,15,15)
        top_layout = QtWidgets.QVBoxLayout()
        top_layout.setContentsMargins(0,0,0,10)
        bottom_layout = QtWidgets.QVBoxLayout()
        bottom_layout.setContentsMargins(0,10,0,0)
        path_layout = QtWidgets.QHBoxLayout()
        corner_layout = QtWidgets.QHBoxLayout()
        corner_layout.setContentsMargins(0,0,0,0)

        #add widgets to layouts
        layout.addWidget(self.splitter)
        top_layout.addWidget(self.tab_widget)
        bottom_layout.addLayout(path_layout)
        bottom_layout.addWidget(self.item_note)
        path_layout.addWidget(self.item_path_label)
        path_layout.addWidget(self.copy_path_button)
        corner_layout.addWidget(self.add_tab_button)
        corner_layout.addWidget(self.options_button)

        #set widget layouts
        self.top_widget.setLayout(top_layout)
        self.bottom_widget.setLayout(bottom_layout)
        self.corner_widget.setLayout(corner_layout)
        self.setLayout(layout)

    def closeEvent(self, event):
        self.save_bookmarks_to_session("Widget Closed")
        for function in hou.hipFile.eventCallbacks():
            if function in [self.save_bookmarks_to_session, self.setup_bookmarks_for_loaded_hipFile]:
                hou.hipFile.removeEventCallback(function)

        for tab_index in range(self.tab_widget.count()):
            tree_view = self.tab_widget.widget(tab_index)
            self.remove_node_callbacks(tree_view)
        super(MainView, self).closeEvent(event)
    
    def remove_node_callbacks(self, tree_view):
        if tree_view is not None:
            for key in tree_view.node_callbacks:
                node = hou.nodeBySessionId(key)
                if node is not None:
                    for callback in tree_view.node_callbacks[key]:
                        node.removeEventCallback((callback[0], ), callback[1])

    def setup_node_callbacks(self):
        for tab_index in range(self.tab_widget.count()):
            tree_view = self.tab_widget.widget(tab_index)
            tree_model = tree_view.model()
            for item in iterate_items(tree_model.invisibleRootItem()):
                if item.data()["category"] == "node":
                    node = hou.node(item.data().get("path"))
                    data = item.data()
                    if node is None:
                        item.setText("DELETED")
                        color = (1,0,0)
                        item.setForeground(QtGui.QBrush(QtGui.QColor(255, 0, 0)))
                        data["color"] = color
                        data["category"] = "deleted_node"
                        item.setData(data)
                        continue
                    session_id = node.sessionId()
                    data["session_id"] = str(session_id)
                    item.setData(data)
                    tree_view.connect_node(node)

    def setup_scene_callbacks(self):
        hou.hipFile.addEventCallback(self.save_bookmarks_to_session)
        hou.hipFile.addEventCallback(self.setup_bookmarks_for_loaded_hipFile)

    def setup_bookmarks_for_loaded_hipFile(self, event_type):
        if event_type in [hou.hipFileEventType.AfterMerge, hou.hipFileEventType.AfterLoad]:
            for tab_index in reversed(range(self.tab_widget.count())):
                self.close_tab(tab_index, False)
            self.load_bookmarks_from_session()


    def save_to_file(self):
        choices = list()
        selection = [0]
        file_path = hou.ui.selectFile(title="Choose file location: ", pattern="*.json *.txt")
        file_path = hou.expandString(file_path)
        if os.path.splitext(file_path)[-1].lower() not in [".txt", ".json"]:
            file_path += ".json"
        if self.tab_widget.count() > 1:
            for index in range(self.tab_widget.count()):
                choices.append(self.tab_widget.tabBar().tabText(index))
            selection = hou.ui.selectFromList(choices, column_header="Tabs", message="Choose tabs to save:", width= 300, height=300)
        
        data = prepare_save_data(self.tab_widget, selection)
        
        with open(file_path, "w") as f:
            json.dump(data, f, indent=4)

    def save_bookmarks_to_session(self, event_type, *args, **kwargs):
        if event_type not in [hou.hipFileEventType.BeforeSave, hou.hipFileEventType.BeforeClear, "Widget Closed"]:
            return
        selection = range(self.tab_widget.count())
        data = prepare_save_data(self.tab_widget, selection)
        code = ("# HOUDINI BOOKMARKS START \n"
                        "def get_houdini_bookmarks_data(): \n"
                        "   return "+str(data)+"\n"
                        "# HOUDINI BOOKMARS END \n")

        old_data = hou.sessionModuleSource()
        old_data = re.sub("# HOUDINI BOOKMARKS START.*# HOUDINI BOOKMARS END", "", old_data, flags=re.DOTALL)
        if hasattr(hou.session, "get_houdini_bookmarks_data"):
            del(hou.session.get_houdini_bookmarks_data)
        hou.setSessionModuleSource(old_data + "\n" + code)
    
    def load_bookmarks_from_session(self):
        if hasattr(hou.session, "get_houdini_bookmarks_data"):
            data = hou.session.get_houdini_bookmarks_data()
            for tab in data["tabs"]:
                tab_widget = self.add_tab(tab["text"])
                self.create_child_items_from_data(tab_widget.model().invisibleRootItem(), tab["children"][0])

        if self.tab_widget.count() == 0:
            self.add_tab()
        self.setup_node_callbacks()

    def load_from_file(self):
        file_path = hou.ui.selectFile(title="Choose file to load: ", pattern="*.json *.txt")
        file_path = hou.expandString(file_path)
        if os.path.splitext(file_path)[-1].lower() not in [".txt", ".json"]:
            print("Can not read selected file.")
            return

        with open(file_path) as file:
            data = json.load(file)
        choices = list()
        for tab in data["tabs"]:
            choices.append(tab["text"])
        selected = hou.ui.selectFromList(choices, column_header="Tabs", message="Choose tabs to save:", width= 300, height=300)

        for index in selected:
            tab = data["tabs"][index]
            tab_widget = self.add_tab(tab["text"])
            self.create_child_items_from_data(tab_widget.model().invisibleRootItem(), tab["children"][0])
        self.setup_node_callbacks()

    def create_child_items_from_data(self, parent_item, data):
        for item_data in data:
            child_item = TreeItem()
            icon = QtGui.QPixmap(icon_path+"/blank.svg")
            if item_data.get("data").get("category") in ["node", "deleted_node"]:
                icon = hou.ui.createQtIcon(hou.nodeType(item_data.get("data").get("icon_type")).icon()).pixmap(50,50)
            elif item_data.get("data").get("category") == "webUrl":
                icon = QtGui.QPixmap(icon_path+"/internet.svg")
            elif item_data.get("data").get("category") == "folder":
                icon = QtGui.QPixmap(icon_path+"/folder.svg")
            elif item_data.get("data").get("category") == "file":
                file_path = item_data.get("data").get("path").replace("file:///", "")
                if os.path.exists(file_path):
                    file_info = QtCore.QFileInfo(file_path)
                    icon = QtWidgets.QFileIconProvider().icon(file_info)
                    size = QtCore.QSize(1,1)
                    icon = icon.pixmap(icon.actualSize(size))

            child_item.setIcon(QtGui.QPixmap(icon))
            child_item.setData(item_data.get("data"))
            child_item.setText(item_data.get("text"))

            color = item_data.get("data").get("color")
            if item_data.get("data").get("category") != "folder":
                child_item.setDropEnabled(False)
            brush = QtGui.QBrush()
            brush.setColor(QtGui.QColor(color[0]*255,color[1]*255,color[2]*255))
            child_item.setForeground(brush)
            parent_item.appendRow(child_item)
            if len(item_data["children"]) != 0:
                self.create_child_items_from_data(child_item, item_data["children"][0])

    def add_tab(self, tab_label = "New Tab"):
        new_tab = TreeView(self.tab_widget)
        new_tab.selectionModel().selectionChanged.connect(self.update_description)
        self.tab_widget.addTab(new_tab, tab_label)
        return new_tab

    def close_tab(self, index, add_tab_when_empty = True):
        self.remove_node_callbacks(self.tab_widget.widget(index))
        self.tab_widget.removeTab(index)
        if add_tab_when_empty:
            if self.tab_widget.count() == 0:
                self.add_tab()

    def copy_to_clipboard(self):
        clipboard = QtWidgets.QApplication.clipboard()
        clipboard.setText(self.item_path_label.text())
        if len(self.tab_widget.currentWidget().selectedIndexes()) != 0:
            index = self.tab_widget.currentWidget().selectedIndexes()[0]
            if self.tab_widget.currentWidget().model().itemFromIndex(index).data()["category"] in {"node", "stickynote"}:
                h_items = list()
                h_items.append(hou.item(self.item_path_label.text()))
                if h_items[0] is not None:
                    h_items[0].parent().copyItemsToClipboard(h_items)
    
    def update_description(self):
        try:
            index = self.tab_widget.currentWidget().selectedIndexes()[0]
            item = self.tab_widget.currentWidget().model().itemFromIndex(index)
            self.item_path_label.setText(item.data()["path"])
            self.item_note.setText(item.data()["note"])
        except:
            self.item_path_label.setText("")
            self.item_note.setText("")
    
    def update_item_note(self):
        try:
            index = self.tab_widget.currentWidget().selectedIndexes()[0]
            item = self.tab_widget.currentWidget().model().itemFromIndex(index)
            get_data = item.data()
            get_data["note"] = self.item_note.toPlainText()
            item.setData(get_data, QtCore.Qt.UserRole + 1)
            if item.data().get("category") == "node":
                node = hou.nodeBySessionId(int(item.data().get("session_id")))
                node.setComment(item.data().get("note"))
            elif item.data().get("category") == "stickynote":
                stickynote = hou.itemBySessionId(hou.networkItemType.StickyNote, int(item.data().get("session_id")))
                stickynote.setText(item.data().get("note"))
        except:
            return

    def load_icons(self, files):
        icons = {}
        for file in files:
            icons[os.path.splitext(file)[0]] = QtGui.QIcon(icon_path+"/"+file)
        return icons

class TabBar(QtWidgets.QTabBar):
    def __init__(self):
        super(TabBar, self).__init__()

    def mouseDoubleClickEvent(self, event):
        def finish_rename():
            self.setTabText(tab, line_edit.text())
            line_edit.deleteLater()
            
        tab = self.tabAt(event.pos())
        rect = self.tabRect(tab)
        top_margin = 3
        left_margin = 6
        line_edit = QtWidgets.QLineEdit(self)
        line_edit.show()
        line_edit.move(rect.left() + left_margin, rect.top() + top_margin)
        line_edit.resize(rect.width() - 2 * left_margin, rect.height() - 2 * top_margin)
        line_edit.setText(self.tabText(tab))
        line_edit.selectAll()
        line_edit.setFocus()
        line_edit.editingFinished.connect(finish_rename)

class TextEdit(QtWidgets.QTextEdit):
    """
    A TextEdit editor that sends editingFinished events
    when the text was changed and focus is lost.
    """
    editingFinished = QtCore.Signal()
    receivedFocus = QtCore.Signal()

    def __init__(self):
        super(TextEdit, self).__init__()
        self._changed = False
        self.setTabChangesFocus(True)
        self.textChanged.connect(self.handle_text_changed)
        self.setStyleSheet("QTextEdit { border: none; }")

    def focusInEvent(self, event):
        super(TextEdit, self).focusInEvent(event)
        self.receivedFocus.emit()

    def focusOutEvent(self, event):
        if self._changed:
            self.editingFinished.emit()
        super(TextEdit, self).focusOutEvent(event)
    
    def handle_text_changed(self):
        self._changed = True

    def setTextChanged(self, state=True):
        self._changed = state

    def setHtml(self, html):
        QtWidgets.QTextEdit.setHtml(self, html)
        self._changed = False
class TreeView(QtWidgets.QTreeView):
    def __init__(self, parent = None):
        super(TreeView, self).__init__(parent)
        self.setDragDropMode(QtWidgets.QAbstractItemView.InternalMove)
        self.setSelectionBehavior(QtWidgets.QTreeView.SelectRows)
        self.setSelectionMode(QtWidgets.QTreeView.ExtendedSelection)
        self.setItemDelegate(ItemDelegate(self))
        self.setModel(QtGui.QStandardItemModel())
        self.setAlternatingRowColors(True)
        self.setHeaderHidden(True)
        self.setContextMenuPolicy(QtCore.Qt.ActionsContextMenu)
        add_folder_action = QtWidgets.QAction(self)
        delete_selected_action = QtWidgets.QAction(self)
        add_folder_action.setText("Add Folder")
        delete_selected_action.setText("Delete Selected")
        add_folder_action.triggered.connect(self.add_folder)
        delete_selected_action.triggered.connect(self.delete_selected)
        self.addAction(add_folder_action)
        self.addAction(delete_selected_action)
        self.setStyleSheet("QTreeView { border: none; }")
        self.node_callbacks = {}
        self.icons = self.parent().parent().parent().parent().icons

    def add_folder(self):
        indices = self.selectedIndexes()
        item = self.model()
        if len(indices) > 0:
            index = indices[0]
            item = self.model().itemFromIndex(index)
            if item.data().get("category") != "folder":
                item = item.parent()
        if item is None:
            item = self.model()
        add_folder(item)            
    
    def delete_selected(self):
        indicies = self.selectedIndexes()
        indicies = sorted(indicies, key=lambda index: int(index.row()))
        for index in reversed(indicies):
            item = self.model().itemFromIndex(index)
            parent_item = index.model().itemFromIndex(index.parent())
            if parent_item is None:
                parent_item = index.model()
            if item.data()["category"] == "node":
                remove_callbacks = True
                session_id = int(item.data()["session_id"])
                for check_item in iterate_items(item.model().invisibleRootItem()):
                    if check_item is item or check_item.data()["category"] != "node":
                        continue
                    if int(check_item.data()["session_id"]) == session_id:
                        remove_callbacks = False
                        break
                if remove_callbacks:
                    node = hou.nodeBySessionId(session_id)
                    for callback in self.node_callbacks[session_id]:
                        node.removeEventCallback((callback[0], ), callback[1])
                    self.node_callbacks.pop(session_id)
            parent_item.takeRow(item.row())

    def dropEvent(self, event):
        if(event.source() == self): 
            super(TreeView, self).dropEvent(event)

        else:
            data_texts = list()
            if event.mimeData().hasUrls():
                data_texts = QtCore.QUrl.toStringList(event.mimeData().urls())
            else:
                data_texts = event.mimeData().text().split()
            try:
                for path in data_texts:
                    text = path
                    item = TreeItem()
                    item.setDropEnabled(False)
                    category = "node"
                    note = ""
                    session_id = ""
                    color = (0.8, 0.8, 0.8)
                    icon_type = ""
                    icon = self.icons["blank"]
                    if "file://" in text and event.mimeData().hasUrls():
                        text = QtCore.QUrl(path).fileName()
                        file_info = QtCore.QFileInfo(text)
                        icon = QtWidgets.QFileIconProvider().icon(file_info)
                        size = QtCore.QSize(1,1)
                        icon = icon.pixmap(icon.actualSize(size))
                        category = "file"
                    elif event.mimeData().hasUrls():
                        category = "webUrl"
                        icon = self.icons["internet"]
                    else:
                        h_item = hou.item(text)
                        h_session_id = h_item.sessionId()
                        h_item_type = h_item.networkItemType()
                        session_id = str(h_session_id)
                        valid_types = [hou.networkItemType.Node, hou.networkItemType.StickyNote, hou.networkItemType.NetworkBox]
                        if h_item_type == valid_types[0]:
                            category = "node"
                            node = hou.node(text)
                            self.connect_node(node)
                            note = node.comment()
                            color = node.color().rgb()
                            try:
                                icon = hou.ui.createQtIcon(node.type().icon())
                                icon_type = node.type().nameWithCategory()
                            except:
                                icon_type = hou.sopNodeTypeCategory().nodeTypes()["null"].nameWithCategory()
                                icon = hou.ui.createQtIcon(hou.sopNodeTypeCategory().nodeTypes()["null"].icon())
                        elif h_item_type == valid_types[1]:
                            category = "stickynote"
                            stickynote = hou.itemBySessionId(h_item_type, h_session_id)
                            note = stickynote.text()
                            color = stickynote.color().rgb()
                        elif h_item_type == valid_types[2]:
                            continue
                        else:
                            continue

                    item.setIcon(icon)
                    brush = QtGui.QBrush()
                    brush.setColor(QtGui.QColor(color[0]*255,color[1]*255,color[2]*255))
                    item.setForeground(brush)
                    data = {"note": note, "path": path, "category": category, "icon_type": icon_type, "session_id": session_id, "color": color}
                    item.setData(data, QtCore.Qt.UserRole + 1)
                    item.setText(text)
                    self.model().appendRow(item)
            except:
                return False
        event.accept()

    def connect_node(self, node):
        def save_set_callback(node, callback_function, event_type):
            add_key = True
            if node.sessionId() in self.node_callbacks:
                add_key = False
                if callback_function in [t[1] for t in self.node_callbacks[node.sessionId()]]:
                    return
            if add_key:
                self.node_callbacks[node.sessionId()] = list()
            node.addEventCallback((event_type, ), callback_function)
            callback_tuple = (event_type, callback_function)
            self.node_callbacks[node.sessionId()].append(callback_tuple)

        save_set_callback(node, self.update_item_path, hou.nodeEventType.NameChanged)
        save_set_callback(node, self.update_item_data, hou.nodeEventType.AppearanceChanged)
        save_set_callback(node, self.mark_node_as_deleted, hou.nodeEventType.BeingDeleted)
        
        parent = node.parent()
        while parent is not None and parent.path().count("/") > 1:
            save_set_callback(parent, self.update_item_path, hou.nodeEventType.NameChanged)
            parent = parent.parent()

    def update_item_data(self, node, change_type = None, **kwargs):
        if change_type not in [hou.appearanceChangeType.Color, hou.appearanceChangeType.Comment]:
            return
        for item in iterate_items(self.model().invisibleRootItem()):
            if item.data()["category"] == "node" and item.data()["session_id"] == str(node.sessionId()):
                color = node.color().rgb()
                brush = QtGui.QBrush()
                brush.setColor(QtGui.QColor(color[0]*255,color[1]*255,color[2]*255))
                item.setForeground(brush)
                data = item.data()
                data["color"] = color
                data["note"] = node.comment()
                item.setData(data)

    def update_item_path(self, node, **kwargs):
        for item in iterate_items(self.model().invisibleRootItem()):
            if item.data()["category"] == "node":
                item_node = hou.nodeBySessionId(int(item.data()["session_id"]))
                is_parent = hou.node(item_node.path())
                if item.data()["session_id"] == str(node.sessionId()) or is_parent:
                    data = item.data()
                    if item.text() == data["path"]:
                        item.setText(item_node.path())
                    data["path"] = item_node.path()
                    item.setData(data)

    def mark_node_as_deleted(self, node, **kwargs):
        for item in iterate_items(self.model().invisibleRootItem()):
            if item.data()["category"] == "node" and item.data()["session_id"] == str(node.sessionId()):
                self.node_callbacks.pop(node.sessionId(), None)
                item.setText("DELETED")
                color = (1,0,0)
                item.setForeground(QtGui.QBrush(QtGui.QColor(255, 0, 0)))
                data = item.data()
                data["color"] = color
                data["category"] = "deleted_node"
                item.setData(data)

class TreeItem(QtGui.QStandardItem):
    def __init__(self):
        super(TreeItem, self).__init__()
        self.button_rects = list()
        self.action_btn_rect = QtCore.QRect()
        self.delete_btn_rect = QtCore.QRect()

class ItemDelegate(QtWidgets.QStyledItemDelegate):
    def __init__(self, parent=None):
        super(ItemDelegate, self).__init__(parent)
        self._pressed = None
        self.event_pos = None
        self.icons = self.parent().parent().parent().parent().parent().icons

    def paint(self, painter, option, index):
        save_option_rect = option.rect
        button_width = 20
        button_spacing = 2
        option.rect = save_option_rect
        painter.save()
        buttons = list()
        buttons.append(QtWidgets.QStyleOptionButton())
        buttons[0].icon = self.icons["delete"]
        buttons[0].iconSize = QtCore.QSize(15,15)
        item = index.model().itemFromIndex(index)
        if item.data()["category"] == "folder":
            buttons.append(QtWidgets.QStyleOptionButton())
            buttons[1].icon = self.icons["add"]
            buttons[1].iconSize = QtCore.QSize(10,10)
        elif item.data()["category"] in {"stickynote", "webUrl"}:
            buttons.append(QtWidgets.QStyleOptionButton())
            buttons[1].icon = self.icons["jump"]
            buttons[1].iconSize = QtCore.QSize(10,10)
        elif item.data()["category"] == "node":
            buttons.append(QtWidgets.QStyleOptionButton())
            buttons[1].icon = self.icons["jump"]
            buttons[1].iconSize = QtCore.QSize(10,10)
            buttons.append(QtWidgets.QStyleOptionButton())
            buttons[2].icon = self.icons["show_parms"]
            buttons[2].iconSize = QtCore.QSize(10,10)
        elif item.data()["category"] == "file":
            buttons.append(QtWidgets.QStyleOptionButton())
            buttons[1].icon = self.icons["jump"]
            buttons[1].iconSize = QtCore.QSize(10,10)
            buttons.append(QtWidgets.QStyleOptionButton())
            buttons[2].icon = self.icons["file"]
            buttons[2].iconSize = QtCore.QSize(10,10)
        item.button_rects = list()
        for idx, button in enumerate(buttons):
            button.ButtonFeature = QtWidgets.QStyleOptionButton.Flat
            button.rect = QtCore.QRect(option.rect.right()-button_width*(idx+1)-button_spacing*idx, option.rect.top(), button_width, option.rect.height())
            button.palette = option.palette
            item.button_rects.append(QtCore.QRect(option.rect.right()-button_width*(idx+1)-button_spacing*idx, option.rect.top(), button_width, option.rect.height()))
        if self._pressed and self._pressed == (index.row(), index.column()):
            for button in buttons:
                if button.rect.contains(self.event_pos):
                    button.state = QtWidgets.QStyle.State_Enabled | QtWidgets.QStyle.State_Sunken
        for button in buttons:
            QtWidgets.QApplication.style().drawControl(QtWidgets.QStyle.CE_PushButton, button, painter)
        painter.restore()
        
        option.rect = QtCore.QRect(option.rect.left(), option.rect.top(), option.rect.right()-button_width*3-button_spacing*3-option.rect.left(), option.rect.height())
        QtWidgets.QStyledItemDelegate.paint(self, painter, option, index)

    def editorEvent(self, event, model, option, index):
        self.event_pos = event.pos()
        self._pressed = (index.row(), index.column())
        item = index.model().itemFromIndex(index)
        if event.type() == QtCore.QEvent.MouseMove:
            return super(ItemDelegate, self).editorEvent(event, model, option, index)

        if event.type() == QtCore.QEvent.MouseButtonPress or event.type() == QtCore.QEvent.MouseButtonDblClick:
            for rect in item.button_rects:
                if rect.contains(event.pos()) is True:
                    return True
            self.event_pos = QtCore.QPoint()
            self._pressed = None
            return super(ItemDelegate, self).editorEvent(event, model, option, index)

        elif event.type() == QtCore.QEvent.MouseButtonRelease:
            if self._pressed == (index.row(), index.column()):
                if item.button_rects[0].contains(event.pos()):
                    parent_item = index.model().itemFromIndex(index.parent())
                    if parent_item is None:
                        parent_item = index.model()

                    if item.data()["category"] == "node":
                        remove_callbacks = True
                        session_id = int(item.data()["session_id"])
                        for check_item in iterate_items(item.model().invisibleRootItem()):
                            if check_item is item or check_item.data()["category"] != "node":
                                continue
                            if int(check_item.data()["session_id"]) == session_id:
                                remove_callbacks = False
                                break
                        if remove_callbacks:
                            node = hou.nodeBySessionId(session_id)
                            for callback in self.parent().node_callbacks[session_id]:
                                node.removeEventCallback((callback[0], ), callback[1])
                            self.parent().node_callbacks.pop(session_id)

                    parent_item.takeRow(item.row())

                if len(item.button_rects) > 1:
                    if item.button_rects[1].contains(event.pos()):
                        panel = self.parent().parent().parent().parent().parent().parent().panel
                        eval_open_item_function(item, panel)
                if len(item.button_rects) > 2:
                    if item.button_rects[2].contains(event.pos()):
                        if item.data()["category"] == "node":
                            open_parameter_tab(item, event.globalPos())
                        if item.data()["category"] == "file":
                            open_file(item)
                        
            self.event_pos = QtCore.QPoint()
            self._pressed = None
            return True
        else:
            for rect in item.button_rects:
                if rect.contains(event.pos()) is True:
                    return True
            return super(ItemDelegate, self).editorEvent(event, model, option, index)

def add_folder(item):
    new_item = TreeItem()
    icon_type = ""
    icon = QtGui.QPixmap(icon_path+"/folder.svg")
    new_item.setIcon(icon)
    new_item.setText("New Folder")
    new_item.setDropEnabled(True)
    data = {"note": "", "path": "", "category": "folder", "icon_type": icon_type, "color": (0.8, 0.8, 0.8)}
    new_item.setData(data, QtCore.Qt.UserRole + 1)
    item.appendRow(new_item)
    
def open_parameter_tab(item, global_mouse_pos):
    node = hou.nodeBySessionId(int(item.data().get("session_id")))
    if node is None:
        return
    desktop = hou.ui.curDesktop()
    parm_pane_size = (400, 500)
    global_mouse_pos = global_mouse_pos.toTuple()
    desktop_widget = QtWidgets.QDesktopWidget()
    parm_pane_pos = (int(global_mouse_pos[0]-parm_pane_size[1]*0.5), int(desktop_widget.availableGeometry().height()-global_mouse_pos[1]-parm_pane_size[1]))
    pane = desktop.createFloatingPane(hou.paneTabType.Parm, parm_pane_pos, parm_pane_size)
    pane.setCurrentNode(node)
    pane.setShowNetworkControls(False)

def center_on_item(item, panel = hou.ui.curDesktop()):
    network_editor = panel.paneTabOfType(hou.paneTabType.NetworkEditor)
    h_item = hou.nodeBySessionId(int(item.data().get("session_id")))
    if h_item is None:
        return
    if item.data().get("category") == "stickynote":
        h_item = hou.stickyNoteBySessionId(int(item.data().get("session_id")))
    network_editor.cd(h_item.parent().path())
    h_pos = h_item.position()
    bounds = hou.BoundingRect()
    bounds.setTo(hou.Vector4(h_pos[0]+1,h_pos[1]-8,h_pos[0]+8,h_pos[1]+8))
    h_item.setSelected(True, True, True)
    network_editor.setVisibleBounds(bounds, transition_time=.05, set_center_when_scale_rejected=True)

def eval_open_item_function(item, panel):
    if item.data()["category"] == "folder":
        add_folder(item)
    elif item.data()["category"] == "node" or item.data()["category"] == "stickynote":
        center_on_item(item, panel)
    elif item.data()["category"] == "file":
        open_file_dir(item)
    elif item.data()["category"] == "webUrl":
        open_url(item)

def open_file(item):
    os.startfile(item.data().get("path"))

def open_file_dir(item):
    os.startfile(os.path.dirname(item.data().get("path")))

def open_url(item):
    webbrowser.open(item.data().get("path"), new=0, autoraise=True)

def prepare_save_data(tab_widget, selection):
    data = {"tabs":[]}
    def iterate_tree_rows(source_item):
        row_item_data = list()
        for row in range(source_item.rowCount()):
            child_item = source_item.child(row, 0)
            item_data = {"data": child_item.data(), "text": child_item.text(), "children": []}
            if(child_item.hasChildren()):
                item_data["children"].append(iterate_tree_rows(child_item))
            row_item_data.append(item_data)
        return row_item_data

    for index in selection:
        root_item = tab_widget.widget(index).model().invisibleRootItem()
        tree_data = iterate_tree_rows(root_item)
        tab_data = {"text": tab_widget.tabBar().tabText(index),
                    "children": []}
        tab_data["children"].append(tree_data)
        data["tabs"].append(tab_data)
    return data

def iterate_items(root):
    if root is not None:
        stack = [root]
        while stack:
            parent = stack.pop(0)
            for row in range(parent.rowCount()):
                for column in range(parent.columnCount()):
                    child = parent.child(row, column)
                    yield child
                    if child.hasChildren():
                        stack.append(child)