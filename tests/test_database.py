"""
Unit tests for DTC codes and ECM ID database lookups.
"""
import unittest
from database.dtc_codes import get_dtc_description
from database.ecm_ids import lookup_ecm


class TestDatabase(unittest.TestCase):
    def test_dtc_lookup(self):
        desc = get_dtc_description('07-02')
        self.assertIn('ECT sensor', desc)
        self.assertIn('circuit high voltage', desc)

        desc_inj = get_dtc_description('12-01')
        self.assertIn('injector', desc_inj.lower())

        desc_unknown = get_dtc_description('99-99')
        self.assertIn('ไม่ได้ระบุในเอกสาร', desc_unknown)

    def test_ecm_lookup_known(self):
        # Lead 125 4V
        res = lookup_ecm(bytes([0x01, 0x04, 0x78, 0x0D, 0x01]))
        self.assertIsNotNone(res)
        self.assertEqual(res['model'], 'Lead 125 4V')
        self.assertEqual(res['pn'], '30400-K2TA-T01')

        # Click 125i (2014)
        res_click = lookup_ecm(bytes([0x01, 0x01, 0xBD, 0x0D, 0x01]))
        self.assertIsNotNone(res_click)
        self.assertEqual(res_click['model'], 'Click 125i')
        self.assertEqual(res_click['pn'], '30400-KZR-601')

    def test_ecm_lookup_variant(self):
        # Partial match on first 3 bytes of MSX 125 SF: 01 02 57
        res_var = lookup_ecm(bytes([0x01, 0x02, 0x57, 0x99, 0x99]))
        self.assertIsNotNone(res_var)
        self.assertIn('Variant', res_var['model'])

    def test_ecm_lookup_unknown(self):
        # Unknown signature
        res_gen = lookup_ecm(bytes([0xEE, 0xEE, 0xEE, 0xEE, 0xEE]))
        self.assertIsNotNone(res_gen)
        self.assertEqual(res_gen['model'], 'Universal K-Line Model')

    def test_ecm_lookup_short_bytes(self):
        self.assertIsNone(lookup_ecm(bytes([0x01, 0x02])))


if __name__ == '__main__':
    unittest.main()
