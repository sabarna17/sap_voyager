import os
import sys
import json
import time
import logging
import weakref
from dotenv import load_dotenv
load_dotenv()

from PyQt5.QtCore import Qt, QPointF, QRectF, QTimer
from PyQt5.QtGui import QPainter, QColor, QPen, QBrush, QPainterPath, QIcon, QFont
from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QGraphicsView, QGraphicsScene,
    QGraphicsItem, QToolBar, QAction, QGraphicsTextItem, QPushButton,
    QWidget, QSizePolicy, QMessageBox, QVBoxLayout, QHBoxLayout, QTextEdit,
    QFileDialog, QDialog, QFormLayout, QLabel, QLineEdit, QComboBox,
    QDialogButtonBox, QGroupBox, QSpinBox, QSpacerItem
)

###############################################################################
# Custom ReverseFileHandler
###############################################################################
class ReverseFileHandler(logging.Handler):
    """
    A custom logging handler that prepends each log message to a file so that
    the latest log entries appear at the top.
    """
    def __init__(self, filename, encoding='utf-8'):
        super().__init__()
        self.filename = filename
        self.encoding = encoding
        if not os.path.exists(self.filename):
            with open(self.filename, 'w', encoding=self.encoding):
                pass

    def emit(self, record):
        try:
            msg = self.format(record)
            if os.path.exists(self.filename):
                with open(self.filename, 'r', encoding=self.encoding) as f:
                    existing = f.read()
            else:
                existing = ""
            with open(self.filename, 'w', encoding=self.encoding) as f:
                f.write(msg + "\n")
                f.write(existing)
        except Exception:
            self.handleError(record)

# Set up logging.
logger = logging.getLogger()
logger.setLevel(logging.DEBUG)
formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')

reverse_handler = ReverseFileHandler("app.log")
reverse_handler.setFormatter(formatter)
logger.addHandler(reverse_handler)

stream_handler = logging.StreamHandler()
stream_handler.setFormatter(formatter)
logger.addHandler(stream_handler)

###############################################################################
# Node class
###############################################################################
class Node(QGraphicsItem):
    def __init__(self, title, pos):
        super().__init__()
        logging.info("Creating Node with title: '%s' at position: %s", title, pos)
        self.title = QGraphicsTextItem(title, self)
        self.title.setTextInteractionFlags(Qt.TextEditorInteraction)
        self.description = QGraphicsTextItem("Description", self)
        self.description.setTextInteractionFlags(Qt.TextEditorInteraction)
        self.setPos(pos)
        self.setFlag(QGraphicsItem.ItemIsMovable)
        self.setFlag(QGraphicsItem.ItemSendsGeometryChanges)
        self.setFlag(QGraphicsItem.ItemIsSelectable)
        self.setAcceptHoverEvents(True)
        self.connections = []
        self.highlighted = False 

    def boundingRect(self):
        title_rect = self.title.boundingRect()
        desc_rect = self.description.boundingRect()
        width = max(title_rect.width(), desc_rect.width()) + 20
        height = title_rect.height() + desc_rect.height() + 30
        return QRectF(0, 0, width, height)

    def paint(self, painter, option, widget):
        painter.save()
        rect = self.boundingRect()
        fill_color = QColor(255, 255, 0) if self.highlighted else QColor(255, 255, 255)
        painter.setBrush(QBrush(fill_color))
        painter.setPen(QPen(Qt.black, 2))
        painter.drawRoundedRect(rect, 10, 10)

        self.title.setPos(10, 10)
        self.description.setPos(10, 10 + self.title.boundingRect().height() + 10)
        self.drawHandles(painter)
        painter.restore()

    def drawHandles(self, painter):
        painter.setBrush(QBrush(QColor(100, 100, 255)))
        painter.setPen(Qt.NoPen)
        top_center = self.getHandlePosition(0)
        bottom_center = self.getHandlePosition(1)
        painter.drawEllipse(top_center, 5, 3)
        painter.drawEllipse(bottom_center, 5, 3)

    def getHandlePosition(self, index):
        rect = self.boundingRect()
        if index == 0:
            return QPointF(rect.width() / 2, 0)
        elif index == 1:
            return QPointF(rect.width() / 2, rect.height())
        return QPointF(0, 0)

    def itemChange(self, change, value):
        if change == QGraphicsItem.ItemPositionHasChanged:
            logging.debug("Node '%s' moved to %s", self.title.toPlainText(), self.pos())
            for connection in self.connections:
                connection.updatePath()
        return super().itemChange(change, value)

    def delete(self):
        logging.info("Deleting Node with title: '%s'", self.title.toPlainText())
        scene = self.scene()
        if scene:
            for connection in self.connections[:]:
                logging.debug("Deleting connection from Node '%s'", self.title.toPlainText())
                scene.removeItem(connection)
            scene.removeItem(self)

    def hoverEnterEvent(self, event):
        try:
            logging.debug("Mouse hover enter on Node '%s'", self.title.toPlainText())
            self.highlighted = True
            self.update()
            super().hoverEnterEvent(event)
        except Exception as e:
            logging.exception("Exception in hoverEnterEvent: %s", e)

    def hoverLeaveEvent(self, event):
        try:
            logging.debug("Mouse hover leave on Node '%s'", self.title.toPlainText())
            self.highlighted = False
            self.update()
            super().hoverLeaveEvent(event)
        except Exception as e:
            logging.exception("Exception in hoverLeaveEvent: %s", e)

