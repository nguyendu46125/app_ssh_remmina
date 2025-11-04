#!/usr/bin/env python3
import sys, os, sqlite3, subprocess, datetime, shutil
from PyQt6.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QHBoxLayout,
    QTableWidget, QTableWidgetItem, QPushButton,
    QDialog, QFormLayout, QLineEdit, QSpinBox, QComboBox,
    QMessageBox, QLabel, QListWidget, QSplitter, QInputDialog
)
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QIcon


# =====================================================
# RESOURCE PATH – dùng được cho DEV, PyInstaller và .deb
# =====================================================
def resource_path(relative):
    if hasattr(sys, '_MEIPASS'):  # PyInstaller
        base = sys._MEIPASS
    else:
        # Khi cài .deb → file thực nằm tại /usr/share/ssh_manager/
        base = os.path.dirname(os.path.abspath(__file__))
    return os.path.join(base, relative)


# DB location
DB_FILE = resource_path("connections.db")

# Optional paramiko support
try:
    import paramiko

    HAVE_PARAMIKO = True
except:
    HAVE_PARAMIKO = False


# ==========================
# DATABASE HELPERS
# ==========================
def init_db():
    conn = sqlite3.connect(DB_FILE)
    cur = conn.cursor()

    # Bảng lưu danh sách kết nối
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

    # ✅ Bảng mới lưu danh sách group
    cur.execute("""
                CREATE TABLE IF NOT EXISTS groups
                (
                    id   INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT UNIQUE
                )
                """)

    # ✅ Bảng mới lưu config table layout
    cur.execute("""
                CREATE TABLE IF NOT EXISTS table_layout
                (
                    col_name TEXT PRIMARY KEY,
                    width    INTEGER
                )
                """)

    conn.commit()
    conn.close()


def fetch_all():
    conn = sqlite3.connect(DB_FILE)
    cur = conn.cursor()
    cur.execute("SELECT * FROM connections ORDER BY grp, name")
    rows = cur.fetchall()
    conn.close()
    return rows


def insert_conn(data):
    conn = sqlite3.connect(DB_FILE)
    cur = conn.cursor()
    cur.execute("""
                INSERT INTO connections (grp, name, host, port, user, password, protocol, last_used)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    data['grp'], data['name'], data['host'], data['port'],
                    data['user'], data['password'], data['protocol'],
                    data.get('last_used', '')
                ))
    conn.commit()
    conn.close()


def update_conn(id_, data):
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
                """, (
                    data['grp'], data['name'], data['host'], data['port'],
                    data['user'], data['password'], data['protocol'],
                    data.get('last_used', ''), id_
                ))
    conn.commit()
    conn.close()


def delete_conn(id_):
    conn = sqlite3.connect(DB_FILE)
    cur = conn.cursor()
    cur.execute("DELETE FROM connections WHERE id=?", (id_,))
    conn.commit()
    conn.close()


