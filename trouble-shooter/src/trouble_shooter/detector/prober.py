from __future__ import annotations

from time import monotonic
from typing import TYPE_CHECKING

from pysnmp.hlapi.v3arch.asyncio import (
    CommunityData,
    ContextData,
    ObjectIdentity,
    ObjectType,
    SnmpEngine,
    UdpTransportTarget,
    bulk_cmd,
    get_cmd,
)
from pysnmp.proto.errind import EmptyResponse
from pysnmp.proto.rfc1905 import EndOfMibView

from .models import Batch, Sample

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator


class SnmpProber:
    def __init__(
        self,
        host: str,
        community: str,
        port: int,
        timeout: float = 5.0,
        retries: int = 2,
    ) -> None:
        self._host = host
        self._community = community
        self._port = port
        self._timeout = timeout
        self._retries = retries

    async def bulk_walk(self, root_oid: str, bulk_size: int) -> AsyncGenerator[Batch]:
        engine = SnmpEngine()
        transport = await UdpTransportTarget.create(
            (self._host, self._port),
            timeout=self._timeout,
            retries=self._retries,
        )
        try:
            cursor = root_oid
            while True:
                t0 = monotonic()
                error_indication, _status, _index, var_binds = await bulk_cmd(
                    engine,
                    CommunityData(self._community),
                    transport,
                    ContextData(),
                    0,  # nonRepeaters
                    bulk_size,  # maxRepetitions
                    ObjectType(ObjectIdentity(cursor)),
                    lookupMib=False,
                )
                elapsed_ms = (monotonic() - t0) * 1000

                if error_indication:
                    # EmptyResponse means the emulator/device has no more OIDs — end of walk
                    if isinstance(error_indication, EmptyResponse):
                        return
                    yield Batch(oids=[(cursor, "")], elapsed_ms=elapsed_ms, timed_out=True)
                    return

                if not var_binds:
                    return

                end_of_mib = any(isinstance(vb[1], EndOfMibView) for vb in var_binds)
                real_vbs = [vb for vb in var_binds if not isinstance(vb[1], EndOfMibView)]

                if not real_vbs:
                    return

                oids = [(str(vb[0]), str(vb[1])) for vb in real_vbs]

                yield Batch(oids=oids, elapsed_ms=elapsed_ms, timed_out=False)

                if end_of_mib:
                    return

                cursor = str(real_vbs[-1][0])
        finally:
            engine.close_dispatcher()

    async def probe_oid(self, oid: str) -> Sample:
        engine = SnmpEngine()
        transport = await UdpTransportTarget.create(
            (self._host, self._port),
            timeout=self._timeout,
            retries=self._retries,
        )
        try:
            t0 = monotonic()
            error_indication, _status, _index, var_binds = await get_cmd(
                engine,
                CommunityData(self._community),
                transport,
                ContextData(),
                ObjectType(ObjectIdentity(oid)),
                lookupMib=False,
            )
            elapsed_ms = (monotonic() - t0) * 1000

            if error_indication or not var_binds:
                return Sample(oid=oid, value="", elapsed_ms=elapsed_ms, responded=False)

            return Sample(
                oid=oid,
                value=str(var_binds[0][1]),
                elapsed_ms=elapsed_ms,
                responded=True,
            )
        finally:
            engine.close_dispatcher()
