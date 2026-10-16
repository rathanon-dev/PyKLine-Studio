"""
Unit tests for Honda K-Line tables specification and decoding.
"""
import unittest
from core.tables import TABLE_17, TABLE_D1, TABLE_20, Field, Flag


class TestTables(unittest.TestCase):
    def test_field_decoding(self):
        f_rpm = Field("rpm", "Engine Speed", "rpm", 0, size=2)
        payload = [0x05, 0xDC]  # 1500
        self.assertEqual(f_rpm.decode(payload), 1500)

        # Unsupported slot (all 0xFF)
        payload_unsupported = [0xFF, 0xFF]
        self.assertIsNone(f_rpm.decode(payload_unsupported))

        # Scaled field with bias (ECT = raw - 40)
        f_ect = Field("ect", "ECT", "°C", 0, bias=-40)
        self.assertEqual(f_ect.decode([125]), 85)

        # Float decimals
        f_bat = Field("battery", "Battery", "V", 0, scale=0.1, decimals=1)
        self.assertEqual(f_bat.decode([142]), 14.2)

    def test_flag_decoding(self):
        # Side stand: bit 0x02 set = DOWN, invert=True -> side_stand_up = False
        fl_stand = Flag("side_stand_up", "Side stand", 0, 0x02, invert=True)
        self.assertFalse(fl_stand.decode([0x02]))
        self.assertTrue(fl_stand.decode([0x00]))

        # Alternative offset/mask test (cranking enrichment fallback)
        fl_crank = Flag("start_interlock", "Start", 0, 0x20, alt_offset=4, alt_mask=0x40)
        self.assertTrue(fl_crank.decode([0x20, 0x00, 0x00, 0x00, 0x00]))
        self.assertTrue(fl_crank.decode([0x00, 0x00, 0x00, 0x00, 0x40]))
        self.assertFalse(fl_crank.decode([0x00, 0x00, 0x00, 0x00, 0x00]))

    def test_table_17_full_decode(self):
        # 19-byte telemetry frame from real Honda Click / Lead 125 capture
        # b0-1: RPM 1500 (0x05DC)
        # b2:   TPS raw 29 (0.57 V)
        # b3:   TPS angle/pct (raw 16 -> 10.0%)
        # b4-7: Unsupported FF FF FF FF
        # b8:   ECT raw (31 -> 0.61 V)
        # b9:   ECT (125 -> 85 °C)
        # b10:  Battery (142 -> 14.2 V)
        # b11-12: Injector (0x0220 = 544 -> 544 * 0.005 = 2.72 ms)
        # b13:  Ignition (152 -> 152 * 0.5 - 64 = 12.0 deg)
        # b14:  IACV (105)
        # b15:  Speed (0)
        # b16-18: 00 00 00
        payload = [
            0x05, 0xDC,  # 0-1 RPM: 1500
            29,          # 2 TPS raw
            16,          # 3 TPS pct
            0xFF, 0xFF, 0xFF, 0xFF, # 4-7 unsupported slots
            31,          # 8 ECT raw V
            125,         # 9 ECT C (85 C)
            142,         # 10 Battery (14.2 V)
            0x02, 0x20,  # 11-12 Inj duration
            152,         # 13 Ignition advance
            105,         # 14 IACV
            0,           # 15 Speed
            0, 0, 0      # 16-18
        ]
        data = TABLE_17.decode(payload)
        self.assertEqual(data['rpm'], 1500)
        self.assertEqual(data['ect'], 85)
        self.assertEqual(data['battery'], 14.2)
        self.assertEqual(data['inj_ms'], 2.72)
        self.assertEqual(data['ign_deg'], 12.0)
        self.assertEqual(data['iacv'], 105)
        self.assertEqual(data['tps_pct'], 10.0)
        self.assertEqual(data['tps_deg'], 8.0)
        self.assertIsNone(data['iat'])
        self.assertIsNone(data['map_mbar'])

    def test_table_d1_decode(self):
        # 5-byte payload:
        # b0: 0x00 (stand UP because bit 0x02 is 0)
        # b4: 0x01 (engine running)
        payload = [0x00, 0x00, 0x00, 0x00, 0x01]
        data = TABLE_D1.decode(payload)
        self.assertTrue(data['side_stand_up'])
        self.assertTrue(data['engine_running'])
        self.assertFalse(data['start_interlock'])

    def test_table_20_decode(self):
        # b0: O2 raw (196 -> 196 * 5 / 255 = 3.84 V)
        # b1: STFT raw (128 -> 128 * 2 / 255 = 1.004)
        # b2: O2 heater raw (0)
        payload = [196, 128, 0]
        data = TABLE_20.decode(payload)
        self.assertEqual(data['o2_v'], 3.84)
        self.assertEqual(data['stft'], 1.004)
        self.assertEqual(data['o2_heater'], 0.0)


if __name__ == '__main__':
    unittest.main()
