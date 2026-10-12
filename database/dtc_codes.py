"""
Diagnostic Trouble Codes (DTC) Database with English and Thai descriptions.
"""

DTC_DATABASE = {
    '01-01': 'MAP sensor circuit low voltage (แรงดัน MAP ต่ำ / ลัดวงจรกราวด์)',
    '01-02': 'MAP sensor circuit high voltage (แรงดัน MAP สูง / ถอดปลั๊กหรือวงจรเปิด)',
    '02-01': 'MAP sensor performance problem (เซนเซอร์ MAP ทำงานผิดปกติ)',
    '07-01': 'ECT sensor circuit low voltage (แรงดัน ECT ต่ำ / ลัดวงจรกราวด์)',
    '07-02': 'ECT sensor circuit high voltage (แรงดัน ECT สูง / ถอดปลั๊กหรือวงจรเปิด)',
    '08-01': 'TP sensor circuit low voltage (แรงดัน TPS ต่ำ / ลัดวงจรกราวด์)',
    '08-02': 'TP sensor circuit high voltage (แรงดัน TPS สูง / ถอดปลั๊กหรือวงจรเปิด)',
    '09-01': 'IAT sensor circuit low voltage (แรงดัน IAT ต่ำ / ลัดวงจรกราวด์)',
    '09-02': 'IAT sensor circuit high voltage (แรงดัน IAT สูง / ถอดปลั๊กหรือวงจรเปิด)',
    '11-01': 'VS sensor no signal (เซนเซอร์ความเร็วล้อไม่มีสัญญาณ)',
    '12-01': 'No.1 primary injector circuit malfunction (หัวฉีดหลักทำงานผิดพลาด)',
    '13-01': 'No.2 primary injector circuit malfunction',
    '18-01': 'CMP sensor no signal (เซนเซอร์ตำแหน่งเพลาลูกเบี้ยว)',
    '19-01': 'CKP sensor no signal (เซนเซอร์เพลาข้อเหวี่ยง)',
    '21-01': 'O2 sensor low voltage (เซนเซอร์ O2 แรงดันต่ำ / ลัดวงจรกราวด์)',
    '21-02': 'O2 sensor high voltage (เซนเซอร์ O2 แรงดันสูง / ส่วนผสมบางมาก)',
    '23-01': 'O2 sensor heater malfunction (ตัวทำความร้อน O2 เสียหาย)',
    '29-01': 'IACV circuit malfunction (มอเตอร์เดินเบา IACV ผิดปกติ)',
    '33-02': 'ECM EEPROM malfunction (หน่วยความจำ EEPROM ของกล่องเสียหาย)',
    '54-01': 'Bank angle sensor circuit low voltage (เซนเซอร์องศาเอียงรถแรงดันต่ำ)',
    '54-02': 'Bank angle sensor circuit high voltage (เซนเซอร์องศาเอียงรถแรงดันสูง / ถอดปลั๊ก)',
    '86-01': 'Serial communication malfunction (การสื่อสารอนุกรมผิดปกติ)',
    '91-01': 'Ignition coil primary circuit malfunction (คอยล์จุดระเบิดผิดปกติ)'
}

def get_dtc_description(code_str):
    return DTC_DATABASE.get(code_str, "รหัสความผิดปกติที่ไม่ได้ระบุในเอกสาร (Undocumented DTC)")
