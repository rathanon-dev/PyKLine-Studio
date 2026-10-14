import os
import sys

# 1. Initialize PyUSB backend (libusb-package / libusb-1.0 / libusb0)
def init_usb_backend():
    """
    Ensures PyUSB can find a working libusb dynamic library on Windows.
    Tries libusb-package first (bundled DLL), then local executable/frozen dirs, then system.
    """
    try:
        import libusb_package
        import usb.backend.libusb1
        be = usb.backend.libusb1.get_backend(find_library=libusb_package.find_library)
        if be is not None:
            return be
    except Exception:
        pass

    # Check PyInstaller frozen bundle dir or executable dir
    search_dirs = []
    if getattr(sys, 'frozen', False):
        if hasattr(sys, '_MEIPASS'):
            search_dirs.append(sys._MEIPASS)
        search_dirs.append(os.path.dirname(sys.executable))
    
    for d in search_dirs:
        dll_path = os.path.join(d, 'libusb-1.0.dll')
        if os.path.exists(dll_path):
            try:
                import usb.backend.libusb1
                be = usb.backend.libusb1.get_backend(find_library=lambda x: dll_path)
                if be is not None:
                    return be
            except Exception:
                pass

    try:
        import usb.backend.libusb1
        be = usb.backend.libusb1.get_backend()
        if be is not None:
            return be
    except Exception:
        pass

    try:
        import usb.backend.libusb0
        be = usb.backend.libusb0.get_backend()
        if be is not None:
            return be
    except Exception:
        pass

    return None

# Prime backend immediately on load
_ = init_usb_backend()

# 2. Check pyftdi support
try:
    from pyftdi.ftdi import Ftdi
    import pyftdi.serialext
    HAS_PYFTDI = True
except ImportError:
    HAS_PYFTDI = False

# 3. Check official FTDI D2XX driver support
try:
    import ftd2xx
    HAS_FTD2XX = True
except Exception:
    HAS_FTD2XX = False

# 4. Check PySerial support
try:
    import serial
    import serial.tools.list_ports
    HAS_PYSERIAL = True
except ImportError:
    HAS_PYSERIAL = False


def scan_adapters():
    """Returns a list of all detected FTDI, D2XX, libusbK, and Serial adapters."""
    adapters = []
    seen_serials = set()
    
    # 1. pyftdi / libusbK / WinUSB
    if HAS_PYFTDI:
        try:
            init_usb_backend()
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
                if desc.sn:
                    seen_serials.add(desc.sn.strip().upper())
        except Exception:
            pass

    # 2. Official FTDI D2XX Genuine Driver (if installed)
    if HAS_FTD2XX:
        try:
            num_devs = ftd2xx.createDeviceInfoList()
            for i in range(num_devs):
                info = ftd2xx.getDeviceInfoDetail(i)
                raw_sn = info.get('serial', b'')
                raw_desc = info.get('description', b'')
                sn = raw_sn.decode('utf-8', errors='ignore').strip() if isinstance(raw_sn, bytes) else str(raw_sn).strip()
                desc = raw_desc.decode('utf-8', errors='ignore').strip() if isinstance(raw_desc, bytes) else str(raw_desc).strip()
                
                # Avoid duplicate if pyftdi already added this exact serial
                if sn and sn.upper() in seen_serials:
                    continue
                
                label = f"FTDI D2XX [Dev {i}]: {desc} ({sn})"
                adapters.append({
                    'type': 'ftd2xx',
                    'label': label,
                    'url': f"ftd2xx://{i}",
                    'sn': sn,
                    'desc': desc,
                    'index': i
                })
                if sn:
                    seen_serials.add(sn.upper())
        except Exception:
            pass

    # 3. PySerial COM ports
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

    # 4. Simulator (Safe TCP Bypass & Local Auto-Detection)
    import socket
    sim_enabled = os.environ.get("PYKLINE_SIM") == "1" or os.environ.get("HONDAECU_SIM") == "1"

    if not sim_enabled:
        try:
            with socket.create_connection(("127.0.0.1", 9999), timeout=0.08):
                sim_enabled = True
        except Exception:
            sim_enabled = False

    if sim_enabled:
        adapters.append({
            'type': 'pyserial',
            'label': 'TEST SIMULATOR (127.0.0.1:9999)',
            'url': 'socket://127.0.0.1:9999',
            'sn': 'SIM_001',
            'desc': 'Local IP ECU Simulator'
        })

    return adapters
