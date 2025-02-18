#!/usr/bin/env python3
import sys, os, subprocess, threading, time, shutil, json, zipfile, webbrowser, requests, re
from bs4 import BeautifulSoup
from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QWidget, QTabWidget, QVBoxLayout, QHBoxLayout,
    QPushButton, QTextEdit, QLineEdit, QLabel, QFileDialog, QListWidget, QListWidgetItem,
    QGroupBox, QGridLayout, QComboBox, QMessageBox, QTreeView, QFileSystemModel,
    QTableWidget, QTableWidgetItem, QHeaderView, QProgressDialog
)
from PyQt5.QtCore import pyqtSignal, QThread, QTimer, Qt
from PyQt5.QtGui import QTextCursor

# ------------------ Settings Manager ------------------
SETTINGS_FILE = "server_settings.json"
DEFAULT_SETTINGS = {
    "java_path": "java",
    "min_mem": "1024M",
    "max_mem": "2048M",
    "server_dir": os.getcwd(),
    "server_jar": ""
}

def load_settings():
    if os.path.exists(SETTINGS_FILE):
        with open(SETTINGS_FILE, "r") as f:
            return json.load(f)
    else:
        save_settings(DEFAULT_SETTINGS)
        return DEFAULT_SETTINGS

def save_settings(settings):
    with open(SETTINGS_FILE, "w") as f:
        json.dump(settings, f, indent=4)

# ------------------ Console Output Filtering ------------------
GARBAGE_PATTERNS = [
    re.compile(r"^\s*$"),
    re.compile(r".*DEBUG:.*", re.IGNORECASE),
    re.compile(r".*FINE:.*", re.IGNORECASE),
    re.compile(r".*java\.app\..*", re.IGNORECASE),
    re.compile(r".*org\.openjdk\.nashorn.*", re.IGNORECASE)
]

def should_filter(line):
    if "Mod Loading has failed" in line:
        return True
    if line.count(" at ") > 1 and "java:" in line:
        return True
    for pat in GARBAGE_PATTERNS:
        if pat.match(line):
            return True
    return False

def format_console_line(line):
    lower = line.lower()
    if "error" in lower:
        return f'<font color="red">{line}</font>'
    elif "warn" in lower:
        return f'<font color="orange">{line}</font>'
    elif "info" in lower:
        return f'<font color="green">{line}</font>'
    else:
        return line

# ------------------ Minecraft Server Manager Backend ------------------
class MinecraftServerManager:
    def __init__(self, settings, jar_file):
        self.settings = settings
        self.server_dir = settings["server_dir"]
        self.jar_file = jar_file
        self.min_mem = settings["min_mem"]
        self.max_mem = settings["max_mem"]
        self.java_path = settings["java_path"]
        self.server_process = None
        self.running = False
        self.restart_flag = False
        self.output_callback = None
        self.output_buffer = []
        self.buffer_lock = threading.Lock()
        self.flush_interval = 500

    def set_output_callback(self, callback):
        self.output_callback = callback

    def start_server(self):
        if self.running:
            return
        cmd = [
            self.java_path,
            f"-Xms{self.min_mem}",
            f"-Xmx{self.max_mem}",
            "-jar",
            self.jar_file,
            "nogui"
        ]
        self._log("Starting server with command: " + " ".join(cmd))
        self.server_process = subprocess.Popen(
            cmd,
            cwd=self.server_dir,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1
        )
        self.running = True
        threading.Thread(target=self._read_output, daemon=True).start()
        threading.Thread(target=self._watch_process, daemon=True).start()
        self._start_buffer_flusher()

    def _start_buffer_flusher(self):
        def flush_buffer():
            with self.buffer_lock:
                if self.output_buffer and self.output_callback:
                    text = "\n".join(self.output_buffer)
                    self.output_callback(text)
                    self.output_buffer = []
        self.flusher = QTimer()
        self.flusher.timeout.connect(flush_buffer)
        self.flusher.start(self.flush_interval)

    def _read_output(self):
        for line in self.server_process.stdout:
            line = line.strip()
            if not should_filter(line):
                formatted = format_console_line(line)
                with self.buffer_lock:
                    self.output_buffer.append(formatted)

    def _watch_process(self):
        while self.running:
            if self.server_process.poll() is not None:
                self.running = False
                self._log("Server process terminated.")
                break
            time.sleep(1)

    def send_command(self, command):
        if self.server_process and self.server_process.stdin:
            try:
                self._log(f"> {command}")
                self.server_process.stdin.write(command + "\n")
                self.server_process.stdin.flush()
            except Exception as e:
                self._log(f"Error sending command: {e}")

    def stop_server(self):
        if self.server_process:
            self.send_command("stop")
            self.server_process.wait()
            self.running = False
            self._log("Server stopped.")

    def restart_server(self):
        if self.running:
            self.restart_flag = True
            self.send_command("stop")

    def _log(self, message):
        if self.output_callback:
            self.output_callback(format_console_line(message))
        else:
            print(message)

