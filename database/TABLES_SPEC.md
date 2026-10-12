# 📋 Universal K-Line ECU Diagnostic Tables Specification
**โครงการ:** PyKLine-Studio  
**โปรโตคอล:** K-Line (10,400 Baud, 8N1, Fast Init 70ms)  

---

## 1. โครงสร้างแพ็กเก็ต (Frame Structure)

### คำสั่งส่งจากคอมพิวเตอร์ (Master Request):
```text
[Header: 0x72] [Length] [Mode] [Table_ID / Sub-function] [Extra...] [Checksum]
```
- **Checksum Formula (Two's Complement):**  
  `Checksum = (0x100 - (Sum(Frame[0..n]) & 0xFF)) & 0xFF`

### แพ็กเก็ตตอบกลับจากกล่อง ECU (Slave Response):
```text
[Echo: 0x02] [Length] [Echo_Mode: 0x71] [Table_ID] [Payload Bytes...] [Checksum]
```

---

## 2. รายละเอียดตาราง Diagnostic Tables

| Table ID | Hex | ชื่อตาราง | คำสั่ง Request | ขนาดตอบกลับ | การใช้งานหลัก |
| :---: | :---: | :--- | :--- | :---: | :--- |
| **0** | `0x00` | **ECU Hardware ID** | `72 05 71 00 18` | 15 bytes | **ตรวจจับกลุ่มฮาร์ดแวร์ & Part No. อัตโนมัติ** |
| **17** | `0x11` | **Live Telemetry** | `72 05 71 17 01` | 24 bytes | **Datalogging เซนเซอร์สด (RPM, TPS, MAP, ECT, ฯลฯ)** |
| **32** | `0x20` | O2 Sensor Bank 1 | `72 05 71 20 F8` | 3 bytes | เซนเซอร์ไอเสีย O2 & ฮีตเตอร์ |
| **112** | `0x70` | Freeze Frame Memory | `72 05 71 70 A8` | 34 bytes | ข้อมูลกล่องขณะเกิดข้อผิดพลาด |
| **115** | `0x73` | History DTCs | `72 05 73 01 15` | 12 bytes | ประวัติโค้ดเสียย้อนหลัง |
| **116** | `0x74` | Active DTCs | `72 05 74 01 14` | 12 bytes | โค้ดเสียปัจจุบันที่กำลังเกิดขึ้น |
| **208** | `0xD0` | Actuators Status | `72 05 71 D0 48` | 34 bytes | สถานะชุดควบคุมภายใน / วาล์ว |
| **209** | `0xD1` | Hardware Switches | `72 05 71 D1 47` | 8 bytes | สวิตช์ขาตั้งข้าง, สถานะเครื่องยนต์ |
| **96** | `0x60` | Clear DTCs | `72 05 60 03 2B` | 5 bytes | ลบโค้ดข้อผิดพลาด (ลบไฟเครื่อง) |

---

## 3. การถอดรหัส Table 0x00 (ECU Model Auto-Detection)

ตัวอย่างผลลัพธ์จากกล่องตัวอย่างจริง:
```text
02 0F 71 00 [01 04 78 0D 01] [EE] 00 00 00 00 05
```
- **Byte 0-1:** `02 0F` (Echo header, ความยาว 15 ไบต์)
- **Byte 2-3:** `71 00` (Echo Mode 0x71, Table 0x00)
- **Byte 4-8 (5 ไบต์):** `01 04 78 0D 01` = **ECM Hardware Signature**
- **Byte 9 (1 ไบต์):** `EE` = **Calibration & Firmware Revision**
- **การเทียบเคียง:**
  - `01 04 78 0D 01` $\rightarrow$ **Lead 125 4V**, รหัสพาร์ท **30400-K2TA-T01**

---

## 4. การถอดรหัส Table 0x17 (Live Engine Telemetry)

| ไบต์ | พารามิเตอร์ | ตัวอย่าง Raw | สูตรคำนวณ | ค่าจริง |
| :---: | :--- | :---: | :--- | :--- |
| **0-1** | รอบเครื่อง (Engine RPM) | `00 00` | `(Byte0 << 8) \| Byte1` | `0 RPM` |
| **2** | ลิ้นเร่ง (TPS Position) | `15` (21) | `max(0, (Raw - 21) / 1.7)` | `0.0 %` (ปิดสนิท) |
| **2** | แรงดันลิ้นเร่ง (TPS Voltage) | `15` (21) | `(Raw / 255.0) * 5.0` | `0.41 V` |
| **8** | แรงดันไอดี (MAP Sensor) | `5D` (93) | `Raw * 7.5` | `697 mBar` |
| **9** | แรงดันแบตเตอรี่ (Battery) | `58` (88) | `Raw / 10.0` | `8.8 V` |
| **10** | ความร้อนเครื่อง (ECT Temp) | `86` (134) | Keihin Resistance LUT | `40 °C` |
| **11-12**| ยกหัวฉีด (Injector Duration)| `00 00` | `((Byte11 << 8) \| Byte12) * 0.005` | `0.00 ms` |
| **13** | องศาไฟจุดระเบิด (Ignition) | `80` (128) | `(Raw * 0.5) - 64.0` | `0.0 °` |
| **14** | มอเตอร์เดินเบา (IACV Steps) | `80` (128) | `Raw` | `128 steps` |
| **15** | ความเร็วรถ (Vehicle Speed) | `00` | `Raw` | `0 Km/h` |

---

## 5. การถอดรหัส Table 0xD1 (Hardware Switch Flags)

- **Byte 0, Bit 1:** สวิตช์ขาตั้งข้าง (Side Stand)
  - `1` = ขาตั้งยกขึ้น (UP - ปกติ)
  - `0` = เอาขาตั้งลง (DOWN - ตัดระบบ)
- **Byte 4, Bit 0:** สถานะเครื่องยนต์ (Engine Run)
  - `1` = เครื่องยนต์กำลังทำงาน (RUNNING)
  - `0` = เครื่องยนต์ดับอยู่ (STOPPED)
