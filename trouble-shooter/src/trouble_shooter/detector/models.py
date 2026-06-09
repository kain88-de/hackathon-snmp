from dataclasses import dataclass, field
from enum import StrEnum


class WalkReason(StrEnum):
    END_OF_MIB = "END_OF_MIB"
    TIMEOUT = "TIMEOUT"
    BUDGET_EXCEEDED = "BUDGET_EXCEEDED"


@dataclass
class Bucket:
    name: str
    max_ms: int | None  # None = catch-all; must be last in list


@dataclass
class Batch:
    oids: list[tuple[str, str]]  # (oid_string, value_string)
    elapsed_ms: float
    timed_out: bool


@dataclass
class Sample:
    oid: str
    value: str
    elapsed_ms: float
    responded: bool


@dataclass
class Region:
    prefix: str  # longest common OID prefix of all OIDs in this region
    bucket: str  # worst bucket name seen across all batches in this region
    batch_ms: float  # max batch elapsed_ms across batches in this region
    oid_count: int
    oids: list[str] = field(default_factory=list)  # internal; excluded from API response


@dataclass
class OidResult:
    oid: str
    value: str
    bucket: str
    ms: float
    phase: str  # "bulk" or "pinpoint"


@dataclass
class DetectorConfig:
    root_oid: str = "1.3.6.1.2.1"
    bulk_size: int = 10
    timeout: float = 5.0
    retries: int = 2
    total_timeout: float = 60.0
    pinpoint: bool = True


@dataclass
class DiagnosisReport:
    complete: bool
    stopped_at: str
    reason: WalkReason
    summary: dict[str, int]  # bucket name → count of OidResults
    regions: list[Region]
    oids: list[OidResult]
    elapsed_total_ms: float