# ==========================
# ENTRY DIALOG
# ==========================
class EntryDialog(QDialog):
    def __init__(self, parent=None, entry=None, default_group=None):
        super().__init__(parent)
        self.setWindowTitle("Add / Edit Connection")
        self.setMinimumWidth(400)

        layout = QFormLayout(self)

        self.grp = QComboBox()
        self.grp.setEditable(False)
        self.load_groups()

        # ✅ Thêm đúng đoạn này – giữ nguyên toàn bộ logic khác
        if default_group and default_group not in [self.grp.itemText(i) for i in range(self.grp.count())]:
            self.grp.addItem(default_group)

        if default_group:
            self.grp.setCurrentText(default_group)

        self.name = QLineEdit()
        self.host = QLineEdit()

        self.port = QSpinBox()
        self.port.setRange(1, 65535);
        self.port.setValue(22)

        self.user = QLineEdit()

        self.password = QLineEdit()
        self.password.setEchoMode(QLineEdit.EchoMode.Password)

        self.protocol = QComboBox()
        self.protocol.addItems(["SSH", "SFTP"])

        layout.addRow("Group:", self.grp)
        layout.addRow("Name:", self.name)
        layout.addRow("Host:", self.host)
        layout.addRow("Port:", self.port)
        layout.addRow("User:", self.user)
        layout.addRow("Password:", self.password)
        layout.addRow("Protocol:", self.protocol)

        btns = QHBoxLayout()
        btn_ok = QPushButton("OK")
        btn_cancel = QPushButton("Cancel")
        btn_ok.clicked.connect(self.accept)
        btn_cancel.clicked.connect(self.reject)
        btns.addWidget(btn_ok)
        btns.addWidget(btn_cancel)
        layout.addRow(btns)

        if entry:
            self.grp.setCurrentText(entry['grp'] or "(no group)")
            self.name.setText(entry['name'])
            self.host.setText(entry['host'])
            self.port.setValue(entry['port'])
            self.user.setText(entry['user'])
            self.password.setText(entry['password'])
            self.protocol.setCurrentText(entry['protocol'])

    def get_data(self):
        return {
            "grp": "" if self.grp.currentText() == "(no group)" else self.grp.currentText(),
            "name": self.name.text().strip(),
            "host": self.host.text().strip(),
            "port": int(self.port.value()),
            "user": self.user.text().strip(),
            "password": self.password.text(),
            "protocol": self.protocol.currentText(),
            "last_used": ""
        }

    def load_groups(self):
        conn = sqlite3.connect(DB_FILE)
        cur = conn.cursor()

        # ✅ Ưu tiên lấy từ bảng groups (nếu có)
        try:
            cur.execute("SELECT name FROM groups ORDER BY name")
            groups = [r[0] for r in cur.fetchall()]
        except Exception as e:
            print(e)
            # fallback: nếu chưa có bảng groups, lấy từ connections
            cur.execute("SELECT DISTINCT grp FROM connections")
            groups = [r[0] for r in cur.fetchall()]

        conn.close()

        # loại None / '' → đổi thành (no group)
        fixed = []
        for g in groups:
            if not g:
                fixed.append("(no group)")
            else:
                fixed.append(g)

        self.grp.clear()
        self.grp.addItems(sorted(fixed))