# ------------------ Jar Download Worker ------------------
class JarDownloadWorker(QThread):
    progress_signal = pyqtSignal(str)
    def __init__(self, url, download_dir):
        super().__init__()
        self.url = url
        self.download_dir = download_dir
    def run(self):
        try:
            local_filename = os.path.join(self.download_dir, self.url.split("/")[-1])
            self.progress_signal.emit(f"Downloading {local_filename} ...")
            r = requests.get(self.url, stream=True)
            with open(local_filename, 'wb') as f:
                for chunk in r.iter_content(chunk_size=8192):
                    if chunk:
                        f.write(chunk)
            self.progress_signal.emit(f"Downloaded: {local_filename}")
        except Exception as e:
            self.progress_signal.emit(f"Download error: {e}")

# ------------------ Fetch Vanilla Jars Worker ------------------
class FetchVanillaJarsWorker(QThread):
    finished_signal = pyqtSignal(list)
    error_signal = pyqtSignal(str)
    def run(self):
        jars = []
        try:
            r = requests.get("https://launchermeta.mojang.com/mc/game/version_manifest_v2.json")
            manifest = r.json()
            versions = manifest.get("versions", [])
            for v in versions:
                if v.get("type") == "release":
                    version_url = v.get("url")
                    vinfo = requests.get(version_url).json()
                    downloads = vinfo.get("downloads", {})
                    server_download = downloads.get("server", {})
                    if server_download:
                        version_name = v.get("id")
                        download_url = server_download.get("url")
                        jars.append((version_name, download_url))
            self.finished_signal.emit(jars)
        except Exception as e:
            self.error_signal.emit(str(e))

# ------------------ Stop Server Worker ------------------
class StopServerWorker(QThread):
    finished_signal = pyqtSignal()
    def __init__(self, manager):
        super().__init__()
        self.manager = manager
    def run(self):
        self.manager.stop_server()
        self.finished_signal.emit()

# ------------------ Java Detection Worker ------------------
class JavaDetectionWorker(QThread):
    result_signal = pyqtSignal(str)
    error_signal = pyqtSignal(str)
    def __init__(self, java_path):
        super().__init__()
        self.java_path = java_path
    def run(self):
        try:
            proc = subprocess.Popen([self.java_path, "-version"], stderr=subprocess.PIPE, stdout=subprocess.PIPE, text=True)
            out, err = proc.communicate(timeout=5)
            version_info = err if err else out
            self.result_signal.emit(version_info)
        except Exception as e:
            self.error_signal.emit(f"Error detecting Java version: {e}")

# ------------------ Plugin Fetching for Bukkit/Spigot ------------------
def fetch_spigot_plugins():
    plugins = []
    try:
        url = "https://www.spigotmc.org/resources/categories/spigot.4/"
        headers = {"User-Agent": "Mozilla/5.0"}
        r = requests.get(url, headers=headers)
        soup = BeautifulSoup(r.text, "html.parser")
        resource_elements = soup.find_all("h3", class_="resource-title")
        for elem in resource_elements:
            title = elem.get_text(strip=True)
            link = elem.find("a")["href"]
            plugins.append((title, link))
    except Exception as e:
        plugins.append(("Error fetching plugins", str(e)))
    return plugins

