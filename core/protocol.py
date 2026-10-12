"""
Honda K-Line Protocol Handler
Checksum calculation, frame building, frame extraction and table decoding.

Byte layouts live in core/tables.py; this module only knows about framing.
"""
import glob
from database.ecm_ids import lookup_ecm
from .tables import TABLE_17, TABLE_D1, TABLE_20

READ_TABLE = 0x71


def calc_honda_checksum(data):
    """Calculates Honda two's complement checksum: (0x100 - sum(data)) & 0xFF"""
    return (0x100 - (sum(data) & 0xFF)) & 0xFF


def format_honda_request(mode, table_id=None, extra_bytes=None):
    """
    Constructs a standard Honda K-Line request frame:
    [0x72, LEN, MODE, (TABLE_ID), (EXTRA...), CHECKSUM]
    """
    body = [0x72]
    payload = [mode]
    if table_id is not None:
        payload.append(table_id)
    if extra_bytes:
        payload.extend(extra_bytes)

    length = len(body) + 1 + len(payload) + 1
    frame = bytearray(body + [length] + payload)
    frame.append(calc_honda_checksum(frame))
    return bytes(frame)


def extract_payload(raw, mode, table_id=None):
    """
    Finds a checksum-valid response frame "02 LEN MODE [TABLE] ... CS" inside
    raw bytes (which may still contain the local K-Line echo) and returns the
    payload after the 4-byte header, without the checksum.

    If table_id is None the 4th byte is not checked (used for DTC frames).
    Returns a list of ints, or None if no valid frame is found.
    """
    if not raw:
        return None
    b = bytes(raw)
    for i in range(len(b) - 4):
        if b[i] != 0x02 or b[i + 2] != mode:
            continue
        if table_id is not None and b[i + 3] != table_id:
            continue
        length = b[i + 1]
        end = i + length
        if length < 5 or end > len(b):
            continue
        frame = b[i:end]
        if calc_honda_checksum(frame[:-1]) != frame[-1]:
            continue
        return list(frame[4:-1])
    return None


def decode_table(spec, raw):
    """Decodes a raw table response using a TableSpec. Returns dict or None."""
    payload = extract_payload(raw, READ_TABLE, spec.table_id)
    if payload is None or len(payload) < spec.min_len:
        return None
    return spec.decode(payload)


def parse_table_0(raw):
    """
    Parses Table 0x00 response to extract ECU Hardware Signature (5 bytes)
    and Calibration / Revision byte.
    Payload: [SIG0, SIG1, SIG2, SIG3, SIG4, REV, 00, 00, 00, 00]
    """
    payload = extract_payload(raw, READ_TABLE, 0x00)
    if payload is None or len(payload) < 6:
        return None

    ecm_sig = bytes(payload[:5])
    rev_byte = payload[5]
    meta = lookup_ecm(ecm_sig)

    info = {
        'sig_bytes': ecm_sig,
        'sig_hex': " ".join(f"{x:02X}" for x in ecm_sig),
        'rev': f"0x{rev_byte:02X}",
        'model': meta.get('model', 'Unknown Model'),
        'year': meta.get('year', '-'),
        'pn': meta.get('pn', 'Unknown PN'),
        'engine': meta.get('engine', 'PGM-FI'),
        'ecu_type': meta.get('ecu_type', 'Keihin/Shindengen'),
        'rom_match': meta.get('rom_match'),
        'xdf_match': meta.get('xdf_match'),
        'rom_status': '❌ ไม่พบไฟล์ ROM ที่ตรงในโฟลเดอร์'
    }

    if info['rom_match']:
        matches = glob.glob(f"**/{info['rom_match']}", recursive=True)
        if matches:
            info['rom_status'] = f"✅ ตรงรุ่น 100% ({info['rom_match']})"
        else:
            info['rom_status'] = f"⚠️ แนะนำ: {info['rom_match']} (ยังไม่มีไฟล์ในโฟลเดอร์)"
    return info


def parse_dtc_frame(raw, mode):
    """
    Parses one DTC response frame (mode 0x73 history / 0x74 current).
    Payload: [X, c1, m1, c2, m2, c3, m3] -> codes "c-m" at offsets 1, 3, 5.
    Returns a list of "NN-NN" strings, or None if the frame is invalid.
    """
    payload = extract_payload(raw, mode)
    if payload is None:
        return None
    codes = []
    for j in (1, 3, 5):
        if j + 1 < len(payload) and payload[j] != 0:
            codes.append(f"{payload[j]:02d}-{payload[j + 1]:02d}")
    return codes


# Backward-compatible wrappers
def parse_table_17(raw):
    return decode_table(TABLE_17, raw)


def parse_table_d1(raw):
    return decode_table(TABLE_D1, raw)


def parse_table_20(raw):
    return decode_table(TABLE_20, raw)
