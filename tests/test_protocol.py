"""
Unit tests for Honda K-Line protocol framing, checksums, and extraction.
"""
import unittest
from core.protocol import (
    calc_honda_checksum,
    format_honda_request,
    extract_payload,
    parse_table_0,
    parse_dtc_frame
)


class TestProtocol(unittest.TestCase):
    def test_checksum_calculation(self):
        # [0xFE, 0x04, 0x72] -> 0x8C
        # 0xFE + 0x04 + 0x72 = 0x174 -> (0x100 - 0x74) & 0xFF = 0x8C
        data = [0xFE, 0x04, 0x72]
        cs = calc_honda_checksum(data)
        self.assertEqual(cs, 0x8C)
        self.assertEqual((sum(data) + cs) & 0xFF, 0)

        # [0x72, 0x05, 0x71, 0x17] -> 0x01
        data2 = [0x72, 0x05, 0x71, 0x17]
        cs2 = calc_honda_checksum(data2)
        self.assertEqual(cs2, 0x01)
        self.assertEqual((sum(data2) + cs2) & 0xFF, 0)

    def test_format_honda_request(self):
        # Format Table 0x17 read request
        frame = format_honda_request(0x71, 0x17)
        self.assertEqual(frame, bytes([0x72, 0x05, 0x71, 0x17, 0x01]))

        # Format Security Access send key request with 2 bytes
        frame_key = format_honda_request(0x27, 0x02, extra_bytes=[0x12, 0x34])
        self.assertEqual(frame_key[0], 0x72)
        self.assertEqual(frame_key[1], 7)  # 72 + len + mode + sub + b1 + b2 + cs = 7
        self.assertEqual(frame_key[2], 0x27)
        self.assertEqual(frame_key[3], 0x02)
        self.assertEqual(frame_key[4], 0x12)
        self.assertEqual(frame_key[5], 0x34)
        self.assertEqual((sum(frame_key)) & 0xFF, 0)

    def test_extract_payload_direct(self):
        # Clean response frame: 02 07 71 17 05 DC [CS]
        # Payload is [0x05, 0xDC]
        body = [0x02, 0x07, 0x71, 0x17, 0x05, 0xDC]
        cs = calc_honda_checksum(body)
        raw = bytes(body + [cs])

        payload = extract_payload(raw, mode=0x71, table_id=0x17)
        self.assertEqual(payload, [0x05, 0xDC])

    def test_extract_payload_with_kline_echo(self):
        # Half-duplex K-Line loopback echo precedes response frame
        echo = bytes([0x72, 0x05, 0x71, 0x17, 0x01])
        resp_body = [0x02, 0x08, 0x71, 0x17, 0x05, 0xDC, 0x1D]
        cs = calc_honda_checksum(resp_body)
        raw = echo + bytes(resp_body + [cs])

        payload = extract_payload(raw, mode=0x71, table_id=0x17)
        self.assertEqual(payload, [0x05, 0xDC, 0x1D])

    def test_extract_payload_corrupted_checksum(self):
        body = [0x02, 0x07, 0x71, 0x17, 0x05, 0xDC]
        cs = (calc_honda_checksum(body) + 1) & 0xFF  # Corrupted!
        raw = bytes(body + [cs])

        payload = extract_payload(raw, mode=0x71, table_id=0x17)
        self.assertIsNone(payload)

    def test_extract_payload_truncated(self):
        raw = bytes([0x02, 0x0A, 0x71, 0x17, 0x01, 0x02])  # Declares len 10 but only 6 bytes
        payload = extract_payload(raw, mode=0x71, table_id=0x17)
        self.assertIsNone(payload)

    def test_parse_table_0_signature(self):
        # Lead 125 4V ECM signature: 01 04 78 0D 01, revision: 0x02
        payload = [0x01, 0x04, 0x78, 0x0D, 0x01, 0x02, 0x00, 0x00, 0x00, 0x00]
        frame = [0x02, len(payload) + 5, 0x71, 0x00] + payload
        frame.append(calc_honda_checksum(frame))

        info = parse_table_0(bytes(frame))
        self.assertIsNotNone(info)
        self.assertEqual(info['model'], 'Lead 125 4V')
        self.assertEqual(info['pn'], '30400-K2TA-T01')
        self.assertEqual(info['rev'], '0x02')
        self.assertEqual(info['sig_hex'], '01 04 78 0D 01')

    def test_parse_dtc_frame(self):
        # Mode 0x74 (current DTCs), packet 1
        # Frame format: 02 LEN MODE PKT_IDX [status, c1_maj, c1_min, c2_maj, c2_min, ...] CS
        payload = [0x00, 7, 2, 12, 1, 0, 0]
        frame = [0x02, len(payload) + 5, 0x74, 0x01] + payload
        frame.append(calc_honda_checksum(frame))

        codes = parse_dtc_frame(bytes(frame), mode=0x74)
        self.assertEqual(codes, ['07-02', '12-01'])


if __name__ == '__main__':
    unittest.main()
