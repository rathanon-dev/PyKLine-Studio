"""
Data-driven Honda K-Line table definitions.

Each field records WHERE its value comes from (byte offset into the payload),
HOW it is scaled, and HOW SURE we are about it. The GUI and the logger are both
generated from these specs, so they can never drift apart, and a field we have
not located is shown as N/A instead of an invented number.

Payload = bytes after the "02 LEN 71 <table>" header, without the checksum.

Table 0x17 below was derived from raw captures on two ECUs that share the same
19-byte layout:
  * Honda Click 125i 2014  (ECM 01 01 BD 0D 01) - logs/live_telemetry.jsonl (2026-10-10)
  * Honda Lead 125 4V 2022 (ECM 01 04 78 0D 01) - honda_raw_log_20261006_125759.csv

Evidence summary (Click 125i, 1273 frames, idle -> shutdown):
  b0-1  RPM            ~1500 at idle, 0 after shutdown
  b2    TPS raw        28-29 (0.55 V) throttle closed
  b3    TPS % (ECU)    0 with throttle closed
  b4-7  FF FF FF FF    never changes, ECU fills unsupported slots with 0xFF.
                       HondaECU v3 reads these as ECT/IAT -> 0xFF - 40 = 215 C.
  b8    ECT raw (V)    45 -> 31 while warming, 31 -> 36 after shutdown
  b9    ECT (C + 40)   117 -> 132 while warming, 132 -> 125 after shutdown
                       b8 + b9 stays ~162 throughout: same thermistor, two forms.
  b10   Battery x0.1V  139-142 running (charging), 126-127 engine off
  b11-12 Injector      0x020B-0x0220 running, 0x01FF engine off
  b13   Ignition       152-153 -> 12.0-12.5 deg (same formula as HondaECU v3)
  b14   IACV           103-109 warm idle, parks at 128 with engine off
  b15-18               always 0 so far (bike on stand)
"""
from dataclasses import dataclass, field as dc_field

# Confidence levels
VERIFIED = "verified"      # offset AND scale cross-checked (physical behaviour + 2nd tool)
LIKELY = "likely"          # offset matches behaviour; scale not independently confirmed
UNVERIFIED = "unverified"  # placeholder; needs a specific test to confirm
NOT_FOUND = "not_found"    # not located in this table for this ECU family


@dataclass(frozen=True)
class Field:
    key: str
    label: str
    unit: str
    offset: int                 # -1 = not present in this table
    size: int = 1               # bytes, big-endian
    scale: float = 1.0
    bias: float = 0.0
    decimals: int = 0
    confidence: str = VERIFIED
    note: str = ""

    def decode(self, payload):
        if self.offset < 0 or self.offset + self.size > len(payload):
            return None
        chunk = payload[self.offset:self.offset + self.size]
        if all(b == 0xFF for b in chunk):  # ECU marks unsupported slots with 0xFF
            return None
        raw = int.from_bytes(bytes(chunk), "big")
        value = raw * self.scale + self.bias
        return int(round(value)) if self.decimals == 0 else round(value, self.decimals)


@dataclass(frozen=True)
class Flag:
    key: str
    label: str
    offset: int
    mask: int
    invert: bool = False
    confidence: str = VERIFIED
    note: str = ""

    def decode(self, payload):
        if self.offset >= len(payload):
            return None
        bit = bool(payload[self.offset] & self.mask)
        return (not bit) if self.invert else bit


@dataclass(frozen=True)
class TableSpec:
    table_id: int
    name: str
    min_len: int
    fields: tuple = dc_field(default_factory=tuple)
    flags: tuple = dc_field(default_factory=tuple)

    @property
    def raw_key(self):
        return f"raw_{self.table_id:02x}"

    @property
    def keys(self):
        return [f.key for f in self.fields] + [f.key for f in self.flags]

    def decode(self, payload):
        out = {f.key: f.decode(payload) for f in self.fields}
        out.update({f.key: f.decode(payload) for f in self.flags})
        out[self.raw_key] = " ".join(f"{b:02X}" for b in payload)
        return out


