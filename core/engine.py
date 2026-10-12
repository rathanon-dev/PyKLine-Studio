"""
Honda K-Line Background Worker Engine
Manages serial communication, wakeup sequences, telemetry polling, and DTCs.
"""

import os
import csv
import json
from datetime import datetime
import time
import threading
import queue

try:
    import pyftdi.serialext
except ImportError:
    pass

try:
    import serial
except ImportError:
    pass

from .protocol import (
    calc_honda_checksum,
    format_honda_request,
    parse_table_0,
    parse_table_17,
    parse_table_d1,
    parse_table_20
)
from .paths import get_logs_directory, get_workspace_directory

BAUD_RATE = 10400

class HondaKLineEngine(threading.Thread):
    def __init__(self, target_device, data_callback, status_callback, dtc_callback):
        super().__init__(daemon=True)
        self.device = target_device
        self.data_cb = data_callback
        self.status_cb = status_callback
        self.dtc_cb = dtc_callback
        self.running = False
        self.ser = None
        self.cmd_queue = queue.Queue()
        self.timeout = 0.25
        self.log_filename = None
        self.jsonl_filename = None
        self.root_jsonl_filename = None
        
    def run(self):
        self.running = True
        while self.running:
            # 1. Open Port
            self.status_cb("connecting", f"กำลังเปิดพอร์ต: {self.device['label']}...")
            try:
                if self.device['type'] == 'pyftdi':
                    self.ser = pyftdi.serialext.serial_for_url(
                        self.device['url'],
                        baudrate=BAUD_RATE,
                        timeout=self.timeout
                    )
                else:
                    self.ser = serial.serial_for_url(
                        self.device['url'],
                        baudrate=BAUD_RATE,
                        timeout=self.timeout
                    )
            except Exception as e:
                self.status_cb("error", f"เปิดอุปกรณ์ไม่สำเร็จ: {e}")
                time.sleep(2.0)
                continue

            time.sleep(0.1)

            # 2. Fast Init / Wake-up Pulse (70ms Low -> 150ms High)
            self.status_cb("connecting", "กำลังส่งสัญญาณปลุกกล่อง ECU (Wake-up Pulse 70ms)...")
            try:
                self.ser.reset_input_buffer()
                if "socket://" not in self.device['url']:
                    self.ser.break_condition = True
                    time.sleep(0.070)
                    self.ser.break_condition = False
                    time.sleep(0.150)
                self.ser.reset_input_buffer()

                # Send Wake-up byte: FE 04 72 8C
                self.ser.write(bytes([0xFE, 0x04, 0x72, 0x8C]))
                time.sleep(0.080)
                self.ser.reset_input_buffer()
                time.sleep(0.080)

                # Send Init command: 72 05 00 F0 99 (Init Table 0x00)
                init_cmd = bytes([0x72, 0x05, 0x00, 0xF0, 0x99])
                init_resp = self._transceive(init_cmd, timeout=0.8)
            except Exception as e:
                self.status_cb("error", f"ปลุกกล่องขัดข้อง: {e}")
                self.ser.close()
                time.sleep(1.5)
                continue

            if not init_resp or (b"\x02\x04\x00\xFA" not in init_resp and not init_resp.startswith(b"\x02\x04")):
                self.status_cb("error", "กล่อง ECU ไม่ตอบสนอง (ตรวจสอบกุญแจรถ ON หรือไฟแบต 12V)")
                self.ser.close()
                time.sleep(2.0)
                continue

            # 3. Connected!
            self.status_cb("connected", f"เชื่อมต่อสำเร็จ 10,400 bps (ECU Active) - {self.device['sn'] or self.device['label']}")

            # Initialize Background Logging Files (Portable Companion Workspace)
            try:
                logs_dir = get_logs_directory()
                
                t_stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                self.log_filename = os.path.join(logs_dir, f"telemetry_{t_stamp}.csv")
                self.jsonl_filename = os.path.join(logs_dir, "live_telemetry.jsonl")
                
                workspace_dir = get_workspace_directory()
                self.root_jsonl_filename = os.path.join(workspace_dir, "ai_telemetry.jsonl")
                
                # Write CSV header
                headers = [
                    "timestamp", "rpm", "tps_pct", "tps_v", "ect", "iat", "map_mbar",
                    "battery", "speed", "inj_ms", "ign_deg", "iacv",
                    "o2_v", "stft", "o2_heater",
                    "side_stand_up", "start_interlock", "engine_running"
                ]
                with open(self.log_filename, "w", newline="", encoding="utf-8") as f:
                    csv.writer(f).writerow(headers)
                    
                self.status_cb("logging_started", self.log_filename)
            except Exception as e:
                print(f"[Logger] Init error: {e}")

            # 3.5 Auto Identify ECU Model via Table 0x00
            try:
                cmd_t0 = format_honda_request(0x71, 0x00)
                resp0 = self._transceive(cmd_t0, timeout=0.35)
                ecu_info = parse_table_0(resp0)
                if ecu_info:
                    self.status_cb("identified", ecu_info)
            except Exception:
                pass

            # 4. Main Telemetry Polling Loop
            cmd_t17 = format_honda_request(0x71, 0x17)
            cmd_td1 = format_honda_request(0x71, 0xD1)
            cmd_t20 = format_honda_request(0x71, 0x20)
            
            fps_timer = time.time()
            frames_count = 0
            
            while self.running and self.ser:
                if not self.cmd_queue.empty():
                    task = self.cmd_queue.get()
                    if task['action'] == 'read_dtc':
                        self._handle_read_dtc(task['mode'])
                    elif task['action'] == 'clear_dtc':
                        self._handle_clear_dtc()
                    elif task['action'] == 'security_access':
                        self._handle_security_access()
                    continue

                resp17 = self._transceive(cmd_t17, timeout=0.25)
                parsed17 = parse_table_17(resp17)
                
                resp_d1 = self._transceive(cmd_td1, timeout=0.15)
                parsed_d1 = parse_table_d1(resp_d1)
                
                resp_20 = self._transceive(cmd_t20, timeout=0.15)
                parsed_20 = parse_table_20(resp_20)
                
                if parsed17:
                    if parsed_d1:
                        parsed17.update(parsed_d1)
                    if parsed_20:
                        parsed17.update(parsed_20)
                    frames_count += 1
                    now = time.time()
                    if (now - fps_timer) >= 1.0:
                        parsed17['fps'] = round(frames_count / (now - fps_timer), 1)
                        fps_timer = now
                        frames_count = 0

                    # Auto Background Logging
                    if self.log_filename:
                        try:
                            t_iso = datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
                            row = [
                                t_iso,
                                parsed17.get('rpm', ''),
                                parsed17.get('tps_pct', ''),
                                parsed17.get('tps_v', ''),
                                parsed17.get('ect', ''),
                                parsed17.get('iat', ''),
                                parsed17.get('map_mbar', ''),
                                parsed17.get('battery', ''),
                                parsed17.get('speed', ''),
                                parsed17.get('inj_ms', ''),
                                parsed17.get('ign_deg', ''),
                                parsed17.get('iacv', ''),
                                parsed17.get('o2_v', ''),
                                parsed17.get('stft', ''),
                                parsed17.get('o2_heater', ''),
                                parsed17.get('side_stand_up', ''),
                                parsed17.get('start_interlock', ''),
                                parsed17.get('engine_running', '')
                            ]
                            with open(self.log_filename, "a", newline="", encoding="utf-8") as f:
                                csv.writer(f).writerow(row)
                            
                            # Stream JSONL
                            j_rec = dict(parsed17)
                            j_rec["timestamp"] = t_iso
                            j_line = json.dumps(j_rec, ensure_ascii=False) + "\n"
                            with open(self.jsonl_filename, "a", encoding="utf-8") as f:
                                f.write(j_line)
                            if self.root_jsonl_filename:
                                with open(self.root_jsonl_filename, "a", encoding="utf-8") as f:
                                    f.write(j_line)
                        except Exception:
                            pass

                    self.data_cb(parsed17)
                
                time.sleep(0.04)

            if self.ser:
                try:
                    self.ser.close()
                except Exception:
                    pass

    def stop(self):
        self.running = False

    def _transceive(self, packet, timeout=0.35):
        if not self.ser:
            return None
        try:
            self.ser.reset_input_buffer()
            self.ser.write(packet)
            if hasattr(self.ser, 'flush'):
                self.ser.flush()

            buf = bytearray()
            start_t = time.time()
            last_rx_t = time.time()
            
            while (time.time() - start_t) < timeout and self.running:
                b = self.ser.read(32)
                if b:
                    buf += b
                    last_rx_t = time.time()
                elif len(buf) > 0 and (time.time() - last_rx_t) > 0.030:
                    break
                time.sleep(0.002)

            echo_len = len(packet)
            if len(buf) >= echo_len and buf[:echo_len] == packet:
                return bytes(buf[echo_len:])
            return bytes(buf)
        except Exception:
            return None

    def _handle_read_dtc(self, mode):
        cmd_base = 0x74 if mode == 'current' else 0x73
        found_codes = []
        for i in range(1, 12):
            req = format_honda_request(cmd_base, i)
            resp = self._transceive(req, timeout=0.3)
            # Valid frame format: 02 LEN MODE PKT X c1 m1 c2 m2 c3 m3 ... CS
            if resp and len(resp) >= 8 and resp[0] == 0x02:
                payload = resp[4:-1] # payload starts at X
                if len(payload) >= 3:
                    # Check up to 3 pairs per packet. Pairs start at offsets 1, 3, 5
                    for j in (1, 3, 5):
                        if j + 1 < len(payload):
                            c_maj = payload[j]
                            c_min = payload[j+1]
                            if c_maj != 0:
                                code_str = f"{c_maj:02d}-{c_min:02d}"
                                if code_str not in found_codes:
                                    found_codes.append(code_str)
                # If packet has fewer than 3 codes, ECU fills rest with 0
                # In many cases, X (payload[0]) is the number of codes or status? Usually 0.
                if len(payload) >= 3 and payload[1] == 0:
                    break
            time.sleep(0.03)
        self.dtc_cb(mode, found_codes)

    def _handle_clear_dtc(self):
        cmd = format_honda_request(0x60, 0x03)
        self._transceive(cmd, timeout=0.5)
        time.sleep(0.1)
        self.dtc_cb('clear', [])

    def _handle_security_access(self):
        cmd1 = bytearray([0x72, 0x08, 0x7D, 0x01, 0x02, ord('P'), ord('G'), ord('M')])
        cmd1.append(calc_honda_checksum(cmd1))
        self._transceive(cmd1, timeout=0.3)
        time.sleep(0.05)

        cmd2 = bytearray([0x72, 0x08, 0x7D, 0x01, 0x03, ord('-'), ord('F'), ord('I')])
        cmd2.append(calc_honda_checksum(cmd2))
        self._transceive(cmd2, timeout=0.3)
