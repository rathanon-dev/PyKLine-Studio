"""
Connection & Hardware Adapter Discovery
Supports both direct libusbK / pyftdi (A50285BI) and Virtual COM Ports.
"""

try:
    from pyftdi.ftdi import Ftdi
    import pyftdi.serialext
    HAS_PYFTDI = True
except ImportError:
    HAS_PYFTDI = False

try:
    import serial
    import serial.tools.list_ports
    HAS_PYSERIAL = True
except ImportError:
    HAS_PYSERIAL = False


def scan_adapters():
    """Returns a list of all detected FTDI and Serial adapters."""
    adapters = []
    
    # 1. pyftdi / libusbK
    if HAS_PYFTDI:
        try:
            ftdi_devs = Ftdi.list_devices()
            for desc, count in ftdi_devs:
                label = f"Bus {desc.bus:03d} Device {desc.address:03d}: FTDI {desc.description} {desc.sn}"
                url = f"ftdi://ftdi:232:{desc.sn}/1" if desc.sn else "ftdi://ftdi:232/1"
                adapters.append({
                    'type': 'pyftdi',
                    'label': label,
                    'url': url,
                    'sn': desc.sn,
                    'desc': desc.description
                })
        except Exception:
            pass

    # 2. PySerial COM ports
    if HAS_PYSERIAL:
        try:
            ports = list(serial.tools.list_ports.comports())
            for p in ports:
                p_desc = f"{p.description} {p.manufacturer or ''}".strip()
                label = f"{p.device}: {p_desc}"
                adapters.append({
                    'type': 'pyserial',
                    'label': label,
                    'url': p.device,
                    'sn': p.serial_number or '',
                    'desc': p_desc
                })
        except Exception:
            pass

    # 3. Simulator (Safe TCP Bypass)
    import os
    if os.environ.get("PYKLINE_SIM") == "1" or os.environ.get("HONDAECU_SIM") == "1":
        adapters.append({
            'type': 'pyserial',
            'label': 'TEST SIMULATOR (127.0.0.1:9999)',
            'url': 'socket://127.0.0.1:9999',
            'sn': 'SIM_001',
            'desc': 'Local IP ECU Simulator'
        })

    return adapters