# ==========================
# MAIN WINDOW
# ==========================
class MainWindow(QWidget):
    def __init__(self):
        super().__init__()
        self.last_created_group = None
        self.setWindowTitle("SSH Manager")
        self.setWindowIcon(QIcon(resource_path("icon.png")))
        self.resize(980, 600)

        init_db()

        layout = QVBoxLayout(self)

        # Top buttons
        top = QHBoxLayout()
        self.btn_add = QPushButton("Add")
        self.btn_edit = QPushButton("Edit")
        self.btn_delete = QPushButton("Delete")
        self.btn_add_group = QPushButton("Add Group")
        self.btn_delete_group = QPushButton("Delete Group")

        self.btn_ssh = QPushButton("Connect SSH")
        self.btn_sftp = QPushButton("Open SFTP")
        self.btn_browse = QPushButton("Browse SFTP")

        top.addWidget(self.btn_add)
        top.addWidget(self.btn_edit)
        top.addWidget(self.btn_delete)
        top.addWidget(self.btn_add_group)
        self.btn_add_group.clicked.connect(self.add_group)
        top.addWidget(self.btn_delete_group)

        top.addStretch()
        top.addWidget(self.btn_ssh)
        top.addWidget(self.btn_sftp)
        top.addWidget(self.btn_browse)
        self.btn_delete_group.clicked.connect(self.delete_group)

        layout.addLayout(top)

        # Splitter
        splitter = QSplitter(Qt.Orientation.Horizontal)
        self.group_list = QListWidget()
        self.group_list.setMaximumWidth(220)
        splitter.addWidget(self.group_list)

        self.table = QTableWidget(0, 7)
        self.table.setHorizontalHeaderLabels([
            "ID", "Group", "Name", "Host:Port", "User", "Protocol", "Last used"
        ])
        # self.table.hideColumn(0)
        splitter.addWidget(self.table)

        header = self.table.horizontalHeader()
        header.sectionResized.connect(self.save_table_layout)
        header.setStretchLastSection(True)
        self.load_table_layout()

        layout.addWidget(splitter)

        # Events
        self.btn_add.clicked.connect(self.add_entry)
        self.btn_edit.clicked.connect(self.edit_entry)
        self.btn_delete.clicked.connect(self.delete_entry)

        self.btn_ssh.clicked.connect(self.open_ssh)
        self.btn_sftp.clicked.connect(self.open_sftp)
        self.btn_browse.clicked.connect(self.browse_sftp)

        self.group_list.itemClicked.connect(self.on_group_changed)

        self.reload()

    def load_table_layout(self):
        conn = sqlite3.connect(DB_FILE)
        cur = conn.cursor()
        cur.execute("SELECT col_name, width FROM table_layout")
        data = dict(cur.fetchall())
        conn.close()

        headers = ["ID", "Group", "Name", "Host:Port", "User", "Protocol", "Last used"]

        for i, name in enumerate(headers):
            if name in data:
                self.table.setColumnWidth(i, data[name])

    def save_table_layout(self, index, old_width, new_width):
        try:
            header = self.table.horizontalHeaderItem(index)
            if not header:
                return
            header_name = header.text()
            conn = sqlite3.connect(DB_FILE)
            cur = conn.cursor()
            cur.execute("""
                        INSERT INTO table_layout (col_name, width)
                        VALUES (?, ?)
                        ON CONFLICT(col_name) DO UPDATE SET width=excluded.width
                        """, (header_name, new_width))
            conn.commit()
            conn.close()
            print(f"💾 Saved column {header_name}: {new_width}px")
        except Exception as e:
            print("save_table_layout error:", e)

    # Load data UI
    def reload(self):
        # Lưu group đang chọn (text hiển thị trong list)
        current_item = self.group_list.currentItem()
        current_group_text = current_item.text() if current_item else "All"

        # Lấy tất cả connections (dùng để hiển thị table khi chọn All hoặc group)
        rows = fetch_all()

        # Lấy danh sách groups từ bảng `groups` nếu có, fallback sang DISTINCT grp từ connections
        conn = sqlite3.connect(DB_FILE)
        cur = conn.cursor()
        try:
            cur.execute("SELECT name FROM groups ORDER BY name")
            db_groups = [r[0] for r in cur.fetchall()]
        except Exception:
            cur.execute("SELECT DISTINCT grp FROM connections")
            db_groups = [r[0] for r in cur.fetchall()]
        conn.close()

        # Kết hợp groups từ bảng groups và các grp có trong connections (đảm bảo không mất group nào)
        groups = set(["All"])
        for g in db_groups:
            groups.add(g or "")  # lưu rỗng -> biểu diễn sau thành (no group)
        for r in rows:
            groups.add(r[1] or "")

        # Rebuild UI list (block signals khi thay đổi để tránh on_group_changed tự chạy)
        self.group_list.blockSignals(True)
        self.group_list.clear()
        for g in sorted(groups):
            self.group_list.addItem(g if g else "(no group)")
        self.group_list.blockSignals(False)

        # Tìm item tương ứng với current_group_text, nếu không có thì chọn "All"
        target_text = current_group_text
        # Nếu user đang thấy "(no group)" thì tìm theo "(no group)"
        items = self.group_list.findItems(target_text, Qt.MatchFlag.MatchExactly)
        if not items:
            items = self.group_list.findItems("All", Qt.MatchFlag.MatchExactly)

        # Nếu tìm được item thì chọn và cập nhật table
        if items:
            target_item = items[0]
            # setCurrentItem có thể phát signal; mình đã blockSignals khi rebuild nên an toàn
            self.group_list.setCurrentItem(target_item)
            # Thực sự cập nhật table theo group
            self.on_group_changed(target_item)
        else:
            # dự phòng: nếu thật sự không có gì, clear table
            self.table.setRowCount(0)
        self.load_table_layout()

    def add_group(self):
        text, ok = QInputDialog.getText(self, "Add Group", "Group name:")
        if ok and text.strip():
            g = text.strip()
            conn = sqlite3.connect(DB_FILE)
            cur = conn.cursor()
            cur.execute("INSERT OR IGNORE INTO groups (name) VALUES (?)", (g,))
            conn.commit()
            conn.close()

            self.reload()
            items = self.group_list.findItems(g, Qt.MatchFlag.MatchExactly)
            if items:
                self.group_list.setCurrentItem(items[0])
                self.on_group_changed(items[0])

    def delete_group(self):
        item = self.group_list.currentItem()
        if not item:
            return

        grp = item.text()
        if grp in ("All", "(no group)"):
            QMessageBox.information(self, "Notice", "Không thể xoá nhóm này.")
            return

        if QMessageBox.question(self, "Confirm",
                                f"Xoá nhóm '{grp}' và tất cả kết nối trong đó?") == QMessageBox.StandardButton.Yes:
            conn = sqlite3.connect(DB_FILE)
            cur = conn.cursor()
            cur.execute("DELETE FROM groups WHERE name=?", (grp,))
            cur.execute("DELETE FROM connections WHERE grp=?", (grp,))
            conn.commit()
            conn.close()
            self.reload()

    def add_row(self, row):
        id_, grp, name, host, port, user, pwd, proto, last = row
        r = self.table.rowCount()
        self.table.insertRow(r)

        self.table.setItem(r, 0, QTableWidgetItem(str(id_)))
        self.table.setItem(r, 1, QTableWidgetItem(grp or ""))
        self.table.setItem(r, 2, QTableWidgetItem(name))
        self.table.setItem(r, 3, QTableWidgetItem(f"{host}:{port}"))
        self.table.setItem(r, 4, QTableWidgetItem(user))
        self.table.setItem(r, 5, QTableWidgetItem(proto))
        self.table.setItem(r, 6, QTableWidgetItem(last or ""))

    def get_selected(self):
        r = self.table.currentRow()
        if r < 0:
            QMessageBox.warning(self, "Select", "Chọn dòng trước.")
            return None

        id_ = int(self.table.item(r, 0).text())

        conn = sqlite3.connect(DB_FILE)
        cur = conn.cursor()
        cur.execute("SELECT * FROM connections WHERE id=?", (id_,))
        row = cur.fetchone()
        conn.close()
        return row

    def select_last_group(self):
        if not self.last_created_group:
            return
        for i in range(self.group_list.count()):
            if self.group_list.item(i).text() == self.last_created_group:
                self.group_list.setCurrentRow(i)
                self.on_group_changed(self.group_list.item(i))
                break
        self.last_created_group = None

    # CRUD
    def add_entry(self):
        item = self.group_list.currentItem()
        current_group = item.text() if item else "(no group)"

        d = EntryDialog(self, default_group=current_group)
        if d.exec():
            data = d.get_data()
            insert_conn(data)
            self.reload()

            if item:
                items = self.group_list.findItems(current_group, Qt.MatchFlag.MatchExactly)
                if items:
                    self.group_list.setCurrentItem(items[0])

    def edit_entry(self):
        sel = self.get_selected()
        if not sel: return

        id_, grp, name, host, port, user, pwd, proto, last = sel
        entry = {
            "grp": grp, "name": name, "host": host,
            "port": port, "user": user, "password": pwd,
            "protocol": proto, "last_used": last
        }

        d = EntryDialog(self, entry)
        if d.exec():
            update_conn(id_, d.get_data())
            self.reload()

    def delete_entry(self):
        sel = self.get_selected()
        if not sel: return

        id_, grp, name = sel[0], sel[1], sel[2]
        if QMessageBox.question(self, "Delete",
                                f"Xóa {name} ({grp}) ?"
                                ) == QMessageBox.StandardButton.Yes:
            delete_conn(id_)
            self.reload()

    # SSH
    def open_ssh(self):
        sel = self.get_selected()
        if not sel: return

        id_, grp, name, host, port, user, pwd, proto, last = sel

        update_conn(id_, {
            "grp": grp, "name": name, "host": host, "port": port,
            "user": user, "password": pwd, "protocol": proto,
            "last_used": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        })
        self.reload()

        # Auto login with sshpass
        if pwd and shutil.which("sshpass"):
            subprocess.Popen([
                "gnome-terminal", "--",
                "sshpass", "-p", pwd,
                "ssh", f"{user}@{host}", "-p", str(port),
                "-o", "StrictHostKeyChecking=no"
            ])
            return

        subprocess.Popen([
            "gnome-terminal", "--",
            "ssh", f"{user}@{host}", "-p", str(port)
        ])

    # Open SFTP via Nautilus
    def open_sftp(self):
        sel = self.get_selected()
        if not sel:
            return
        id_, grp, name, host, port, user, pwd, proto, last = sel

        uri = f"sftp://{user}:{pwd}@{host}:{port}" if pwd else f"sftp://{user}@{host}:{port}"

        # Tìm file manager khả dụng nhất
        file_managers = ["nautilus", "nemo", "thunar", "pcmanfm"]
        fm = None
        for fm_name in file_managers:
            if shutil.which(fm_name):
                fm = fm_name
                break

        if not fm:
            QMessageBox.critical(self, "Error", "Không tìm thấy file manager (nautilus/nemo/thunar).")
            return

        # Thử mở trước
        try:
            subprocess.Popen([fm, uri])
            return
        except Exception as e:
            print(e)
            pass

        # --- Nếu lỗi: reset GVFS ---
        # Kill file manager
        kill_cmds = [
            ["nautilus", "-q"],
            ["nautilus", "--quit"],
            ["pkill", "-f", "nautilus"],
            ["pkill", "-f", "nemo"],
            ["pkill", "-f", "thunar"]
        ]
        for cmd in kill_cmds:
            try:
                subprocess.Popen(cmd)
            except Exception as e:
                print(e)
                pass

        # Xóa cache GVFS
        subprocess.Popen(["rm", "-rf", os.path.expanduser("~/.cache/gvfs")])

        # Restart tất cả service GVFS nếu tồn tại
        gvfs_services = [
            "gvfs-daemon",
            "gvfs-ssh-volume-monitor",
            "gvfs-afc-volume-monitor",
            "gvfs-gphoto2-volume-monitor",
            "gvfs-mtp-volume-monitor",
        ]

        for svc in gvfs_services:
            try:
                subprocess.Popen(["systemctl", "--user", "restart", svc])
            except Exception as e:
                print(e)
                pass

        # Mở lại file manager
        try:
            subprocess.Popen([fm])
        except Exception as e:
            print(e)
            pass

        # Cuối cùng thử mở lại SFTP
        subprocess.Popen([fm, uri])

    # Browse SFTP inside-app
    def browse_sftp(self):
        if not HAVE_PARAMIKO:
            QMessageBox.warning(self, "Missing", "Cài paramiko: pip install paramiko")
            return

        sel = self.get_selected()
        if not sel: return
        id_, grp, name, host, port, user, pwd, proto, last = sel

        if proto.upper() != "SFTP":
            QMessageBox.information(self, "Notice", "Chỉ dùng cho SFTP")
            return

        try:
            t = paramiko.Transport((host, port))
            t.connect(username=user, password=pwd)
            sftp = paramiko.SFTPClient.from_transport(t)
            files = sftp.listdir(".")
            t.close()
        except Exception as e:
            QMessageBox.critical(self, "SFTP Error", str(e))
            return

        dlg = QDialog(self)
        dlg.setWindowTitle(f"SFTP – {host}")
        layout = QVBoxLayout(dlg)
        lw = QListWidget()
        lw.addItems(files)
        layout.addWidget(QLabel("Remote root files:"))
        layout.addWidget(lw)
        btn = QPushButton("Close")
        btn.clicked.connect(dlg.accept)
        layout.addWidget(btn)
        dlg.exec()

    # Filter by group
    def on_group_changed(self, item):
        grp = item.text()
        if grp == "All":
            rows = fetch_all()
        else:
            g = "" if grp == "(no group)" else grp
            conn = sqlite3.connect(DB_FILE)
            cur = conn.cursor()
            cur.execute("SELECT * FROM connections WHERE grp=? ORDER BY name", (g,))
            rows = cur.fetchall()
            conn.close()

        self.table.setRowCount(0)
        for r in rows:
            self.add_row(r)


# ==========================
# RUN APP
# ==========================
if __name__ == "__main__":
    app = QApplication(sys.argv)
    w = MainWindow()
    w.show()
    sys.exit(app.exec())