###############################################################################
# Edge class
###############################################################################
class Edge(QGraphicsItem):
    def __init__(self, start_node, start_handle_index, end_node, end_handle_index, temporary_end=None):
        logging.info("Creating Edge from Node %s (handle %d) to Node %s (handle %s)",
                     str(id(start_node)), start_handle_index,
                     str(id(end_node)) if end_node is not None else "None",
                     str(end_handle_index) if end_handle_index is not None else "None")
        super().__init__()
        self.start_node = start_node
        self.start_handle_index = start_handle_index
        self.end_node = end_node
        self.end_handle_index = end_handle_index
        self.temporary_end = temporary_end  # Used when dragging an edge
        self.setZValue(-1)
        self.updatePath()

    def updatePath(self):
        start_pos = self.start_node.mapToScene(self.start_node.getHandlePosition(self.start_handle_index))
        if self.end_node is not None and self.end_handle_index is not None:
            end_pos = self.end_node.mapToScene(self.end_node.getHandlePosition(self.end_handle_index))
        else:
            end_pos = self.temporary_end if self.temporary_end is not None else start_pos

        self.path = self.calculateCurve(start_pos, end_pos)
        self.prepareGeometryChange()
        self.update()

    def calculateCurve(self, start, end):
        control_point1 = start + QPointF(100, 0)
        control_point2 = end - QPointF(100, 0)
        path = QPainterPath(start)
        path.cubicTo(control_point1, control_point2, end)
        return path

    def boundingRect(self):
        return self.path.boundingRect()

    def paint(self, painter, option, widget):
        painter.setPen(QPen(Qt.black, 2))
        painter.drawPath(self.path)

    def delete(self):
        logging.info("Deleting Edge from Node %s to Node %s", str(id(self.start_node)), str(id(self.end_node)))
        scene = self.scene()
        if scene:
            scene.removeItem(self)

###############################################################################
# (Assumed) External Agent Functions
###############################################################################
# from main import run_agent  # Ensure this function exists in your main module

