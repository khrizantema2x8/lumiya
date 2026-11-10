"""PEP 420 namespace entry point for PORTtralica Lumiya core modules (no __init__.py)."""
from __future__ import annotations

from core.cleaner import cleanMemoryAndStorage
from core.config import (
    APP_VERSION,
    BOUNDS,
    CHOICES,
    DEFAULT_ALGO_IDS,
    MAX_STEPS,
    THEME_ID_RE,
    VALID_EXTS,
    SuiteConfig,
    atomicWrite,
    clampSetting,
    safeFloat,
    safeInt,
)
from core.loader import AlgoPluginManager, hardwareBlockReason
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
    "APP_VERSION",
    "BOUNDS",
    "CHOICES",
    "DEFAULT_ALGO_IDS",
    "MAX_STEPS",
    "THEME_ID_RE",
    "VALID_EXTS",
    "WINDOWS_RESERVED_NAMES",
    "AlgoPluginManager",
    "SensorSnapshot",
    "SuiteConfig",
    "TelemetryMonitor",
    "atomicWrite",
    "clampSetting",
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

