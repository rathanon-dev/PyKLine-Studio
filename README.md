# ⚡ PyKLine-Studio (Universal K-Line ECU Telemetry & Diagnostic Suite)

[![TH](https://img.shields.io/badge/Language-ภาษาไทย-green.svg)](#-ภาพรวมโครงการ-thai-version)
[![EN](https://img.shields.io/badge/Language-English-red.svg)#-english-version)
[![Python](https://img.shields.io/badge/Python-3.10%2B-blue.svg)](https://www.python.org/)
[![Protocol](https://img.shields.io/badge/Protocol-K--Line-orange.svg)]()
[![Hardware](https://img.shields.io/badge/Hardware-FTDI%20FT232RL%20%2F%20CH340-green.svg)]()
[![License](https://img.shields.io/badge/License-MIT-lightgrey.svg)]()

> **ชุดเครื่องมือซอฟต์แวร์โอเพนซอร์สสำหรับการอ่านค่าเซนเซอร์สด วิเคราะห์ข้อมูล และตรวจสอบสถานะกล่อง ECU ผ่านสายสัญญาณ K-Line**

---

## 🇹🇭 ภาพรวมโครงการ (Thai Version)

**PyKLine-Studio** คือชุดซอฟต์แวร์ภาษา Python แบบ Modular ออกแบบมาสำหรับการเชื่อมต่อ ตรวจสอบค่าเซนเซอร์สด (**Live Telemetry**) และวิเคราะห์ข้อผิดพลาดของกล่องควบคุมอิเล็กทรอนิกส์ (**ECU**) ของยานยนต์ขนาดเล็กผ่านสายเดี่ยว **K-Line** ที่อัตราความเร็ว **10,400 Baud**

---

### 🌟 ฟีเจอร์หลัก (Key Features)

- **⚡ ตรวจจับพอร์ตอัตโนมัติ (Zero-Config Auto Detection):** สแกนและเชื่อมต่อกับตัวแปลงสัญญาณ USB-to-UART / FTDI (`FT232RL`, `CH340`, `CP210x`) โดยอัตโนมัติ
- **🏎️ หน้าปัดแสดงผลกราฟิก (Visual Cluster Dashboard):**
  - **มาตรวัดรอบ 260° (Auto-scaling Tachometer):** ระบบปรับย่านวัดรอบตามพฤติกรรมการบิดคันเร่งอัตโนมัติ (0–3,000 / 0–6,000 / 0–10,000 / 0–12,000 / 0–15,000 RPM) พร้อมเข็ม Peak Hold ค้างค่ารอบสูงสุด 2 วินาที
  - **มาตรวัดความเร็ว (Speedometer):** แสดงผลความเร็ว 0–160 km/h แบบเกจ์เข็มกวาดตอบสนองไว
  - **แถบวัดระดับคันเร่ง (TPS Dynamic Gauge):** แสดงเปอร์เซ็นต์และระดับแรงดันการเปิดลิ้นเร่งแบบเรียลไทม์
  - **กราฟคลื่นสัญญาณสด (Dual-channel Waveform Strip-chart):** กราฟคลื่นเปรียบเทียบ RPM (เขียว) และ TPS (ฟ้า) ย้อนหลัง 10 วินาทีแบบสด
  - **การ์ดสถานะเครื่องยนต์ (Vital Engine Cards):** แสดงค่าอุณหภูมิเครื่องยนต์ (ECT), แรงดันไอดี (MAP), ระยะเวลาฉีด (INJ), องศาไฟจุดระเบิด (IGN), แรงดัน O2 และแรงดันแบตเตอรี่
  - **ไฟสถานะสวิตช์ฮาร์ดแวร์ (Interlock Status Badges):** แสดงสถานะขาตั้งข้าง (Side Stand) และสถานะเครื่องยนต์ทำงาน (Engine Running)
  - **บันทึกภาพหน้าปัด (Export Snapshot):** ปุ่มบันทึกภาพหน้าปัด Dashboard เป็นไฟล์ภาพ PNG ได้ทันที
- **📊 ตารางข้อมูลเซนเซอร์ละเอียด (Raw Sensor Table):** แสดงค่าตัวเลขดิบและหน่วยวัดของเซนเซอร์ทุกตัวอย่างครบถ้วน (`Table 0x17`, `Table 0xD1`)
- **🔍 อ่านรหัสระบุกล่อง (`Table 0x00`):** ดึงค่าลายเซ็นฮาร์ดแวร์ ECM 5 ไบต์ และเวอร์ชันการปรับจูน (Calibration Revision) เพื่อจำแนกกลุ่มฮาร์ดแวร์
- **🩺 ตรวจสอบและลบโค้ดข้อผิดพลาด (DTC Scanner & Clear):** สแกนโค้ดปัญหาปัจจุบันและประวัติย้อนหลัง พร้อมคำอธิบาย 2 ภาษา (ไทย/อังกฤษ) และปุ่มสั่งลบโค้ดไฟเครื่อง (`Table 0x60`)
- **🎮 ระบบจำลองสัญญาณในตัว (Built-in Dyno Simulator):** รองรับการทดสอบหน้าต่าง GUI และแอนิเมชันเกจ์วัดได้เต็มรูปแบบแม้ไม่มีกล่องจริงต่ออยู่

---

### 🔌 การเชื่อมต่อวงจรฮาร์ดแวร์ (Hardware Setup)

การสื่อสารระหว่างคอมพิวเตอร์และกล่อง ECU ใช้สายสัญญาณแบบ Half-duplex Bidirectional K-Line ผ่านวงจรทรานซีฟเวอร์มาตรฐาน **CTX K-Line Interface**:

![CTX K-Line Interface](https://gonzos.net/projects/wp-content/uploads/2017/04/CTX-kline-interface.png)

*แหล่งอ้างอิงวงจร: [CTX-OBD Project (gonzos.net)](https://gonzos.net/projects/ctx-obd/)*

---

### 🏛️ โครงสร้างโปรเจกต์ (Project Structure)

```text
PyKLine-Studio/
├── README.md               # เอกสารคู่มือระบบ 2 ภาษา (TH / EN)
├── requirements.txt        # แพ็กเกจที่ต้องการ (pyserial, pyftdi)
├── .gitignore              # การยกเว้นไฟล์ชั่วคราวและแคชระบบ
├── main.py                 # จุดเริ่มต้นโปรแกรมหลัก
├── start_main.bat          # สคริปต์คลิกรันบน Windows
├── start_simulator.bat     # สคริปต์รันโหมดจำลองกล่อง ECU
├── core/                   # ตรรกะโปรโตคอล K-Line, คำสั่งวินิจฉัย และการเชื่อมต่อ
├── database/               # ฐานข้อมูล Hardware ID และรหัสไฟกะพริบ DTC (TH/EN)
├── gui/                    # หน้าจอ Visual Cluster และ Raw Sensor Dashboard
└── tools/                  # เครื่องมือจำลองสัญญาณ ECU Dyno Simulator
```

---

### 🧠 แผนงานพัฒนา (Roadmap)

- [ ] ระบบบันทึกและส่งออกข้อมูล Telemetry เป็นไฟล์ CSV / Datalog
- [ ] เพิ่มหน้าต่างวิเคราะห์ความสัมพันธ์ของเซนเซอร์ (Scatter Plot & Histogram)
- [ ] รองรับการเชื่อมต่อและดึงค่า Custom Diagnostic Tables เพิ่มเติม

---

### 📚 แหล่งอ้างอิงทางเทคนิค (Technical References)

โครงสร้างและการพัฒนาของ `PyKLine-Studio` อ้างอิงจากงานวิจัยและโครงการโอเพนซอร์ส 4 เสาหลัก:
1. **วงจรแปลงสัญญาณฮาร์ดแวร์ (Hardware Interface):**  
   [gonzos.net / CTX-OBD](https://gonzos.net/projects/ctx-obd/) — ผังวงจรทรานซีฟเวอร์ [CTX-kline-interface.png](https://gonzos.net/projects/wp-content/uploads/2017/04/CTX-kline-interface.png)
2. **โครงสร้างโปรโตคอลและตารางวินิจฉัย (Protocol & Diagnostic Tables):**  
   [andreibaw/Honda_K-Line_KWP2000](https://github.com/andreibaw/Honda_K-Line_KWP2000) — สเปกแพ็กเก็ต Header 0x72, Checksum Two's Complement และตาราง 0x00, 0x17, 0xD1
3. **อัลกอริทึมความปลอดภัยและคำสั่งวินิจฉัย (Automotive Embedded Tools):**  
   [Rajkaran75 / Automotive_Embedded_Engineering_Tools](https://github.com/Rajkaran75/Automotive_Embedded_Engineering_Tools) — แนวทางการสร้างเครื่องมือสำหรับวิศวกรรมยานยนต์
4. **สถาปัตยกรรมเครื่องมือวินิจฉัยและจัดการกล่อง ECU (Diagnostic Architecture):**  
   [bouletmarc/HondaReflashTool](https://github.com/bouletmarc/HondaReflashTool) — ลำดับคำสั่งการสื่อสารและการจัดการหน่วยความจำ ECU ผ่าน K-Line

---

### 🚀 วิธีเริ่มต้นใช้งาน (Quick Start)

#### 1. ติดตั้งไลบรารีที่จำเป็น
```bash
pip install -r requirements.txt
```

#### 2. เปิดใช้งานโปรแกรมหลัก
ดับเบิลคลิกไฟล์ `start_main.bat` หรือสั่งผ่านคำสั่ง:
```bash
python main.py
```

#### 3. เปิดใช้งานโหมดจำลองกล่อง (Offline Test)
ดับเบิลคลิกไฟล์ `start_simulator.bat` หรือสั่ง:
```bash
python tools/ecu_gui_simulator.py
```

---

### 📜 ตารางคำสั่งวินิจฉัย (Diagnostic Table Summary)

| Table ID | Hex | ชื่อตาราง | คำสั่ง Request | ขนาดตอบกลับ | การใช้งานหลัก |
| :---: | :---: | :--- | :--- | :---: | :--- |
| **0** | `0x00` | ECU Model ID | `72 05 71 00 18` | 15 bytes | ระบุรหัสฮาร์ดแวร์และพาร์ทกล่อง |
| **17** | `0x11` | Live Telemetry | `72 05 71 17 01` | 24 bytes | ค่าเซนเซอร์สด (RPM, TPS, MAP, ECT, Battery) |
| **115** | `0x73` | History DTCs | `72 05 73 01 15` | 12 bytes | ประวัติโค้ดข้อผิดพลาดย้อนหลัง |
| **116** | `0x74` | Active DTCs | `72 05 74 01 14` | 12 bytes | โค้ดข้อผิดพลาดปัจจุบันที่กำลังเกิดขึ้น |
| **209** | `0xD1` | Hardware Switches | `72 05 71 D1 47` | 8 bytes | สถานะขาตั้งข้างและสวิตช์เครื่องยนต์ |
| **96** | `0x60` | Clear DTCs | `72 05 60 03 2B` | 5 bytes | คำสั่งลบโค้ดข้อผิดพลาดไฟเครื่อง |

> 💡 **สูตรคำนวณ Checksum (Two's Complement):**
>
> $$
> \text{Checksum} = (0\text{x}100 - (\sum \text{Frame}[0..n] \ \& \ 0\text{xFF})) \ \& \ 0\text{xFF}
> $$
>
> ```python
> checksum = (0x100 - (sum(frame) & 0xFF)) & 0xFF
> ```

---

<br>

<details id="-english-version">
<summary><b>🌐 Click to expand English Version (คลิกเพื่อดูเวอร์ชันภาษาอังกฤษ)</b></summary>

<br>

# ⚡ PyKLine-Studio (Universal K-Line ECU Telemetry & Diagnostic Suite)

**PyKLine-Studio** is an open, modular Python-based diagnostic and live telemetry suite for motorcycle and small engine ECUs communicating via the single-wire **K-Line** protocol at **10,400 baud**.

---

### 🌟 Key Features

- **⚡ Zero-Configuration Auto-Detection:** Automatically scans and binds to USB-to-UART / FTDI adapters (`FT232RL`, `CH340`, `CP210x`).
- **🏎️ Visual Cluster Dashboard:**
  - **Auto-Scaling Tachometer (260° Sweep):** Dynamic scale expansion matching throttle demand (0–3,000 / 0–6,000 / 0–10,000 / 0–12,000 / 0–15,000 RPM) with 2-second peak-hold decay marker.
  - **Speedometer:** Responsive 0–160 km/h visual dial gauge.
  - **Dynamic TPS Gauge:** Live throttle opening percentage and voltage bar.
  - **Dual-Channel Live Waveform:** Real-time 10-second rolling strip-chart comparing RPM (green) against TPS (cyan).
  - **Vital Engine Cards:** Quick-glance readouts for ECT (Engine Coolant/Oil Temp), MAP (Manifold Pressure), INJ (Injection Duration), IGN (Advance Angle), O2, and Battery Voltage.
  - **Hardware Interlock Badges:** Side Stand status and Engine Run flags.
  - **Snapshot Export:** One-click dashboard image capture to high-resolution PNG.
- **📊 Raw Sensor Table:** Comprehensive numerical display of all sensor parameters and diagnostic tables (`Table 0x17`, `Table 0xD1`).
- **🔍 Auto ECU Identification (`Table 0x00`):** Reads the 5-byte ECM Hardware Signature and revision byte to accurately identify hardware families.
- **🩺 Diagnostic Trouble Codes (DTC Scanner & Clear):** Read active and historical trouble codes with bilingual (EN/TH) descriptions, plus one-click DTC clearing (`Table 0x60`).
- **🎮 Built-in Dyno Simulator:** Allows full GUI, gauge, and protocol testing without a physical ECU connection.

---

### 🔌 Hardware Setup (K-Line Transceiver Interface)

Hardware communication uses a standard bidirectional K-Line transceiver circuit interfacing an FTDI USB-to-UART adapter with the ECU diagnostic port.

The circuit design is based on the **CTX K-Line Interface**:

![CTX K-Line Interface](https://gonzos.net/projects/wp-content/uploads/2017/04/CTX-kline-interface.png)

*Reference: [CTX-OBD Project](https://gonzos.net/projects/ctx-obd/)*

---

### 🏛️ Project Structure

```text
PyKLine-Studio/
├── README.md               # Bilingual Documentation & References (TH / EN)
├── requirements.txt        # Lightweight dependencies (pyserial, pyftdi)
├── .gitignore              # Cache and temporary file exclusions
├── main.py                 # Double-clickable entry point
├── start_main.bat          # Windows one-click launcher
├── start_simulator.bat     # Windows simulator launcher
├── core/                   # Protocol parsers, diagnostic commands, and connection engine
├── database/               # Model signatures (ecm_ids) & DTC trouble codes (TH/EN)
├── gui/                    # Visual Cluster & Raw Sensor dashboard components
└── tools/                  # ECU hardware simulator & signal sweepers
```

---

### 🧠 Roadmap

- [ ] Telemetry data logging and export to CSV / Datalog formats
- [ ] Correlation analysis scatter plots & histograms
- [ ] Support for extended custom diagnostic tables

---

### 📚 Technical References & Acknowledgements

The architecture of `PyKLine-Studio` is built upon the foundational work and research of the following open-source projects and publications:

1. **Hardware Transceiver Circuit:**
   - [CTX-OBD: K-Line Interface](https://gonzos.net/projects/ctx-obd/)
   - Schematic: [CTX-kline-interface.png](https://gonzos.net/projects/wp-content/uploads/2017/04/CTX-kline-interface.png)

2. **K-Line Protocol & Diagnostic Tables:**
   - [andreibaw/Honda_K-Line_KWP2000](https://github.com/andreibaw/Honda_K-Line_KWP2000)
   - Frame headers (0x72), Two's Complement Checksum formula, and Diagnostic Table specifications.

3. **Diagnostic Algorithms & Automotive Tools:**
   - [Rajkaran75 / Automotive_Embedded_Engineering_Tools](https://github.com/Rajkaran75/Automotive_Embedded_Engineering_Tools)
   - Methodologies and structures for automotive diagnostic and embedded tools.

4. **ECU Diagnostic & Architecture Reference:**
   - [bouletmarc/HondaReflashTool](https://github.com/bouletmarc/HondaReflashTool)
   - Communication sequences and ECU memory inspection architecture via K-Line.

---

### 🚀 Quick Start

#### 1. Installation
```bash
pip install -r requirements.txt
```

#### 2. Launching Application
Double-click `start_main.bat` or run:
```bash
python main.py
```

#### 3. Launching Simulator (Offline Mode)
Double-click `start_simulator.bat` or run:
```bash
python tools/ecu_gui_simulator.py
```

---

### ⚖️ Disclaimer & License

This project is developed strictly for diagnostic, educational, and research purposes. Distributed under the MIT License.

</details>

---

## ⚖️ ข้อจำกัดความรับผิดชอบและสัญญาอนุญาต (Disclaimer & License)

โครงการนี้พัฒนาขึ้นเพื่อการวินิจฉัย การศึกษา และการวิจัยทางวิศวกรรมระบบเท่านั้น ซอฟต์แวร์นี้เผยแพร่ภายใต้สัญญาอนุญาต **MIT License**
