from pysnmp.proto import rfc1902

SnmpValue = (
    rfc1902.OctetString
    | rfc1902.ObjectIdentifier
    | rfc1902.Integer32
    | rfc1902.Counter32
    | rfc1902.Gauge32
    | rfc1902.TimeTicks
)


def build_oid_tree(n_interfaces: int = 4) -> dict[tuple[int, ...], SnmpValue]:
    data: dict[tuple[int, ...], SnmpValue] = {}

    # system group (fast)
    data[(1, 3, 6, 1, 2, 1, 1, 1, 0)] = rfc1902.OctetString(
        "Emulated Slow SNMP Device; Cisco IOS 15.2 (emulated)"
    )
    data[(1, 3, 6, 1, 2, 1, 1, 2, 0)] = rfc1902.ObjectIdentifier(
        (1, 3, 6, 1, 4, 1, 9, 1, 1)
    )
    data[(1, 3, 6, 1, 2, 1, 1, 4, 0)] = rfc1902.OctetString("noc@example.com")
    data[(1, 3, 6, 1, 2, 1, 1, 5, 0)] = rfc1902.OctetString("slow-router.example.com")
    data[(1, 3, 6, 1, 2, 1, 1, 6, 0)] = rfc1902.OctetString("Lab, Rack 1, Unit 3")
    data[(1, 3, 6, 1, 2, 1, 1, 7, 0)] = rfc1902.Integer32(78)

    data[(1, 3, 6, 1, 2, 1, 2, 1, 0)] = rfc1902.Integer32(n_interfaces)

    for idx in range(1, n_interfaces + 1):
        p = (1, 3, 6, 1, 2, 1, 2, 2, 1)
        data[p + (1, idx)] = rfc1902.Integer32(idx)
        data[p + (2, idx)] = rfc1902.OctetString(f"GigabitEthernet0/{idx - 1}")
        data[p + (3, idx)] = rfc1902.Integer32(6)
        data[p + (4, idx)] = rfc1902.Integer32(1500)
        data[p + (5, idx)] = rfc1902.Gauge32(1_000_000_000)
        data[p + (6, idx)] = rfc1902.OctetString(
            bytes([0x00, 0x11, 0x22, 0x33, 0x44, idx])
        )
        data[p + (7, idx)] = rfc1902.Integer32(1)
        data[p + (8, idx)] = rfc1902.Integer32(1)
        data[p + (9, idx)] = rfc1902.TimeTicks(0)
        data[p + (10, idx)] = rfc1902.Counter32(idx * 1_234_567)
        data[p + (11, idx)] = rfc1902.Counter32(idx * 8_901)
        data[p + (12, idx)] = rfc1902.Counter32(0)
        data[p + (13, idx)] = rfc1902.Counter32(0)
        data[p + (14, idx)] = rfc1902.Counter32(0)
        data[p + (15, idx)] = rfc1902.Counter32(0)
        data[p + (16, idx)] = rfc1902.Counter32(idx * 987_654)
        data[p + (17, idx)] = rfc1902.Counter32(idx * 7_432)
        data[p + (18, idx)] = rfc1902.Counter32(0)
        data[p + (19, idx)] = rfc1902.Counter32(0)
        data[p + (20, idx)] = rfc1902.Counter32(0)
        data[p + (21, idx)] = rfc1902.Gauge32(0)
        data[p + (22, idx)] = rfc1902.ObjectIdentifier((1, 3, 6, 1, 2, 1, 10, 7, 1))

    return dict(sorted(data.items()))
