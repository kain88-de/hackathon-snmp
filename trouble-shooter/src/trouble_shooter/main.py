import asyncio
import ipaddress
import re
import subprocess
import time

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from pysnmp.hlapi.v3arch.asyncio import (
    CommunityData,
    ContextData,
    ObjectIdentity,
    ObjectType,
    SnmpEngine,
    UdpTransportTarget,
    get_cmd,
    walk_cmd,
)

from trouble_shooter.detector import SnmpProber, diagnose
from trouble_shooter.detector.models import Bucket, DetectorConfig

app = FastAPI()

app.mount("/static", StaticFiles(directory="static"), name="static")


@app.get("/")
def index() -> FileResponse:
    return FileResponse("static/index.html")


class CheckRequest(BaseModel):
    host: str
    community: str = "public"
    port: int = 1161
    timeout: float = 2.0
    retries: int = 1


class WalkRequest(BaseModel):
    host: str
    community: str = "public"
    port: int = 1161
    root_oid: str = "1.3.6.1.2.1"
    timeout: int = 5
    total_timeout: int = 30


class BucketSpec(BaseModel):
    name: str
    max_ms: int | None = None


class DiagnoseRequest(BaseModel):
    host: str
    community: str = "public"
    port: int = 1161
    root_oid: str = "1.3.6.1.2.1"
    bulk_size: int = 10
    timeout: float = 5.0
    retries: int = 2
    total_timeout: float = 60.0
    pinpoint: bool = True
    buckets: list[BucketSpec] = Field(
        default_factory=lambda: [
            BucketSpec(name="OK", max_ms=500),
            BucketSpec(name="SLOW", max_ms=3000),
            BucketSpec(name="CRITICAL", max_ms=None),
        ]
    )


@app.post("/api/walk")
async def walk_device(req: WalkRequest) -> dict[str, list[dict[str, str | int]]]:
    if not _valid_host(req.host):
        raise HTTPException(status_code=400, detail="Invalid host")
    oids = await _snmp_walk(
        req.host, req.community, req.port, req.root_oid, req.timeout, req.total_timeout
    )
    return {"oids": oids}


@app.post("/api/diagnose")
async def diagnose_device(req: DiagnoseRequest) -> dict[str, object]:
    if not _valid_host(req.host):
        raise HTTPException(status_code=400, detail="Invalid host")
    prober = SnmpProber(req.host, req.community, req.port, req.timeout, req.retries)
    buckets = [Bucket(name=b.name, max_ms=b.max_ms) for b in req.buckets]
    config = DetectorConfig(
        root_oid=req.root_oid,
        bulk_size=req.bulk_size,
        timeout=req.timeout,
        retries=req.retries,
        total_timeout=req.total_timeout,
        pinpoint=req.pinpoint,
    )
    report = await diagnose(prober, buckets=buckets, config=config)
    return {
        "complete": report.complete,
        "stopped_at": report.stopped_at,
        "reason": report.reason.value,
        "summary": report.summary,
        "regions": [
            {
                "prefix": r.prefix,
                "bucket": r.bucket,
                "batch_ms": r.batch_ms,
                "oid_count": r.oid_count,
            }
            for r in report.regions
        ],
        "oids": [
            {"oid": o.oid, "value": o.value, "bucket": o.bucket, "ms": o.ms, "phase": o.phase}
            for o in report.oids
        ],
        "elapsed_total_ms": report.elapsed_total_ms,
    }


@app.post("/api/check")
async def check_device(req: CheckRequest) -> dict[str, object]:
    if not _valid_host(req.host):
        raise HTTPException(status_code=400, detail="Invalid host")
    ping_ok = _ping(req.host)
    snmp = await _snmp_get(req.host, req.community, req.port, req.timeout, req.retries)
    return {"host": req.host, "ping": ping_ok, "snmp": snmp}


def _valid_host(h: str) -> bool:
    try:
        ipaddress.ip_address(h)
        return True
    except ValueError:
        return bool(re.fullmatch(r"[A-Za-z0-9.-]{1,253}", h)) and not h.startswith("-")


def _ping(host: str) -> bool:
    if not _valid_host(host):
        return False
    result = subprocess.run(
        ["/usr/bin/ping", "-c", "1", "-W", "2", "--", host],
        capture_output=True,
        check=False,
    )
    return result.returncode == 0


async def _snmp_get(
    host: str, community: str, port: int, timeout: float = 2.0, retries: int = 1
) -> dict[str, object]:
    engine = SnmpEngine()
    try:
        error_indication, error_status, error_index, var_binds = await get_cmd(
            engine,
            CommunityData(community),
            await UdpTransportTarget.create((host, port), timeout=timeout, retries=retries),
            ContextData(),
            ObjectType(ObjectIdentity("SNMPv2-MIB", "sysDescr", 0)),
        )
    finally:
        engine.close_dispatcher()

    if error_indication:
        return {"reachable": False, "error": str(error_indication)}
    if error_status:
        return {
            "reachable": False,
            "error": f"{error_status} at index {error_index}",
        }

    sys_descr = str(var_binds[0][1])
    return {"reachable": True, "sysDescr": sys_descr}


async def _snmp_walk(
    host: str,
    community: str,
    port: int,
    root_oid: str,
    timeout: int = 5,
    total_timeout: int = 30,
) -> list[dict[str, str | int]]:
    engine = SnmpEngine()
    results = []
    try:
        async with asyncio.timeout(total_timeout):
            t = time.monotonic()
            async for error_indication, error_status, _, var_binds in walk_cmd(
                engine,
                CommunityData(community),
                await UdpTransportTarget.create((host, port), timeout=timeout, retries=1),
                ContextData(),
                ObjectType(ObjectIdentity(root_oid)),
            ):
                elapsed_ms = round((time.monotonic() - t) * 1000)
                t = time.monotonic()
                if error_indication:
                    break
                if error_status and int(error_status):
                    break
                results.extend(
                    {"oid": str(var_bind[0]), "value": str(var_bind[1]), "ms": elapsed_ms}
                    for var_bind in var_binds
                )
    except TimeoutError:
        pass
    finally:
        engine.close_dispatcher()
    return results


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("trouble_shooter.main:app", host="0.0.0.0", port=8080, reload=True)
