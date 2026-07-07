"""PoC: thinnest vertical slice of the OIDSense suite, to test the core ideas.

Exercised end to end:
  1. Hand-rolled minimal BER codec (encode GetBulk, decode Response) — feasibility/size.
  2. Tolerant transport: a device answering with a FIXED request-id (1) is walked
     successfully; the violation is recorded, not dropped.
  3. Trace emission per traceformat/trace-format.md, every line validated against
     traceformat/trace-format.schema.json; survey + pinpoint runs share a session id.
  4. Profile-driven emulator (OIDEmu idea): tree + latency rules + quirks, served
     over real loopback UDP.
  5. Settings-finder idea: survey walk (bulk 10) finds slow ranges; pinpoint walk
     (bulk 1) attributes latency to single OIDs; fit recovers tree, quirk and slow
     OIDs from the traces and is compared against the emulator's ground truth.

Deliberately NOT in the PoC: scrubber, asyncio, retries beyond basics, v1, CLI.

Run: uv run --with jsonschema,pysnmp python experiments/poc_roundtrip.py
"""

import gzip
import json
import random
import socket
import threading
import time
from pathlib import Path

OUT = Path(__file__).parent / "data"
SCHEMA = Path(__file__).parent.parent / "traceformat" / "trace-format.schema.json"

# ---------------------------------------------------------------- BER codec

TAG_NAMES = {0x02: "Integer", 0x04: "OctetString", 0x05: "Null",
             0x06: "ObjectIdentifier", 0x41: "Counter32", 0x42: "Gauge32",
             0x43: "TimeTicks", 0x82: "EndOfMibView"}


