"""Session Keeper for Claude Code — GUI (PySide6).

실행:  pythonw app.py            (일반 실행)
       pythonw app.py --startup  (시작프로그램에서 호출: 트레이로 시작 + 자동 복원 확인)
"""
from __future__ import annotations

import os
import sys
import threading
import time
from pathlib import Path

import psutil
from PySide6.QtCore import QObject, Qt, QTimer, Signal
from PySide6.QtGui import QAction, QColor, QFont, QIcon, QPainter, QPixmap
from PySide6.QtNetwork import QLocalServer, QLocalSocket
from PySide6.QtWidgets import (
    QApplication, QCheckBox, QComboBox, QFormLayout, QHBoxLayout, QHeaderView, QInputDialog,
    QLabel, QLineEdit, QListWidget, QListWidgetItem, QMainWindow, QMenu, QMessageBox,
    QPlainTextEdit, QPushButton, QSpinBox, QSplitter, QSystemTrayIcon, QTabWidget, QToolBar,
    QTreeWidget, QTreeWidgetItem, QVBoxLayout, QWidget,
)

sys.path.insert(0, str(Path(__file__).parent))
import core  # noqa: E402
from version import __version__  # noqa: E402

SERVER_NAME = "ClaudeSessionKeeper-single"
ID_SRC_LABEL = {"hook": "훅", "cmdline": "인자", "guess": "추정", "none": "-"}


def make_icon() -> QIcon:
    pm = QPixmap(64, 64)
    pm.fill(Qt.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.Antialiasing)
    p.setBrush(QColor("#3B6EA8"))
    p.setPen(Qt.NoPen)
    p.drawRoundedRect(4, 4, 56, 56, 14, 14)
    p.setPen(QColor("white"))
    f = QFont("Segoe UI", 26, QFont.Bold)
    p.setFont(f)
    p.drawText(pm.rect(), Qt.AlignCenter, "K")
    p.end()
    return QIcon(pm)


class Bus(QObject):
    log = Signal(str)
    refreshed = Signal(list, list)
    request_refresh = Signal()


