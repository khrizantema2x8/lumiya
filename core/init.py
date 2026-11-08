"""PEP 420 namespace entry point for PORTtralica Lumiya core modules (no __init__.py)."""
from __future__ import annotations

from core.cleaner import cleanMemoryAndStorage
from core.config import (
    DEFAULT_ALGO_IDS,
    MAX_STEPS,
    VALID_EXTS,
    SuiteConfig,
    atomicWrite,
    safeFloat,
    safeInt,
)
from core.loader import LEGACY_SKIP_DIRS, AlgoPluginManager, hardwareBlockReason
from core.security import (
    WINDOWS_RESERVED_NAMES,
    isLoopbackClient,
    isTrustedRequest,
    openPathForeground,
    parseJsonBody,
    sanitizeFilename,
    verifyBrandAssets,
)
from core.telemetry import SensorSnapshot, TelemetryMonitor, resolveHardwareTier
from core.updater import (
    checkRemoteUpdate,
    computeProgramIntegrity,
    filterSafeRequirements,
    isAllowedGitRemote,
    runProtectedUpdate,
)

__all__ = [
    "DEFAULT_ALGO_IDS",
    "LEGACY_SKIP_DIRS",
    "MAX_STEPS",
    "VALID_EXTS",
    "WINDOWS_RESERVED_NAMES",
    "AlgoPluginManager",
    "SensorSnapshot",
    "SuiteConfig",
    "TelemetryMonitor",
    "atomicWrite",
    "checkRemoteUpdate",
    "cleanMemoryAndStorage",
    "computeProgramIntegrity",
    "filterSafeRequirements",
    "hardwareBlockReason",
    "isAllowedGitRemote",
    "isLoopbackClient",
    "isTrustedRequest",
    "openPathForeground",
    "parseJsonBody",
    "resolveHardwareTier",
    "runProtectedUpdate",
    "safeFloat",
    "safeInt",
    "sanitizeFilename",
    "verifyBrandAssets",
]