def _len(n: int) -> bytes:
    if n < 0x80:
        return bytes([n])
    b = n.to_bytes((n.bit_length() + 7) // 8, "big")
    return bytes([0x80 | len(b)]) + b


def tlv(tag: int, payload: bytes) -> bytes:
    return bytes([tag]) + _len(len(payload)) + payload


def enc_int(v: int, tag: int = 0x02) -> bytes:
    return tlv(tag, v.to_bytes(v.bit_length() // 8 + 1, "big", signed=True))


def enc_oid(oid: str) -> bytes:
    arcs = [int(x) for x in oid.split(".")]
    body = bytearray([40 * arcs[0] + arcs[1]])
    for a in arcs[2:]:
        chunk = [a & 0x7F]
        a >>= 7
        while a:
            chunk.insert(0, (a & 0x7F) | 0x80)
            a >>= 7
        body.extend(chunk)
    return tlv(0x06, bytes(body))


def rd_tlv(b: bytes, i: int) -> tuple[int, bytes, int]:
    tag = b[i]
    ln = b[i + 1]
    i += 2
    if ln & 0x80:
        n = ln & 0x7F
        ln = int.from_bytes(b[i:i + n], "big")
        i += n
    return tag, b[i:i + ln], i + ln


def dec_int(body: bytes) -> int:
    return int.from_bytes(body, "big", signed=True)


def dec_oid(body: bytes) -> str:
    arcs = [body[0] // 40, body[0] % 40]
    acc = 0
    for byte in body[1:]:
        acc = (acc << 7) | (byte & 0x7F)
        if not byte & 0x80:
            arcs.append(acc)
            acc = 0
    return ".".join(map(str, arcs))


def encode_getbulk(req_id: int, oid: str, non_rep: int, max_rep: int,
                   community: bytes = b"public") -> bytes:
    vbs = tlv(0x30, tlv(0x30, enc_oid(oid) + tlv(0x05, b"")))
    pdu = tlv(0xA5, enc_int(req_id) + enc_int(non_rep) + enc_int(max_rep) + vbs)
    return tlv(0x30, enc_int(1) + tlv(0x04, community) + pdu)


def encode_response(req_id: int, varbinds: list[tuple[str, int, bytes]],
                    community: bytes = b"public") -> bytes:
    vbs = b"".join(tlv(0x30, enc_oid(o) + tlv(tag, val)) for o, tag, val in varbinds)
    pdu = tlv(0xA2, enc_int(req_id) + enc_int(0) + enc_int(0) + tlv(0x30, vbs))
    return tlv(0x30, enc_int(1) + tlv(0x04, community) + pdu)


def decode_message(raw: bytes) -> dict:
    """Tolerant-ish: returns parsed fields; raises only on structural garbage."""
    _, body, _ = rd_tlv(raw, 0)
    _, _ver, i = rd_tlv(body, 0)
    _, _community, i = rd_tlv(body, i)
    pdu_tag, pdu, _ = rd_tlv(body, i)
    _, rid, j = rd_tlv(pdu, 0)
    _, f1, j = rd_tlv(pdu, j)   # error-status | non-repeaters
    _, f2, j = rd_tlv(pdu, j)   # error-index  | max-repetitions
    _, vbs, _ = rd_tlv(pdu, j)
    varbinds = []
    k = 0
    while k < len(vbs):
        _, vb, k = rd_tlv(vbs, k)
        _, oid_b, m = rd_tlv(vb, 0)
        vtag, val, _ = rd_tlv(vb, m)
        varbinds.append({"oid": dec_oid(oid_b), "vtag": vtag, "vlen": len(val)})
    return {"pdu_tag": pdu_tag, "request_id": dec_int(rid),
            "f1": dec_int(f1), "f2": dec_int(f2), "varbinds": varbinds}


# ------------------------------------------------------------- emulator (OIDEmu idea)

PROFILE = {
    "tree": [],  # filled in main(): [(oid, ber_tag, vlen)]
    "latency": {"default_ms": 1,
                "rules": [{"prefix": "1.3.6.1.2.1.2.2.1.7.", "per_oid_ms": 20}]},
    "quirks": {"request_id": "fixed:1"},
}


def per_oid_latency(oid: str, profile: dict) -> float:
    for rule in profile["latency"]["rules"]:
        if oid.startswith(rule["prefix"]):
            return rule["per_oid_ms"] / 1000
    return profile["latency"]["default_ms"] / 1000


class Emulator(threading.Thread):
    def __init__(self, profile: dict):
        super().__init__(daemon=True)
        self.profile = profile
        self.oids = [t[0] for t in profile["tree"]]
        self.keys = [tuple(map(int, o.split("."))) for o in self.oids]
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.sock.bind(("127.0.0.1", 0))
        self.sock.settimeout(0.1)
        self.port = self.sock.getsockname()[1]
        self.running = True

    def run(self):
        import bisect
        while self.running:
            try:
                raw, addr = self.sock.recvfrom(65535)
            except socket.timeout:
                continue
            req = decode_message(raw)
            start = tuple(map(int, req["varbinds"][0]["oid"].split(".")))
            idx = bisect.bisect_right(self.keys, start)
            chunk = self.profile["tree"][idx:idx + max(req["f2"], 1)]
            if chunk:
                vbs = [(o, tag, b"\x00" * vlen) for o, tag, vlen in chunk]
                time.sleep(sum(per_oid_latency(o, self.profile) for o, _, _ in chunk))
            else:
                vbs = [(req["varbinds"][0]["oid"], 0x82, b"")]
            rid = 1 if self.profile["quirks"].get("request_id") == "fixed:1" else req["request_id"]
            self.sock.sendto(encode_response(rid, vbs), addr)


# ------------------------------------------------------------- prober + trace writer

def walk(port: int, path: Path, session: dict, bulk: int, start_oid: str,
         stop_prefix: str | None = None, timeout_s: float = 2.0) -> None:
    """GetBulk walk writing a trace per traceformat/trace-format.md."""
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.settimeout(timeout_s)
    t0 = time.monotonic()
    rel = lambda: round(time.monotonic() - t0, 6)
    rng = random.Random(42)
    with gzip.open(path, "wt", encoding="utf-8") as f:
        def emit(rec):
            f.write(json.dumps(rec, separators=(",", ":")) + "\n")
            f.flush()

        emit({"type": "header", "format_version": 1, "tool": "oidtrace-poc 0.0.1",
              "started_at": "2026-06-11T15:00:00Z", "label": "poc-roundtrip",
              "session": session, "snmp": {"version": "2c"},
              "settings": {"bulk_size": bulk, "timeout_s": timeout_s, "retries": 2,
                           "start_oid": start_oid}})
        cur, seq, done = start_oid, 0, False
        while not done:
            seq += 1
            rid = rng.randrange(1000, 2 ** 31)
            raw_req = encode_getbulk(rid, cur, 0, bulk)
            sent_at = rel()
            sock.sendto(raw_req, ("127.0.0.1", port))
            raw_resp, _ = sock.recvfrom(65535)
            received_at = rel()
            resp = decode_message(raw_resp)
            violations = []
            if resp["request_id"] != rid:
                violations.append("request-id-mismatch")
            varbinds = [{"oid": vb["oid"], "vtype": TAG_NAMES.get(vb["vtag"], f"tag:0x{vb['vtag']:02x}"),
                         "vlen": vb["vlen"]} for vb in resp["varbinds"]]
            rec = {"type": "exchange", "seq": seq,
                   "request": {"pdu": "getbulk", "request_id": rid, "oids": [cur],
                               "non_repeaters": 0, "max_repetitions": bulk,
                               "raw": raw_req.hex()},
                   "attempts": [{"sent_at": sent_at, "received_at": received_at}],
                   "response": {"request_id": resp["request_id"], "error_status": resp["f1"],
                                "error_index": resp["f2"], "varbinds": varbinds,
                                "raw": raw_resp.hex()}}
            if violations:
                rec["violations"] = violations
            emit(rec)
            for vb in varbinds:
                if vb["vtype"] == "EndOfMibView" or (stop_prefix and not vb["oid"].startswith(stop_prefix)):
                    done = True
            if varbinds and not done:
                cur = varbinds[-1]["oid"]
        emit({"type": "summary", "at": rel(), "exchanges": seq,
              "oids_seen": 0, "end_reason": "completed", "violation_counts":
              {"request-id-mismatch": seq}})
    sock.close()


# ------------------------------------------------------------------------ fit

def fit(paths: list[Path]) -> dict:
    """Streaming single pass per file; merge across the session bundle."""
    tree: dict[str, tuple[str, int]] = {}
    per_oid_ms: dict[str, float] = {}
    rid_returned: set[int] = set()
    session_ids = set()
    for path in paths:
        with gzip.open(path, "rt", encoding="utf-8") as f:
            bulk = None
            for line in f:
                rec = json.loads(line)
                if rec["type"] == "header":
                    session_ids.add(rec["session"]["id"])
                    bulk = rec["settings"]["bulk_size"]
                if rec["type"] != "exchange" or not rec.get("response"):
                    continue
                a = rec["attempts"][-1]
                dt_ms = (a["received_at"] - a["sent_at"]) * 1000
                vbs = [vb for vb in rec["response"]["varbinds"] if vb["vtype"] != "EndOfMibView"]
                for vb in vbs:
                    tree[vb["oid"]] = (vb["vtype"], vb["vlen"])
                if bulk == 1 and len(vbs) == 1:  # pinpoint: direct per-OID attribution
                    per_oid_ms[vbs[0]["oid"]] = dt_ms
                rid_returned.add(rec["response"]["request_id"])
    assert len(session_ids) == 1, "bundle must share one session id"
    quirk = f"fixed:{rid_returned.pop()}" if len(rid_returned) == 1 else "echo"
    return {"tree": tree, "per_oid_ms": per_oid_ms, "request_id": quirk}


# ----------------------------------------------------------------------- main

def main() -> None:
    OUT.mkdir(exist_ok=True)
    rng = random.Random(3)
    n = 1000
    cols = [f"1.3.6.1.2.1.2.2.1.{c}" for c in range(1, 11)]
    PROFILE["tree"] = sorted(
        ((f"{col}.{i}", rng.choice((0x02, 0x04, 0x41, 0x42)), rng.choice((1, 4, 11, 17)))
         for col in cols for i in range(1, n // 10 + 1)),
        key=lambda t: tuple(map(int, t[0].split("."))))

    emu = Emulator(PROFILE)
    emu.start()
    print(f"emulator: {n} OIDs on 127.0.0.1:{emu.port}, slow prefix "
          f"{PROFILE['latency']['rules'][0]['prefix']}* at "
          f"{PROFILE['latency']['rules'][0]['per_oid_ms']} ms/OID, quirk request_id=fixed:1")

    session = {"id": "0a4be5cc-1bb6-4ad2-9e6e-1f6a37f2b9aa", "run": 1, "runs_total": 2}
    survey = OUT / "poc_survey.oidtrace.jsonl.gz"
    t0 = time.monotonic()
    walk(emu.port, survey, session, bulk=10, start_oid="1.3.6.1")
    print(f"survey walk (bulk 10): completed in {time.monotonic() - t0:.2f}s -> {survey.name}")

    # settings-finder idea, phase 1: find slow ranges from the survey trace
    slow_ranges = []
    with gzip.open(survey, "rt", encoding="utf-8") as f:
        for line in f:
            rec = json.loads(line)
            if rec["type"] == "exchange" and rec.get("response"):
                a = rec["attempts"][-1]
                if (a["received_at"] - a["sent_at"]) * 1000 > 50:
                    slow_ranges.append(rec["request"]["oids"][0])
    print(f"phase 1: {len(slow_ranges)} slow exchanges found in survey")
    assert slow_ranges, "survey failed to find the slow range"

    # phase 2: pinpoint — bulk-1 walk over the slow column only
    slow_prefix = PROFILE["latency"]["rules"][0]["prefix"]
    pinpoint = OUT / "poc_pinpoint.oidtrace.jsonl.gz"
    session2 = dict(session, run=2)
    t0 = time.monotonic()
    walk(emu.port, pinpoint, session2, bulk=1,
         start_oid=slow_prefix.rstrip("."), stop_prefix=slow_prefix)
    print(f"pinpoint walk (bulk 1): completed in {time.monotonic() - t0:.2f}s -> {pinpoint.name}")

    # idea 3: every line of both traces is schema-valid
    from jsonschema import Draft202012Validator
    v = Draft202012Validator(json.load(SCHEMA.open()))
    lines = 0
    for path in (survey, pinpoint):
        with gzip.open(path, "rt", encoding="utf-8") as f:
            for line in f:
                v.validate(json.loads(line))
                lines += 1
    print(f"schema: all {lines} trace lines valid")

    # idea 1 cross-check: packets decode against pysnmp's SNMP message spec
    # (pyasn1's schemaless decoder can't walk context-tagged PDUs; the spec-driven
    # decode is the meaningful independent validation anyway)
    from pyasn1.codec.ber import decoder as ber_decoder
    from pysnmp.proto import api as snmp_api
    pmods = getattr(snmp_api, "PROTOCOL_MODULES", None) or snmp_api.protoModules
    v2c = getattr(snmp_api, "SNMP_VERSION_2C", None) or snmp_api.protoVersion2c
    spec = pmods[v2c].Message()
    with gzip.open(survey, "rt", encoding="utf-8") as f:
        for line in f:
            rec = json.loads(line)
            if rec["type"] == "exchange":
                for raw_hex in (rec["request"]["raw"], rec["response"]["raw"]):
                    _, rest = ber_decoder.decode(bytes.fromhex(raw_hex), asn1Spec=spec)
                    assert not rest
    print("codec: all survey packets decode against pysnmp's v2c Message spec")

    # ideas 4+5: fit a profile back from the bundle, compare with ground truth
    fitted = fit([survey, pinpoint])
    truth_tree = {o: (TAG_NAMES[tag], vlen) for o, tag, vlen in PROFILE["tree"]}
    assert fitted["tree"] == truth_tree, "fitted tree differs from emulator ground truth"
    assert fitted["request_id"] == "fixed:1", fitted["request_id"]
    slow_oids = {o for o, ms in fitted["per_oid_ms"].items() if ms > 10}
    truth_slow = {o for o in truth_tree if o.startswith(slow_prefix)}
    assert slow_oids == truth_slow, (len(slow_oids), len(truth_slow))
    max_ms = max(fitted["per_oid_ms"].values())
    print(f"fit: tree ({len(fitted['tree'])} OIDs) == ground truth; quirk {fitted['request_id']} "
          f"detected; {len(slow_oids)}/{len(truth_slow)} slow OIDs pinpointed")
    print(f"derived settings: timeout >= {max_ms / 1000:.3f}s + 1s margin, "
          f"exclude/separate subtree {slow_prefix}*")

    emu.running = False
    emu.join()
    print("\nPoC PASS: codec, quirk-tolerant walk, schema-valid traces, "
          "profile emulator, survey->pinpoint->fit loop all work")


if __name__ == "__main__":
    main()
