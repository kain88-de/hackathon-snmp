#!/usr/bin/env python3
"""SNMP v1/v2c device emulator — fast system OIDs, slow interface table."""

import os
import socket
import time
from pyasn1.codec.ber import encoder, decoder
from pyasn1.type.univ import ObjectIdentifier
from pysnmp.proto import api, rfc1902

import mibs

COMMUNITY = os.environ.get("SNMP_COMMUNITY", "public")
HOST = os.environ.get("SNMP_HOST", "0.0.0.0")
PORT = int(os.environ.get("SNMP_PORT", "1161"))

_start_time = time.monotonic()
_oid_tree: dict = {}
_sorted_oids: list = []

SYSUPTIME_OID = (1, 3, 6, 1, 2, 1, 1, 3, 0)


def setup():
    global _oid_tree, _sorted_oids
    _oid_tree = mibs.build_oid_tree()
    _sorted_oids = sorted(_oid_tree.keys())


def lookup(oid_tuple: tuple):
    if oid_tuple == SYSUPTIME_OID:
        return rfc1902.TimeTicks(int((time.monotonic() - _start_time) * 100))
    return _oid_tree.get(oid_tuple)


def lookup_next(oid_tuple: tuple) -> tuple[tuple | None, object]:
    for oid in _sorted_oids:
        if oid > oid_tuple:
            val = lookup(oid)
            if val is not None:
                return oid, val
    return None, None


def oid_is_slow(oid_tuple: tuple) -> bool:
    s = ".".join(map(str, oid_tuple))
    return any(s.startswith(p) for p in mibs.SLOW_PREFIXES)


def process(data: bytes, addr) -> bytes | None:
    t0 = time.monotonic()

    try:
        ver = api.decodeMessageVersion(data)
        pMod = api.PROTOCOL_MODULES[ver]
        reqMsg, _ = decoder.decode(data, asn1Spec=pMod.Message())
    except Exception as e:
        print(f"[WARN] decode error from {addr}: {e}")
        return None

    if bytes(pMod.apiMessage.get_community(reqMsg)).decode() != COMMUNITY:
        return None

    reqPDU = pMod.apiMessage.get_pdu(reqMsg)
    pdu_name = reqPDU.__class__.__name__

    req_binds = pMod.apiPDU.get_varbinds(reqPDU)
    rsp_binds = []
    slow = False

    if pdu_name == "GetRequestPDU":
        for oid, _ in req_binds:
            t = tuple(oid)
            if oid_is_slow(t):
                slow = True
            val = lookup(t)
            rsp_binds.append((oid, val if val is not None else rfc1902.OctetString("")))

    elif pdu_name == "GetNextRequestPDU":
        for oid, _ in req_binds:
            t = tuple(oid)
            next_oid, val = lookup_next(t)
            if next_oid is None:
                break
            if oid_is_slow(next_oid):
                slow = True
            rsp_binds.append((ObjectIdentifier(next_oid), val))

    elif pdu_name == "GetBulkRequestPDU":
        non_rep = int(pMod.apiBulkPDU.get_non_repeaters(reqPDU))
        max_rep = int(pMod.apiBulkPDU.get_max_repetitions(reqPDU))

        for oid, _ in req_binds[:non_rep]:
            t = tuple(oid)
            next_oid, val = lookup_next(t)
            if next_oid and val is not None:
                if oid_is_slow(next_oid):
                    slow = True
                rsp_binds.append((ObjectIdentifier(next_oid), val))

        rep_oids = [tuple(oid) for oid, _ in req_binds[non_rep:]]
        for _ in range(max_rep):
            if not rep_oids:
                break
            advanced = []
            for t in rep_oids:
                next_oid, val = lookup_next(t)
                if next_oid and val is not None:
                    if oid_is_slow(next_oid):
                        slow = True
                    rsp_binds.append((ObjectIdentifier(next_oid), val))
                    advanced.append(next_oid)
            rep_oids = advanced

    else:
        return None

    first_oid = ".".join(map(str, tuple(req_binds[0][0])))
    tag = "[SLOW]" if slow else "[FAST]"
    print(f"{tag} {pdu_name:<22} {first_oid}", end="", flush=True)

    if slow:
        time.sleep(mibs.SLOW_DELAY)

    rspMsg = pMod.apiMessage.get_response(reqMsg)
    rspPDU = pMod.apiMessage.get_pdu(rspMsg)
    pMod.apiPDU.set_varbinds(rspPDU, rsp_binds)
    pMod.apiPDU.set_error_status(rspPDU, 0)
    pMod.apiPDU.set_error_index(rspPDU, 0)

    elapsed = time.monotonic() - t0
    print(f"  →  {elapsed:.2f}s", flush=True)

    return encoder.encode(rspMsg)


def main():
    setup()
    print(f"SNMP emulator  udp://{HOST}:{PORT}  community={COMMUNITY}")
    print(f"Slow prefix: {mibs.SLOW_PREFIXES}  delay={mibs.SLOW_DELAY}s")
    n_ifaces = sum(1 for k in _sorted_oids if len(k) == 11 and k[:10] == (1,3,6,1,2,1,2,2,1,1))
    print(f"MIB tree: {len(_oid_tree)} OIDs  ({n_ifaces} interfaces)")
    print()

    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    sock.bind((HOST, PORT))
    print("Listening... (Ctrl-C to stop)\n")

    try:
        while True:
            data, addr = sock.recvfrom(65535)
            resp = process(data, addr)
            if resp:
                sock.sendto(resp, addr)
    except KeyboardInterrupt:
        print("\nDone.")
    finally:
        sock.close()


if __name__ == "__main__":
    main()