###############################################################################
# FlowView class
###############################################################################
class FlowView(QGraphicsView):
    def __init__(self):
        super().__init__()
        logging.info("Initializing FlowView.")
        self.scene = QGraphicsScene()
        self.setScene(self.scene)
        self.setRenderHints(QPainter.Antialiasing)
        self.current_edge = None
        self.drag_start = None
        self.setDragMode(QGraphicsView.RubberBandDrag)

    def wheelEvent(self, event):
        factor = 1.2 if event.angleDelta().y() > 0 else 1 / 1.2
        logging.debug("Wheel event: scaling by factor %s", factor)
        self.scale(factor, factor)

    def mousePressEvent(self, event):
        logging.debug("Mouse pressed at %s", event.pos())
        item = self.itemAt(event.pos())
        if isinstance(item, Node):
            node_point = item.mapFromScene(self.mapToScene(event.pos()))
            for i in range(2):
                h = item.getHandlePosition(i)
                if (node_point - h).manhattanLength() < 20:
                    self.drag_start = (item, i)
                    self.current_edge = Edge(item, i, None, None, temporary_end=self.mapToScene(event.pos()))
                    self.scene.addItem(self.current_edge)
                    logging.debug("Started dragging edge from Node '%s'", item.title.toPlainText())
                    return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self.current_edge:
            self.current_edge.temporary_end = self.mapToScene(event.pos())
            self.current_edge.updatePath()
            item = self.itemAt(event.pos())
            if isinstance(item, Node):
                item.highlighted = True
                item.update()
            else:
                for node in self.scene.items():
                    if isinstance(node, Node) and node.highlighted:
                        node.highlighted = False
                        node.update()
        else:
            super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        logging.debug("Mouse released at %s", event.pos())
        try:
            if self.current_edge:
                item = self.itemAt(event.pos())
                if isinstance(item, Node) and item != self.drag_start[0]:
                    node_point = item.mapFromScene(self.mapToScene(event.pos()))
                    edge_created = False
                    for i in range(2):
                        h = item.getHandlePosition(i)
                        if (node_point - h).manhattanLength() < 20:
                            if self.current_edge and self.current_edge.scene() is not None:
                                self.scene.removeItem(self.current_edge)
                            edge = Edge(self.drag_start[0], self.drag_start[1], item, i)
                            self.scene.addItem(edge)
                            self.drag_start[0].connections.append(edge)
                            item.connections.append(edge)
                            item.highlighted = True
                            item.update()
                            # Use a weak reference in the delayed call.
                            weak_item = weakref.ref(item)
                            QTimer.singleShot(500, lambda: self.safe_remove_highlight(weak_item()))
                            logging.info("Created edge between Node %s and Node %s",
                                         str(id(self.drag_start[0])), str(id(item)))
                            edge_created = True
                            break
                    if not edge_created:
                        logging.info("Cancelled edge creation (no valid handle found).")
                        if self.current_edge and self.current_edge.scene() is not None:
                            self.scene.removeItem(self.current_edge)
                else:
                    logging.info("Cancelled edge creation (invalid drop target).")
                    if self.current_edge and self.current_edge.scene() is not None:
                        self.scene.removeItem(self.current_edge)
                self.current_edge = None
                self.drag_start = None
            else:
                super().mouseReleaseEvent(event)
        except Exception as e:
            logging.exception("Error during mouseReleaseEvent: %s", e)

    def safe_remove_highlight(self, node):
        try:
            if node is not None and node.scene() is not None:
                node.highlighted = False
                node.update()
        except Exception as e:
            logging.exception("Exception in safe_remove_highlight: %s", e)

    def export_to_json(self):
        logging.info("Exporting scene to JSON file (voyager.json).")
        nodes = []
        edges = []
        for item in self.scene.items():
            if isinstance(item, Node):
                node_data = {
                    "id": str(id(item)),
                    "title": item.title.toPlainText(),
                    "description": item.description.toPlainText(),
                    "x": item.x(),
                    "y": item.y()
                }
                nodes.append(node_data)
        for item in self.scene.items():
            if isinstance(item, Edge) and item.end_node is not None:
                edge_data = {
                    "start_id": str(id(item.start_node)),
                    "start_handle": item.start_handle_index,
                    "end_id": str(id(item.end_node)),
                    "end_handle": item.end_handle_index
                }
                edges.append(edge_data)

        data = {"nodes": nodes, "edges": edges}
        try:
            with open("voyager.json", "w") as f:
                json.dump(data, f, indent=4)
            logging.info("Successfully exported JSON to voyager.json")
            QMessageBox.information(self, "Export JSON", "JSON exported to voyager.json successfully.")
        except Exception as e:
            logging.exception("Failed to export JSON: %s", e)
            QMessageBox.warning(self, "Export JSON", f"Failed to export JSON:\n{str(e)}")
            
    def flow_to_instructtion(self):
        logging.info("Converting flow to instructions.")
        nodes = []
        edges = []
        for item in self.scene.items():
            if isinstance(item, Node):
                node_data = {
                    "id": str(id(item)),
                    "title": item.title.toPlainText(),
                    "description": item.description.toPlainText(),
                    "x": item.x(),
                    "y": item.y()
                }
                nodes.append(node_data)
        for item in self.scene.items():
            if isinstance(item, Edge) and item.end_node is not None:
                edge_data = {
                    "start_id": str(id(item.start_node)),
                    "start_handle": item.start_handle_index,
                    "end_id": str(id(item.end_node)),
                    "end_handle": item.end_handle_index
                }
                edges.append(edge_data)

        data = {"nodes": nodes, "edges": edges}
        try:
            with open("voyager.json", "w") as f:
                json.dump(data, f, indent=4)
            logging.info("JSON for instruction conversion written to voyager.json")
        except Exception as e:
            logging.exception("Failed to write JSON for instruction conversion: %s", e)
            QMessageBox.warning(self, "Export JSON", f"Failed to export JSON:\n{str(e)}")
        
        from main import convert_ask_into_steps
        with open('voyager.json', "r") as file:
            data = json.load(file)
        data_str = str(data)
        ask = f"""
        Your task is to convert the taks into step by instructions in text format.
        - If you find the instructions are related to SAP GUI then proceed.
        - Else you must respond blank.
        
        Here is the json data which contains nodal links. 
        {data_str}
        """
        steps = str(convert_ask_into_steps(ask))
        instructions_text = steps
        main_windows = [w for w in QApplication.topLevelWidgets() if isinstance(w, QMainWindow)]
        if main_windows:
            main_window = main_windows[0]
            if hasattr(main_window, "right_widget"):
                main_window.right_widget.setPlainText(instructions_text)
                logging.info("Instructions updated in main window.")
            else:
                logging.error("Main window does not have 'right_widget' attribute.")
        else:
            logging.error("Main window not found.")
        return ''
    
    def import_from_json(self):
        logging.info("Importing JSON flow from file.")
        file_name, _ = QFileDialog.getOpenFileName(self, "Open JSON File", "", "JSON Files (*.json);;All Files (*)")
        if not file_name:
            logging.info("Import JSON cancelled; no file selected.")
            return

        try:
            with open(file_name, "r") as file:
                data = json.load(file)
            logging.info("Successfully loaded JSON file: %s", file_name)
        except Exception as e:
            logging.exception("Failed to load JSON: %s", e)
            QMessageBox.warning(self, "Error", f"Failed to load JSON:\n{str(e)}")
            return

        self.scene.clear()
        node_mapping = {}
        nodes_data = []
        edges_data = []

        if isinstance(data, dict):
            nodes_data = data.get("nodes", [])
            edges_data = data.get("edges", [])
        elif isinstance(data, list):
            nodes_data = data

        for node_data in nodes_data:
            node_id = node_data.get("id")
            title = node_data.get("title", "Node")
            x = node_data.get("x", 0)
            y = node_data.get("y", 0)
            description = node_data.get("description", "")
            node = Node(title, QPointF(x, y))
            node.title.setPlainText(title)
            node.description.setPlainText(description)
            self.scene.addItem(node)
            if node_id is not None:
                node_mapping[str(node_id)] = node
            else:
                node_mapping[str(id(node))] = node
            logging.info("Imported Node '%s' at (%d, %d)", title, x, y)

        for edge_data in edges_data:
            start_id = edge_data.get("start_id")
            end_id = edge_data.get("end_id")
            start_handle = edge_data.get("start_handle", 0)
            end_handle = edge_data.get("end_handle", 1)
            start_id = str(start_id) if start_id is not None else None
            end_id = str(end_id) if end_id is not None else None
            start_node = node_mapping.get(start_id)
            end_node = node_mapping.get(end_id)
            if start_node is None or end_node is None:
                logging.warning("Edge not created, missing node mapping for edge data: %s", edge_data)
                continue
            edge = Edge(start_node, start_handle, end_node, end_handle)
            self.scene.addItem(edge)
            start_node.connections.append(edge)
            end_node.connections.append(edge)
            logging.info("Imported Edge from Node %s to Node %s", start_id, end_id)

    def start_agent(self):
        logging.info("Start Agent triggered.")
        msg_box = QMessageBox()
        msg_box.setWindowTitle("Starting the Agent")
        msg_box.setText("Do you want to proceed?")
        
        main_windows = [w for w in QApplication.topLevelWidgets() if isinstance(w, QMainWindow)]
        if main_windows:
            main_window = main_windows[0]
            if hasattr(main_window, "left_widget"):
                flow_text = main_window.right_widget.toPlainText()
                logging.debug("Agent flow text: %s", flow_text)
                print('sabchatterjee---->>> ', 'Change here')
                print(flow_text)
                print('sabchatterjee---->>> ', 'Change here')
                # run_agent(flow_text)
            else:
                logging.error("Main window does not have 'left_widget' attribute.")
        else:
            logging.error("Main window not found.")

