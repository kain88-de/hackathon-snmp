#!/usr/bin/env python3
import os
import signal

from emulator import EmulatorConfig, EmulatorServer


def main() -> None:
    config = EmulatorConfig(
        username=os.environ.get("SNMP_USERNAME", "monitor"),
        auth_password=os.environ.get("SNMP_AUTH_PASSWORD", "authpass1"),
        slow_prefixes=tuple(os.environ.get("SLOW_PREFIXES", "1.3.6.1.2.1.2.2.1").split(",")),
        slow_delay=float(os.environ.get("SLOW_DELAY", "0.1")),
        n_interfaces=int(os.environ.get("N_INTERFACES", "4")),
    )
    host = os.environ.get("SNMP_HOST", "0.0.0.0")  # noqa: S104
    port = int(os.environ.get("SNMP_PORT", "1161"))

    server = EmulatorServer(config, port=port, host=host)
    server.start()
    n_oids = len(server._oid_tree)
    print(f"SNMP emulator  udp://{host}:{server.port}  user={config.username}")
    print(f"Slow prefix: {config.slow_prefixes}  delay={config.slow_delay}s")
    print(f"MIB tree: {n_oids} OIDs  ({config.n_interfaces} interfaces)")
    print()
    print("Listening... (Ctrl-C to stop)")
    print()

    try:
        signal.pause()
    except KeyboardInterrupt, SystemExit:
        pass
    finally:
        server.stop()
        print("Done.")


if __name__ == "__main__":
    main()