# ---------------------------------------------------------------------------
# Table 0x17 - main live data (Honda eSP scooter, 19-byte payload)
# ---------------------------------------------------------------------------
TABLE_17 = TableSpec(
    table_id=0x17,
    name="Live Telemetry",
    min_len=15,
    fields=(
        Field("rpm", "Engine speed", "rpm", 0, size=2,
              note="0 when stopped, ~1500 at idle; matches HondaECU v3"),
        Field("tps_pct", "TPS (ECU %)", "%", 3, scale=1 / 1.6, decimals=1,
              confidence=LIKELY,
              note="ECU-computed opening. Reads 0 closed; sweep throttle to confirm 100% at WOT"),
        Field("tps_deg", "TPS angle", "°", 3, scale=0.5, decimals=1,
              confidence=VERIFIED,
              note="throttle opening angle in degrees (b3 * 0.5)"),
        Field("tps_v", "TPS voltage", "V", 2, scale=5 / 255, decimals=2,
              note="same formula as HondaECU v3"),
        Field("ect", "ECT (coolant)", "°C", 9, bias=-40,
              confidence=LIKELY,
              note="rose 77->92 C at idle, fell after shutdown. Confirm on a cold engine (should be ~ambient)"),
        Field("ect_v", "ECT voltage", "V", 8, scale=5 / 255, decimals=2,
              confidence=LIKELY,
              note="thermistor voltage; falls as ECT rises (b8 + b9 ~ 162)"),
        Field("battery", "Battery voltage", "V", 10, scale=0.1, decimals=1,
              note="~14 V charging, 12.6 V engine off; matches HondaECU v3"),
        Field("inj_ms", "Injector duration", "ms", 11, size=2, scale=0.005, decimals=2,
              confidence=UNVERIFIED,
              note="16-bit value is real (changes with engine state); ms scale not confirmed"),
        Field("ign_deg", "Ignition advance", "°", 13, scale=0.5, bias=-64, decimals=1,
              note="same formula as HondaECU v3"),
        Field("iacv", "IACV (raw count)", "", 14,
              confidence=LIKELY,
              note="parks at 128 with engine off, ~103-109 at warm idle; unit not confirmed"),
        Field("speed", "Vehicle speed", "km/h", 15,
              confidence=UNVERIFIED,
              note="always 0 so far; spin the rear wheel on the stand to confirm"),
        Field("map_mbar", "MAP sensor", "mBar", -1, confidence=NOT_FOUND,
              note="not located in Table 0x17 on this ECU family"),
        Field("iat", "IAT sensor", "°C", -1, confidence=NOT_FOUND,
              note="slot b6/b7 is 0xFF (unsupported) on this ECU family"),
    ),
)

# ---------------------------------------------------------------------------
# Table 0xD1 - switch / status flags (decoded empirically, see handover doc)
# ---------------------------------------------------------------------------
TABLE_D1 = TableSpec(
    table_id=0xD1,
    name="Switch Flags",
    min_len=5,
    flags=(
        Flag("side_stand_up", "Side stand", 0, 0x02, invert=True,
             note="bit set = stand DOWN"),
        Flag("start_interlock", "Start interlock", 0, 0x20,
             note="left brake + starter button in series"),
        Flag("engine_running", "Engine running", 4, 0x01),
    ),
)

# ---------------------------------------------------------------------------
# Table 0x20 - O2 sensor / fuel trim (formulas from HondaECU v3)
# ---------------------------------------------------------------------------
TABLE_20 = TableSpec(
    table_id=0x20,
    name="O2 & Fuel Trim",
    min_len=3,
    fields=(
        Field("o2_v", "O2 sensor #1", "V", 0, scale=5 / 255, decimals=2,
              confidence=UNVERIFIED,
              note="read 3.84 V engine-off. Confirm with engine running (narrowband swings ~0.1-0.9 V)"),
        Field("stft", "STFT #1", "", 1, scale=2 / 255, decimals=3,
              confidence=LIKELY,
              note="1.000 = no correction; raw 128 seen"),
        Field("o2_heater", "O2 heater #1", "V", 2, scale=5 / 255, decimals=2,
              confidence=UNVERIFIED),
    ),
)

# Tables requested on every polling cycle, in order. TABLE_17 must be first.
POLL_TABLES = (TABLE_17, TABLE_D1, TABLE_20)