class MainWindow(QMainWindow):
    def __init__(self, startup: bool):
        super().__init__()
        core.ensure_dirs()
        core.prune_live_records()
        self.cfg = core.load_config()
        self.startup = startup
        self.quitting = False
        self.bus = Bus()
        self.bus.log.connect(self._append_log)
        self.bus.refreshed.connect(self._fill_running)
        self.bus.request_refresh.connect(lambda: QTimer.singleShot(2500, self.refresh_running))
        self._refreshing = False
        self.pending_timer: QTimer | None = None

        self.setWindowTitle(f"Session Keeper for Claude Code {__version__}"
                            + (" (Store)" if core.IS_PACKAGED else ""))
        self.setWindowIcon(make_icon())
        self.resize(1100, 640)

        self._build_toolbar()
        self.tabs = QTabWidget()
        self.tabs.addTab(self._build_running_tab(), "실행 중")
        self.tabs.addTab(self._build_snap_tab(), "스냅샷")
        self.tabs.addTab(self._build_settings_tab(), "설정")
        self.log_view = QPlainTextEdit(readOnly=True)
        self.tabs.addTab(self.log_view, "로그")
        self.setCentralWidget(self.tabs)
        self.status = QLabel()
        self.statusBar().addWidget(self.status)

        self._build_tray()

        self.refresh_timer = QTimer(self, interval=5000,
                                    timeout=lambda: self.isVisible() and self.refresh_running())
        self.refresh_timer.start()
        self.autosave_timer = QTimer(self, timeout=self.autosave)
        self._apply_autosave_interval()

        self.refresh_running()
        self.reload_snapshots()
        QTimer.singleShot(1500, self.startup_checks)

    # ─────────────── UI 구성 ───────────────
    def _build_toolbar(self):
        tb = QToolBar("main", movable=False)
        self.addToolBar(tb)
        for text, slot in [
            ("새로고침", self.refresh_running),
            ("스냅샷 저장", self.snapshot_named),
            ("스냅샷 → 재부팅", lambda: self.snapshot_and_power("restart")),
            ("스냅샷 → 시스템 종료", lambda: self.snapshot_and_power("shutdown")),
            ("재부팅/종료 취소", self.cancel_power),
        ]:
            act = QAction(text, self)
            act.triggered.connect(slot)
            tb.addAction(act)

    def _build_running_tab(self) -> QWidget:
        self.run_tree = QTreeWidget()
        self.run_tree.setHeaderLabels(["항목", "폴더 / 위치", "세션 ID", "ID 출처", "제목", "셸", "시작"])
        self.run_tree.header().setSectionResizeMode(QHeaderView.Interactive)
        for i, w in enumerate([150, 300, 110, 60, 280, 110, 120]):
            self.run_tree.setColumnWidth(i, w)
        self.run_tree.setContextMenuPolicy(Qt.CustomContextMenu)
        self.run_tree.customContextMenuRequested.connect(self._running_menu)
        hint = QLabel("ID 출처가 '추정'인 세션은 같은 폴더에서 여러 개 실행 중이면 틀릴 수 있습니다. "
                      "설정 탭에서 훅을 설치하면 정확해집니다 (훅 설치 후 새로 시작/재개한 세션부터 적용).")
        hint.setWordWrap(True)
        hint.setStyleSheet("color: gray;")
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.addWidget(self.run_tree)
        lay.addWidget(hint)
        return w

    def _build_snap_tab(self) -> QWidget:
        self.snap_list = QListWidget()
        self.snap_list.currentItemChanged.connect(self._show_snap_detail)
        self.snap_detail = QTreeWidget()
        self.snap_detail.setHeaderLabels(["항목", "폴더 / 위치", "세션 ID", "제목"])
        for i, w in enumerate([170, 320, 110, 300]):
            self.snap_detail.setColumnWidth(i, w)

        btn_restore = QPushButton("체크한 항목 복원")
        btn_restore.clicked.connect(self.restore_checked)
        btn_rename = QPushButton("이름 변경")
        btn_rename.clicked.connect(self.rename_snapshot)
        btn_delete = QPushButton("삭제")
        btn_delete.clicked.connect(self.delete_snapshot)
        btn_folder = QPushButton("폴더 열기")
        btn_folder.clicked.connect(lambda: os.startfile(core.SNAP_DIR))
        row = QHBoxLayout()
        for b in (btn_restore, btn_rename, btn_delete, btn_folder):
            row.addWidget(b)
        row.addStretch()

        right = QWidget()
        rl = QVBoxLayout(right)
        rl.setContentsMargins(0, 0, 0, 0)
        rl.addWidget(self.snap_detail)
        rl.addLayout(row)
        split = QSplitter()
        split.addWidget(self.snap_list)
        split.addWidget(right)
        split.setSizes([300, 800])
        return split

    def _build_settings_tab(self) -> QWidget:
        c = self.cfg
        self.s_autosave = QSpinBox(minimum=0, maximum=120, suffix=" 분 (0=끔)", value=c["autosave_minutes"])
        self.s_terminal = QComboBox()
        self.s_terminal.addItem("Windows Terminal 탭으로 묶기", "wt")
        self.s_terminal.addItem("개별 콘솔 창", "console")
        self.s_terminal.setCurrentIndex(0 if c["terminal"] == "wt" else 1)
        self.s_shell = QComboBox()
        self.s_shell.addItem("PowerShell 7 (pwsh)", "pwsh")
        self.s_shell.addItem("Windows PowerShell 5.1", "powershell")
        self.s_shell.setCurrentIndex(0 if c["shell"] == "pwsh" else 1)
        self.s_cmd = QLineEdit(c["claude_cmd"])
        self.s_extra = QLineEdit(c["extra_args"])
        self.s_extra.setPlaceholderText("예: --model opus")
        self.s_delay = QSpinBox(minimum=0, maximum=300, suffix=" 초", value=c["restore_delay_sec"])
        self.s_desk = QCheckBox("Claude Desktop도 실행·창 배치 복원", checked=c["restore_desktop"])
        self.s_desk_launch = QLineEdit(c["desktop_launch"])
        self.s_desk_launch.setPlaceholderText("비우면 자동 탐지 (실행 안 되면 claude.exe 경로 지정)")
        self.s_min = QCheckBox("시작프로그램 실행 시 트레이로 시작", checked=c["start_minimized"])
        self.s_unexpected = QComboBox()
        self.s_unexpected.addItem("복원할지 묻기", "ask")
        self.s_unexpected.addItem("묻지 않고 자동 복원 (대기 중 트레이에서 취소 가능)", "auto")
        self.s_unexpected.addItem("아무것도 하지 않기 (자동저장만 유지)", "off")
        self.s_unexpected.setCurrentIndex(max(0, self.s_unexpected.findData(c["unexpected_reboot"])))
        self.s_unexpected.setToolTip("앱의 '스냅샷 → 재부팅'이 아닌 재부팅(시작 메뉴 다시 시작, Windows 업데이트, 정전 등) 뒤의 동작.\n"
                                     "'스냅샷 → 재부팅'으로 한 재부팅은 이 설정과 상관없이 자동 복원합니다.")
        self.s_startup = QCheckBox("Windows 시작 시 실행 (재부팅 후 자동 복원에 필요)")
        self.s_startup.setChecked(core.is_startup_enabled())
        if core.startup_managed_by_os():
            self.s_startup.setEnabled(False)
            self.s_startup.setText("Windows 시작 시 실행 — 스토어 버전은 작업 관리자 > 시작 앱에서 켜고 끕니다")

        self.hook_label = QLabel()
        self.hook_btn = QPushButton()
        self.hook_btn.clicked.connect(self.toggle_hook)
        self._update_hook_ui()
        hook_row = QHBoxLayout()
        hook_row.addWidget(self.hook_label)
        hook_row.addWidget(self.hook_btn)
        hook_row.addStretch()

        save = QPushButton("설정 저장")
        save.clicked.connect(self.save_settings)

        form = QFormLayout()
        form.addRow("자동 스냅샷 주기", self.s_autosave)
        form.addRow("복원 방식", self.s_terminal)
        form.addRow("셸", self.s_shell)
        form.addRow("claude 명령", self.s_cmd)
        form.addRow("추가 인자", self.s_extra)
        form.addRow("부팅 후 복원 대기", self.s_delay)
        form.addRow("", self.s_desk)
        form.addRow("Desktop 실행 경로", self.s_desk_launch)
        form.addRow("", self.s_min)
        form.addRow("예고 없는 재부팅 뒤", self.s_unexpected)
        form.addRow("", self.s_startup)
        form.addRow("세션 ID 훅", hook_row)
        form.addRow("", save)
        form.addRow("데이터 폴더", QLabel(str(core.DATA_DIR)))
        form.addRow("버전", QLabel(__version__ + (" · Microsoft Store" if core.IS_PACKAGED else "")))
        w = QWidget()
        w.setLayout(form)
        return w

    def _build_tray(self):
        self.tray = QSystemTrayIcon(make_icon(), self)
        self.tray.setToolTip("Session Keeper for Claude Code")
        menu = QMenu()
        for text, slot in [
            ("열기", self.show_normal),
            ("지금 스냅샷", self.snapshot_named),
            ("스냅샷 → 재부팅", lambda: self.snapshot_and_power("restart")),
            ("최근 스냅샷 복원", self.restore_latest),
        ]:
            menu.addAction(text, slot)
        self.cancel_pending_act = menu.addAction("예약된 자동 복원 취소", self.cancel_pending_restore)
        self.cancel_pending_act.setVisible(False)
        menu.addSeparator()
        menu.addAction("완전 종료", self.quit_app)
        self.tray.setContextMenu(menu)
        self.tray.activated.connect(
            lambda r: self.show_normal() if r == QSystemTrayIcon.Trigger else None)
        self.tray.show()

    # ─────────────── 로그 ───────────────
    def log(self, msg: str):
        self.bus.log.emit(msg)

    def _append_log(self, msg: str):
        self.log_view.appendPlainText(time.strftime("[%H:%M:%S] ") + msg)
        self.status.setText(msg)
        core.append_log_file(msg)

    # ─────────────── 실행 중 목록 ───────────────
    def refresh_running(self):
        if self._refreshing:
            return
        self._refreshing = True

        def work():
            try:
                sessions = core.list_code_sessions()
                procs = core.desktop_processes()
                wins = core.list_desktop_windows({p.pid for p in procs})
                self.bus.refreshed.emit(sessions, [bool(procs)] + wins)
            except Exception as e:  # noqa: BLE001
                self.log(f"탐지 오류: {e}")
            finally:
                self._refreshing = False

        threading.Thread(target=work, daemon=True).start()

    def _fill_running(self, sessions: list, desk: list):
        running, wins = desk[0], desk[1:]
        t = self.run_tree
        t.clear()
        g1 = QTreeWidgetItem([f"Claude Code 세션 ({len(sessions)})"])
        for s in sorted(sessions, key=lambda s: s.started):
            mode = core.resume_mode(core.asdict(s))
            title = s.title or ("(대화 없음: 아직 메시지를 보내지 않음)" if mode == "new" else "")
            it = QTreeWidgetItem([
                f"PID {s.pid}", s.cwd, (s.session_id or "")[:8], ID_SRC_LABEL[s.id_source],
                title, f"{s.shell} / {s.host}", time.strftime("%m-%d %H:%M", time.localtime(s.started)),
            ])
            it.setData(0, Qt.UserRole, s)
            it.setToolTip(2, s.session_id or "")
            if s.id_source == "guess":
                it.setForeground(3, QColor("#c08000"))
            g1.addChild(it)
        state = "실행 중" if running else "꺼짐"
        g2 = QTreeWidgetItem([f"Claude Desktop ({state}, 창 {len(wins)})"])
        for w in wins:
            l, tp, r, b = w.rect
            g2.addChild(QTreeWidgetItem([w.title, f"{l},{tp}  {r - l}×{b - tp}  [{w.show}]"]))
        t.addTopLevelItems([g1, g2])
        t.expandAll()
        self.tray.setToolTip(f"Session Keeper for Claude Code — Code {len(sessions)} · Desktop 창 {len(wins)}")

    def _running_menu(self, pos):
        it = self.run_tree.itemAt(pos)
        s = it.data(0, Qt.UserRole) if it else None
        if not isinstance(s, core.CodeSession):
            return
        m = QMenu(self)
        cb = QApplication.clipboard()
        if s.session_id:
            m.addAction("세션 ID 복사", lambda: cb.setText(s.session_id))
        m.addAction("재개 명령 복사", lambda: cb.setText(
            f'cd "{s.cwd}"; {core.resume_command(self.cfg, core.asdict(s))}'))
        m.addAction("폴더 열기", lambda: os.startfile(s.cwd))
        m.addSeparator()
        m.addAction("세션 종료 (claude 프로세스만)", lambda: self.kill_session(s))
        m.exec(self.run_tree.viewport().mapToGlobal(pos))

    def kill_session(self, s):
        if QMessageBox.question(self, "세션 종료", f"PID {s.pid} ({s.cwd})를 종료할까요?\n"
                                "대화 기록은 디스크에 남아 있어 나중에 --resume 가능합니다.") != QMessageBox.Yes:
            return
        try:
            psutil.Process(s.pid).terminate()
            self.log(f"종료: PID {s.pid}")
        except psutil.Error as e:
            self.log(f"종료 실패: {e}")
        QTimer.singleShot(800, self.refresh_running)

    # ─────────────── 스냅샷 ───────────────
    def reload_snapshots(self, select: Path | None = None):
        self.snap_list.clear()
        for path, snap in core.list_snapshots():
            label = snap.get("name", path.stem)
            if path.name == core.AUTOSAVE_FILE:
                label = "⟳ 자동저장"
            when = time.strftime("%m-%d %H:%M", time.localtime(snap.get("created", 0)))
            it = QListWidgetItem(f"{label}\n  {when} · {core.snapshot_summary(snap)}")
            it.setData(Qt.UserRole, (path, snap))
            self.snap_list.addItem(it)
            if select and path == select:
                self.snap_list.setCurrentItem(it)
        if not self.snap_list.currentItem() and self.snap_list.count():
            self.snap_list.setCurrentRow(0)

    def _show_snap_detail(self, cur, _prev=None):
        t = self.snap_detail
        t.clear()
        if not cur:
            return
        _, snap = cur.data(Qt.UserRole)
        g1 = QTreeWidgetItem([f"Claude Code 세션 ({len(snap.get('sessions', []))})"])
        g1.setFlags(g1.flags() | Qt.ItemIsUserCheckable | Qt.ItemIsAutoTristate)
        g1.setCheckState(0, Qt.Checked)
        for s in snap.get("sessions", []):
            mode = core.resume_mode(s)
            sid_text = s["session_id"][:12] if mode == "resume" else core.RESUME_LABEL[mode]
            it = QTreeWidgetItem([Path(s["cwd"]).name or s["cwd"], s["cwd"], sid_text, s.get("title", "")])
            it.setToolTip(2, f"복원 명령: {core.resume_command(self.cfg, s)}")
            it.setFlags(it.flags() | Qt.ItemIsUserCheckable)
            it.setCheckState(0, Qt.Checked)
            it.setData(0, Qt.UserRole, s)
            g1.addChild(it)
        d = snap.get("desktop", {})
        g2 = QTreeWidgetItem([f"Claude Desktop ({'실행' if d.get('running') else '꺼짐'}, "
                              f"창 {len(d.get('windows', []))})"])
        g2.setFlags(g2.flags() | Qt.ItemIsUserCheckable)
        g2.setCheckState(0, Qt.Checked if d.get("running") and self.cfg["restore_desktop"] else Qt.Unchecked)
        g2.setData(0, Qt.UserRole, "desktop")
        for w in d.get("windows", []):
            l, tp, r, b = w["rect"]
            g2.addChild(QTreeWidgetItem([w["title"], f"{l},{tp}  {r - l}×{b - tp}  [{w['show']}]"]))
        t.addTopLevelItems([g1, g2])
        t.expandAll()

    def _current_snap(self):
        it = self.snap_list.currentItem()
        return it.data(Qt.UserRole) if it else (None, None)

    def snapshot_named(self):
        name, ok = QInputDialog.getText(self, "스냅샷 저장", "이름 (비우면 날짜/시간):")
        if not ok:
            return
        path = self.save_snapshot(name.strip())
        self.reload_snapshots(select=path)

    def save_snapshot(self, name: str = "", filename: str | None = None) -> Path:
        snap = core.take_snapshot(name)
        path = core.save_snapshot(snap, filename)
        self.log(f"스냅샷 저장: {snap['name']} ({core.snapshot_summary(snap)})")
        return path

    def autosave(self):
        def work():
            try:
                snap = core.take_snapshot("자동저장")
                core.save_snapshot(snap, core.AUTOSAVE_FILE)
            except Exception as e:  # noqa: BLE001
                self.log(f"자동저장 실패: {e}")
        threading.Thread(target=work, daemon=True).start()

    def _apply_autosave_interval(self):
        m = int(self.cfg["autosave_minutes"])
        if m > 0:
            self.autosave_timer.start(m * 60_000)
        else:
            self.autosave_timer.stop()

    def rename_snapshot(self):
        path, snap = self._current_snap()
        if not path or path.name == core.AUTOSAVE_FILE:
            return
        name, ok = QInputDialog.getText(self, "이름 변경", "새 이름:", text=snap.get("name", ""))
        if ok and name.strip():
            snap["name"] = name.strip()
            core.save_snapshot(snap, path.name)
            self.reload_snapshots(select=path)

    def delete_snapshot(self):
        path, snap = self._current_snap()
        if path and QMessageBox.question(self, "삭제", f"'{snap.get('name')}' 스냅샷을 삭제할까요?") == QMessageBox.Yes:
            path.unlink(missing_ok=True)
            self.reload_snapshots()

    def restore_checked(self):
        path, snap = self._current_snap()
        if not snap:
            return
        sessions, desktop = [], False
        for i in range(self.snap_detail.topLevelItemCount()):
            g = self.snap_detail.topLevelItem(i)
            if g.data(0, Qt.UserRole) == "desktop":
                desktop = g.checkState(0) == Qt.Checked
                continue
            for j in range(g.childCount()):
                c = g.child(j)
                if c.checkState(0) == Qt.Checked:
                    sessions.append(c.data(0, Qt.UserRole))
        self.run_restore(snap, sessions, desktop)

    def restore_latest(self):
        items = [(p, s) for p, s in core.list_snapshots() if not core.snapshot_is_empty(s)]
        if items:
            self.run_restore(items[0][1])
        else:
            self.log("복원할 스냅샷이 없습니다.")

    def run_restore(self, snap: dict, sessions=None, desktop=None):
        self.log(f"복원 시작: {snap.get('name')}")
        cfg = dict(self.cfg)

        def work():
            try:
                core.restore_snapshot(snap, cfg, self.log, sessions, desktop)
            except Exception as e:  # noqa: BLE001
                self.log(f"복원 오류: {e}")
            self.bus.request_refresh.emit()

        threading.Thread(target=work, daemon=True).start()

    # ─────────────── 재부팅 / 종료 ───────────────
    def snapshot_and_power(self, kind: str):
        label = "재부팅" if kind == "restart" else "시스템 종료"
        if not core.startup_managed_by_os() and not core.is_startup_enabled():
            r = QMessageBox.question(
                self, label, "부팅 후 자동 복원을 하려면 'Windows 시작 시 실행'이 필요합니다.\n지금 켤까요?")
            if r == QMessageBox.Yes:
                core.set_startup(True)
                self.s_startup.setChecked(True)
        snap = core.take_snapshot(f"{label} 전 ({time.strftime('%m-%d %H:%M')})")
        msg = (f"현재 상태를 저장하고 10초 후 {label}합니다.\n\n{core.snapshot_summary(snap)}\n\n"
               "저장 안 된 다른 작업(에디터, 브라우저 등)이 있으면 먼저 저장하세요.\n"
               "응답 생성 중인 Claude Code 세션은 그 응답이 끊길 수 있습니다.")
        if QMessageBox.warning(self, label, msg, QMessageBox.Ok | QMessageBox.Cancel) != QMessageBox.Ok:
            return
        path = core.save_snapshot(snap)
        core.mark_pending_restore(path)
        self.reload_snapshots(select=path)
        self.log(f"{label} 예약 (복원 대기: {path.name})")
        core.schedule_power(kind, 10)

    def cancel_power(self):
        core.cancel_power()
        core.clear_pending_restore()
        self.log("재부팅/종료 예약 취소 및 복원 대기 해제")

    # ─────────────── 부팅 후 처리 ───────────────
    def startup_checks(self):
        try:
            if core.hook_status() == "stale":
                core.install_hook()
                self.log("프로그램 위치가 바뀌어 훅 경로를 갱신했습니다.")
            if not core.startup_managed_by_os() and core.is_startup_enabled():
                core.set_startup(True)          # 시작프로그램 경로도 현재 위치로 갱신
            self._update_hook_ui()
        except Exception as e:  # noqa: BLE001
            self.log(f"경로 갱신 실패: {e}")
        action, snap = core.boot_action(self.cfg, psutil.boot_time())
        if action in ("pending", "auto"):
            delay = int(self.cfg["restore_delay_sec"])
            what = f"'{snap['name']}'" if action == "pending" else "재부팅 전 자동저장"
            self.tray.showMessage("Session Keeper for Claude Code",
                                  f"{delay}초 후 {what} 복원 ({core.snapshot_summary(snap)})")
            self.log(f"{delay}초 후 자동 복원 예정 — 트레이 메뉴에서 취소 가능")
            self.cancel_pending_act.setVisible(True)
            self.pending_timer = QTimer(self, singleShot=True)
            self.pending_timer.timeout.connect(lambda: self._do_pending(snap))
            self.pending_timer.start(delay * 1000)
        elif action == "ask":
            auto = snap
            self.show_normal()
            when = time.strftime("%m-%d %H:%M", time.localtime(auto["created"]))
            if QMessageBox.question(
                    self, "이전 세션 복원",
                    f"재부팅 전 자동저장({when})이 있습니다.\n{core.snapshot_summary(auto)}\n\n복원할까요?"
            ) == QMessageBox.Yes:
                self.run_restore(auto)
            else:
                self.tabs.setCurrentIndex(1)

    def _do_pending(self, snap):
        self.cancel_pending_act.setVisible(False)
        core.clear_pending_restore()
        self.run_restore(snap)

    def cancel_pending_restore(self):
        if self.pending_timer:
            self.pending_timer.stop()
        self.cancel_pending_act.setVisible(False)
        core.clear_pending_restore()
        self.log("자동 복원을 취소했습니다. 스냅샷 탭에서 수동 복원할 수 있습니다.")

    # ─────────────── 설정 ───────────────
    def save_settings(self):
        c = self.cfg
        c["autosave_minutes"] = self.s_autosave.value()
        c["terminal"] = self.s_terminal.currentData()
        c["shell"] = self.s_shell.currentData()
        c["claude_cmd"] = self.s_cmd.text().strip() or "claude"
        c["extra_args"] = self.s_extra.text().strip()
        c["restore_delay_sec"] = self.s_delay.value()
        c["restore_desktop"] = self.s_desk.isChecked()
        c["desktop_launch"] = self.s_desk_launch.text().strip()
        c["start_minimized"] = self.s_min.isChecked()
        c["unexpected_reboot"] = self.s_unexpected.currentData()
        core.save_config(c)
        try:
            if not core.startup_managed_by_os():
                core.set_startup(self.s_startup.isChecked())
        except OSError as e:
            self.log(f"시작프로그램 설정 실패: {e}")
        self._apply_autosave_interval()
        self.log("설정 저장됨")

    def _update_hook_ui(self):
        st = core.hook_status()
        self.hook_label.setText({"ok": "설치됨 ✓", "none": "미설치 (세션 ID를 추정으로만 판단)",
                                 "stale": "⚠ 다른 경로로 설치됨 (프로그램 폴더 이동?)"}[st])
        self.hook_btn.setText({"ok": "훅 제거", "none": "훅 설치 (~/.claude/settings.json)",
                               "stale": "현재 위치로 재설치"}[st])

    def toggle_hook(self):
        try:
            if core.hook_status() == "ok":
                core.uninstall_hook()
                self.log("훅 제거됨")
            else:
                core.install_hook()
                self.log("훅 설치됨 (기존 설정은 settings.json.csk-bak 으로 백업)")
        except Exception as e:  # noqa: BLE001
            QMessageBox.critical(self, "훅", f"실패: {e}")
        self._update_hook_ui()

    # ─────────────── 창/종료 ───────────────
    def show_normal(self):
        self.showNormal()
        self.raise_()
        self.activateWindow()
        self.refresh_running()

    def closeEvent(self, e):
        if self.quitting:
            e.accept()
            return
        e.ignore()
        self.hide()
        self.tray.showMessage("Session Keeper for Claude Code", "트레이에서 계속 실행 중 (자동저장 유지)")

    def quit_app(self):
        self.quitting = True
        self.tray.hide()
        QApplication.quit()


def main():
    startup = "--startup" in sys.argv
    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)

    sock = QLocalSocket()                      # 단일 인스턴스
    sock.connectToServer(SERVER_NAME)
    if sock.waitForConnected(300):
        sock.write(b"show")
        sock.flush()
        sock.waitForBytesWritten(300)
        return
    QLocalServer.removeServer(SERVER_NAME)
    server = QLocalServer()
    server.listen(SERVER_NAME)

    win = MainWindow(startup)

    def on_conn():
        c = server.nextPendingConnection()
        c.readyRead.connect(win.show_normal)
    server.newConnection.connect(on_conn)

    if not (startup and win.cfg["start_minimized"]):
        win.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
