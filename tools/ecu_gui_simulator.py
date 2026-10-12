import tkinter as tk
from tkinter import ttk
import socket
import threading
import time
import random

PORT = 9999

def calc_honda_checksum(data):
    return (0x100 - (sum(data) & 0xFF)) & 0xFF

class ECU_Simulator(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("ECU Physics & Flash Simulator")
        self.geometry("500x650")
        self.protocol("WM_DELETE_WINDOW", self.on_close)
        
        self.server = None
        self.running = True
        
        # ECU State
        self.engine_on = tk.BooleanVar(value=False)
        self.brake_left = tk.BooleanVar(value=False)
        self.stand_down = tk.BooleanVar(value=True) # Default stand down
        self.start_btn_pressed = False
        
        self.throttle_pct = tk.DoubleVar(value=0.0)
        
        # Faults
        self.fault_ect = tk.BooleanVar(value=False)
        self.fault_tps = tk.BooleanVar(value=False)
        self.fault_iac = tk.BooleanVar(value=False)
        self.fault_o2 = tk.BooleanVar(value=False)
        self.fault_inj = tk.BooleanVar(value=False)
        # Physics State
        self.engine_temp_c = 35.0
        self.current_rpm = 0
        self.vehicle_speed = 0.0
        self.inj_ms = 0.0
        self.ign_deg = -64.0
        
        self.build_ui()
        self.start_server_thread()
        self.update_physics()
        
    def build_ui(self):
        main_frame = ttk.Frame(self, padding=10)
        main_frame.pack(fill=tk.BOTH, expand=True)
        
        # --- Engine Status ---
        status_frame = ttk.LabelFrame(main_frame, text="Engine Status", padding=10)
        status_frame.pack(fill=tk.X, pady=5)
        
        self.lbl_status = ttk.Label(status_frame, text="ENGINE OFF", foreground="red", font=("Arial", 16, "bold"))
        self.lbl_status.pack()
        
        self.lbl_rpm = ttk.Label(status_frame, text="RPM: 0", font=("Arial", 12))
        self.lbl_rpm.pack()
        
        # --- Controls ---
        ctrl_frame = ttk.LabelFrame(main_frame, text="Rider Controls", padding=10)
        ctrl_frame.pack(fill=tk.X, pady=5)
        
        ttk.Checkbutton(ctrl_frame, text="Stand Down (ขาตั้งลง)", variable=self.stand_down, command=self.check_engine_stall).pack(anchor=tk.W)
        ttk.Checkbutton(ctrl_frame, text="Hold Left Brake (กำเบรกซ้าย)", variable=self.brake_left).pack(anchor=tk.W)
        
        self.btn_start = ttk.Button(ctrl_frame, text="[HOLD] START ENGINE", command=None)
        self.btn_start.bind("<ButtonPress-1>", self.on_start_press)
        self.btn_start.bind("<ButtonRelease-1>", self.on_start_release)
        self.btn_start.pack(pady=10, fill=tk.X)
        
        ttk.Label(ctrl_frame, text="Throttle (คันเร่ง):").pack(anchor=tk.W)
        self.scale_throttle = ttk.Scale(ctrl_frame, from_=0, to=100, variable=self.throttle_pct, orient=tk.HORIZONTAL)
        self.scale_throttle.pack(fill=tk.X)
        
        # --- Fault Injection ---
        fault_frame = ttk.LabelFrame(main_frame, text="Fault Injection (DTCs)", padding=10)
        fault_frame.pack(fill=tk.X, pady=5)
        
        ttk.Checkbutton(fault_frame, text="ECT Sensor Disconnected (เซนเซอร์อุณหภูมิหลุด)", variable=self.fault_ect, command=self.check_engine_stall).pack(anchor=tk.W)
        ttk.Checkbutton(fault_frame, text="TPS Sensor Missing (เซนเซอร์ปีกผีเสื้อหาย)", variable=self.fault_tps, command=self.check_engine_stall).pack(anchor=tk.W)
        ttk.Checkbutton(fault_frame, text="IAC Valve Fault (มอเตอร์เดินเบาพัง)", variable=self.fault_iac).pack(anchor=tk.W)
        ttk.Checkbutton(fault_frame, text="O2 Sensor Fault", variable=self.fault_o2).pack(anchor=tk.W)
        ttk.Checkbutton(fault_frame, text="Injector Wiring Fault (สายหัวฉีดขาด)", variable=self.fault_inj, command=self.check_engine_stall).pack(anchor=tk.W)

    def on_start_press(self, event):
        self.start_btn_pressed = True
        
    def on_start_release(self, event):
        self.start_btn_pressed = False
        self.try_start_engine()
        
    def try_start_engine(self):
        if self.stand_down.get():
            return
        if not self.brake_left.get():
            return
        
        # Check critical faults that prevent starting
        if self.fault_inj.get() or self.fault_ect.get():
            return
            
        self.engine_on.set(True)
        self.lbl_status.config(text="ENGINE RUNNING", foreground="green")
        
    def check_engine_stall(self):
        # Conditions that kill the engine
        if self.stand_down.get() or self.fault_inj.get() or self.fault_ect.get() or self.fault_tps.get():
            self.engine_on.set(False)
            self.lbl_status.config(text="ENGINE OFF", foreground="red")
            self.throttle_pct.set(0.0)

    def update_physics(self):
        # Physics Engine Update (called every 100ms)
        dt_sec = 0.1
        
        # Engine Temp (ECT)
        if self.engine_on.get():
            # Warm up to 95C
            self.engine_temp_c = min(95.0, self.engine_temp_c + (1.0 * dt_sec))
        else:
            # Cool down to 35C ambient
            self.engine_temp_c = max(35.0, self.engine_temp_c - (0.5 * dt_sec))

        # Engine State Machine
        if not self.engine_on.get():
            if self.start_btn_pressed and self.brake_left.get() and not self.stand_down.get():
                self.current_rpm = random.randint(400, 600)
                self.lbl_status.config(text="CRANKING...", foreground="orange")
            else:
                self.current_rpm = 0
                self.lbl_status.config(text="ENGINE OFF", foreground="red")
        else:
            base_rpm = 1500
            max_rpm = 10800  # Lead/Click 125 Rev Limit
            thr = self.throttle_pct.get() / 100.0
            
            target_rpm = base_rpm + (thr * (max_rpm - base_rpm))
            rpm = target_rpm + random.randint(-80, 80)
            
            if rpm > max_rpm:
                rpm = max_rpm - random.randint(100, 300) # Rev bounce
                
            self.current_rpm = int(rpm)
            self.lbl_status.config(text="ENGINE RUNNING", foreground="green")

        # Vehicle Speed (Clutch engages ~3000 RPM)
        if self.current_rpm > 3000 and self.engine_on.get():
            # CVT ratio approx: 90km/h at 9500 RPM
            target_speed = (self.current_rpm - 3000) * 0.0138
            self.vehicle_speed = min(120.0, target_speed)
        else:
            self.vehicle_speed = 0.0

        # Injector Duration (ms)
        if not self.engine_on.get():
            self.inj_ms = 0.0
        else:
            # Base idle ~2.5ms. Throttle adds load. Cold engine adds enrichment.
            base_inj = 2.5
            load_add = (self.throttle_pct.get() / 100.0) * 4.0 # up to +4ms under WOT
            cold_add = max(0, (80.0 - self.engine_temp_c) * 0.02) # up to +1ms cold
            self.inj_ms = base_inj + load_add + cold_add

        # Ignition Advance (deg)
        if not self.engine_on.get():
            self.ign_deg = -64.0
        else:
            # Idle ~12.5 deg, advances up to ~35 deg at high RPM
            if self.current_rpm < 2000:
                self.ign_deg = 12.5 + random.uniform(-0.5, 0.5)
            else:
                # Map 2000-9000 RPM to 15-35 deg
                rpm_clamped = min(9000, self.current_rpm)
                self.ign_deg = 15.0 + ((rpm_clamped - 2000) / 7000.0) * 20.0

        self.lbl_rpm.config(text=f"RPM: {self.current_rpm}")
        
        if self.running:
            self.after(100, self.update_physics)
        
    def get_table_17(self):
        # 19 bytes payload
        b = bytearray(19)
        # b4-b7 usually FF (IAT/MAP not supported on this ECU)
        b[4] = b[5] = b[6] = b[7] = 0xFF
        
        # RPM (b0, b1)
        rpm = self.current_rpm
        b[0] = (rpm >> 8) & 0xFF
        b[1] = rpm & 0xFF
        
        # TPS (b2, b3)
        if self.fault_tps.get():
            b[2] = 0
            b[3] = 0
        else:
            pct = self.throttle_pct.get()
            b[2] = int(28 + (pct * 2.22)) # raw 28-250
            b[3] = int(pct) # 0-100%
            
        # ECT (b8, b9)
        if self.fault_ect.get():
            b[8] = 0xFF
            b[9] = 0xFF
        else:
            ect_raw_c = int(self.engine_temp_c) + 40
            b[8] = max(0, 255 - ect_raw_c) # fake raw voltage inverse
            b[9] = ect_raw_c
            
        # Battery (b10) - scale 0.1
        if self.start_btn_pressed:
            b[10] = 115 # 11.5V under crank load
        else:
            b[10] = 142 if self.engine_on.get() else 125
        
        # Injector (b11, b12) - scale 0.005 ms
        if self.fault_inj.get() or not self.engine_on.get():
            b[11] = 0x01
            b[12] = 0xFF
        else:
            inj_raw = int(self.inj_ms / 0.005)
            b[11] = (inj_raw >> 8) & 0xFF
            b[12] = inj_raw & 0xFF
            
        # Ignition (b13) - scale 0.5, bias -64
        ign_raw = int((self.ign_deg + 64) * 2)
        b[13] = max(0, min(255, ign_raw))
        
        # IACV (b14)
        if self.fault_iac.get():
            b[14] = 0
        else:
            b[14] = random.randint(103, 109) if self.engine_on.get() else 128
            
        # Vehicle Speed (b15) - km/h
        b[15] = int(self.vehicle_speed)
        
        # b16-b18 = 0
        return b

    def get_table_d1(self):
        # 5 bytes
        b = bytearray(5)
        
        # Byte 0 flags: 0x02 = Stand DOWN (inverted?), 0x20 = Start Interlock (brake+start)
        # Wait, tables.py says: bit set = stand DOWN for mask 0x02 (invert=True means the GUI inverts it? No, if inverted in GUI, the bit 1 = stand down physically)
        if self.stand_down.get():
            b[0] |= 0x02
        if self.start_btn_pressed and self.brake_left.get():
            b[0] |= 0x20
            
        # Byte 4 flags: 0x01 = Engine running
        if self.engine_on.get():
            b[4] |= 0x01
            
        b[1] = 0x01
        b[2] = 0xBD
        b[3] = 0x0D
        return b
        
    def get_dtcs(self, packet_idx):
        codes = []
        if self.fault_ect.get(): codes.extend([7, 1]) # ECT code 7-1
        if self.fault_tps.get(): codes.extend([8, 1]) # TPS code 8-1
        if self.fault_iac.get(): codes.extend([29, 1]) # IAC code 29-1
        if self.fault_o2.get(): codes.extend([21, 1]) # O2 code 21-1
        if self.fault_inj.get(): codes.extend([12, 1]) # INJ code 12-1
        
        # Honda puts up to 3 codes per packet (6 bytes max)
        start_idx = (packet_idx - 1) * 6
        chunk = codes[start_idx : start_idx + 6]
        
        payload = bytearray([0x00]) # X byte (status) usually 0
        payload.extend(chunk)
        
        # Pad to 7 bytes
        while len(payload) < 7:
            payload.append(0x00)
            
        return payload

    def get_table_20(self):
        # 3 bytes: o2_v, stft, o2_heater
        b = bytearray(3)
        if self.engine_on.get() and not self.fault_o2.get():
            # simulate 0.1V - 0.9V sweep (scale 5/255) -> 5 to 45 raw
            b[0] = random.randint(10, 40)
            b[1] = 128 # STFT ~ 1.0
            b[2] = 20  # Heater active
        else:
            b[0] = 196 # 3.84V off
            b[1] = 128 
            b[2] = 0
        return b

    # --- Server Thread ---
    def start_server_thread(self):
        t = threading.Thread(target=self.server_loop, daemon=True)
        t.start()
        
    def server_loop(self):
        self.server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.server.bind(("127.0.0.1", PORT))
        self.server.listen(1)
        
        while self.running:
            try:
                self.server.settimeout(1.0)
                conn, addr = self.server.accept()
                conn.settimeout(0.5)
                
                while self.running:
                    try:
                        data = conn.recv(1024)
                        if not data: break
                        
                        # Init Table 0x00
                        if b'\x72\x05\x00' in data:
                            conn.sendall(b'\x02\x04\x00\xFA')
                            
                        # ECU ID / Part Number Request (Table 0x00 Read)
                        if b'\x71\x00' in data or b'\x21\x00' in data:
                            # 5-byte Sig for 30400-K2TA-T01: 01 04 78 0D 01, Rev: EE
                            payload = bytearray([0x01, 0x04, 0x78, 0x0D, 0x01, 0xEE, 0x00, 0x00, 0x00, 0x00])
                            frame = bytearray([0x02, 4 + len(payload), 0x71, 0x00]) + payload
                            frame.append(calc_honda_checksum(frame))
                            conn.sendall(frame)
                        
                        # Flashing: PGM-FI Handshake 1
                        if b'\x7D\x01\x02PGM' in data:
                            conn.sendall(b'\x02\x04\x7D\x80')  # Dummy ACK
                            
                        # Flashing: PGM-FI Handshake 2
                        if b'\x7D\x01\x03-FI' in data:
                            conn.sendall(b'\x02\x04\x7D\x80')  # Dummy ACK
                            
                        # Flashing: Security Access (Request Seed)
                        if (b'\x27\xE0' in data or b'\x27\x01' in data) and len(data) <= 6:
                            # Send Dummy Seed (Length depends on Old vs New ECU)
                            mode = data[data.find(b'\x27')+1]
                            seed = b'\xAA\xBB\xCC\xDD\xEE\xFF\x11' if mode == 0xE0 else b'\xAA\xBB'
                            frame = bytearray([0x02, 4 + len(seed), 0x67, mode]) + seed
                            frame.append(calc_honda_checksum(frame))
                            conn.sendall(frame)
                            
                        # Flashing: Security Access (Send Key) 
                        elif (b'\x27\xE0' in data or b'\x27\x02' in data) and len(data) > 6:
                            mode = data[data.find(b'\x27')+1]
                            
                            if self.var_force_lock.get():
                                # 7F 27 35 (Negative Response, Service 27, Error 35: Invalid Key)
                                frame = bytearray([0x02, 5, 0x7F, 0x27, 0x35])
                                frame.append(calc_honda_checksum(frame))
                                conn.sendall(frame)
                            else:
                                # Success (67 02)
                                frame = bytearray([0x02, 4, 0x67, mode])
                                frame.append(calc_honda_checksum(frame))
                                conn.sendall(frame)
                            
                        # Flashing: Erase Memory 0x31
                        elif b'\x31' in data:
                            frame = bytearray([0x02, 3, 0x71, 0x71]) # Dummy Erase ACK
                            conn.sendall(frame)
                            
                        # Flashing: Request Download 0x34
                        elif b'\x34' in data:
                            self.simulated_flash_buffer = bytearray()
                            frame = bytearray([0x02, 3, 0x74, 0x74]) # Dummy Req ACK
                            conn.sendall(frame)
                            
                        # Flashing: Transfer Data 0x36
                        elif b'\x36' in data:
                            idx = data.find(b'\x36')
                            payload = data[idx+1:-1] # Skip 0x36 and checksum
                            self.simulated_flash_buffer.extend(payload)
                            frame = bytearray([0x02, 3, 0x76, 0x76]) # Positive Response to 36
                            conn.sendall(frame)
                            
                        # Flashing: Transfer Exit 0x37
                        elif b'\x37' in data:
                            out_path = os.path.join(self.storage_dir, "flashed_rom.bin")
                            with open(out_path, "wb") as bf:
                                bf.write(self.simulated_flash_buffer)
                            frame = bytearray([0x02, 3, 0x77, 0x77]) # Positive Response to 37
                            conn.sendall(frame)
                            
                        # Flashing: ECU Reset 0x11
                        elif b'\x11' in data:
                            frame = bytearray([0x02, 3, 0x51, 0x51]) # Positive Response to 11
                            conn.sendall(frame)

                        # Read Table 17 (Telemetry)
                        if b'\x71\x17' in data:
                            pl = self.get_table_17()
                            frame = bytearray([0x02, 1 + 1 + 2 + len(pl) + 1, 0x71, 0x17]) + pl
                            frame.append(calc_honda_checksum(frame))
                            conn.sendall(frame)
                            
                        # Read Table D1 (Flags)
                        if b'\x71\xD1' in data or b'\x71\xd1' in data:
                            pl = self.get_table_d1()
                            frame = bytearray([0x02, 1 + 1 + 2 + len(pl) + 1, 0x71, 0xD1]) + pl
                            frame.append(calc_honda_checksum(frame))
                            conn.sendall(frame)
                            
                        # Read Table 20 (O2)
                        if b'\x71\x20' in data:
                            pl = self.get_table_20()
                            frame = bytearray([0x02, 1 + 1 + 2 + len(pl) + 1, 0x71, 0x20]) + pl
                            frame.append(calc_honda_checksum(frame))
                            conn.sendall(frame)
                            
                        # Read DTCs (0x73 = past, 0x74 = current)
                        for mode in (0x73, 0x74):
                            idx = data.find(bytes([0x72, 0x05, mode]))
                            if idx != -1 and idx + 3 < len(data):
                                pkt_idx = data[idx + 3]
                                pl = self.get_dtcs(pkt_idx)
                                frame = bytearray([0x02, 1 + 1 + 2 + len(pl) + 1, mode, pkt_idx]) + pl
                                frame.append(calc_honda_checksum(frame))
                                conn.sendall(frame)
                            
                    except socket.timeout:
                        continue
                    except Exception:
                        break
            except socket.timeout:
                continue
            except Exception:
                pass

    def on_close(self):
        self.running = False
        if self.server:
            self.server.close()
        self.destroy()

if __name__ == "__main__":
    app = ECU_Simulator()
    app.mainloop()