###############################################################################
# ResizableWindow class
###############################################################################
class ResizableWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        logging.info("Initializing ResizableWindow.")
        self.setWindowTitle("Draggable Window Example")
        self.setGeometry(100, 100, 800, 600)
        self.setWindowIcon(QIcon("Designer (26).jpeg"))
        
        self.central_widget = QWidget()
        self.setCentralWidget(self.central_widget)

        self.layout = QHBoxLayout(self.central_widget)
        self.left_widget = FlowView()
        self.left_widget.setStyleSheet("background-color: lightblue;")
        self.layout.addWidget(self.left_widget)

        self.right_widget = QTextEdit()
        self.right_widget.setStyleSheet("background-color: lightgreen;")
        self.layout.addWidget(self.right_widget)

        self.console_output = QTextEdit()
        self.console_output.setReadOnly(True)
        self.console_output.setStyleSheet("background-color: lightyellow;")
        sys.stdout = ConsoleOutput(self.console_output)
        sys.stderr = ConsoleOutput(self.console_output)
        self.layout.addWidget(self.console_output)

        self.setMouseTracking(True)
        self.is_dragging = False
        self.drag_start_x = 0

        toolbar = QToolBar()
        self.addToolBar(toolbar)
        
        settings_action = QAction("⚙️", self)
        settings_action.setToolTip("Settings")
        settings_action.triggered.connect(self.open_settings_dialog)
        toolbar.addAction(settings_action)

        clear_action = QAction("🗑️", self)
        clear_action.setToolTip("Clear all items from the scene")
        clear_action.triggered.connect(self.clear_scene)
        toolbar.addAction(clear_action)

        toolbar.addSeparator()
        toolbar.addSeparator()

        add_node_action = QAction("➕ Add Node", self)
        add_node_action.setToolTip("Add a new node")
        add_node_action.triggered.connect(self.add_node)
        toolbar.addAction(add_node_action)
        add_node_button = toolbar.widgetForAction(add_node_action)
        if add_node_button:
            add_node_button.setStyleSheet("background-color: #A8D5BA;")

        delete_action = QAction("❌ Delete", self)
        delete_action.setToolTip("Delete selected items")
        delete_action.triggered.connect(self.delete_selected)
        toolbar.addAction(delete_action)
        delete_button = toolbar.widgetForAction(delete_action)
        if delete_button:
            delete_button.setStyleSheet("background-color: #FFCCCB;")

        toolbar.addSeparator()
        toolbar.addSeparator()

        export_json_action = QAction("⬇️ Export ", self)
        export_json_action.triggered.connect(self.left_widget.export_to_json)
        toolbar.addAction(export_json_action)
        export_json_button = toolbar.widgetForAction(export_json_action)
        if export_json_button:
            export_json_button.setStyleSheet("background-color: #CCCCCC;")

        import_json_action = QAction("⬆️ Import", self)
        import_json_action.setToolTip("Import a flow from a JSON file")
        import_json_action.triggered.connect(self.left_widget.import_from_json)
        toolbar.addAction(import_json_action)
        import_json_button = toolbar.widgetForAction(import_json_action)
        if import_json_button:
            import_json_button.setStyleSheet("background-color: #CCCCCC;")

        toolbar.addSeparator()

        flow_to_instruct_action = QAction("➡️ To instruction", self)
        flow_to_instruct_action.setToolTip("Flow to instruction")
        flow_to_instruct_action.triggered.connect(self.left_widget.flow_to_instructtion)
        toolbar.addAction(flow_to_instruct_action)
        flow_to_instruct_button = toolbar.widgetForAction(flow_to_instruct_action)
        if flow_to_instruct_button:
            flow_to_instruct_button.setStyleSheet("background-color: #e0b7f7;")

        spacer = QWidget()
        spacer.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        toolbar.addWidget(spacer)

        start_agent_action = QAction("Start Agent ▶️", self)
        start_agent_action.triggered.connect(self.left_widget.start_agent)
        toolbar.addAction(start_agent_action)
        start_agent_button = toolbar.widgetForAction(start_agent_action)
        if start_agent_button:
            start_agent_button.setStyleSheet("background-color: lightblue;")

        self.setGeometry(100, 100, 800, 600)
        self.setWindowTitle("SAP Voyager Flow Creator")
        self.initUI()
        self.showSettingsDialog() 
               
    def initUI(self):
        self.setWindowTitle("Your Application")
        self.setGeometry(100, 100, 800, 600)

    def showSettingsDialog(self):
        dialog = SettingsDialog()
        if dialog.exec_() == QDialog.Accepted:
            logging.info("Settings saved via SettingsDialog.")
        else:
            logging.info("Settings dialog canceled.")

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.is_dragging = True
            self.drag_start_x = event.x()
            logging.debug("ResizableWindow mouse press at x=%d", event.x())
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self.is_dragging:
            new_width = event.x()
            self.left_widget.setFixedWidth(max(0, new_width))
            logging.debug("Resizing left widget to width %d", new_width)
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.is_dragging = False
            logging.debug("ResizableWindow mouse release.")
        super().mouseReleaseEvent(event)

    def add_node(self):
        logging.info("Adding new node to scene.")
        node = Node("Node", QPointF(0, 0))
        self.left_widget.scene.addItem(node)
        node.setPos(self.left_widget.mapToScene(self.left_widget.viewport().rect().center()))

    def delete_selected(self):
        logging.info("Deleting selected items from scene.")
        for item in self.left_widget.scene.selectedItems():
            if isinstance(item, (Node, Edge)):
                logging.debug("Deleting selected item: %s", str(item))
                item.delete()
                
    def clear_scene(self):
        logging.info("User requested scene clear.")
        confirmation = QMessageBox.question(
            self,
            "Clear Scene",
            "Are you sure you want to clear the scene?",
            QMessageBox.Yes | QMessageBox.No
        )
        if confirmation == QMessageBox.Yes:
            logging.info("Scene cleared.")
            self.left_widget.scene.clear()   

    def open_settings_dialog(self):
        logging.info("Opening settings dialog.")
        dialog = SettingsDialog()
        if dialog.exec_() == QDialog.Accepted:
            sap_settings = {
                "SAP_SERVER": dialog.sap_server_edit.text(),
                "SAP_USER": dialog.sap_user_edit.text(),
                "SAP_PASSWORD": dialog.sap_password_edit.text()
            }
            langchain_settings = {
                "LANGCHAIN_PROJECT": dialog.langchain_project_edit.text(),
                "LANGCHAIN_ENDPOINT": dialog.langchain_endpoint_edit.text(),
                "LANGCHAIN_API_KEY": dialog.langchain_api_key_edit.text(),
                "recursion_limit": dialog.recursion_limit.text()
            }
            provider = dialog.provider_combo.currentText()
            additional_settings = {}
            if provider != "Select Provider":
                for key, widget in dialog.provider_fields.items():
                    additional_settings[key] = widget.text()
            logging.info("SAP Settings: %s", sap_settings)
            logging.info("Langchain Settings: %s", langchain_settings)
            logging.info("Provider Selected: %s", provider)
            logging.info("Additional Provider Settings: %s", additional_settings)
        else:
            logging.info("Settings dialog canceled.")

