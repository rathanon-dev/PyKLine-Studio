"""
PyKLine Studio - Graphical User Interface
Modular telemetry dashboard with dual views:
1. Visual Cluster (Digital Cockpit HUD with auto-scaling RPM gauge, speed, TPS, continuous live waveform, center alert overlay, vitals)
2. Sensor Table (Raw table with all parameters, NULL state display, and hardware switches)
"""

import os
import sys
import time
import math
import collections
from datetime import datetime
import tkinter as tk
from tkinter import ttk, messagebox

from core.connection import scan_adapters
from core.engine import HondaKLineEngine
from core.paths import get_workspace_directory, get_sub_directory
from database.dtc_codes import get_dtc_description


class PyKLineApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("PyKLine Studio - Universal K-Line Telemetry & Diagnostic Suite")
        self.geometry("1140x760")
        self.minsize(980, 680)
        self.configure(bg="#F0F2F5")

        self.worker = None
        self.detected_devices = []
        self.selected_device = None
        self.status_state = "disconnected"
        self.ecu_online = False
        self.session_start_ts = None
        self.last_rx_ts = 0.0
        self.last_comm_status = "NO_DATA"
        self.last_error_reason = ""
        self.wakeup_attempt = 0
        self.logged_rows = 0
        self.current_log_file = ""
        self.pulse_toggle = False

        # Telemetry State & Auto-Scale Buffer
        self.current_rpm = None
        self.current_speed = None
        self.current_tps = None
        self.current_ect = None
        self.current_inj = None
        self.peak_rpm = 0
        self.peak_rpm_time = 0
        self.auto_rpm_scale = 3000

        # Rolling Waveform History (last 120 samples: None = NULL/Dropout)
        self.history_rpm = collections.deque(maxlen=120)
        self.history_tps = collections.deque(maxlen=120)
        self.history_ect = collections.deque(maxlen=120)
        self.history_valid = collections.deque(maxlen=120)
        for _ in range(120):
            self.history_rpm.append(0)
            self.history_tps.append(0.0)
            self.history_ect.append(0)
            self.history_valid.append(True)

        # Style & Layout
        self._setup_styles()
        self._build_top_bar()
        self._build_main_body()
        self._build_status_bar()

        self.refresh_devices()

        # Start continuous UI & Waveform heartbeat loop (runs forever at 4 Hz)
        self.after(150, self._initial_canvas_redraw)
        self.after(250, self._ui_heartbeat_tick)

    def _setup_styles(self):
        style = ttk.Style()
        style.theme_use('clam')
        style.configure("TLabel", background="#F0F2F5", font=("Segoe UI", 9))
        style.configure("Header.TLabel", font=("Segoe UI", 10, "bold"), background="#F0F2F5")
        style.configure("Card.TFrame", background="#FFFFFF", relief="groove", borderwidth=1)

    # =========================================================================
    # 1. TOP BAR
    # =========================================================================
    def _build_top_bar(self):
        top_frame = tk.Frame(self, bg="#E9ECEF", height=50, bd=1, relief="ridge")
        top_frame.pack(side=tk.TOP, fill=tk.X)

        # Brand Logo
        brand_label = tk.Label(top_frame, text="⚡ PyKLine Studio", font=("Segoe UI", 12, "bold"), bg="#E9ECEF", fg="#0B5ED7")
        brand_label.pack(side=tk.LEFT, padx=(14, 18), pady=8)

        # Device Selector
        dev_lbl = tk.Label(top_frame, text="Adapter / Port:", font=("Segoe UI", 9, "bold"), bg="#E9ECEF", fg="#495057")
        dev_lbl.pack(side=tk.LEFT, padx=(0, 6), pady=8)

        self.dev_combo = ttk.Combobox(top_frame, width=44, state="readonly")
        self.dev_combo.pack(side=tk.LEFT, padx=(0, 8), pady=8)
        self.dev_combo.bind("<<ComboboxSelected>>", self._on_device_selected)

        refresh_btn = tk.Button(top_frame, text="🔄 สแกนพอร์ต", font=("Segoe UI", 9), command=self.refresh_devices, bg="#FFFFFF", relief="groove", padx=6)
        refresh_btn.pack(side=tk.LEFT, padx=(0, 10), pady=8)

        # Connect Button
        self.connect_btn = tk.Button(
            top_frame,
            text="⚡ เชื่อมต่อ (Connect)",
            font=("Segoe UI", 9, "bold"),
            bg="#198754",
            fg="#FFFFFF",
            relief="groove",
            command=self.toggle_connection,
            padx=14
        )
        self.connect_btn.pack(side=tk.LEFT, padx=(0, 10), pady=8)

        # Security Access Button
        self.sec_btn = tk.Button(top_frame, text="🔒 Security Access", font=("Segoe UI", 9), bg="#FFFFFF", relief="groove", command=self.on_security_access, padx=8)
        self.sec_btn.pack(side=tk.RIGHT, padx=(4, 12), pady=8)

        # Open Workspace Folder Button
        self.folder_btn = tk.Button(top_frame, text="📁 เปิดโฟลเดอร์ข้อมูล", font=("Segoe UI", 9), bg="#FFFFFF", relief="groove", command=self.open_workspace_folder, padx=8)
        self.folder_btn.pack(side=tk.RIGHT, padx=4, pady=8)

    def open_workspace_folder(self):
        """Opens the portable companion data workspace in system file manager"""
        folder = get_workspace_directory()
        try:
            if sys.platform == 'win32':
                os.startfile(folder)
            elif sys.platform == 'darwin':
                import subprocess
                subprocess.Popen(['open', folder])
            else:
                import subprocess
                subprocess.Popen(['xdg-open', folder])
        except Exception as e:
            messagebox.showerror("ข้อผิดพลาด", f"ไม่สามารถเปิดโฟลเดอร์ได้: {e}")

    # =========================================================================
    # 2. MAIN BODY & SIDEBAR
    # =========================================================================
    def _build_main_body(self):
        body_frame = tk.Frame(self, bg="#F0F2F5")
        body_frame.pack(side=tk.TOP, fill=tk.BOTH, expand=True)

        # Sidebar Navigation
        self.sidebar = tk.Frame(body_frame, bg="#DDE2E6", width=160, bd=1, relief="ridge")
        self.sidebar.pack(side=tk.LEFT, fill=tk.Y)

        self.nav_buttons = {}
        tabs = [
            ("visual_dash", "🏎️ Visual Cluster"),
            ("data_logging", "📋 Sensor Table (Raw)"),
            ("trouble_codes", "⚠️ Trouble Codes"),
            ("settings", "⚙️ Settings")
        ]

        for key, text in tabs:
            btn = tk.Button(
                self.sidebar,
                text=text,
                font=("Segoe UI", 10, "bold" if key == "visual_dash" else "normal"),
                anchor="w",
                bg="#DDE2E6",
                fg="#212529",
                relief="flat",
                padx=12,
                pady=12,
                command=lambda k=key: self.switch_tab(k)
            )
            btn.pack(fill=tk.X, padx=2, pady=1)
            self.nav_buttons[key] = btn

        # Content Container
        self.content_container = tk.Frame(body_frame, bg="#F0F2F5")
        self.content_container.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=8, pady=8)

        self.pages = {}
        self.pages["visual_dash"] = self._create_visual_dash_page()
        self.pages["data_logging"] = self._create_data_logging_page()
        self.pages["trouble_codes"] = self._create_trouble_codes_page()
        self.pages["settings"] = self._create_settings_page()

        self.switch_tab("visual_dash")

    def switch_tab(self, tab_key):
        for k, page in self.pages.items():
            if k == tab_key:
                page.pack(fill=tk.BOTH, expand=True)
            else:
                page.pack_forget()

        for k, btn in self.nav_buttons.items():
            if k == tab_key:
                btn.configure(bg="#FFFFFF", fg="#0B5ED7", relief="groove")
            else:
                btn.configure(bg="#DDE2E6", fg="#212529", relief="flat")

    # =========================================================================
    # 3. PAGE 1: VISUAL CLUSTER (NEW DIGITAL COCKPIT DASHBOARD)
    # =========================================================================
    def _create_visual_dash_page(self):
        page = tk.Frame(self.content_container, bg="#0D1117")

        # 3.1 Top HUD Strip (ECU Status + Session Timer + Active Log File)
        hud_top = tk.Frame(page, bg="#161B22", height=40, bd=1, relief="ridge")
        hud_top.pack(fill=tk.X, padx=6, pady=(4, 6))

        self.hud_model_lbl = tk.Label(
            hud_top,
            text="⏸️ สถานะ: NO DATA (ยังไม่ได้กดเชื่อมต่อ)",
            font=("Segoe UI", 9, "bold"),
            bg="#161B22",
            fg="#8B949E"
        )
        self.hud_model_lbl.pack(side=tk.LEFT, padx=10, pady=6)

        self.hud_part_lbl = tk.Label(hud_top, text="Part: ---", font=("Consolas", 9), bg="#161B22", fg="#8B949E")
        self.hud_part_lbl.pack(side=tk.LEFT, padx=8, pady=6)

        self.hud_timer_lbl = tk.Label(
            hud_top,
            text="⏱️ เวลาเซสชัน: 00:00:00",
            font=("Consolas", 9, "bold"),
            bg="#161B22",
            fg="#58A6FF"
        )
        self.hud_timer_lbl.pack(side=tk.LEFT, padx=12, pady=6)

        self.hud_log_lbl = tk.Label(
            hud_top,
            text="📝 ล็อก: รอกดเชื่อมต่อ",
            font=("Segoe UI", 8, "bold"),
            bg="#161B22",
            fg="#8B949E"
        )
        self.hud_log_lbl.pack(side=tk.LEFT, padx=8, pady=6)

        export_btn = tk.Button(
            hud_top,
            text="📸 บันทึกภาพ Snapshot",
            font=("Segoe UI", 8, "bold"),
            bg="#21262D",
            fg="#C9D1D9",
            relief="groove",
            command=self._export_snapshot,
            padx=8
        )
        export_btn.pack(side=tk.RIGHT, padx=10, pady=4)

        # 3.2 Middle Gauges Section (RPM Tachometer + Speedometer + Throttle)
        gauges_frame = tk.Frame(page, bg="#0D1117")
        gauges_frame.pack(fill=tk.X, padx=6, pady=2)

        # Tachometer (RPM Gauge Canvas)
        tacho_box = tk.Frame(gauges_frame, bg="#161B22", bd=1, relief="groove")
        tacho_box.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(0, 4))

        self.rpm_canvas = tk.Canvas(tacho_box, width=320, height=210, bg="#161B22", highlightthickness=0)
        self.rpm_canvas.pack(fill=tk.BOTH, expand=True, padx=6, pady=4)
        self.rpm_canvas.bind("<Configure>", lambda e: self._render_tachometer(self.current_rpm, self.auto_rpm_scale, self.peak_rpm))

        # Speedometer (Speed Gauge Canvas)
        speed_box = tk.Frame(gauges_frame, bg="#161B22", bd=1, relief="groove")
        speed_box.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(0, 4))

        self.speed_canvas = tk.Canvas(speed_box, width=280, height=210, bg="#161B22", highlightthickness=0)
        self.speed_canvas.pack(fill=tk.BOTH, expand=True, padx=6, pady=4)
        self.speed_canvas.bind("<Configure>", lambda e: self._render_speedometer(self.current_speed))

        # Side Status Column (TPS Bar + Battery + Interlocks)
        aux_box = tk.Frame(gauges_frame, bg="#161B22", width=250, bd=1, relief="groove")
        aux_box.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        tk.Label(aux_box, text="คันเร่ง THROTTLE (TPS)", font=("Segoe UI", 9, "bold"), bg="#161B22", fg="#8B949E").pack(anchor="w", padx=12, pady=(10, 2))
        self.hud_tps_val_lbl = tk.Label(aux_box, text="NO DATA | --- V", font=("Segoe UI", 12, "bold"), bg="#161B22", fg="#8B949E")
        self.hud_tps_val_lbl.pack(anchor="w", padx=12)

        # TPS Bar Canvas
        self.tps_bar_canvas = tk.Canvas(aux_box, height=18, bg="#21262D", highlightthickness=0)
        self.tps_bar_canvas.pack(fill=tk.X, padx=12, pady=(4, 10))
        self.tps_bar_canvas.bind("<Configure>", lambda e: self._render_tps_bar(self.current_tps or 0.0))

        # Battery Bar
        tk.Label(aux_box, text="แรงดันไฟ BATTERY", font=("Segoe UI", 9, "bold"), bg="#161B22", fg="#8B949E").pack(anchor="w", padx=12, pady=(2, 2))
        self.hud_bat_val_lbl = tk.Label(aux_box, text="NO DATA [ --- % ]", font=("Segoe UI", 11, "bold"), bg="#161B22", fg="#8B949E")
        self.hud_bat_val_lbl.pack(anchor="w", padx=12)

        # Interlock Badges
        flag_frame = tk.Frame(aux_box, bg="#161B22")
        flag_frame.pack(fill=tk.X, padx=12, pady=(10, 8))

        self.hud_stand_badge = tk.Label(flag_frame, text="ขาตั้ง: ---", font=("Segoe UI", 9, "bold"), bg="#21262D", fg="#8B949E", padx=8, pady=3)
        self.hud_stand_badge.pack(side=tk.LEFT, padx=(0, 6))

        self.hud_eng_badge = tk.Label(flag_frame, text="เครื่องยนต์: ---", font=("Segoe UI", 9, "bold"), bg="#21262D", fg="#8B949E", padx=8, pady=3)
        self.hud_eng_badge.pack(side=tk.LEFT)

        # 3.3 Real-time Rolling Waveform Strip-Chart (RPM vs TPS vs ECT over time)
        wave_box = tk.Frame(page, bg="#161B22", bd=1, relief="groove")
        wave_box.pack(fill=tk.BOTH, expand=True, padx=6, pady=(4, 6))

        wave_hdr = tk.Frame(wave_box, bg="#161B22")
        wave_hdr.pack(fill=tk.X, padx=10, pady=(6, 2))
        tk.Label(
            wave_hdr,
            text="📈 REAL-TIME TELEMETRY WAVEFORM (CONTINUOUS 30s ROLLING MONITOR)",
            font=("Segoe UI", 8, "bold"),
            bg="#161B22",
            fg="#8B949E"
        ).pack(side=tk.LEFT)
        tk.Label(
            wave_hdr,
            text="🟢 รอบเครื่อง RPM   |   🔵 คันเร่ง TPS %   |   🟠 อุณหภูมิ ECT °C   |   🟥 ช่วงสัญญาณหลุด (NULL)",
            font=("Segoe UI", 8, "bold"),
            bg="#161B22",
            fg="#58A6FF"
        ).pack(side=tk.RIGHT)

        self.wave_canvas = tk.Canvas(wave_box, height=150, bg="#0D1117", highlightthickness=0)
        self.wave_canvas.pack(fill=tk.BOTH, expand=True, padx=8, pady=(0, 6))
        self.wave_canvas.bind("<Configure>", lambda e: self._render_waveform())

        # 3.4 Bottom Engine Vitals Cards
        vitals_frame = tk.Frame(page, bg="#0D1117")
        vitals_frame.pack(fill=tk.X, padx=6, pady=(0, 6))

        self.hud_cards = {}
        vitals_spec = [
            ("ect", "🌡️ ความร้อน ECT", "NO DATA", "#8B949E"),
            ("map", "💨 แรงดันไอดี MAP", "N/A", "#8B949E"),
            ("inj", "⏱️ ยกหัวฉีด INJ", "NO DATA", "#8B949E"),
            ("ign", "⚡ องศาไฟ IGN", "NO DATA", "#8B949E"),
            ("o2", "🔌 เซนเซอร์ไอเสีย O2", "NO DATA", "#8B949E")
        ]

        for key, title, init_val, color in vitals_spec:
            card = tk.Frame(vitals_frame, bg="#161B22", bd=1, relief="groove")
            card.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=2)

            tk.Label(card, text=title, font=("Segoe UI", 8, "bold"), bg="#161B22", fg="#8B949E").pack(anchor="w", padx=8, pady=(4, 1))
            val_lbl = tk.Label(card, text=init_val, font=("Segoe UI", 12, "bold"), bg="#161B22", fg=color)
            val_lbl.pack(anchor="w", padx=8, pady=(0, 4))
            self.hud_cards[key] = val_lbl

        return page

    def _initial_canvas_redraw(self):
        """Forces an initial redraw after Tkinter has mapped the main window geometry."""
        self.update_idletasks()
        self._render_tachometer(self.current_rpm, self.auto_rpm_scale, self.peak_rpm)
        self._render_speedometer(self.current_speed)
        self._render_tps_bar(self.current_tps or 0.0)
        self._render_waveform()

    def _ui_heartbeat_tick(self):
        """
        Continuous 4 Hz UI timer that keeps the session clock ticking,
        scrolls the waveform during dropouts, and animates connection alerts.
        """
        self.pulse_toggle = not self.pulse_toggle
        now = time.time()

        is_session_active = bool(self.worker and getattr(self.worker, 'running', False))
        if is_session_active and self.session_start_ts:
            elapsed = int(now - self.session_start_ts)
            hh = elapsed // 3600
            mm = (elapsed % 3600) // 60
            ss = elapsed % 60
            self.hud_timer_lbl.configure(text=f"⏱️ เวลาบันทึก: {hh:02d}:{mm:02d}:{ss:02d}", fg="#3FB950" if self.ecu_online else "#D29922")

            # If no packet arrived in the last 0.65s while session is active, push a NULL sample to keep waveform scrolling
            if (now - self.last_rx_ts) > 0.65:
                self.history_rpm.append(0)
                self.history_tps.append(0.0)
                self.history_ect.append(self.current_ect or 0)
                self.history_valid.append(False)

        self._render_tachometer(self.current_rpm, self.auto_rpm_scale, self.peak_rpm)
        self._render_speedometer(self.current_speed)
        self._render_waveform()

        self.after(250, self._ui_heartbeat_tick)

    # =========================================================================
    # 4. GAUGE RENDERING MATH (CANVAS VECTOR CLUSTER)
    # =========================================================================
    @staticmethod
    def _safe_canvas_dims(canvas, default_w, default_h):
        w = canvas.winfo_width()
        h = canvas.winfo_height()
        if w < 50:
            w = default_w
        if h < 40:
            h = default_h
        return w, h

    def _render_tachometer(self, rpm, max_scale, peak_val):
        c = self.rpm_canvas
        c.delete("all")
        w, h = self._safe_canvas_dims(c, 320, 210)

        cx = w / 2
        cy = h / 2 + 10
        r = min(w, h) * 0.41

        start_arc = 220
        sweep_ang = 260
        num_rpm = rpm if (rpm is not None and self.ecu_online) else 0
        pct = max(0.0, min(1.0, num_rpm / max_scale if max_scale else 0))

        # Background track arc
        c.create_arc(cx - r, cy - r, cx + r, cy + r, start=start_arc, extent=-sweep_ang, style=tk.ARC, outline="#21262D", width=14)

        # Active fill arc
        fill_extent = int(pct * sweep_ang)
        if fill_extent > 0 and self.ecu_online:
            if pct < 0.65:
                arc_color = "#3FB950"
            elif pct < 0.85:
                arc_color = "#D29922"
            else:
                arc_color = "#F85149"
            c.create_arc(cx - r, cy - r, cx + r, cy + r, start=start_arc, extent=-fill_extent, style=tk.ARC, outline=arc_color, width=14)

        # Peak Hold Tick
        if peak_val > 0 and peak_val <= max_scale and self.ecu_online:
            peak_pct = peak_val / max_scale
            peak_ang = math.radians(140 + peak_pct * sweep_ang)
            px1 = cx + (r - 10) * math.cos(peak_ang)
            py1 = cy + (r - 10) * math.sin(peak_ang)
            px2 = cx + (r + 10) * math.cos(peak_ang)
            py2 = cy + (r + 10) * math.sin(peak_ang)
            c.create_line(px1, py1, px2, py2, fill="#FF7B72", width=3)

        # Center Text Readouts based on state
        is_session_active = bool(self.worker and getattr(self.worker, 'running', False))
        if not is_session_active:
            c.create_text(cx, cy - 12, text="NO DATA", font=("Segoe UI", 20, "bold"), fill="#8B949E")
            c.create_text(cx, cy + 16, text="RPM (ยังไม่ได้เชื่อมต่อ)", font=("Segoe UI", 9, "bold"), fill="#6E7681")
            c.create_text(cx, cy + 34, text=f"สเกล: 0 - {max_scale:,} RPM", font=("Segoe UI", 8), fill="#58A6FF")
        elif not self.ecu_online or rpm is None:
            c.create_text(cx, cy - 12, text="NULL", font=("Segoe UI", 22, "bold"), fill="#F85149" if self.pulse_toggle else "#D29922")
            c.create_text(cx, cy + 16, text="RPM (รอสัญญาณกล่อง)", font=("Segoe UI", 9, "bold"), fill="#D29922")
            c.create_text(cx, cy + 34, text=f"Wake-up #{self.wakeup_attempt}", font=("Segoe UI", 8), fill="#58A6FF")
        else:
            c.create_text(cx, cy - 14, text=f"{rpm:,}", font=("Segoe UI", 24, "bold"), fill="#F0F6FC")
            c.create_text(cx, cy + 16, text="RPM", font=("Segoe UI", 10, "bold"), fill="#8B949E")
            c.create_text(cx, cy + 34, text=f"สเกล: 0 - {max_scale:,} RPM", font=("Segoe UI", 8), fill="#58A6FF")
            if peak_val > 0:
                c.create_text(cx, cy + 50, text=f"Peak: {peak_val:,} RPM", font=("Segoe UI", 8, "bold"), fill="#FF7B72")

    def _render_speedometer(self, speed):
        c = self.speed_canvas
        c.delete("all")
        w, h = self._safe_canvas_dims(c, 280, 210)

        cx = w / 2
        cy = h / 2 + 10
        r = min(w, h) * 0.41

        start_arc = 220
        sweep_ang = 260
        max_speed = 160
        num_speed = speed if (speed is not None and self.ecu_online) else 0
        pct = max(0.0, min(1.0, num_speed / max_speed))

        # Background track arc
        c.create_arc(cx - r, cy - r, cx + r, cy + r, start=start_arc, extent=-sweep_ang, style=tk.ARC, outline="#21262D", width=14)

        # Active speed arc
        fill_extent = int(pct * sweep_ang)
        if fill_extent > 0 and self.ecu_online:
            c.create_arc(cx - r, cy - r, cx + r, cy + r, start=start_arc, extent=-fill_extent, style=tk.ARC, outline="#58A6FF", width=14)

        is_session_active = bool(self.worker and getattr(self.worker, 'running', False))
        if not is_session_active:
            c.create_text(cx, cy - 12, text="NO DATA", font=("Segoe UI", 20, "bold"), fill="#8B949E")
            c.create_text(cx, cy + 18, text="KM/H", font=("Segoe UI", 10, "bold"), fill="#6E7681")
            c.create_text(cx, cy + 36, text="รอการกดเชื่อมต่อ", font=("Segoe UI", 8), fill="#6E7681")
        elif not self.ecu_online or speed is None:
            c.create_text(cx, cy - 12, text="NULL", font=("Segoe UI", 22, "bold"), fill="#F85149" if self.pulse_toggle else "#D29922")
            c.create_text(cx, cy + 18, text="KM/H (NO SIGNAL)", font=("Segoe UI", 9, "bold"), fill="#D29922")
            c.create_text(cx, cy + 36, text="กำลังบันทึกค่า NULL...", font=("Segoe UI", 8), fill="#D29922")
        else:
            c.create_text(cx, cy - 14, text=str(int(speed)), font=("Segoe UI", 26, "bold"), fill="#F0F6FC")
            c.create_text(cx, cy + 18, text="KM/H", font=("Segoe UI", 10, "bold"), fill="#8B949E")
            c.create_text(cx, cy + 36, text="Vehicle Speed", font=("Segoe UI", 8), fill="#7EE787")

    def _render_tps_bar(self, tps_pct):
        c = self.tps_bar_canvas
        c.delete("all")
        w, h = self._safe_canvas_dims(c, 220, 18)

        fill_w = int((max(0.0, min(100.0, tps_pct)) / 100.0) * w)
        if fill_w > 0 and self.ecu_online:
            color = "#58A6FF" if tps_pct < 50 else ("#D29922" if tps_pct < 85 else "#F85149")
            c.create_rectangle(0, 0, fill_w, h, fill=color, outline="")

    def _render_waveform(self):
        c = self.wave_canvas
        c.delete("all")
        w, h = self._safe_canvas_dims(c, 780, 150)

        # Draw horizontal grid lines & scale labels
        for frac, lbl in [(0.25, "75%"), (0.50, "50%"), (0.75, "25%")]:
            y_step = h * frac
            c.create_line(0, y_step, w, y_step, fill="#1C2128", dash=(2, 4))
            c.create_text(w - 6, y_step - 6, text=lbl, anchor="e", font=("Consolas", 7), fill="#484F58")

        # Draw vertical time grid lines
        for x_frac in [0.2, 0.4, 0.6, 0.8]:
            x_step = w * x_frac
            c.create_line(x_step, 0, x_step, h, fill="#161B22", dash=(2, 4))

        count = len(self.history_rpm)
        is_session_active = bool(self.worker and getattr(self.worker, 'running', False))

        if count >= 2 and is_session_active:
            dx = w / (count - 1)
            rpm_scale = self.auto_rpm_scale if self.auto_rpm_scale else 3000

            # 1. Shade NULL / Dropout intervals in dark red so user sees exact dropout history
            for i in range(count - 1):
                if not self.history_valid[i] or not self.history_valid[i + 1]:
                    x1 = i * dx
                    x2 = (i + 1) * dx
                    c.create_rectangle(x1, 0, x2 + 1, h, fill="#2D1215", outline="")

            # 2. Draw contiguous valid segments for RPM (green), TPS (blue), ECT (orange)
            rpm_seg = []
            tps_seg = []
            ect_seg = []

            def _flush_segments():
                if len(rpm_seg) >= 4:
                    c.create_line(rpm_seg, fill="#3FB950", width=2, smooth=True)
                if len(tps_seg) >= 4:
                    c.create_line(tps_seg, fill="#58A6FF", width=2, smooth=True)
                if len(ect_seg) >= 4:
                    c.create_line(ect_seg, fill="#F0883E", width=1, smooth=True)

            for i in range(count):
                if not self.history_valid[i]:
                    _flush_segments()
                    rpm_seg.clear()
                    tps_seg.clear()
                    ect_seg.clear()
                    continue

                x = i * dx
                norm_rpm = max(0.0, min(1.0, (self.history_rpm[i] or 0) / rpm_scale))
                y_rpm = h - (norm_rpm * (h - 18)) - 8
                rpm_seg.extend([x, y_rpm])

                norm_tps = max(0.0, min(1.0, (self.history_tps[i] or 0.0) / 100.0))
                y_tps = h - (norm_tps * (h - 18)) - 8
                tps_seg.extend([x, y_tps])

                norm_ect = max(0.0, min(1.0, (self.history_ect[i] or 0) / 120.0))
                y_ect = h - (norm_ect * (h - 18)) - 8
                ect_seg.extend([x, y_ect])

            _flush_segments()

            # Live numerical overlay in top-left of waveform when online
            if self.ecu_online and self.current_rpm is not None:
                live_summary = (
                    f"LIVE ▶  RPM: {self.current_rpm:,}  |  "
                    f"TPS: {self.current_tps or 0.0:.1f}%  |  "
                    f"ECT: {self.current_ect if self.current_ect is not None else '---'} °C  |  "
                    f"INJ: {self.current_inj if self.current_inj is not None else 0.0:.2f} ms"
                )
                c.create_rectangle(8, 6, 460, 26, fill="#161B22", outline="#30363D")
                c.create_text(16, 16, text=live_summary, anchor="w", font=("Consolas", 9, "bold"), fill="#7EE787")

        # 3. Center Overlay Banner for NO DATA (Disconnected) or ECU LOST / WAKEUP RETRY
        cx = w / 2
        cy = h / 2

        if not is_session_active:
            box_w = min(w - 40, 620)
            box_h = 68
            c.create_rectangle(
                cx - box_w / 2, cy - box_h / 2,
                cx + box_w / 2, cy + box_h / 2,
                fill="#161B22", outline="#30363D", width=2
            )
            c.create_text(
                cx, cy - 12,
                text="⏸️ NO DATA — ยังไม่ได้เชื่อมต่อกับกล่อง ECU (Waiting for Connection)",
                font=("Segoe UI", 11, "bold"),
                fill="#C9D1D9"
            )
            c.create_text(
                cx, cy + 14,
                text="กดปุ่ม  [⚡ เชื่อมต่อ (Connect)]  ด้านบนเพื่อเริ่มจับเวลา แสดงกราฟ Real-Time และบันทึกล็อกอัตโนมัติ",
                font=("Segoe UI", 9),
                fill="#58A6FF"
            )
        elif not self.ecu_online:
            box_w = min(w - 30, 720)
            box_h = 88
            border_col = "#F85149" if self.pulse_toggle else "#D29922"
            c.create_rectangle(
                cx - box_w / 2, cy - box_h / 2,
                cx + box_w / 2, cy + box_h / 2,
                fill="#1F1215", outline=border_col, width=2
            )
            c.create_text(
                cx, cy - 24,
                text=f"⚠️ แจ้งเตือน: กล่อง ECU ไม่ตอบสนอง / สัญญาณหลุด! (สถานะข้อมูลปัจจุบัน = NULL)",
                font=("Segoe UI", 10, "bold"),
                fill="#FF7B72"
            )
            c.create_text(
                cx, cy + 1,
                text=f"📝 ระบบยังทำงานต่อและบันทึกค่า 'NULL' ลงไฟล์ล็อกต่อเนื่อง ({self.current_log_file or 'CSV/JSONL'} | แถวที่ #{self.logged_rows})",
                font=("Segoe UI", 9, "bold"),
                fill="#F0F6FC"
            )
            c.create_text(
                cx, cy + 24,
                text=f"🔧 คำแนะนำ: ลองขยับปลั๊กสาย DLC หรือบิดสวิตช์กุญแจเปิด ON — กำลังยิงสัญญาณ Wake-up อัตโนมัติ (ครั้งที่ #{self.wakeup_attempt})...",
                font=("Segoe UI", 9),
                fill="#79C0FF"
            )

    # =========================================================================
    # 5. PAGE 2: ORIGINAL RAW SENSOR TABLE (ตารางเดิมครบถ้วน)
    # =========================================================================
    def _create_data_logging_page(self):
        page = tk.Frame(self.content_container, bg="#F0F2F5")

        # 5.1 Top ECU Identification Banner
        self.id_box = tk.LabelFrame(
            page,
            text=" 🏍️ ข้อมูลรุ่นกล่อง ECU (Auto-Detected Model & Hardware ID) ",
            font=("Segoe UI", 9, "bold"),
            bg="#FFFFFF",
            fg="#003366",
            padx=12,
            pady=8
        )
        self.id_box.pack(side=tk.TOP, fill=tk.X, padx=0, pady=(0, 10))

        tk.Label(self.id_box, text="รุ่นรถ (Model):", font=("Segoe UI", 9, "bold"), bg="#FFFFFF", fg="#495057").grid(row=0, column=0, sticky="w", padx=(4, 6), pady=2)
        self.model_val_lbl = tk.Label(self.id_box, text="--- (รอการเชื่อมต่อ)", font=("Segoe UI", 9, "bold"), bg="#FFFFFF", fg="#6C757D")
        self.model_val_lbl.grid(row=0, column=1, sticky="w", padx=(0, 24), pady=2)

        tk.Label(self.id_box, text="รหัสกล่อง (Part No.):", font=("Segoe UI", 9, "bold"), bg="#FFFFFF", fg="#495057").grid(row=0, column=2, sticky="w", padx=(4, 6), pady=2)
        self.pn_val_lbl = tk.Label(self.id_box, text="---", font=("Segoe UI", 9, "bold"), bg="#FFFFFF", fg="#6C757D")
        self.pn_val_lbl.grid(row=0, column=3, sticky="w", padx=(0, 16), pady=2)

        tk.Label(self.id_box, text="Hardware ECM ID:", font=("Segoe UI", 9, "bold"), bg="#FFFFFF", fg="#495057").grid(row=1, column=0, sticky="w", padx=(4, 6), pady=2)
        self.ecmid_val_lbl = tk.Label(self.id_box, text="---", font=("Consolas", 9, "bold"), bg="#FFFFFF", fg="#6C757D")
        self.ecmid_val_lbl.grid(row=1, column=1, sticky="w", padx=(0, 24), pady=2)

        tk.Label(self.id_box, text="สถานะการจับคู่ (Match Status):", font=("Segoe UI", 9, "bold"), bg="#FFFFFF", fg="#495057").grid(row=1, column=2, sticky="w", padx=(4, 6), pady=2)
        self.rom_match_val_lbl = tk.Label(self.id_box, text="---", font=("Segoe UI", 9, "bold"), bg="#FFFFFF", fg="#6C757D")
        self.rom_match_val_lbl.grid(row=1, column=3, sticky="w", padx=(0, 16), pady=2)

        # 5.2 Main Telemetry & Switch Table Frame
        grid_frame = tk.Frame(page, bg="#F0F2F5")
        grid_frame.pack(side=tk.TOP, fill=tk.BOTH, expand=True)

        # Left Column: Table 0x17
        self.t17_box = tk.LabelFrame(grid_frame, text=" Table 0x17 (Main Telemetry) ", font=("Segoe UI", 9, "bold"), bg="#FFFFFF", fg="#003366", padx=12, pady=10)
        self.t17_box.grid(row=0, column=0, rowspan=2, sticky="nsew", padx=(0, 6), pady=0)

        self.sensor_widgets = {}
        sensors = [
            ("rpm", "Engine speed:", "rpm"),
            ("tps_pct", "TPS opening:", "%"),
            ("tps_deg", "TPS angle:", "°"),
            ("tps_v", "TPS voltage:", "V"),
            ("ect", "ECT sensor:", "°C"),
            ("iat", "IAT sensor:", "°C"),
            ("map_mbar", "MAP sensor:", "mBar"),
            ("battery", "Battery voltage:", "V"),
            ("speed", "Vehicle speed:", "Km/h"),
            ("inj_ms", "Injector duration:", "ms"),
            ("ign_deg", "Ignition advance:", "°"),
            ("iacv", "IACV pulse count:", "")
        ]

        for idx, (key, label, unit) in enumerate(sensors):
            tk.Label(self.t17_box, text=label, font=("Segoe UI", 9), bg="#FFFFFF", fg="#495057").grid(row=idx, column=0, sticky="e", padx=(8, 12), pady=3)
            val_lbl = tk.Label(self.t17_box, text="NO DATA", font=("Consolas", 10, "bold"), bg="#FFFFFF", fg="#6C757D", width=9, anchor="e", relief="sunken", bd=1)
            val_lbl.grid(row=idx, column=1, sticky="w", padx=(0, 6), pady=3)
            tk.Label(self.t17_box, text=unit, font=("Segoe UI", 9), bg="#FFFFFF", fg="#6C757D").grid(row=idx, column=2, sticky="w", padx=(0, 8), pady=3)
            self.sensor_widgets[key] = val_lbl

        # Right Top: Table 0xD1 Switches
        d1_box = tk.LabelFrame(grid_frame, text=" Table 0xD1 (Switch Flags) ", font=("Segoe UI", 9, "bold"), bg="#FFFFFF", fg="#003366", padx=12, pady=10)
        d1_box.grid(row=0, column=1, sticky="nsew", padx=(6, 0), pady=(0, 6))

        tk.Label(d1_box, text="Side Stand Switch:", font=("Segoe UI", 9), bg="#FFFFFF", fg="#495057").grid(row=0, column=0, sticky="w", padx=4, pady=4)
        self.stand_lbl = tk.Label(d1_box, text="NO DATA", font=("Segoe UI", 9, "bold"), bg="#FFFFFF", fg="#6C757D")
        self.stand_lbl.grid(row=0, column=1, sticky="w", padx=12, pady=4)

        tk.Label(d1_box, text="Start Interlock (เบรก+สตาร์ท):", font=("Segoe UI", 9), bg="#FFFFFF", fg="#495057").grid(row=1, column=0, sticky="w", padx=4, pady=4)
        self.brake_lbl = tk.Label(d1_box, text="NO DATA", font=("Segoe UI", 9, "bold"), bg="#FFFFFF", fg="#6C757D")
        self.brake_lbl.grid(row=1, column=1, sticky="w", padx=12, pady=4)

        tk.Label(d1_box, text="Engine Status:", font=("Segoe UI", 9), bg="#FFFFFF", fg="#495057").grid(row=2, column=0, sticky="w", padx=4, pady=4)
        self.engine_run_lbl = tk.Label(d1_box, text="NO DATA", font=("Segoe UI", 9, "bold"), bg="#FFFFFF", fg="#6C757D")
        self.engine_run_lbl.grid(row=2, column=1, sticky="w", padx=12, pady=4)

        # Right Bottom: Table 0x20 (O2 & Fuel Trim)
        o2_box = tk.LabelFrame(grid_frame, text=" Table 0x20 (O2 & Fuel Trim) ", font=("Segoe UI", 9, "bold"), bg="#FFFFFF", fg="#003366", padx=12, pady=10)
        o2_box.grid(row=1, column=1, sticky="nsew", padx=(6, 0), pady=(6, 0))

        tk.Label(o2_box, text="O2 Sensor #1:", font=("Segoe UI", 9), bg="#FFFFFF", fg="#495057").grid(row=0, column=0, sticky="e", padx=(8, 12), pady=3)
        self.o2_val_lbl = tk.Label(o2_box, text="NO DATA", font=("Consolas", 10, "bold"), bg="#FFFFFF", fg="#6C757D", width=9, anchor="e", relief="sunken", bd=1)
        self.o2_val_lbl.grid(row=0, column=1, sticky="w", padx=(0, 6), pady=3)
        tk.Label(o2_box, text="V", font=("Segoe UI", 9), bg="#FFFFFF", fg="#6C757D").grid(row=0, column=2, sticky="w", padx=(0, 8), pady=3)

        tk.Label(o2_box, text="O2 Heater #1:", font=("Segoe UI", 9), bg="#FFFFFF", fg="#495057").grid(row=1, column=0, sticky="e", padx=(8, 12), pady=3)
        self.o2_heater_lbl = tk.Label(o2_box, text="NO DATA", font=("Consolas", 10, "bold"), bg="#FFFFFF", fg="#6C757D", width=9, anchor="e", relief="sunken", bd=1)
        self.o2_heater_lbl.grid(row=1, column=1, sticky="w", padx=(0, 6), pady=3)
        tk.Label(o2_box, text="V", font=("Segoe UI", 9), bg="#FFFFFF", fg="#6C757D").grid(row=1, column=2, sticky="w", padx=(0, 8), pady=3)

        tk.Label(o2_box, text="STFT #1 (Fuel Trim):", font=("Segoe UI", 9), bg="#FFFFFF", fg="#495057").grid(row=2, column=0, sticky="e", padx=(8, 12), pady=3)
        self.stft_val_lbl = tk.Label(o2_box, text="NO DATA", font=("Consolas", 10, "bold"), bg="#FFFFFF", fg="#6C757D", width=9, anchor="e", relief="sunken", bd=1)
        self.stft_val_lbl.grid(row=2, column=1, sticky="w", padx=(0, 6), pady=3)

        grid_frame.columnconfigure(0, weight=3)
        grid_frame.columnconfigure(1, weight=2)
        grid_frame.rowconfigure(0, weight=1)
        grid_frame.rowconfigure(1, weight=1)

        return page

    # =========================================================================
    # 6. PAGE 3: TROUBLE CODES (DTC)
    # =========================================================================
    def _create_trouble_codes_page(self):
        page = tk.Frame(self.content_container, bg="#F0F2F5")
        act_frame = tk.Frame(page, bg="#F0F2F5")
        act_frame.pack(side=tk.TOP, fill=tk.X, pady=(0, 10))

        read_cur_btn = tk.Button(act_frame, text="🔍 อ่านโค้ดปัจจุบัน (Current DTC)", font=("Segoe UI", 9), bg="#FFFFFF", relief="groove", command=lambda: self.request_dtc('current'))
        read_cur_btn.pack(side=tk.LEFT, padx=(0, 8))

        read_past_btn = tk.Button(act_frame, text="📜 อ่านโค้ดย้อนหลัง (Past DTC)", font=("Segoe UI", 9), bg="#FFFFFF", relief="groove", command=lambda: self.request_dtc('past'))
        read_past_btn.pack(side=tk.LEFT, padx=(0, 8))

        clear_btn = tk.Button(act_frame, text="🗑️ ลบโค้ด (Clear DTC)", font=("Segoe UI", 9, "bold"), bg="#DC3545", fg="#FFFFFF", relief="groove", command=self.request_clear_dtc)
        clear_btn.pack(side=tk.RIGHT, padx=0)

        cols = ("code", "description")
        self.dtc_tree = ttk.Treeview(page, columns=cols, show="headings", height=15)
        self.dtc_tree.heading("code", text="DTC Code")
        self.dtc_tree.heading("description", text="Description / รายละเอียดปัญหา")
        self.dtc_tree.column("code", width=120, anchor="center")
        self.dtc_tree.column("description", width=600, anchor="w")
        self.dtc_tree.pack(fill=tk.BOTH, expand=True)

        return page

    # =========================================================================
    # 7. PAGE 4: SETTINGS & SIMULATOR
    # =========================================================================
    def _create_settings_page(self):
        page = tk.Frame(self.content_container, bg="#FFFFFF", bd=1, relief="groove")
        tk.Label(page, text="⚙️ Configuration & Telemetry Engine", font=("Segoe UI", 12, "bold"), bg="#FFFFFF", fg="#003366").pack(anchor="w", padx=16, pady=12)

        opt_frame = tk.Frame(page, bg="#FFFFFF")
        opt_frame.pack(fill=tk.X, padx=16, pady=4)

        tk.Checkbutton(opt_frame, text="Auto-Detect Model & ECM ID upon connection", bg="#FFFFFF").pack(anchor="w", pady=2)
        tk.Checkbutton(opt_frame, text="Save Telemetry Session Logs into storage/ (รวมถึงการบันทึกค่า NULL ตอนสัญญาณหลุด)", bg="#FFFFFF").pack(anchor="w", pady=2)

        lbl = tk.Label(opt_frame, text="Baud Rate: 10,400 Baud (Fixed standard K-Line | Auto Fast-Init 70ms Re-Wakeup)", font=("Segoe UI", 9, "bold"), bg="#FFFFFF", fg="#495057")
        lbl.pack(anchor="w", pady=6)

        return page

    # =========================================================================
    # 8. STATUS BAR
    # =========================================================================
    def _build_status_bar(self):
        self.status_bar = tk.Frame(self, bg="#E9ECEF", height=28, bd=1, relief="sunken")
        self.status_bar.pack(side=tk.BOTTOM, fill=tk.X)

        self.bullet_canvas = tk.Canvas(self.status_bar, width=16, height=16, bg="#E9ECEF", highlightthickness=0)
        self.bullet_canvas.pack(side=tk.LEFT, padx=(8, 4), pady=6)
        self.bullet_id = self.bullet_canvas.create_oval(3, 3, 13, 13, fill="#6C757D", outline="#495057")

        self.status_label = tk.Label(self.status_bar, text="พร้อมทำงาน (NO DATA — เลือกพอร์ตแล้วกดเชื่อมต่อ)", font=("Segoe UI", 9), bg="#E9ECEF", fg="#333333")
        self.status_label.pack(side=tk.LEFT, padx=4, pady=4)

        self.fps_label = tk.Label(self.status_bar, text="Rate: 0.0 Hz", font=("Segoe UI", 9, "bold"), bg="#E9ECEF", fg="#0B5ED7")
        self.fps_label.pack(side=tk.RIGHT, padx=16, pady=4)

    # =========================================================================
    # 9. TELEMETRY EVENT DISPATCHER & DUAL-RENDERER
    # =========================================================================
    def _on_telemetry_received(self, data):
        self.after(0, self._render_telemetry, data)

    def _render_telemetry(self, data):
        self.last_rx_ts = time.time()
        is_connected = data.get("connected", True)
        self.ecu_online = bool(is_connected)
        self.last_comm_status = data.get("comm_status", "OK" if is_connected else "ECU_LOST")
        self.last_error_reason = data.get("error_reason", "")
        self.wakeup_attempt = data.get("wakeup_attempt", self.wakeup_attempt)
        self.logged_rows = data.get("logged_rows", self.logged_rows)
        if data.get("log_file"):
            self.current_log_file = data["log_file"]

        if self.current_log_file:
            self.hud_log_lbl.configure(
                text=f"📝 ล็อก: {self.current_log_file} (#{self.logged_rows})",
                fg="#3FB950" if self.ecu_online else "#D29922"
            )

        # Handle NULL / Dropout Frame
        if not is_connected:
            self.current_rpm = None
            self.current_speed = None
            self.current_tps = None

            self.history_rpm.append(0)
            self.history_tps.append(0.0)
            self.history_ect.append(self.current_ect or 0)
            self.history_valid.append(False)

            # Set Page 2 widgets to NULL
            for key, val_widget in self.sensor_widgets.items():
                val_widget.configure(text="NULL", fg="#DC3545")
            self.stand_lbl.configure(text="NULL (สัญญาณหลุด)", fg="#DC3545")
            self.brake_lbl.configure(text="NULL", fg="#DC3545")
            self.engine_run_lbl.configure(text="NULL", fg="#DC3545")
            self.o2_val_lbl.configure(text="NULL", fg="#DC3545")
            self.o2_heater_lbl.configure(text="NULL", fg="#DC3545")
            self.stft_val_lbl.configure(text="NULL", fg="#DC3545")
            self.fps_label.configure(text="Rate: 0.0 Hz (NULL)")

            # Set Page 1 HUD & Vitals to NULL
            self.hud_tps_val_lbl.configure(text="NULL | --- V", fg="#D29922")
            self.hud_bat_val_lbl.configure(text="NULL [ --- % ]", fg="#D29922")
            self.hud_stand_badge.configure(text="ขาตั้ง: NULL", fg="#D29922")
            self.hud_eng_badge.configure(text="เครื่องยนต์: NULL", fg="#D29922")
            for k, card_lbl in self.hud_cards.items():
                card_lbl.configure(text="NULL", fg="#D29922")

            self._render_tachometer(None, self.auto_rpm_scale, self.peak_rpm)
            self._render_speedometer(None)
            self._render_tps_bar(0.0)
            self._render_waveform()
            return

        # 1. Update Raw Table Widgets (Page 2) for valid frame
        for key, val_widget in self.sensor_widgets.items():
            if key in data and data[key] is not None:
                val_widget.configure(text=str(data[key]), fg="#212529")
            else:
                val_widget.configure(text="N/A", fg="#6C757D")

        if 'side_stand_up' in data and data['side_stand_up'] is not None:
            if data['side_stand_up']:
                self.stand_lbl.configure(text="UP (เอาขาขึ้น)", fg="#198754", bg="#FFFFFF")
            else:
                self.stand_lbl.configure(text="DOWN (เอาขาลง)", fg="#DC3545", bg="#FFFFFF")

        if 'start_interlock' in data or 'brake_active' in data:
            active = data.get('start_interlock', data.get('brake_active', False))
            if active:
                self.brake_lbl.configure(text="ACTIVE (กดสตาร์ท/เบรก)", fg="#198754", bg="#FFFFFF")
            else:
                self.brake_lbl.configure(text="OFF (ปล่อย)", fg="#6C757D", bg="#FFFFFF")

        if 'engine_running' in data and data['engine_running'] is not None:
            if data['engine_running']:
                self.engine_run_lbl.configure(text="RUNNING (ติดเครื่อง)", fg="#198754", bg="#FFFFFF")
            else:
                self.engine_run_lbl.configure(text="STOPPED (ดับเครื่อง)", fg="#DC3545", bg="#FFFFFF")

        if 'o2_v' in data and data['o2_v'] is not None:
            self.o2_val_lbl.configure(text=f"{data['o2_v']:.2f}", fg="#212529")
        if 'o2_heater' in data and data['o2_heater'] is not None:
            self.o2_heater_lbl.configure(text=f"{data['o2_heater']:.2f}", fg="#212529")
        if 'stft' in data and data['stft'] is not None:
            self.stft_val_lbl.configure(text=f"{data['stft']:.4f}", fg="#212529")

        if 'fps' in data:
            self.fps_label.configure(text=f"Rate: {data['fps']} Hz")

        # 2. Update Visual Cluster Widgets (Page 1)
        rpm = data.get('rpm', 0) or 0
        speed = data.get('speed', 0) or 0
        tps_pct = data.get('tps_pct', 0.0) or 0.0
        tps_v = data.get('tps_v', 0.5) or 0.5
        bat = data.get('battery', 0.0) or 0.0
        ect = data.get('ect')
        inj = data.get('inj_ms')

        self.current_rpm = rpm
        self.current_speed = speed
        self.current_tps = tps_pct
        self.current_ect = ect
        self.current_inj = inj

        # Dynamic Peak & Auto-Scale Math
        now = time.time()
        if rpm > self.peak_rpm:
            self.peak_rpm = rpm
            self.peak_rpm_time = now
        elif now - self.peak_rpm_time > 2.0:
            self.peak_rpm = max(rpm, int(self.peak_rpm * 0.96))

        if self.peak_rpm > 11500:
            self.auto_rpm_scale = 15000
        elif self.peak_rpm > 8500:
            self.auto_rpm_scale = 12000
        elif self.peak_rpm > 5500:
            self.auto_rpm_scale = 10000
        elif self.peak_rpm > 2600:
            self.auto_rpm_scale = 6000
        else:
            self.auto_rpm_scale = 3000

        # Feed Rolling Waveform
        self.history_rpm.append(rpm)
        self.history_tps.append(tps_pct)
        self.history_ect.append(ect if ect is not None else 0)
        self.history_valid.append(True)

        # Render Visual Cluster Gauges
        self._render_tachometer(rpm, self.auto_rpm_scale, self.peak_rpm)
        self._render_speedometer(speed)
        self._render_tps_bar(tps_pct)
        self._render_waveform()

        # Update Auxiliary Texts
        tps_deg = data.get('tps_deg')
        if tps_deg is None:
            tps_deg = min(78.5, round(tps_pct * 0.785, 1))
        self.hud_tps_val_lbl.configure(text=f"{tps_pct:.1f}% ({tps_deg:.1f}°) | {tps_v:.2f} V", fg="#58A6FF")
        bat_pct = max(0, min(100, int((bat - 10.5) / 3.0 * 100))) if bat > 0 else 0
        self.hud_bat_val_lbl.configure(text=f"{bat:.1f} V [ {bat_pct}% ]", fg="#3FB950")

        if 'side_stand_up' in data and data['side_stand_up'] is not None:
            if data['side_stand_up']:
                self.hud_stand_badge.configure(text="ขาตั้ง: 🟢 ยกขึ้น (UP)", fg="#3FB950")
            else:
                self.hud_stand_badge.configure(text="ขาตั้ง: 🔴 เอาลง (DOWN)", fg="#F85149")

        if 'engine_running' in data and data['engine_running'] is not None:
            if data['engine_running']:
                self.hud_eng_badge.configure(text="เครื่องยนต์: 🟢 RUNNING", fg="#3FB950")
            else:
                self.hud_eng_badge.configure(text="เครื่องยนต์: ⚪ STOPPED", fg="#8B949E")

        # Update Vital Cards
        if ect is not None:
            ect_color = "#58A6FF" if ect < 45 else ("#3FB950" if ect < 100 else "#F85149")
            self.hud_cards['ect'].configure(text=f"{ect} °C", fg=ect_color)
        if 'map_mbar' in data and data['map_mbar'] is not None:
            self.hud_cards['map'].configure(text=f"{data['map_mbar']} mBar", fg="#58A6FF")
        else:
            self.hud_cards['map'].configure(text="N/A", fg="#6E7681")
        if 'inj_ms' in data and data['inj_ms'] is not None:
            self.hud_cards['inj'].configure(text=f"{data['inj_ms']:.2f} ms", fg="#58A6FF")
        if 'ign_deg' in data and data['ign_deg'] is not None:
            self.hud_cards['ign'].configure(text=f"{data['ign_deg']:.1f} °", fg="#58A6FF")
        if 'o2_v' in data and data['o2_v'] is not None:
            self.hud_cards['o2'].configure(text=f"{data['o2_v']:.2f} V", fg="#58A6FF")

    # =========================================================================
    # 10. HARDWARE & ADAPTER DISCOVERY
    # =========================================================================
    def refresh_devices(self):
        self.detected_devices = scan_adapters()
        choices = [d['label'] for d in self.detected_devices]
        self.dev_combo['values'] = choices

        if choices:
            self.dev_combo.current(0)
            self.selected_device = self.detected_devices[0]
            self.connect_btn.config(state="normal")
        else:
            self.dev_combo.set("ไม่พบพอร์ต USB / FTDI")
            self.selected_device = None
            self.connect_btn.config(state="disabled")

    def _on_device_selected(self, event):
        idx = self.dev_combo.current()
        if idx >= 0:
            self.selected_device = self.detected_devices[idx]

    def toggle_connection(self):
        if self.worker and getattr(self.worker, 'running', False):
            self.worker.running = False
            self.connect_btn.configure(text="⚡ เชื่อมต่อ (Connect)", bg="#198754")
            self.ecu_online = False
            self.session_start_ts = None
            self._update_status("disconnected", "ตัดการเชื่อมต่อแล้ว (NO DATA)")
            self._reset_sensor_values()
            self.worker = None
        else:
            if not self.selected_device:
                messagebox.showwarning("คำเตือน", "กรุณาเลือกอุปกรณ์ USB / FTDI Adapter ก่อน")
                return

            self.session_start_ts = time.time()
            self.last_rx_ts = time.time()
            self.ecu_online = False
            self.wakeup_attempt = 0
            self.logged_rows = 0

            # Clear waveform history on new session start
            self.history_rpm.clear()
            self.history_tps.clear()
            self.history_ect.clear()
            self.history_valid.clear()
            for _ in range(120):
                self.history_rpm.append(0)
                self.history_tps.append(0.0)
                self.history_ect.append(0)
                self.history_valid.append(True)

            self.connect_btn.configure(text="🛑 ยกเลิก (Disconnect)", bg="#DC3545")
            self.hud_model_lbl.configure(text="⚡ กำลังเชื่อมต่อไปยังกล่อง ECU...", fg="#D29922")
            self.worker = HondaKLineEngine(
                self.selected_device,
                data_callback=self._on_telemetry_received,
                status_callback=self._on_status_changed,
                dtc_callback=self._on_dtc_received
            )
            self.worker.start()

    def _update_status(self, state, msg):
        self.status_state = state

        if state == "identified" and isinstance(msg, dict):
            model = msg.get("model", "Honda PGM-FI")
            pn = msg.get("pn", "---")
            sig_hex = msg.get("sig_hex", "---")
            rom_st = msg.get("rom_status", "---")
            self.model_val_lbl.configure(text=model, fg="#198754")
            self.pn_val_lbl.configure(text=pn, fg="#0B5ED7")
            self.ecmid_val_lbl.configure(text=sig_hex, fg="#212529")
            self.rom_match_val_lbl.configure(text=rom_st, fg="#198754")
            self.hud_model_lbl.configure(text=f"🟢 ECU: {model}", fg="#3FB950")
            self.hud_part_lbl.configure(text=f"Part: {pn} ({sig_hex})", fg="#C9D1D9")
            return

        if state == "logging_started":
            self.current_log_file = os.path.basename(str(msg))
            self.hud_log_lbl.configure(text=f"📝 ล็อก: {self.current_log_file}", fg="#58A6FF")
            return

        self.status_label.configure(text=str(msg))

        if state == "connected":
            self.ecu_online = True
            self.hud_model_lbl.configure(text="🟢 ECU: เชื่อมต่อสำเร็จ (LIVE TELEMETRY)", fg="#3FB950")
        elif state in ("connecting", "reconnecting", "error"):
            self.ecu_online = False
            self.hud_model_lbl.configure(text="⚠️ ECU: สัญญาณขาดหาย / กำลังปลุกกล่อง (บันทึกค่า NULL)", fg="#FF7B72")
        elif state == "disconnected":
            self.ecu_online = False
            self.hud_model_lbl.configure(text="⏸️ สถานะ: NO DATA (ยังไม่ได้กดเชื่อมต่อ)", fg="#8B949E")

        color_map = {
            "disconnected": ("#6C757D", "#495057"),
            "connecting": ("#FFC107", "#856404"),
            "reconnecting": ("#FD7E14", "#856404"),
            "connected": ("#28A745", "#155724"),
            "error": ("#DC3545", "#721C24")
        }
        fill_c, out_c = color_map.get(state, ("#6C757D", "#495057"))
        self.bullet_canvas.itemconfig(self.bullet_id, fill=fill_c, outline=out_c)

    def _reset_sensor_values(self):
        for widget in self.sensor_widgets.values():
            widget.configure(text="NO DATA", fg="#6C757D")
        self.stand_lbl.configure(text="NO DATA", fg="#6C757D", bg="#FFFFFF")
        self.brake_lbl.configure(text="NO DATA", fg="#6C757D", bg="#FFFFFF")
        self.engine_run_lbl.configure(text="NO DATA", fg="#6C757D", bg="#FFFFFF")
        self.o2_val_lbl.configure(text="NO DATA", fg="#6C757D")
        self.o2_heater_lbl.configure(text="NO DATA", fg="#6C757D")
        self.stft_val_lbl.configure(text="NO DATA", fg="#6C757D")
        self.fps_label.configure(text="Rate: 0.0 Hz")
        self.model_val_lbl.configure(text="--- (รอการเชื่อมต่อ)", fg="#6C757D")
        self.pn_val_lbl.configure(text="---", fg="#6C757D")
        self.ecmid_val_lbl.configure(text="---", fg="#6C757D")
        self.rom_match_val_lbl.configure(text="---", fg="#6C757D")

        self.hud_model_lbl.configure(text="⏸️ สถานะ: NO DATA (ยังไม่ได้กดเชื่อมต่อ)", fg="#8B949E")
        self.hud_part_lbl.configure(text="Part: ---")
        self.hud_timer_lbl.configure(text="⏱️ เวลาเซสชัน: 00:00:00", fg="#58A6FF")
        self.hud_tps_val_lbl.configure(text="NO DATA | --- V", fg="#8B949E")
        self.hud_bat_val_lbl.configure(text="NO DATA [ --- % ]", fg="#8B949E")
        self.hud_stand_badge.configure(text="ขาตั้ง: ---", fg="#8B949E")
        self.hud_eng_badge.configure(text="เครื่องยนต์: ---", fg="#8B949E")
        for k, card_lbl in self.hud_cards.items():
            card_lbl.configure(text="NO DATA", fg="#8B949E")

        self.current_rpm = None
        self.current_speed = None
        self.current_tps = None
        self.peak_rpm = 0
        self._render_tachometer(None, 3000, 0)
        self._render_speedometer(None)
        self._render_tps_bar(0.0)
        self._render_waveform()

    def _on_status_changed(self, state, msg):
        self.after(0, self._update_status, state, msg)

    def _on_dtc_received(self, mode, codes):
        self.after(0, self._render_dtc, mode, codes)

    def _render_dtc(self, mode, codes):
        for item in self.dtc_tree.get_children():
            self.dtc_tree.delete(item)

        if not codes:
            self.dtc_tree.insert("", tk.END, values=("OK", f"ไม่พบโค้ดข้อผิดพลาดในระบบ ({mode})"))
            return

        for c in codes:
            desc = get_dtc_description(c)
            self.dtc_tree.insert("", tk.END, values=(c, desc))

    def request_dtc(self, mode):
        if self.worker and getattr(self.worker, 'running', False):
            self.worker.cmd_queue.put({'action': 'read_dtc', 'mode': mode})
        else:
            messagebox.showinfo("แจ้งเตือน", "กรุณาเชื่อมต่อกับกล่อง ECU ก่อนอ่านโค้ด")

    def request_clear_dtc(self):
        if self.worker and getattr(self.worker, 'running', False):
            if messagebox.askyesno("ยืนยัน", "คุณต้องการลบโค้ดข้อผิดพลาด (DTC) ทั้งหมดใช่หรือไม่?"):
                self.worker.cmd_queue.put({'action': 'clear_dtc'})
        else:
            messagebox.showinfo("แจ้งเตือน", "กรุณาเชื่อมต่อกับกล่อง ECU ก่อนลบโค้ด")

    def on_security_access(self):
        if self.worker and getattr(self.worker, 'running', False):
            self.sec_btn.configure(state="disabled", text="⏳ Authenticating...")
            self.worker.cmd_queue.put({
                'action': 'security_access',
                'callback': self._on_security_result
            })
        else:
            messagebox.showinfo("Security Access", "กรุณาเชื่อมต่อกับกล่อง ECU ก่อนทำ Security Access")

    def _on_security_result(self, success, message):
        self.after(0, self._show_security_result_ui, success, message)

    def _show_security_result_ui(self, success, message):
        self.sec_btn.configure(state="normal", text="🔒 Security Access")
        if success:
            messagebox.showinfo("Security Access", f"✅ สำเร็จ:\n{message}")
        else:
            messagebox.showerror("Security Access", f"❌ การเข้าถึงถูกปฏิเสธ (Denied):\n{message}")

    def _export_snapshot(self):
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        target_dir = get_sub_directory("data")
        file_path = os.path.join(target_dir, f"telemetry_snapshot_{timestamp}.txt")

        try:
            with open(file_path, "w", encoding="utf-8") as f:
                f.write("=== PyKLine Studio Telemetry Snapshot ===\n")
                f.write(f"Timestamp: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
                f.write(f"Connection Status: {'ONLINE' if self.ecu_online else 'NULL / DISCONNECTED'}\n")
                f.write(f"Engine Speed (RPM): {self.current_rpm}\n")
                f.write(f"Peak RPM (Session): {self.peak_rpm}\n")
                f.write(f"Throttle (TPS %): {self.current_tps}\n")
                f.write(f"Coolant Temp (ECT): {self.current_ect} C\n")
                f.write(f"Vehicle Speed: {self.current_speed} Km/h\n")
                f.write(f"Auto-Scale Range: 0 - {self.auto_rpm_scale} RPM\n")
            messagebox.showinfo("Snapshot Export", f"บันทึกข้อมูล Telemetry Snapshot เรียบร้อย:\n{os.path.basename(file_path)}")
        except Exception as e:
            messagebox.showerror("Error", f"ไม่สามารถบันทึก Snapshot ได้: {e}")


def main():
    app = PyKLineApp()
    app.mainloop()


if __name__ == '__main__':
    main()
