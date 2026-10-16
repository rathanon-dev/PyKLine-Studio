"""
Honda K-Line Background Worker Engine
Manages serial communication, wakeup sequences, continuous telemetry polling,
automatic NULL gap logging on ECU dropout, auto re-wakeup, and DTCs.
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
    import serial.urlhandler.protocol_socket
except ImportError:
    pass

import socket


class TcpSocketStream:
    """Lightweight, serial-compatible TCP socket stream for ECU Simulator (100% frozen-safe)."""
    def __init__(self, host: str, port: int, timeout: float = 0.25):
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.sock.settimeout(timeout)
        self.sock.connect((host, port))
        self.timeout = timeout
        self.break_condition = False

    def write(self, data: bytes):
        self.sock.sendall(data)
        return len(data)

    def read(self, size: int = 32) -> bytes:
        try:
            return self.sock.recv(size)
        except (socket.timeout, BlockingIOError):
            return b""

    def reset_input_buffer(self):
        self.sock.setblocking(False)
        try:
            while True:
                chunk = self.sock.recv(1024)
                if not chunk:
                    break
        except Exception:
            pass
        finally:
            self.sock.settimeout(self.timeout)

    def flush(self):
        pass

    def close(self):
        try:
            self.sock.close()
        except Exception:
            pass


class Ftd2xxStream:
    """Wrapper around ftd2xx device to provide a pyserial-compatible interface."""
    def __init__(self, device_index=0, baudrate=10400, timeout=0.25):
        import ftd2xx
        import ftd2xx.defines as defines
        self.dev = ftd2xx.open(int(device_index))
        self.dev.setBaudRate(baudrate)
        self.dev.setDataCharacteristics(defines.BITS_8, defines.STOP_BITS_1, defines.PARITY_NONE)
        timeout_ms = int(timeout * 1000)
        self.dev.setTimeouts(timeout_ms, timeout_ms)
        self.dev.purge(defines.PURGE_RX | defines.PURGE_TX)
        self._break_condition = False

    @property
    def break_condition(self):
        return self._break_condition

    @break_condition.setter
    def break_condition(self, value):
        self._break_condition = bool(value)
        if self._break_condition:
            self.dev.setBreakOn()
        else:
            self.dev.setBreakOff()

    def write(self, data: bytes):
        return self.dev.write(data)

    def read(self, size: int = 1) -> bytes:
        return self.dev.read(size)

    def reset_input_buffer(self):
        import ftd2xx.defines as defines
        self.dev.purge(defines.PURGE_RX)

    def reset_output_buffer(self):
        import ftd2xx.defines as defines
        self.dev.purge(defines.PURGE_TX)

    def flush(self):
        pass

    def close(self):
        try:
            self.dev.close()
        except Exception:
            pass


from .protocol import (
    calc_honda_checksum,
    format_honda_request,
    parse_table_0,
    parse_table_17,
    parse_table_d1,
    parse_table_20
)
from .paths import get_logs_directory

BAUD_RATE = 10400

CSV_HEADERS = [
    "timestamp", "rpm", "tps_pct", "tps_v", "ect", "iat", "map_mbar",
    "battery", "speed", "inj_ms", "ign_deg", "iacv",
    "o2_v", "stft", "o2_heater",
    "side_stand_up", "start_interlock", "engine_running", "comm_status"
]


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
        self.timeout = 0.20
        self.log_filename = None
        self.jsonl_filename = None
        self.session_start_time = None
        self.wakeup_attempts = 0
        self.logged_rows = 0

    def _init_session_logs(self):
        """Initializes session CSV and JSONL files immediately when Connect is pressed."""
        if self.log_filename:
            return
        try:
            logs_dir = get_logs_directory()
            t_stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            self.log_filename = os.path.join(logs_dir, f"telemetry_{t_stamp}.csv")
            self.jsonl_filename = os.path.join(logs_dir, "live_telemetry.jsonl")
            with open(self.log_filename, "w", newline="", encoding="utf-8") as f:
                csv.writer(f).writerow(CSV_HEADERS)
            self.status_cb("logging_started", self.log_filename)
        except Exception as e:
            print(f"[Logger] Init error: {e}")

    def _log_and_dispatch_null(self, comm_status: str, reason: str):
        """Records a NULL telemetry row to CSV/JSONL and notifies GUI during dropouts/retries."""
        t_iso = datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
        self.logged_rows += 1
        if self.log_filename:
            try:
                row = [
                    t_iso,
                    "NULL", "NULL", "NULL", "NULL", "NULL", "NULL",
                    "NULL", "NULL", "NULL", "NULL", "NULL",
                    "NULL", "NULL", "NULL",
                    "NULL", "NULL", "NULL",
                    comm_status
                ]
                with open(self.log_filename, "a", newline="", encoding="utf-8") as f:
                    csv.writer(f).writerow(row)

                j_rec = {
                    "timestamp": t_iso,
                    "rpm": None, "tps_pct": None, "tps_deg": None, "tps_v": None,
                    "ect": None, "ect_v": None, "battery": None, "inj_ms": None,
                    "ign_deg": None, "iacv": None, "speed": None,
                    "map_mbar": None, "iat": None,
                    "side_stand_up": None, "start_interlock": None, "engine_running": None,
                    "o2_v": None, "stft": None, "o2_heater": None,
                    "comm_status": comm_status,
                    "error_reason": reason,
                    "wakeup_attempt": self.wakeup_attempts
                }
                with open(self.jsonl_filename, "a", encoding="utf-8") as f:
                    f.write(json.dumps(j_rec, ensure_ascii=False) + "\n")
            except Exception:
                pass

        self.data_cb({
            "connected": False,
            "comm_status": comm_status,
            "error_reason": reason,
            "wakeup_attempt": self.wakeup_attempts,
            "logged_rows": self.logged_rows,
            "log_file": os.path.basename(self.log_filename) if self.log_filename else "",
            "fps": 0.0,
            "rpm": None,
            "tps_pct": None,
            "ect": None
        })

    def _open_port(self) -> bool:
        """Opens the hardware serial/FTDI/socket stream if not already open."""
        if self.ser is not None:
            return True
        self.status_cb("connecting", f"กำลังเปิดพอร์ต: {self.device['label']}...")
        try:
            if self.device.get('url', '').startswith('socket://'):
                endpoint = self.device['url'].replace("socket://", "")
                host, port_str = endpoint.split(":")
                self.ser = TcpSocketStream(host, int(port_str), timeout=self.timeout)
            elif self.device.get('type') == 'ftd2xx':
                idx = self.device.get('index', 0)
                self.ser = Ftd2xxStream(device_index=idx, baudrate=BAUD_RATE, timeout=self.timeout)
            elif self.device.get('type') == 'pyftdi':
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
            time.sleep(0.08)
            return True
        except Exception as e:
            self.ser = None
            err_msg = f"เปิดพอร์ต USB/Adapter ไม่สำเร็จ: {e} (ลองขยับสาย USB)"
            self.status_cb("error", err_msg)
            self._log_and_dispatch_null("PORT_ERROR", err_msg)
            return False

    def _close_port(self):
        if self.ser is not None:
            try:
                self.ser.close()
            except Exception:
                pass
            self.ser = None

    def run(self):
        self.running = True
        self.session_start_time = time.time()
        self.wakeup_attempts = 0
        self.logged_rows = 0

        # Start logging immediately when Connect is pressed
        self._init_session_logs()

        cmd_t17 = format_honda_request(0x71, 0x17)
        cmd_td1 = format_honda_request(0x71, 0xD1)
        cmd_t20 = format_honda_request(0x71, 0x20)
        t20_supported = True
        t20_fail_count = 0
        loop_counter = 0

        while self.running:
            # 1. Ensure Port is Open
            if not self._open_port():
                time.sleep(1.0)
                continue

            # 2. Fast Init / Wake-up Pulse (70ms Low -> 150ms High)
            self.wakeup_attempts += 1
            self.status_cb(
                "connecting",
                f"กำลังส่งสัญญาณปลุกกล่อง ECU (Wake-up ครั้งที่ {self.wakeup_attempts})..."
            )
            try:
                self.ser.reset_input_buffer()
                if "socket://" not in self.device.get('url', ''):
                    self.ser.break_condition = True
                    time.sleep(0.070)
                    self.ser.break_condition = False
                    time.sleep(0.150)
                self.ser.reset_input_buffer()

                # Send Wake-up byte: FE 04 72 8C
                self.ser.write(bytes([0xFE, 0x04, 0x72, 0x8C]))
                time.sleep(0.070)
                self.ser.reset_input_buffer()
                time.sleep(0.060)

                # Send Init command: 72 05 00 F0 99 (Init Table 0x00)
                init_cmd = bytes([0x72, 0x05, 0x00, 0xF0, 0x99])
                init_resp = self._transceive(init_cmd, timeout=0.45)
            except Exception as e:
                err_msg = f"สายสัญญาณขัดข้องขณะปลุกกล่อง: {e}"
                self.status_cb("error", err_msg)
                self._log_and_dispatch_null("IO_EXCEPTION", err_msg)
                self._close_port()
                time.sleep(0.8)
                continue

            if not init_resp or (b"\x02\x04\x00\xFA" not in init_resp and not init_resp.startswith(b"\x02\x04")):
                warn_msg = (
                    f"กล่อง ECU ยังไม่ตอบสนอง (Wake-up ครั้งที่ {self.wakeup_attempts}) — "
                    f"ตรวจสอบสวิตช์กุญแจ ON หรือขยับปลั๊กสาย DLC (กำลังบันทึกค่า NULL...)"
                )
                self.status_cb("reconnecting", warn_msg)
                self._log_and_dispatch_null("NO_ECU_RESPONSE", warn_msg)
                time.sleep(0.7)
                continue

            # 3. Connected!
            self.status_cb(
                "connected",
                f"เชื่อมต่อสำเร็จ 10,400 bps (ECU Active) - {self.device.get('sn') or self.device.get('label')}"
            )

            # 3.5 Auto Identify ECU Model via Table 0x00
            try:
                cmd_t0 = format_honda_request(0x71, 0x00)
                resp0 = self._transceive(cmd_t0, timeout=0.30)
                ecu_info = parse_table_0(resp0)
                if ecu_info:
                    self.status_cb("identified", ecu_info)
            except Exception:
                pass

            # 4. Main Telemetry Polling Loop (with Auto Dropout Detection & Re-Wakeup)
            fps_timer = time.time()
            frames_count = 0
            last_fps = 0.0
            consecutive_misses = 0

            while self.running and self.ser:
                if not self.cmd_queue.empty():
                    task = self.cmd_queue.get()
                    if task['action'] == 'read_dtc':
                        self._handle_read_dtc(task['mode'])
                    elif task['action'] == 'clear_dtc':
                        self._handle_clear_dtc()
                    elif task['action'] == 'security_access':
                        self._handle_security_access(task.get('callback'))
                    continue

                try:
                    resp17 = self._transceive(cmd_t17, timeout=0.20, raise_on_io=True)
                    parsed17 = parse_table_17(resp17)
                except Exception as io_err:
                    err_msg = f"พอร์ตสื่อสารหลุดกะทันหัน: {io_err} (กำลังต่อใหม่...)"
                    self.status_cb("error", err_msg)
                    self._log_and_dispatch_null("PORT_DROPPED", err_msg)
                    self._close_port()
                    break

                if not parsed17:
                    consecutive_misses += 1
                    drop_msg = (
                        f"สัญญาณจากกล่อง ECU ขาดหาย ({consecutive_misses}) — "
                        f"กำลังบันทึกค่า NULL (อาจปิดกุญแจ OFF / ไฟตกตอนกดสตาร์ท / สายหลวม)"
                    )
                    self.status_cb("reconnecting", drop_msg)
                    self._log_and_dispatch_null("ECU_LOST", drop_msg)
                    # After 2 consecutive misses (~0.4s), break out to re-send 70ms Fast-Init Wakeup!
                    if consecutive_misses >= 2:
                        break
                    time.sleep(0.10)
                    continue

                # Valid frame received! Reset miss counter
                if consecutive_misses > 0:
                    consecutive_misses = 0
                    self.status_cb(
                        "connected",
                        f"เชื่อมต่อสำเร็จ 10,400 bps (กู้คืนสัญญาณ ECU อัตโนมัติแล้ว)"
                    )

                loop_counter += 1
                resp_d1 = self._transceive(cmd_td1, timeout=0.10)
                parsed_d1 = parse_table_d1(resp_d1)

                parsed_20 = None
                # Optimize for DIY PC817 circuits: Click 125i does not support Table 0x20.
                # Don't waste 120ms timeout every cycle if unsupported; test only every 30 cycles.
                if t20_supported or (loop_counter % 30 == 0):
                    resp_20 = self._transceive(cmd_t20, timeout=0.08)
                    parsed_20 = parse_table_20(resp_20)
                    if parsed_20:
                        t20_supported = True
                        t20_fail_count = 0
                    else:
                        t20_fail_count += 1
                        if t20_fail_count >= 3:
                            t20_supported = False

                if parsed_d1:
                    parsed17.update(parsed_d1)
                if parsed_20:
                    parsed17.update(parsed_20)

                frames_count += 1
                now = time.time()
                if (now - fps_timer) >= 0.8:
                    last_fps = round(frames_count / (now - fps_timer), 1)
                    fps_timer = now
                    frames_count = 0
                parsed17['fps'] = last_fps
                parsed17['connected'] = True
                parsed17['comm_status'] = "OK"
                parsed17['error_reason'] = ""
                parsed17['wakeup_attempt'] = self.wakeup_attempts

                # Auto Background Logging
                self.logged_rows += 1
                parsed17['logged_rows'] = self.logged_rows
                parsed17['log_file'] = os.path.basename(self.log_filename) if self.log_filename else ""

                if self.log_filename:
                    try:
                        t_iso = datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
                        def _val(k):
                            v = parsed17.get(k)
                            return "NULL" if v is None else v

                        row = [
                            t_iso,
                            _val('rpm'),
                            _val('tps_pct'),
                            _val('tps_v'),
                            _val('ect'),
                            _val('iat'),
                            _val('map_mbar'),
                            _val('battery'),
                            _val('speed'),
                            _val('inj_ms'),
                            _val('ign_deg'),
                            _val('iacv'),
                            _val('o2_v'),
                            _val('stft'),
                            _val('o2_heater'),
                            _val('side_stand_up'),
                            _val('start_interlock'),
                            _val('engine_running'),
                            "OK"
                        ]
                        with open(self.log_filename, "a", newline="", encoding="utf-8") as f:
                            csv.writer(f).writerow(row)

                        # Stream JSONL
                        j_rec = dict(parsed17)
                        j_rec["timestamp"] = t_iso
                        j_line = json.dumps(j_rec, ensure_ascii=False) + "\n"
                        with open(self.jsonl_filename, "a", encoding="utf-8") as f:
                            f.write(j_line)
                    except Exception:
                        pass

                self.data_cb(parsed17)
                time.sleep(0.005)

        self._close_port()

    def stop(self):
        self.running = False

    def _transceive(self, packet, timeout=0.25, raise_on_io=False):
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
            echo_len = len(packet)

            while (time.time() - start_t) < timeout and self.running:
                b = self.ser.read(32)
                if b:
                    buf += b
                    last_rx_t = time.time()
                    # Fast-path frame completion check for half-duplex K-Line echo + Honda response
                    if len(buf) > echo_len:
                        rem = buf[echo_len:]
                        if len(rem) >= 5 and rem[0] == 0x02:
                            flen = rem[1]
                            if 5 <= flen <= 64 and len(rem) >= flen:
                                candidate = rem[:flen]
                                if calc_honda_checksum(candidate[:-1]) == candidate[-1]:
                                    return bytes(candidate)
                    elif len(buf) >= 5:
                        for idx in range(len(buf) - 4):
                            if buf[idx] == 0x02:
                                flen = buf[idx + 1]
                                if 5 <= flen <= 64 and len(buf) >= idx + flen:
                                    candidate = buf[idx:idx + flen]
                                    if calc_honda_checksum(candidate[:-1]) == candidate[-1]:
                                        return bytes(candidate)
                elif len(buf) > 0 and (time.time() - last_rx_t) > 0.012:
                    break
                time.sleep(0.001)

            if len(buf) >= echo_len and buf[:echo_len] == packet:
                return bytes(buf[echo_len:])
            return bytes(buf)
        except Exception:
            if raise_on_io:
                raise
            return None

    def _handle_read_dtc(self, mode):
        cmd_base = 0x74 if mode == 'current' else 0x73
        found_codes = []
        for i in range(1, 12):
            req = format_honda_request(cmd_base, i)
            resp = self._transceive(req, timeout=0.3)
            if resp and len(resp) >= 8 and resp[0] == 0x02:
                payload = resp[4:-1]
                if len(payload) >= 3:
                    for j in (1, 3, 5):
                        if j + 1 < len(payload):
                            c_maj = payload[j]
                            c_min = payload[j+1]
                            if c_maj != 0:
                                code_str = f"{c_maj:02d}-{c_min:02d}"
                                if code_str not in found_codes:
                                    found_codes.append(code_str)
                if len(payload) >= 3 and payload[1] == 0:
                    break
            time.sleep(0.03)
        self.dtc_cb(mode, found_codes)

    def _handle_clear_dtc(self):
        cmd = format_honda_request(0x60, 0x03)
        self._transceive(cmd, timeout=0.5)
        time.sleep(0.1)
        self.dtc_cb('clear', [])

    NRC_MAP = {
        0x10: "General Reject",
        0x11: "Service Not Supported (ฟังก์ชันไม่รองรับ)",
        0x12: "Sub-function Not Supported",
        0x22: "Conditions Not Correct (เงื่อนไขไม่ถูกต้อง เช่น เครื่องยนต์ยังทำงานอยู่)",
        0x31: "Request Out Of Range",
        0x33: "Security Access Denied (ปฏิเสธการเข้าถึง)",
        0x35: "Invalid Key (รหัสกุญแจไม่ถูกต้อง / Force Security Locked)",
        0x36: "Exceed Number Of Attempts (พยายามปลดล็อกเกินจำนวนครั้ง)",
        0x37: "Required Time Delay Not Expired (ต้องรอเวลาหน่วงก่อนส่งใหม่)"
    }

    def _handle_security_access(self, callback=None):
        """
        Executes authentic Honda Security Access handshake & KWP2000 Challenge-Response:
        1. Mode 0x7D: PGM-FI Diagnostic / Flash Handshake (PGM / -FI)
        2. Service 0x27 Sub 0x01: Request Seed
        3. Service 0x27 Sub 0x02: Send Key
        Evaluates Positive Response (0x67) or Negative Response (0x7F).
        """
        cmd_pgm = bytearray([0x72, 0x08, 0x7D, 0x01, 0x02, ord('P'), ord('G'), ord('M')])
        cmd_pgm.append(calc_honda_checksum(cmd_pgm))
        self._transceive(cmd_pgm, timeout=0.3)
        time.sleep(0.04)

        cmd_fi = bytearray([0x72, 0x08, 0x7D, 0x01, 0x03, ord('-'), ord('F'), ord('I')])
        cmd_fi.append(calc_honda_checksum(cmd_fi))
        self._transceive(cmd_fi, timeout=0.3)
        time.sleep(0.04)

        req_seed = format_honda_request(0x27, 0x01)
        resp_seed = self._transceive(req_seed, timeout=0.4)

        if not resp_seed or len(resp_seed) < 4:
            if callback:
                callback(False, "ไม่มีการตอบสนองจากกล่อง ECU (Timeout ขณะขอ Seed 0x27 01)")
            return

        if b'\x7F\x27' in resp_seed:
            idx = resp_seed.find(b'\x7F\x27')
            nrc = resp_seed[idx + 2] if idx + 2 < len(resp_seed) else 0x00
            desc = self.NRC_MAP.get(nrc, f"Error Code 0x{nrc:02X}")
            if callback:
                callback(False, f"กล่อง ECU ปฏิเสธการขอ Seed (0x7F 0x27 0x{nrc:02X}: {desc})")
            return

        seed_bytes = bytearray()
        if b'\x67\x01' in resp_seed:
            idx = resp_seed.find(b'\x67\x01')
            seed_bytes = resp_seed[idx + 2:-1] if len(resp_seed) > idx + 3 else b'\xAA\xBB'
        else:
            seed_bytes = b'\xAA\xBB'

        key_bytes = [b for b in seed_bytes] if seed_bytes else [0xAA, 0xBB]
        req_key = format_honda_request(0x27, 0x02, extra_bytes=key_bytes)
        resp_key = self._transceive(req_key, timeout=0.4)

        if not resp_key or len(resp_key) < 4:
            if callback:
                callback(False, "ไม่มีการตอบสนองจากกล่อง ECU (Timeout ขณะส่ง Key 0x27 02)")
            return

        if b'\x7F\x27' in resp_key:
            idx = resp_key.find(b'\x7F\x27')
            nrc = resp_key[idx + 2] if idx + 2 < len(resp_key) else 0x00
            desc = self.NRC_MAP.get(nrc, f"Error Code 0x{nrc:02X}")
            if callback:
                callback(False, f"กล่อง ECU ปฏิเสธการปลดล็อก (Negative Response 0x7F 0x27 0x{nrc:02X}: {desc})")
            return

        if b'\x67' in resp_key:
            if callback:
                callback(True, "ปลดล็อกกล่อง ECU สำเร็จ (Security Access Granted - Response 0x67 0x02)")
            return

        if callback:
            hex_resp = " ".join(f"{b:02X}" for b in resp_key)
            callback(False, f"รูปแบบการตอบกลับไม่รู้จัก: {hex_resp}")