###############################################################################
# SettingsDialog class
###############################################################################
class SettingsDialog(QDialog):
    def __init__(self):
        super().__init__()
        logging.info("Initializing SettingsDialog.")
        self.setWindowTitle("Settings")
        self.setFixedSize(400, 400)
        
        main_layout = QVBoxLayout()
        self.sap_fields = {}
        form_layout = QFormLayout()

        for field in ["SAP_SERVER", "SAP_USER", "SAP_PASSWORD"]:
            label = QLabel(f"{field}: *")
            input_field = QLineEdit()
            input_field.setText(os.getenv(field, ""))
            if field == "SAP_PASSWORD":
                input_field.setEchoMode(QLineEdit.Password)
            form_layout.addRow(label, input_field)
            self.sap_fields[field] = input_field

        self.langchain_fields = {}
        for field in ["LANGCHAIN_PROJECT", "LANGCHAIN_ENDPOINT", "LANGCHAIN_API_KEY"]:
            label = QLabel(f"{field}:")
            input_field = QLineEdit()
            form_layout.addRow(label, input_field)
            self.langchain_fields[field] = input_field    
            input_field.setText(os.getenv(field, ""))

        self.recursion_limit = QLineEdit("50")
        form_layout.addRow(QLabel("Recursion Limit:"), self.recursion_limit)

        main_layout.addLayout(form_layout)
        main_layout.addItem(QSpacerItem(20, 10, QSizePolicy.Minimum, QSizePolicy.Expanding))

        main_layout.addWidget(QLabel("Additional Provider Configuration:"))
        self.provider_combo = QComboBox()
        self.provider_combo.addItems(["Select Provider", "Azure OpenAI", "GROQ", "ANTHROPIC"])
        self.provider_combo.currentIndexChanged.connect(self.update_dynamic_form)
        main_layout.addWidget(self.provider_combo)

        self.dynamic_form = QFormLayout()
        main_layout.addLayout(self.dynamic_form)

        button_layout = QHBoxLayout()
        self.ok_button = QPushButton("Save")
        self.ok_button.clicked.connect(self.show_popup)
        self.cancel_button = QPushButton("Done")
        self.cancel_button.clicked.connect(self.reject)
        button_layout.addWidget(self.ok_button)
        button_layout.addWidget(self.cancel_button)
        main_layout.addLayout(button_layout)

        self.setLayout(main_layout)
        self.provider_fields = {}

    def show_popup(self):
        logging.info("Settings saved; showing confirmation popup.")
        msg_box = QMessageBox()
        msg_box.setIcon(QMessageBox.Information)
        msg_box.setWindowTitle("Confirmation")
        msg_box.setText("Settings saved successfully!")
        time.sleep(1)
        msg_box.setStandardButtons(QMessageBox.Ok)
        msg_box.exec_()
        self.accept()

    def make_label(self, text):
        label = QLabel(text)
        label.setFont(QFont("Arial", 10))
        return label

    def update_dynamic_form(self):
        selected_provider = self.provider_combo.currentText()
        logging.info("Provider selection changed to: %s", selected_provider)
        # Clear previous fields
        for i in reversed(range(self.dynamic_form.count())):
            widget = self.dynamic_form.itemAt(i).widget()
            if widget is not None:
                widget.setParent(None)
        self.provider_fields = {}
        provider_fields = {
            "Azure OpenAI": ["openai_api_version", "openai_api_key", "azure_endpoint", "deployment_name"],
            "GROQ": ["GROQ_MODEL", "GROQ_API_KEY"],
            "ANTHROPIC": ["ANTHROPIC_MODEL", "ANTHROPIC_KEY"]
        }
        if selected_provider in provider_fields:
            for field in provider_fields[selected_provider]:
                label = QLabel(f"{field}: *")
                input_field = QLineEdit()
                self.dynamic_form.addRow(label, input_field)
                input_field.setText(os.getenv(field, ""))
                self.provider_fields[field] = input_field

###############################################################################
# ConsoleOutput class
###############################################################################
class ConsoleOutput:
    """Redirects stdout & stderr to the PyQt widget."""
    def __init__(self, text_widget):
        self.text_widget = text_widget

    def write(self, message):
        if message.strip():
            logging.debug("ConsoleOutput: %s", message.strip())
            self.text_widget.append(message.strip())

    def flush(self):
        pass

###############################################################################
# Main Application execution
###############################################################################
if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = ResizableWindow()
    window.show()
    logging.info("Application started.")
    sys.exit(app.exec_())
