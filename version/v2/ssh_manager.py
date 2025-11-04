#!/usr/bin/env python3
# ssh_manager_sqlite.py
import shutil
import sys, os, sqlite3, subprocess, datetime
from PyQt6.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QHBoxLayout,
    QTableWidget, QTableWidgetItem, QPushButton,
    QDialog, QFormLayout, QLineEdit, QSpinBox, QComboBox,
    QMessageBox, QLabel, QListWidget, QSplitter, QPlainTextEdit
)
from PyQt6.QtCore import Qt

# Optional paramiko usage for simple SFTP browse
try:
    import paramiko

    HAVE_PARAMIKO = True
except Exception:
    HAVE_PARAMIKO = False

DB_FILE = "connections.db"


# ---------------------------
# Database helpers
# ---------------------------
def init_db():
    conn = sqlite3.connect(DB_FILE)
    cur = conn.cursor()
    cur.execute("""
                CREATE TABLE IF NOT EXISTS connections
                (
                    id        INTEGER PRIMARY KEY AUTOINCREMENT,
                    grp       TEXT,
                    name      TEXT,
                    host      TEXT,
                    port      INTEGER,
                    user      TEXT,
                    password  TEXT,
                    protocol  TEXT,
                    last_used TEXT
                )
                """)
    conn.commit()
    conn.close()


def fetch_all():
    conn = sqlite3.connect(DB_FILE)
    cur = conn.cursor()
    cur.execute(
        "SELECT id, grp, name, host, port, user, password, protocol, last_used FROM connections ORDER BY grp, name")
    rows = cur.fetchall()
    conn.close()
    return rows


def insert_conn(entry):
    conn = sqlite3.connect(DB_FILE)
    cur = conn.cursor()
    cur.execute("""
                INSERT INTO connections (grp, name, host, port, user, password, protocol, last_used)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """, (entry['grp'], entry['name'], entry['host'], entry['port'], entry['user'], entry['password'],
                      entry['protocol'], entry.get('last_used', '')))
    conn.commit()
    conn.close()


def update_conn(id_, entry):
    conn = sqlite3.connect(DB_FILE)
    cur = conn.cursor()
    cur.execute("""
                UPDATE connections
                SET grp=?,
                    name=?,
                    host=?,
                    port=?,
                    user=?,
                    password=?,
                    protocol=?,
                    last_used=?
                WHERE id = ?
                """, (entry['grp'], entry['name'], entry['host'], entry['port'], entry['user'], entry['password'],
                      entry['protocol'], entry.get('last_used', ''), id_))
    conn.commit()
    conn.close()


def delete_conn(id_):
    conn = sqlite3.connect(DB_FILE)
    cur = conn.cursor()
    cur.execute("DELETE FROM connections WHERE id=?", (id_,))
    conn.commit()
    conn.close()


# ---------------------------
# GUI: Entry dialog
# ---------------------------
class EntryDialog(QDialog):
    def __init__(self, parent=None, entry=None):
        super().__init__(parent)
        self.setWindowTitle("Add / Edit Connection")
        self.setMinimumWidth(420)
        layout = QFormLayout(self)

        self.grp = QLineEdit()
        self.name = QLineEdit()
        self.host = QLineEdit()
        self.port = QSpinBox();
        self.port.setRange(1, 65535);
        self.port.setValue(22)
        self.user = QLineEdit()
        self.password = QLineEdit();
        self.password.setEchoMode(QLineEdit.EchoMode.Password)
        self.protocol = QComboBox();
        self.protocol.addItems(["SSH", "SFTP"])

        layout.addRow("Group:", self.grp)
        layout.addRow("Name:", self.name)
        layout.addRow("Host (IP/domain):", self.host)
        layout.addRow("Port:", self.port)
        layout.addRow("User:", self.user)
        layout.addRow("Password:", self.password)
        layout.addRow("Protocol:", self.protocol)

        btns = QHBoxLayout()
        ok = QPushButton("OK");
        cancel = QPushButton("Cancel")
        ok.clicked.connect(self.accept);
        cancel.clicked.connect(self.reject)
        btns.addWidget(ok);
        btns.addWidget(cancel)
        layout.addRow(btns)

        if entry:
            self.grp.setText(entry.get('grp', ''))
            self.name.setText(entry.get('name', ''))
            self.host.setText(entry.get('host', ''))
            self.port.setValue(int(entry.get('port', 22)))
            self.user.setText(entry.get('user', ''))
            self.password.setText(entry.get('password', ''))
            self.protocol.setCurrentText(entry.get('protocol', 'SSH'))

    def get_data(self):
        return {
            'grp': self.grp.text().strip(),
            'name': self.name.text().strip(),
            'host': self.host.text().strip(),
            'port': int(self.port.value()),
            'user': self.user.text().strip(),
            'password': self.password.text(),
            'protocol': self.protocol.currentText(),
            'last_used': ''
        }