# ------------------ Main GUI Application ------------------
class ServerGUI(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Minecraft ArcLight Server Manager")
        self.resize(1200, 800)
        self.settings = load_settings()
        self.manager = None
        self.current_jar = ""
        self.init_ui()
        self.monitor_timer = QTimer()
        self.monitor_timer.timeout.connect(self.update_server_status)
        self.monitor_timer.start(2000)

    def init_ui(self):
        self.tabs = QTabWidget()
        self.setCentralWidget(self.tabs)
        self.control_tab = QWidget()
        self.init_control_tab()
        self.tabs.addTab(self.control_tab, "Server Control")
        self.admin_tab = QWidget()
        self.init_admin_tab()
        self.tabs.addTab(self.admin_tab, "Administration")
        self.creative_tab = QWidget()
        self.init_creative_tab()
        self.tabs.addTab(self.creative_tab, "Creative Tools")
        self.plugin_tab = QWidget()
        self.init_plugin_tab()
        self.tabs.addTab(self.plugin_tab, "Plugin Directory")
        self.downloader_tab = QWidget()
        self.init_downloader_tab()
        self.tabs.addTab(self.downloader_tab, "Jar Downloader")
        self.settings_tab = QWidget()
        self.init_settings_tab()
        self.tabs.addTab(self.settings_tab, "Settings")
        self.java_tab = QWidget()
        self.init_java_tab()
        self.tabs.addTab(self.java_tab, "Java Manager")
        self.file_explorer_tab = QWidget()
        self.init_file_explorer_tab()
        self.tabs.addTab(self.file_explorer_tab, "File Explorer")
        self.logs_tab = QTabWidget()
        self.init_logs_tab()
        self.tabs.addTab(self.logs_tab, "Logs")

    def update_server_status(self):
        if self.manager is None:
            self.status_label.setText("Status: No jar selected")
            self.start_btn.setEnabled(False)
            self.stop_btn.setEnabled(False)
        elif self.manager.running:
            self.status_label.setText("Status: Running")
            self.start_btn.setEnabled(False)
            self.stop_btn.setEnabled(True)
        else:
            self.status_label.setText("Status: Stopped")
            self.start_btn.setEnabled(True)
            self.stop_btn.setEnabled(False)

    def init_logs_tab(self):
        self.latest_log_edit = QTextEdit()
        self.latest_log_edit.setReadOnly(True)
        load_latest_btn = QPushButton("Load Latest Log")
        load_latest_btn.setToolTip("Load logs/latest.log")
        load_latest_btn.clicked.connect(self.load_latest_log)
        latest_layout = QVBoxLayout()
        latest_layout.addWidget(load_latest_btn)
        latest_layout.addWidget(self.latest_log_edit)
        latest_tab = QWidget()
        latest_tab.setLayout(latest_layout)
        self.error_log_edit = QTextEdit()
        self.error_log_edit.setReadOnly(True)
        error_tab = QWidget()
        error_layout = QVBoxLayout()
        error_layout.addWidget(self.error_log_edit)
        error_tab.setLayout(error_layout)
        self.warn_log_edit = QTextEdit()
        self.warn_log_edit.setReadOnly(True)
        warn_tab = QWidget()
        warn_layout = QVBoxLayout()
        warn_layout.addWidget(self.warn_log_edit)
        warn_tab.setLayout(warn_layout)
        self.info_log_edit = QTextEdit()
        self.info_log_edit.setReadOnly(True)
        info_tab = QWidget()
        info_layout = QVBoxLayout()
        info_layout.addWidget(self.info_log_edit)
        info_tab.setLayout(info_layout)
        self.mods_log_edit = QTextEdit()
        self.mods_log_edit.setReadOnly(True)
        mods_tab = QWidget()
        mods_layout = QVBoxLayout()
        mods_layout.addWidget(self.mods_log_edit)
        mods_tab.setLayout(mods_layout)
        self.logs_tab.addTab(latest_tab, "Latest")
        self.logs_tab.addTab(error_tab, "Errors")
        self.logs_tab.addTab(warn_tab, "Warns")
        self.logs_tab.addTab(info_tab, "Info")
        self.logs_tab.addTab(mods_tab, "Mods")

    def load_latest_log(self):
        log_path = os.path.join(self.settings["server_dir"], "logs", "latest.log")
        if os.path.exists(log_path):
            with open(log_path, "r", encoding="utf-8") as f:
                content = f.read()
            self.latest_log_edit.setPlainText(content)
        else:
            self.latest_log_edit.setPlainText("latest.log not found.")

    def init_control_tab(self):
        layout = QVBoxLayout()
        btn_layout = QHBoxLayout()
        self.start_btn = QPushButton("Start Server")
        self.start_btn.setToolTip("Start the Minecraft server")
        self.start_btn.clicked.connect(self.start_server)
        self.stop_btn = QPushButton("Stop Server")
        self.stop_btn.setToolTip("Stop the Minecraft server")
        self.stop_btn.clicked.connect(self.handle_stop_server)
        self.restart_btn = QPushButton("Restart Server")
        self.restart_btn.setToolTip("Restart the server (only works if server is running)")
        self.restart_btn.clicked.connect(self.restart_server)
        btn_layout.addWidget(self.start_btn)
        btn_layout.addWidget(self.stop_btn)
        btn_layout.addWidget(self.restart_btn)
        layout.addLayout(btn_layout)
        self.status_label = QLabel("Status: Unknown")
        layout.addWidget(self.status_label)
        cmd_layout = QHBoxLayout()
        self.cmd_input = QLineEdit()
        self.cmd_input.setPlaceholderText("Enter server command...")
        send_btn = QPushButton("Send Command")
        send_btn.setToolTip("Send a command to the server console")
        send_btn.clicked.connect(self.send_command)
        cmd_layout.addWidget(self.cmd_input)
        cmd_layout.addWidget(send_btn)
        layout.addLayout(cmd_layout)
        self.log_output = QTextEdit()
        self.log_output.setReadOnly(True)
        self.log_output.setLineWrapMode(QTextEdit.NoWrap)
        layout.addWidget(self.log_output)
        self.control_tab.setLayout(layout)

    def append_log(self, text):
        self.log_output.append(text)
        for line in text.splitlines():
            plain = re.sub(r'<\/?[^>]+>', '', line)
            lower = plain.lower()
            if "error" in lower:
                self.error_log_edit.append(plain)
            elif "warn" in lower:
                self.warn_log_edit.append(plain)
            elif "info" in lower:
                self.info_log_edit.append(plain)
            elif plain.startswith("re "):
                self.mods_log_edit.append(plain)

    def init_admin_tab(self):
        layout = QVBoxLayout()
        prop_group = QGroupBox("Server Properties")
        prop_layout = QVBoxLayout()
        self.prop_table = QTableWidget()
        self.prop_table.setColumnCount(2)
        self.prop_table.setHorizontalHeaderLabels(["Option", "Value"])
        self.prop_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        btn_load_props = QPushButton("Load Properties")
        btn_load_props.setToolTip("Load server.properties")
        btn_load_props.clicked.connect(self.load_properties)
        btn_save_props = QPushButton("Save Properties")
        btn_save_props.setToolTip("Save changes to server.properties")
        btn_save_props.clicked.connect(self.save_settings_method)
        prop_btn_layout = QHBoxLayout()
        prop_btn_layout.addWidget(btn_load_props)
        prop_btn_layout.addWidget(btn_save_props)
        prop_layout.addWidget(self.prop_table)
        prop_layout.addLayout(prop_btn_layout)
        prop_group.setLayout(prop_layout)
        layout.addWidget(prop_group)
        self.admin_tab.setLayout(layout)

    def load_properties(self):
        prop_path = os.path.join(self.settings["server_dir"], "server.properties")
        if os.path.exists(prop_path):
            self.prop_table.clearContents()
            with open(prop_path, "r") as f:
                lines = f.readlines()
            kv_lines = [line.strip() for line in lines if "=" in line and not line.strip().startswith("#")]
            self.prop_table.setRowCount(len(kv_lines))
            for i, line in enumerate(kv_lines):
                key, value = line.split("=", 1)
                key_item = QTableWidgetItem(key)
                value_item = QTableWidgetItem(value)
                self.prop_table.setItem(i, 0, key_item)
                self.prop_table.setItem(i, 1, value_item)
        else:
            QMessageBox.warning(self, "File Not Found", "server.properties not found.")

    def save_properties(self):
        prop_path = os.path.join(self.settings["server_dir"], "server.properties")
        try:
            rows = self.prop_table.rowCount()
            lines = []
            for i in range(rows):
                key = self.prop_table.item(i, 0).text() if self.prop_table.item(i, 0) else ""
                value = self.prop_table.item(i, 1).text() if self.prop_table.item(i, 1) else ""
                lines.append(f"{key}={value}")
            with open(prop_path, "w") as f:
                f.write("\n".join(lines))
            QMessageBox.information(self, "Saved", "server.properties saved successfully.")
        except Exception as e:
            QMessageBox.warning(self, "Error", str(e))

    def init_creative_tab(self):
        layout = QVBoxLayout()
        layout.addWidget(QLabel("Creative tools and utilities:"))
        self.creative_editor = QTextEdit()
        self.creative_editor.setPlaceholderText("Enter creative commands here...")
        btn_send = QPushButton("Send Creative Command")
        btn_send.setToolTip("Send creative command to server")
        btn_send.clicked.connect(lambda: self.send_command(self.creative_editor.toPlainText()))
        layout.addWidget(self.creative_editor)
        layout.addWidget(btn_send)
        self.creative_tab.setLayout(layout)

    def init_plugin_tab(self):
        layout = QVBoxLayout()
        self.plugin_tabs_inner = QTabWidget()
        spigot_tab = QWidget()
        spigot_layout = QVBoxLayout()
        info = QLabel("Click the button to open Spigot plugins website:")
        btn_spigot = QPushButton("Open Spigot Resources")
        btn_spigot.setToolTip("Visit Spigot Resources website")
        btn_spigot.clicked.connect(lambda: webbrowser.open("https://www.spigotmc.org/resources/"))
        spigot_layout.addWidget(info)
        spigot_layout.addWidget(btn_spigot)
        spigot_tab.setLayout(spigot_layout)
        self.plugin_tabs_inner.addTab(spigot_tab, "Bukkit/Spigot")
        for name, url in [("Forge", "https://www.curseforge.com/minecraft/mc-mods"),
                          ("Mohist", "https://mohistmc.com/"),
                          ("Arclight", "https://github.com/IzzelAliz/Arclight")]:
            tab = QWidget()
            vbox = QVBoxLayout()
            label = QLabel(f"Click the button to open {name} plugins website:")
            btn = QPushButton(f"Open {name} Website")
            btn.setToolTip(f"Visit {name} website")
            btn.clicked.connect(lambda checked, u=url: webbrowser.open(u))
            vbox.addWidget(label)
            vbox.addWidget(btn)
            tab.setLayout(vbox)
            self.plugin_tabs_inner.addTab(tab, name)
        layout.addWidget(self.plugin_tabs_inner)
        self.plugin_tab.setLayout(layout)

    def init_downloader_tab(self):
        layout = QVBoxLayout()
        dl_group = QGroupBox("Minecraft Server Jar Downloader")
        grid = QGridLayout()
        grid.addWidget(QLabel("Server Type:"), 0, 0)
        self.server_type_combo = QComboBox()
        self.server_type_combo.addItems(["Vanilla", "Forge", "Mohist", "Arclight", "Fabric"])
        grid.addWidget(self.server_type_combo, 0, 1)
        btn_fetch = QPushButton("Fetch Versions")
        btn_fetch.setToolTip("Fetch available server versions")
        btn_fetch.clicked.connect(self.fetch_available_jars)
        grid.addWidget(btn_fetch, 0, 2)
        grid.addWidget(QLabel("Download Directory:"), 1, 0)
        self.download_dir_input = QLineEdit(self.settings["server_dir"])
        grid.addWidget(self.download_dir_input, 1, 1)
        browse_btn = QPushButton("Browse")
        browse_btn.setToolTip("Select download directory")
        browse_btn.clicked.connect(self.browse_download_dir)
        grid.addWidget(browse_btn, 1, 2)
        dl_group.setLayout(grid)
        layout.addWidget(dl_group)
        self.jar_list = QListWidget()
        layout.addWidget(self.jar_list)
        btn_download = QPushButton("Download Selected Jar")
        btn_download.setToolTip("Download the selected jar file")
        btn_download.clicked.connect(self.download_selected_jar)
        layout.addWidget(btn_download)
        self.download_status = QTextEdit()
        self.download_status.setReadOnly(True)
        layout.addWidget(self.download_status)
        self.downloader_tab.setLayout(layout)

    def fetch_available_jars(self):
        server_type = self.server_type_combo.currentText()
        self.jar_list.clear()
        if server_type == "Vanilla":
            self.progress_dialog = QProgressDialog("Fetching Vanilla versions...", "Cancel", 0, 0, self)
            self.progress_dialog.setWindowModality(Qt.WindowModal)
            self.progress_dialog.show()
            self.fetch_worker = FetchVanillaJarsWorker()
            self.fetch_worker.finished_signal.connect(self.on_vanilla_fetched)
            self.fetch_worker.error_signal.connect(self.on_vanilla_fetch_error)
            self.fetch_worker.start()
        elif server_type == "Forge":
            try:
                r = requests.get("https://files.minecraftforge.net/maven/net/minecraftforge/forge/promotions_slim.json")
                data = r.json()
                for ver in [data.get("recommended"), data.get("latest")]:
                    if ver:
                        url = f"https://files.minecraftforge.net/maven/net/minecraftforge/forge/{ver}/forge-{ver}-installer.jar"
                        item = QListWidgetItem(f"Forge {ver}")
                        item.setData(1000, url)
                        self.jar_list.addItem(item)
                self.download_status.append(f"Fetched Forge versions.")
            except Exception as e:
                self.download_status.append(f"Error fetching Forge versions: {e}")
        elif server_type == "Mohist":
            try:
                versions = ["1.7.10", "1.16.5", "1.20.1"]
                for ver in versions:
                    url = f"https://mohistmc.com/downloadSoftware?project=mohist&projectVersion={ver}"
                    item = QListWidgetItem(f"Mohist {ver}")
                    item.setData(1000, url)
                    self.jar_list.addItem(item)
                self.download_status.append("Fetched Mohist versions.")
            except Exception as e:
                self.download_status.append(f"Error fetching Mohist versions: {e}")
        elif server_type == "Arclight":
            try:
                r = requests.get("https://api.github.com/repos/IzzelAliz/Arclight/releases")
                releases = r.json()
                for rel in releases:
                    tag = rel.get("tag_name")
                    assets = rel.get("assets", [])
                    for asset in assets:
                        name = asset.get("name")
                        if name.endswith(".jar"):
                            download_url = asset.get("browser_download_url")
                            item = QListWidgetItem(f"Arclight {tag} - {name}")
                            item.setData(1000, download_url)
                            self.jar_list.addItem(item)
                            break
                self.download_status.append("Fetched Arclight versions.")
            except Exception as e:
                self.download_status.append(f"Error fetching Arclight versions: {e}")
        elif server_type == "Fabric":
            try:
                url = "https://maven.fabricmc.net/net/fabricmc/fabric-installer/0.14.21/fabric-installer-0.14.21.jar"
                item = QListWidgetItem("Fabric 0.14.21")
                item.setData(1000, url)
                self.jar_list.addItem(item)
                self.download_status.append("Fetched Fabric versions.")
            except Exception as e:
                self.download_status.append(f"Error fetching Fabric versions: {e}")

    def on_vanilla_fetched(self, jars):
        self.progress_dialog.close()
        for version_name, download_url in jars:
            item = QListWidgetItem(f"{version_name}")
            item.setData(1000, download_url)
            self.jar_list.addItem(item)
        self.download_status.append("Fetched Vanilla versions.")

    def on_vanilla_fetch_error(self, error):
        self.progress_dialog.close()
        self.download_status.append(f"Error fetching Vanilla versions: {error}")

    def download_selected_jar(self):
        selected_item = self.jar_list.currentItem()
        if selected_item:
            url = selected_item.data(1000)
            download_dir = self.download_dir_input.text().strip()
            if url and download_dir:
                self.download_status.append(f"Starting download from {url} ...")
                self.downloader_worker = JarDownloadWorker(url, download_dir)
                self.downloader_worker.progress_signal.connect(self.download_status.append)
                self.downloader_worker.start()
            else:
                self.download_status.append("Invalid URL or download directory.")
        else:
            self.download_status.append("No jar selected.")

    def init_settings_tab(self):
        layout = QVBoxLayout()
        grid = QGridLayout()
        grid.addWidget(QLabel("Java Executable:"), 0, 0)
        self.java_path_input = QLineEdit(self.settings["java_path"])
        self.java_path_input.editingFinished.connect(self.auto_save_settings)
        grid.addWidget(self.java_path_input, 0, 1)
        btn_browse_java = QPushButton("Browse")
        btn_browse_java.setToolTip("Select Java executable")
        btn_browse_java.clicked.connect(self.select_java)
        grid.addWidget(btn_browse_java, 0, 2)
        grid.addWidget(QLabel("Min Memory:"), 1, 0)
        self.min_mem_input = QLineEdit(self.settings["min_mem"])
        self.min_mem_input.editingFinished.connect(self.auto_save_settings)
        grid.addWidget(self.min_mem_input, 1, 1)
        grid.addWidget(QLabel("Max Memory:"), 2, 0)
        self.max_mem_input = QLineEdit(self.settings["max_mem"])
        self.max_mem_input.editingFinished.connect(self.auto_save_settings)
        grid.addWidget(self.max_mem_input, 2, 1)
        grid.addWidget(QLabel("Server Directory:"), 3, 0)
        self.server_dir_input = QLineEdit(self.settings["server_dir"])
        self.server_dir_input.editingFinished.connect(self.auto_save_settings)
        grid.addWidget(self.server_dir_input, 3, 1)
        btn_browse_dir = QPushButton("Browse")
        btn_browse_dir.setToolTip("Select server directory")
        btn_browse_dir.clicked.connect(self.select_server_dir)
        grid.addWidget(btn_browse_dir, 3, 2)
        grid.addWidget(QLabel("Server Jar:"), 4, 0)
        self.server_jar_input = QLineEdit(self.settings.get("server_jar", ""))
        self.server_jar_input.editingFinished.connect(self.auto_save_settings)
        grid.addWidget(self.server_jar_input, 4, 1)
        btn_select_jar = QPushButton("Select Jar")
        btn_select_jar.setToolTip("Select the server jar file")
        btn_select_jar.clicked.connect(self.select_jar)
        grid.addWidget(btn_select_jar, 4, 2)
        btn_save = QPushButton("Save Settings")
        btn_save.setToolTip("Save settings")
        btn_save.clicked.connect(self.save_settings_method)
        grid.addWidget(btn_save, 5, 0, 1, 3)
        layout.addLayout(grid)
        self.settings_tab.setLayout(layout)

    def auto_save_settings(self):
        self.settings["java_path"] = self.java_path_input.text().strip()
        self.settings["min_mem"] = self.min_mem_input.text().strip()
        self.settings["max_mem"] = self.max_mem_input.text().strip()
        self.settings["server_dir"] = self.server_dir_input.text().strip()
        self.settings["server_jar"] = self.server_jar_input.text().strip()
        save_settings(self.settings)
        if hasattr(self, 'file_model'):
            self.file_model.setRootPath(self.settings["server_dir"])
            self.refresh_file_explorer()

    def select_server_dir(self):
        directory = QFileDialog.getExistingDirectory(self, "Select Server Directory", self.settings["server_dir"])
        if directory:
            self.settings["server_dir"] = directory
            self.server_dir_input.setText(directory)
            if hasattr(self, 'file_model'):
                self.file_model.setRootPath(directory)
                self.refresh_file_explorer()
            self.auto_save_settings()

    def init_java_tab(self):
        layout = QVBoxLayout()
        detect_group = QGroupBox("Installed Java")
        detect_layout = QVBoxLayout()
        self.java_version_output = QTextEdit()
        self.java_version_output.setReadOnly(True)
        btn_detect = QPushButton("Detect Installed Java Version")
        btn_detect.setToolTip("Run 'java -version'")
        btn_detect.clicked.connect(self.detect_java_version)
        detect_layout.addWidget(btn_detect)
        detect_layout.addWidget(self.java_version_output)
        detect_group.setLayout(detect_layout)
        layout.addWidget(detect_group)
        download_group = QGroupBox("Download Popular Java Versions")
        download_layout = QVBoxLayout()
        self.java_download_list = QListWidget()
        java_downloads = [
            ("Temurin 8", "https://adoptium.net/temurin/releases/?version=8"),
            ("Temurin 11", "https://adoptium.net/temurin/releases/?version=11"),
            ("Temurin 17", "https://adoptium.net/temurin/releases/?version=17")
        ]
        for name, link in java_downloads:
            item = QListWidgetItem(name)
            item.setData(1000, link)
            self.java_download_list.addItem(item)
        self.java_download_list.itemDoubleClicked.connect(lambda item: webbrowser.open(item.data(1000)))
        download_layout.addWidget(QLabel("Double-click to open download link:"))
        download_layout.addWidget(self.java_download_list)
        download_group.setLayout(download_layout)
        layout.addWidget(download_group)
        self.java_tab.setLayout(layout)

    def detect_java_version(self):
        self.java_progress = QProgressDialog("Detecting Java version...", "Cancel", 0, 0, self)
        self.java_progress.setWindowModality(Qt.WindowModal)
        self.java_progress.show()
        self.java_worker = JavaDetectionWorker(self.java_path_input.text().strip())
        self.java_worker.result_signal.connect(self.on_java_detected)
        self.java_worker.error_signal.connect(self.on_java_error)
        self.java_worker.start()

    def on_java_detected(self, result):
        self.java_progress.close()
        self.java_version_output.setPlainText(result)

    def on_java_error(self, error):
        self.java_progress.close()
        self.java_version_output.setPlainText(error)

    def init_file_explorer_tab(self):
        layout = QVBoxLayout()
        self.file_model = QFileSystemModel()
        self.file_model.setRootPath(self.settings["server_dir"])
        self.file_view = QTreeView()
        self.file_view.setModel(self.file_model)
        self.file_view.setRootIndex(self.file_model.index(self.settings["server_dir"]))
        layout.addWidget(self.file_view)
        refresh_btn = QPushButton("Refresh")
        refresh_btn.setToolTip("Refresh file explorer")
        refresh_btn.clicked.connect(self.refresh_file_explorer)
        layout.addWidget(refresh_btn)
        self.file_explorer_tab.setLayout(layout)

    def refresh_file_explorer(self):
        self.file_view.setRootIndex(self.file_model.index(self.settings["server_dir"]))

    def select_java(self):
        path, _ = QFileDialog.getOpenFileName(self, "Select Java Executable", "", "Executables (*.exe);;All Files (*)")
        if path:
            self.settings["java_path"] = path
            self.java_path_input.setText(path)
            self.auto_save_settings()

    def select_jar(self):
        jar_path, _ = QFileDialog.getOpenFileName(self, "Select Server Jar", self.settings["server_dir"], "Jar Files (*.jar)")
        if jar_path:
            self.current_jar = os.path.basename(jar_path)
            self.server_jar_input.setText(self.current_jar)
            self.settings["server_jar"] = jar_path
            self.auto_save_settings()
            self.manager = MinecraftServerManager(self.settings, jar_path)
            self.manager.set_output_callback(self.append_log)
            if hasattr(self, 'file_model'):
                self.file_model.setRootPath(self.settings["server_dir"])
                self.refresh_file_explorer()

    def start_server(self):
        if self.manager and not self.manager.running:
            self.append_log("Starting server...")
            self.manager.start_server()
        else:
            self.append_log("No jar selected or server already running!")

    def handle_stop_server(self):
        if self.manager and self.manager.running:
            self.append_log("Stopping server...")
            self.stop_progress = QProgressDialog("Stopping server...", "Cancel", 0, 0, self)
            self.stop_progress.setWindowModality(Qt.WindowModal)
            self.stop_progress.show()
            self.stop_worker = StopServerWorker(self.manager)
            self.stop_worker.finished_signal.connect(self.on_server_stopped)
            self.stop_worker.start()
        else:
            self.append_log("Server not running!")

    def on_server_stopped(self):
        self.stop_progress.close()
        self.append_log("Server stopped!")

    def restart_server(self):
        if self.manager and self.manager.running:
            self.append_log("Restarting server...")
            self.manager.restart_server()
        else:
            self.append_log("Server not running!")

    def send_command(self, cmd=None):
        command = cmd if cmd is not None else self.cmd_input.text().strip()
        if command and self.manager and self.manager.running:
            self.append_log(f"> {command}")
            self.manager.send_command(command)
            self.cmd_input.clear()
        else:
            self.append_log("Server not running or empty command.")

    def browse_download_dir(self):
        directory = QFileDialog.getExistingDirectory(self, "Select Download Directory", self.settings["server_dir"])
        if directory:
            self.download_dir_input.setText(directory)

    def save_settings_method(self):
        self.auto_save_settings()
        QMessageBox.information(self, "Settings Saved", "Settings have been saved.")

if __name__ == "__main__":
    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    qss = """
    QWidget {
        font-size: 14px;
        color: #dcdcdc;
    }
    QMainWindow {
        background-color: #2e2e2e;
    }
    QTabWidget::pane {
        border: 1px solid #444;
    }
    QTabBar::tab {
        background: #444;
        color: #dcdcdc;
        padding: 8px;
        margin: 2px;
    }
    QTabBar::tab:selected {
        background: #2a82da;
    }
    QPushButton {
        background-color: #2a82da;
        border: none;
        color: white;
        padding: 5px;
    }
    QPushButton:hover {
        background-color: #1c5b9e;
    }
    QTextEdit, QLineEdit, QListWidget, QTreeView, QTableWidget {
        background-color: #1e1e1e;
        color: #dcdcdc;
    }
    QLabel {
        color: #dcdcdc;
    }
    """
    app.setStyleSheet(qss)
    window = ServerGUI()
    window.show()
    sys.exit(app.exec_())
