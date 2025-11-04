#!/usr/bin/env python3
# ssh_manager_json.py
import sys, os, json, subprocess, datetime, shlex
from PyQt6.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QHBoxLayout,
    QTableWidget, QTableWidgetItem, QPushButton, QInputDialog,
    QMessageBox, QLineEdit, QDialog, QLabel, QComboBox, QSpinBox, QFormLayout
)
from PyQt6.QtCore import Qt

DATA_FILE = "servers.json"

def load_data():
    if not os.path.exists(DATA_FILE):
        return []
    try:
        with open(DATA_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return []

def save_data(data):
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def have_sshpass():
    return subprocess.call(["which", "sshpass"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL) == 0

class EntryDialog(QDialog):
    def __init__(self, parent=None, entry=None):
        super().__init__(parent)
        self.setWindowTitle("Add / Edit Entry")
        self.setModal(True)
        layout = QFormLayout(self)

        self.name = QLineEdit()
        self.server = QLineEdit()
        self.user = QLineEdit()
        self.port = QSpinBox()
        self.port.setRange(1, 65535)
        self.port.setValue(22)
        self.protocol = QComboBox()
        self.protocol.addItems(["SSH", "SFTP"])
        self.password = QLineEdit()
        self.password.setEchoMode(QLineEdit.EchoMode.Password)

        layout.addRow("Name:", self.name)
        layout.addRow("Server (IP/domain):", self.server)
        layout.addRow("User:", self.user)
        layout.addRow("Port:", self.port)
        layout.addRow("Protocol:", self.protocol)
        layout.addRow("Password:", self.password)

        btns = QHBoxLayout()
        ok = QPushButton("OK"); cancel = QPushButton("Cancel")
        ok.clicked.connect(self.accept); cancel.clicked.connect(self.reject)
        btns.addWidget(ok); btns.addWidget(cancel)
        layout.addRow(btns)

        if entry:
            self.name.setText(entry.get("name",""))
            self.server.setText(entry.get("server",""))
            self.user.setText(entry.get("user",""))
            self.port.setValue(int(entry.get("port",22)))
            self.protocol.setCurrentText(entry.get("protocol","SSH"))
            self.password.setText(entry.get("password",""))

    def get_data(self):
        return {
            "name": self.name.text().strip(),
            "server": self.server.text().strip(),
            "user": self.user.text().strip(),
            "port": int(self.port.value()),
            "protocol": self.protocol.currentText(),
            "password": self.password.text()
        }

class MainWindow(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("SSH Manager (JSON, saves password)")
        self.resize(1000, 600)
        self.data = load_data()

        v = QVBoxLayout(self)
        self.table = QTableWidget(0, 5)
        self.table.setHorizontalHeaderLabels(["Name","Server","User","Protocol","Last used"])
        self.table.setSelectionBehavior(self.table.SelectionBehavior.SelectRows)
        self.table.setEditTriggers(self.table.EditTrigger.NoEditTriggers)
        v.addWidget(self.table)

        h = QHBoxLayout()
        btn_add = QPushButton("Add")
        btn_edit = QPushButton("Edit")
        btn_del = QPushButton("Delete")
        btn_connect = QPushButton("Connect")
        btn_connect_nautilus = QPushButton("Open (Nautilus SFTP)")
        h.addWidget(btn_add); h.addWidget(btn_edit); h.addWidget(btn_del)
        h.addStretch()
        h.addWidget(btn_connect); h.addWidget(btn_connect_nautilus)
        v.addLayout(h)

        btn_add.clicked.connect(self.add_entry)
        btn_edit.clicked.connect(self.edit_entry)
        btn_del.clicked.connect(self.delete_entry)
        btn_connect.clicked.connect(self.connect_ssh)
        btn_connect_nautilus.clicked.connect(self.open_nautilus)

        self.reload_table()

    def reload_table(self):
        self.table.setRowCount(0)
        for item in self.data:
            row = self.table.rowCount()
            self.table.insertRow(row)
            self.table.setItem(row,0,QTableWidgetItem(item.get("name","")))
            srv = f"{item.get('server','')}:{item.get('port',22)}"
            self.table.setItem(row,1,QTableWidgetItem(srv))
            self.table.setItem(row,2,QTableWidgetItem(item.get("user","")))
            self.table.setItem(row,3,QTableWidgetItem(item.get("protocol","SSH")))
            self.table.setItem(row,4,QTableWidgetItem(item.get("last_used","")))
        self.table.resizeColumnsToContents()

    def add_entry(self):
        d = EntryDialog(self)
        if d.exec() == QDialog.DialogCode.Accepted:
            new = d.get_data()
            new["last_used"] = ""
            self.data.append(new)
            save_data(self.data)
            self.reload_table()

    def edit_entry(self):
        r = self.table.currentRow()
        if r < 0:
            QMessageBox.warning(self, "Select", "Chọn 1 entry để sửa")
            return
        cur = self.data[r]
        d = EntryDialog(self, entry=cur)
        if d.exec() == QDialog.DialogCode.Accepted:
            self.data[r].update(d.get_data())
            save_data(self.data)
            self.reload_table()

    def delete_entry(self):
        r = self.table.currentRow()
        if r < 0:
            QMessageBox.warning(self, "Select", "Chọn 1 entry để xóa")
            return
        name = self.data[r].get("name","(no name)")
        if QMessageBox.question(self, "Delete", f"Delete {name}?") == QMessageBox.StandardButton.Yes:
            self.data.pop(r)
            save_data(self.data)
            self.reload_table()

    def get_selected(self):
        r = self.table.currentRow()
        if r < 0:
            QMessageBox.warning(self, "Select", "Chọn 1 entry")
            return None, None
        return r, self.data[r]

    def connect_ssh(self):
        idx, entry = self.get_selected()
        if not entry: return
        # update last used
        entry["last_used"] = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        save_data(self.data)
        self.reload_table()

        user = entry["user"]
        host = entry["server"]
        port = entry.get("port",22)
        pwd = entry.get("password","")

        # prefer sshpass if available
        if have_sshpass() and pwd:
            # quote password safely
            cmd = ["sshpass", "-p", pwd, "gnome-terminal", "--", "ssh", f"{user}@{host}", "-p", str(port)]
            try:
                subprocess.Popen(cmd)
                return
            except Exception as e:
                QMessageBox.critical(self, "Error", f"Failed to run sshpass: {e}")
        # fallback: open terminal without password (user types)
        try:
            subprocess.Popen(["gnome-terminal", "--", "ssh", f"{user}@{host}", "-p", str(port)])
        except Exception as e:
            QMessageBox.critical(self, "Error", str(e))

    def open_nautilus(self):
        idx, entry = self.get_selected()
        if not entry: return
        user = entry["user"]
        host = entry["server"]
        port = entry.get("port",22)
        pwd = entry.get("password","")

        # Try opening with user:password in URI (may or may not be accepted)
        uri = f"sftp://{user}:{pwd}@{host}:{port}" if pwd else f"sftp://{user}@{host}:{port}"
        try:
            # Use subprocess without shell
            subprocess.Popen(["nautilus", uri])
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to open Nautilus: {e}")

def main():
    app = QApplication(sys.argv)
    w = MainWindow()
    w.show()
    sys.exit(app.exec())

if __name__ == "__main__":
    main()