# ---------------------------
# GUI: Main window
# ---------------------------
class MainWindow(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("SSH/SFTP Manager - SQLite")
        self.resize(1000, 600)
        init_db()

        main_layout = QVBoxLayout(self)

        # Top actions
        top_actions = QHBoxLayout()
        self.btn_add = QPushButton("Add")
        self.btn_edit = QPushButton("Edit")
        self.btn_delete = QPushButton("Delete")
        self.btn_connect = QPushButton("Connect (SSH)")
        self.btn_sftp = QPushButton("Open (SFTP)")
        self.btn_browse = QPushButton("Browse (SFTP in-app)")
        top_actions.addWidget(self.btn_add);
        top_actions.addWidget(self.btn_edit);
        top_actions.addWidget(self.btn_delete)
        top_actions.addStretch()
        top_actions.addWidget(self.btn_connect);
        top_actions.addWidget(self.btn_sftp);
        top_actions.addWidget(self.btn_browse)
        main_layout.addLayout(top_actions)

        # Splitter: left groups list, right table
        splitter = QSplitter(Qt.Orientation.Horizontal)
        self.group_list = QListWidget()
        self.group_list.addItem("All")
        self.group_list.setMaximumWidth(220)
        splitter.addWidget(self.group_list)

        self.table = QTableWidget(0, 7)
        self.table.setHorizontalHeaderLabels(["ID", "Group", "Name", "Server", "User", "Protocol", "Last used"])
        self.table.hideColumn(0)  # hide ID column visually (but keep it)
        self.table.setSelectionBehavior(self.table.SelectionBehavior.SelectRows)
        splitter.addWidget(self.table)
        main_layout.addWidget(splitter)

        # Connect signals
        self.btn_add.clicked.connect(self.add_entry)
        self.btn_edit.clicked.connect(self.edit_entry)
        self.btn_delete.clicked.connect(self.delete_entry)
        self.btn_connect.clicked.connect(self.connect_ssh)
        self.btn_sftp.clicked.connect(self.open_nautilus)
        self.btn_browse.clicked.connect(self.browse_sftp)
        self.group_list.itemClicked.connect(self.on_group_selected)

        self.reload()

    def reload(self):
        rows = fetch_all()
        # populate groups
        groups = {"All"}
        for r in rows:
            groups.add(r[1] or "")
        self.group_list.clear()
        items = sorted(list(groups))
        if "" in items:
            items.remove("")
            items.insert(0, "(no group)")
        for g in items:
            self.group_list.addItem(g or "(no group)")

        # fill table
        self.table.setRowCount(0)
        for r in rows:
            self._insert_row(r)
        self.table.resizeColumnsToContents()

    def _insert_row(self, row):
        # row = (id, grp, name, host, port, user, password, protocol, last_used)
        rownum = self.table.rowCount()
        self.table.insertRow(rownum)
        for i, val in enumerate(
                row[:7]):  # keep only first 7 columns to match header (id,grp,name,server,user,protocol,last_used)
            # We need to map columns: id(0) -> col0, grp(1)->col1, name(2)->col2, host(3)->col3, port(4) used in host col3, user(5)->col4, password(6) not shown, protocol(7)->col5, last_used(8)->col6
            pass
        # manual set to align header
        id_, grp, name, host, port, user, password, protocol, last_used = row
        self.table.setItem(rownum, 0, QTableWidgetItem(str(id_)))
        self.table.setItem(rownum, 1, QTableWidgetItem(grp or ""))
        self.table.setItem(rownum, 2, QTableWidgetItem(name or ""))
        srv = f"{host}:{port}"
        self.table.setItem(rownum, 3, QTableWidgetItem(srv))
        self.table.setItem(rownum, 4, QTableWidgetItem(user or ""))
        self.table.setItem(rownum, 5, QTableWidgetItem(protocol or ""))
        self.table.setItem(rownum, 6, QTableWidgetItem(last_used or ""))

    def get_selected(self):
        r = self.table.currentRow()
        if r < 0:
            QMessageBox.warning(self, "Select", "Choose a connection row first.")
            return None
        id_item = self.table.item(r, 0)
        if not id_item: return None
        id_ = int(id_item.text())
        # fetch full entry by id
        conn = sqlite3.connect(DB_FILE)
        cur = conn.cursor()
        cur.execute("SELECT id, grp, name, host, port, user, password, protocol, last_used FROM connections WHERE id=?",
                    (id_,))
        row = cur.fetchone()
        conn.close()
        return row

    def add_entry(self):
        d = EntryDialog(self)
        if d.exec() == QDialog.DialogCode.Accepted:
            entry = d.get_data()
            insert_conn(entry)
            self.reload()

    def edit_entry(self):
        sel = self.get_selected()
        if not sel: return
        id_, grp, name, host, port, user, password, protocol, last_used = sel
        entry = {'grp': grp, 'name': name, 'host': host, 'port': port, 'user': user, 'password': password,
                 'protocol': protocol, 'last_used': last_used}
        d = EntryDialog(self, entry=entry)
        if d.exec() == QDialog.DialogCode.Accepted:
            new = d.get_data()
            update_conn(id_, new)
            self.reload()

    def delete_entry(self):
        sel = self.get_selected()
        if not sel: return
        id_, grp, name = sel[0], sel[1], sel[2]
        if QMessageBox.question(self, "Delete", f"Delete {name} ({grp})?") == QMessageBox.StandardButton.Yes:
            delete_conn(id_)
            self.reload()

    def connect_ssh(self):
        sel = self.get_selected()
        if not sel:
            return

        id_, grp, name, host, port, user, password, protocol, last_used = sel

        now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        update_conn(id_, {
            'grp': grp, 'name': name, 'host': host, 'port': port,
            'user': user, 'password': password,
            'protocol': protocol, 'last_used': now
        })
        self.reload()

        # ✅ Nếu có password và có sshpass → SSH auto login như Remmina
        if password and shutil.which("sshpass"):
            try:
                subprocess.Popen([
                    "gnome-terminal", "--",
                    "sshpass", "-p", password,
                    "ssh", f"{user}@{host}", "-p", str(port),
                    "-o", "StrictHostKeyChecking=no"
                ])
                return
            except Exception as e:
                QMessageBox.critical(self, "sshpass error", str(e))

        # ✅ fallback paramiko nếu không có sshpass
        if HAVE_PARAMIKO and password:
            ...
            # (phần paramiko bạn đã có)

        # ✅ Cuối cùng fallback mở ssh chuẩn (phải nhập pass)
        try:
            subprocess.Popen(["gnome-terminal", "--", "ssh",
                              f"{user}@{host}", "-p", str(port)])
        except Exception as e:
            QMessageBox.critical(self, "Error", str(e))

    def open_nautilus(self):
        sel = self.get_selected()
        if not sel: return
        id_, grp, name, host, port, user, password, protocol, last_used = sel
        uri = f"sftp://{user}:{password}@{host}:{port}" if password else f"sftp://{user}@{host}:{port}"
        try:
            subprocess.Popen(["nautilus", uri])
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to open Nautilus: {e}")

    def browse_sftp(self):
        if not HAVE_PARAMIKO:
            QMessageBox.information(self, "paramiko missing",
                                    "paramiko not installed. Install with: pip install paramiko")
            return
        sel = self.get_selected()
        if not sel: return
        id_, grp, name, host, port, user, password, protocol, last_used = sel
        # only for SFTP protocol
        if protocol.upper() != "SFTP":
            QMessageBox.information(self, "Protocol", "Browse SFTP only works for protocol = SFTP")
            return
        # connect via paramiko and list root
        try:
            t = paramiko.Transport((host, int(port)))
            t.connect(None, username=user, password=password)
            sftp = paramiko.SFTPClient.from_transport(t)
            files = sftp.listdir(".")
            t.close()
            dlg = QDialog(self)
            dlg.setWindowTitle(f"SFTP: {user}@{host}:{port}")
            layout = QVBoxLayout(dlg)
            layout.addWidget(QLabel("Remote files (root):"))
            lw = QListWidget()
            lw.addItems(files)
            layout.addWidget(lw)
            btn = QPushButton("Close")
            btn.clicked.connect(dlg.accept)
            layout.addWidget(btn)
            dlg.exec()
        except Exception as e:
            QMessageBox.critical(self, "SFTP Error", str(e))

    def on_group_selected(self, item):
        grp = item.text()
        if grp == "All":
            rows = fetch_all()
        else:
            conn = sqlite3.connect(DB_FILE)
            cur = conn.cursor()
            cur.execute(
                "SELECT id, grp, name, host, port, user, password, protocol, last_used FROM connections WHERE grp=? ORDER BY name",
                (("" if grp == "(no group)" else grp),))
            rows = cur.fetchall()
            conn.close()
        self.table.setRowCount(0)
        for r in rows:
            self._insert_row(r)
        self.table.resizeColumnsToContents()


# small helper
def shutil_which(name):
    from shutil import which
    return which(name) is not None


# ---------------------------
# Run
# ---------------------------
if __name__ == "__main__":
    app = QApplication(sys.argv)
    w = MainWindow()
    w.show()
    sys.exit(app.exec())
