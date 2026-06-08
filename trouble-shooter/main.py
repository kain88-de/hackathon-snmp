import ipaddress
import re
import subprocess
import time

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from pysnmp.hlapi.v3arch.asyncio import (
    get_cmd,
    walk_cmd,
    SnmpEngine,
    CommunityData,
    UdpTransportTarget,
    ContextData,
    ObjectType,
    ObjectIdentity,
)

app = FastAPI()

app.mount("/static", StaticFiles(directory="static"), name="static")


@app.get("/")
def index():
    return FileResponse("static/index.html")


class CheckRequest(BaseModel):
    host: str
    community: str = "public"
    port: int = 1161


class WalkRequest(BaseModel):
    host: str
    community: str = "public"
    port: int = 1161
    root_oid: str = "1.3.6.1.2.1"


@app.post("/api/walk")
async def walk_device(req: WalkRequest):
    if not _valid_host(req.host):
        raise HTTPException(status_code=400, detail="Invalid host")
    oids = await _snmp_walk(req.host, req.community, req.port, req.root_oid)
    return {"oids": oids}


@app.post("/api/check")
async def check_device(req: CheckRequest):
    if not _valid_host(req.host):
        raise HTTPException(status_code=400, detail="Invalid host")
    ping_ok = _ping(req.host)
    snmp = await _snmp_get(req.host, req.community, req.port)
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
        ["ping", "-c", "1", "-W", "2", "--", host],
        capture_output=True,
    )
    return result.returncode == 0


async def _snmp_get(host: str, community: str, port: int) -> dict:
    engine = SnmpEngine()
    try:
        error_indication, error_status, error_index, var_binds = await get_cmd(
            engine,
            CommunityData(community),
            await UdpTransportTarget.create((host, port), timeout=2, retries=1),
            ContextData(),
            ObjectType(ObjectIdentity("SNMPv2-MIB", "sysDescr", 0)),
        )
    finally:
        engine.close_dispatcher()

    if error_indication:
        return {"reachable": False, "error": str(error_indication)}
    if error_status:
        return {"reachable": False, "error": f"{error_status.prettyPrint()} at index {error_index}"}

    sys_descr = str(var_binds[0][1])
    return {"reachable": True, "sysDescr": sys_descr}


async def _snmp_walk(host: str, community: str, port: int, root_oid: str) -> list:
    engine = SnmpEngine()
    results = []
    try:
        t = time.monotonic()
        async for error_indication, error_status, _, var_binds in walk_cmd(
            engine,
            CommunityData(community),
            await UdpTransportTarget.create((host, port), timeout=2, retries=1),
            ContextData(),
            ObjectType(ObjectIdentity(root_oid)),
        ):
            elapsed_ms = round((time.monotonic() - t) * 1000)
            t = time.monotonic()
            if error_indication:
                break
            if error_status and int(error_status):
                break
            for var_bind in var_binds:
                results.append({
                    "oid": str(var_bind[0]),
                    "value": str(var_bind[1]),
                    "ms": elapsed_ms,
                })
    finally:
        engine.close_dispatcher()
    return results


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8080, reload=True)
