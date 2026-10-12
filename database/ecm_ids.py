"""
Database of Universal ECM Hardware Signatures and Vehicle Mappings
Used for Auto-detecting ECU Model, Part Number, and Engine Variant via Table 0x00.
"""

ECM_DATABASE = {
    # Lead 125 (eSP+ 4V 2022-2024)
    bytes([0x01, 0x04, 0x78, 0x0D, 0x01]): {
        'model': 'Lead 125 4V',
        'year': '2022-2024',
        'pn': '30400-K2TA-T01',
        'engine': 'eSP+ 125cc 4-Valve',
        'ecu_type': 'K-Line ECU'
    },
    # Lead 125 (2V)
    bytes([0x01, 0x03, 0x12, 0x0D, 0x01]): {
        'model': 'Lead 125 2V',
        'year': '2018-2021',
        'pn': '30400-K12M-J01',
        'engine': 'eSP 125cc 2-Valve',
        'ecu_type': 'K-Line ECU'
    },
    # Click 125i (2014) - KZR
    bytes([0x01, 0x01, 0xBD, 0x0D, 0x01]): {
        'model': 'Click 125i',
        'year': '2014',
        'pn': '30400-KZR-601',
        'engine': 'eSP 125cc 2-Valve (KZR)',
        'ecu_type': 'K-Line ECU'
    },
    # Click 125i (eSP 2015-2018)
    bytes([0x01, 0x01, 0x24, 0x04, 0x01]): {
        'model': 'Click 125i',
        'year': '2015-2018',
        'pn': '30400-K59-A11',
        'engine': 'eSP 125cc 2-Valve',
        'ecu_type': 'K-Line ECU'
    },
    # MSX 125
    bytes([0x01, 0x01, 0x35, 0x05, 0x01]): {
        'model': 'MSX 125',
        'year': '2013-2015',
        'pn': '38770-K26-911',
        'engine': '125cc 2-Valve',
        'ecu_type': 'K-Line ECU'
    },
    bytes([0x01, 0x02, 0x57, 0x05, 0x01]): {
        'model': 'MSX 125 SF',
        'year': '2016-2019',
        'pn': '38770-K26-C31',
        'engine': '125cc 2-Valve',
        'ecu_type': 'K-Line ECU'
    },
    # CBR 650 F
    bytes([0x01, 0x01, 0x4E, 0x12, 0x01]): {
        'model': 'CBR 650 F',
        'year': '2014-2016',
        'pn': '38770-MJE-G12',
        'engine': '650cc 4-Cylinder',
        'ecu_type': 'K-Line ECU'
    },
    # CBR 1000 RR
    bytes([0x01, 0x00, 0x2B, 0x01, 0x01]): {
        'model': 'CBR 1000 RR',
        'year': '2006-2007',
        'pn': '38770-MEL-D21',
        'engine': '1000cc 4-Cylinder',
        'ecu_type': 'K-Line ECU'
    },
    # VFR 1200 F
    bytes([0x01, 0x00, 0xAA, 0x01, 0x02]): {
        'model': 'VFR 1200 F',
        'year': '2010-2011',
        'pn': '38770-MGE-D02',
        'engine': 'V4 1200cc',
        'ecu_type': 'K-Line ECU'
    }
}

def lookup_ecm(sig_bytes):
    """Looks up ECM details from a 5-byte signature."""
    if not sig_bytes or len(sig_bytes) < 5:
        return None
    sig5 = bytes(sig_bytes[:5])
    if sig5 in ECM_DATABASE:
        return dict(ECM_DATABASE[sig5])
    # Prefix match
    for k, v in ECM_DATABASE.items():
        if k[:3] == sig5[:3]:
            res = dict(v)
            res['model'] = f"{res['model']} (Variant)"
            return res
    return {
        'model': 'Universal K-Line Model',
        'year': '-',
        'pn': 'Generic Part No.',
        'engine': 'Small Engine EFI',
        'ecu_type': 'K-Line ECU'
    }
