"""GitHub self-updater and SHA-256 / MD5 program integrity validator."""
from __future__ import annotations

import base64
import hashlib
import os
import py_compile
import re
import shutil
import subprocess
import sys
import time
import zlib
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from core.config import SuiteConfig
from core.security import verifyBrandAssets

INTEGRITY_MAGIC = "LMY_INTEGRITY_V1:"

ALLOWED_REMOTE_PATTERNS = (
    re.compile(r"^https://github\.com/khrizantema2x[08]/lumiya(?:\.git)?/?$", re.IGNORECASE),
    re.compile(r"^git@github\.com:khrizantema2x[08]/lumiya(?:\.git)?$", re.IGNORECASE),
    re.compile(r"^ssh://git@github\.com/khrizantema2x[08]/lumiya(?:\.git)?/?$", re.IGNORECASE),
)

CORE_SERVICES_FILES: Tuple[str, ...] = (
    "protect.py",
    "core/init.py",
    "core/cleaner.py",
    "core/config.py",
    "core/loader.py",
    "core/security.py",
    "core/telemetry.py",
    "core/updater.py",
    "core/ui.html",
    "core/requirements.txt",
)

CORE_FUNCTIONS_FILES: Tuple[str, ...] = (
    "stego/__init__.py",
    "stego/lsb.py",
    "stego/mark.py",
    "algos/anti_i2v/algo.py",
    "algos/anti_inpainting/algo.py",
    "algos/antiprompt/algo.py",
    "algos/antipure/algo.py",
    "algos/blurguard/algo.py",
    "algos/chronolock/algo.py",
    "algos/decontext/algo.py",
    "algos/decontext_cad/algo.py",
    "algos/diffusionguard/algo.py",
    "algos/diffvax/algo.py",
    "algos/fastprotect/algo.py",
    "algos/fastprotect_tcuap/algo.py",
    "algos/genptw/algo.py",
    "algos/genptw_tagwm/algo.py",
    "algos/idguardian/algo.py",
    "algos/idprotector/algo.py",
    "algos/impress/algo.py",
    "algos/metacloak/algo.py",
    "algos/mirage/algo.py",
    "algos/mist/algo.py",
    "algos/mistv2/algo.py",
    "algos/obliviate/algo.py",
    "algos/photoguard/algo.py",
    "algos/promptflare/algo.py",
    "algos/srim/algo.py",
    "algos/tag_wm/algo.py",
    "algos/tc_uap/algo.py",
    "algos/veto/algo.py",
    "algos/veto/vetoConfig.py",
    "algos/veto/vetoHook.py",
    "algos/veto/vetoTrajectory.py",
    "algos/vid_freeze/algo.py",
)

SCRIPT_PILLAR_FILES: Tuple[str, ...] = (
    "run.bat",
    "install.bat",
    "uninstall.bat",
    "run.sh",
)

_SAFE_REQ_RE = re.compile(r"^[A-Za-z0-9_.\-]+(?:\[[A-Za-z0-9_,.\-]+\])?(?:(?:==|>=|<=|~=|!=|>|<)[A-Za-z0-9_.*+\-]+)?$")


def isAllowedGitRemote(remoteUrl: str) -> bool:
    """Strictly validates that a Git remote URL points to the official repository over HTTPS or SSH."""
    clean = (remoteUrl or "").strip()
    if not clean or clean.startswith("-"):
        return False
    return any(pat.match(clean) for pat in ALLOWED_REMOTE_PATTERNS)


def filterSafeRequirements(reqText: str) -> List[str]:
    """Extracts safe PEP-508 package specifiers while excluding torch/torchvision and blocking pip flag injection."""
    safeSpecs: List[str] = []
    for rawLine in (reqText or "").splitlines():
        line = rawLine.split("#", 1)[0].strip()
        if not line or line.startswith("-"):
            continue
        if not _SAFE_REQ_RE.match(line):
            continue
        pkgName = re.split(r"[=<>!~\[]", line, maxsplit=1)[0].strip().lower()
        if pkgName in ("torch", "torchvision", "torchaudio"):
            continue
        safeSpecs.append(line)
    return safeSpecs


def _normalizedFileBytes(filePath: Path, isBinary: bool = False) -> bytes:
    raw = filePath.read_bytes()
    if isBinary:
        return raw
    return raw.replace(b"\r\n", b"\n")


def hashFileDigests(filePath: Path, isBinary: bool = False) -> Tuple[str, str]:
    """Returns uppercase (SHA-256, MD5) of a file (LF-normalized for text/code files for cross-OS consistency)."""
    data = _normalizedFileBytes(filePath, isBinary=isBinary)
    return hashlib.sha256(data).hexdigest().upper(), hashlib.md5(data).hexdigest().upper()


def _computeLumpSum(entries: List[Tuple[str, str, str]]) -> Dict[str, str]:
    """Computes a deterministic combined SHA-256 and MD5 lump-sum over (relPath, sha256, md5) tuples."""
    manifestBytes = "".join(f"{rel}:{s256}:{md5}\n" for rel, s256, md5 in entries).encode("utf-8")
    return {
        "sha256": hashlib.sha256(manifestBytes).hexdigest().upper(),
        "md5": hashlib.md5(manifestBytes).hexdigest().upper(),
    }


def _parseIntegrityText(rawText: str) -> Tuple[str, Dict[str, Tuple[str, str]]]:
    """Decodes a `LMY_INTEGRITY_V1:<version>:<b85>` string into `(version, expectedMap)`."""
    expected: Dict[str, Tuple[str, str]] = {}
    manifestVer = ""
    text = (rawText or "").strip()
    if not text.startswith(INTEGRITY_MAGIC):
        return manifestVer, expected
    try:
        rest = text[len(INTEGRITY_MAGIC):].strip()
        if ":" in rest:
            manifestVer, b85Str = rest.split(":", 1)
        else:
            b85Str = rest
        decodedText = zlib.decompress(base64.b85decode(b85Str.strip().encode("ascii"))).decode("utf-8")
        for line in decodedText.splitlines():
            line = line.strip()
            if line.startswith("@version:"):
                manifestVer = line.split(":", 1)[1].strip()
                continue
            parts = line.split(":")
            if len(parts) == 3 and len(parts[1]) == 64 and len(parts[2]) == 32:
                expected[parts[0].strip()] = (parts[1].upper(), parts[2].upper())
    except Exception:
        pass
    return manifestVer, expected


def _loadIntegrityHashes(manifestPath: Optional[Path]) -> Tuple[str, Dict[str, Tuple[str, str]]]:
    """Decodes Lumiya's encoded integrity manifest (`core/integrity.lmy`)."""
    if not manifestPath or not manifestPath.is_file():
        return "", {}
    try:
        return _parseIntegrityText(manifestPath.read_text(encoding="utf-8", errors="replace"))
    except Exception:
        return "", {}


def writeIntegrityFile(rootDir: Path, versionStr: str = "v0.6.073.8820") -> Path:
    """Generates and writes `core/integrity.lmy` with embedded version and file checksums."""
    cleanVer = (versionStr or "v0.6.073.8820").split()[0].strip()
    serviceEntries = [(rel, *hashFileDigests(rootDir / rel)) for rel in CORE_SERVICES_FILES if (rootDir / rel).is_file()]
    funcEntries = [(rel, *hashFileDigests(rootDir / rel)) for rel in CORE_FUNCTIONS_FILES if (rootDir / rel).is_file()]
    scriptEntries = [(rel, *hashFileDigests(rootDir / rel)) for rel in SCRIPT_PILLAR_FILES if (rootDir / rel).is_file()]
    serviceSum = _computeLumpSum(serviceEntries)
    funcSum = _computeLumpSum(funcEntries)
    scriptSum = _computeLumpSum(scriptEntries)
    lines = [
        f"@version:{cleanVer}",
        f"core-services:{serviceSum['sha256']}:{serviceSum['md5']}",
        f"core-functions:{funcSum['sha256']}:{funcSum['md5']}",
        f"executables:{scriptSum['sha256']}:{scriptSum['md5']}",
    ]
    for rel, s256, md5 in serviceEntries + funcEntries + scriptEntries:
        lines.append(f"{rel}:{s256}:{md5}")
    payloadBytes = "\n".join(lines).encode("utf-8")
    b85 = base64.b85encode(zlib.compress(payloadBytes, level=9)).decode("ascii")
    encoded = f"{INTEGRITY_MAGIC}{cleanVer}:{b85}"
    outPath = rootDir / "core" / "integrity.lmy"
    outPath.write_text(encoded + "\n", encoding="utf-8")
    return outPath


def resolveReleaseNoteFile(rootDir: Path, versionStr: str = "") -> Optional[Path]:
    lmyFile = rootDir / "core" / "integrity.lmy"
    if lmyFile.is_file():
        return lmyFile
    return None


def computeProgramIntegrity(rootDir: Path, versionStr: str = "v0.6.073.8820") -> Dict[str, Any]:
    """Computes per-file and group SHA-256 & MD5 hashes and validates them against `core/integrity.lmy`."""
    cleanVer = (versionStr or "v0.6.073.8820").split()[0].strip()
    releaseFile = resolveReleaseNoteFile(rootDir, cleanVer)
    manifestVer, expectedMap = _loadIntegrityHashes(releaseFile)

    serviceEntries: List[Tuple[str, str, str]] = []
    funcEntries: List[Tuple[str, str, str]] = []
    scriptEntries: List[Tuple[str, str, str]] = []
    fileReports: List[Dict[str, Any]] = []
    mismatches: List[str] = []

    def processGroup(relList: Tuple[str, ...], pillarName: str, isBinary: bool, targetList: List[Tuple[str, str, str]]) -> None:
        for rel in relList:
            p = rootDir / rel
            if not p.is_file():
                fileReports.append(
                    {
                        "path": rel,
                        "pillar": pillarName,
                        "exists": False,
                        "sha256": "MISSING",
                        "md5": "MISSING",
                        "status": "MISSING",
                    }
                )
                mismatches.append(rel)
                continue
            s256, md5 = hashFileDigests(p, isBinary=isBinary)
            targetList.append((rel, s256, md5))
            exp = expectedMap.get(rel)
            if exp is not None:
                matched = (s256 == exp[0]) and (md5 == exp[1])
                status = "VERIFIED" if matched else "MODIFIED"
                if not matched:
                    mismatches.append(rel)
            else:
                status = "VERIFIED"
            fileReports.append(
                {
                    "path": rel,
                    "pillar": pillarName,
                    "exists": True,
                    "sha256": s256,
                    "md5": md5,
                    "status": status,
                }
            )

    processGroup(CORE_SERVICES_FILES, "core-services", False, serviceEntries)
    processGroup(CORE_FUNCTIONS_FILES, "core-functions", False, funcEntries)
    processGroup(SCRIPT_PILLAR_FILES, "executables", False, scriptEntries)

    serviceLump = _computeLumpSum(serviceEntries)
    funcLump = _computeLumpSum(funcEntries)
    scriptsLump = _computeLumpSum(scriptEntries)

    lumpSums = {
        "master": {
            "key": "core-services",
            "count": len(CORE_SERVICES_FILES),
            **serviceLump,
            "status": "VERIFIED",
        },
        "core": {
            "key": "core-functions",
            "count": len(CORE_FUNCTIONS_FILES),
            **funcLump,
            "status": "VERIFIED",
        },
        "scripts": {
            "key": "executables",
            "count": len(SCRIPT_PILLAR_FILES),
            **scriptsLump,
            "status": "VERIFIED",
        },
    }
    for label, key in (
        ("core-services", "master"),
        ("core-functions", "core"),
        ("executables", "scripts"),
    ):
        exp = expectedMap.get(label)
        if exp is not None:
            okLump = lumpSums[key]["sha256"] == exp[0] and lumpSums[key]["md5"] == exp[1]
            lumpSums[key]["status"] = "VERIFIED" if okLump else "MODIFIED"
            if not okLump and label not in mismatches:
                mismatches.append(label)

    if manifestVer and manifestVer != cleanVer:
        mismatches.append(f"version({manifestVer}!={cleanVer})")

    return {
        "ok": len(mismatches) == 0,
        "manifestLinked": bool(expectedMap),
        "manifestVersion": manifestVer or cleanVer,
        "releaseNoteFile": str(releaseFile.relative_to(rootDir)).replace("\\", "/") if releaseFile else "None",
        "lumpSums": lumpSums,
        "files": fileReports,
        "mismatches": mismatches,
        "checkedAt": time.strftime("%Y-%m-%d %H:%M:%S"),
    }


def _runGit(rootDir: Path, args: List[str], timeout: float = 15.0) -> subprocess.CompletedProcess:
    gitBin = shutil.which("git") or (
        r"C:\Program Files\Git\cmd\git.exe" if Path(r"C:\Program Files\Git\cmd\git.exe").exists() else "git"
    )
    env = dict(os.environ)
    env["GIT_TERMINAL_PROMPT"] = "0"
    env["LC_ALL"] = "C"
    startupInfo = None
    if sys.platform == "win32":
        startupInfo = subprocess.STARTUPINFO()
        startupInfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
    cmd = [
        gitBin,
        "-c",
        "protocol.file.allow=never",
        "-c",
        "core.hooksPath=/dev/null",
        *args,
    ]
    return subprocess.run(
        cmd,
        cwd=str(rootDir),
        env=env,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=timeout,
        startupinfo=startupInfo,
    )


def _parseVersionTuple(verStr: str) -> Tuple[int, ...]:
    nums = [int(x) for x in re.findall(r"\d+", (verStr or "").split()[0])]
    return tuple(nums) if nums else (0,)


def _extractRemoteVersion(rootDir: Path) -> str:
    """Extracts the version string from `origin/main:core/integrity.lmy` or `origin/main:protect.py`."""
    lmyShow = _runGit(rootDir, ["show", "origin/main:core/integrity.lmy"], timeout=5.0)
    if lmyShow.returncode == 0 and lmyShow.stdout.strip():
        rVer, _ = _parseIntegrityText(lmyShow.stdout.strip())
        if rVer:
            return rVer
    pyShow = _runGit(rootDir, ["show", "origin/main:protect.py"], timeout=5.0)
    if pyShow.returncode == 0 and pyShow.stdout:
        m = re.search(r'APP_VERSION\s*=\s*["\']([^"\']+)["\']', pyShow.stdout)
        if m:
            return m.group(1).split()[0].strip()
    return ""


def checkRemoteUpdate(rootDir: Path, versionStr: str = "v0.6.073.8820", fetchRemote: bool = True) -> Dict[str, Any]:
    """Inspects local Git state, verifies remote origin against allowlist, and checks for incoming commits on origin/main."""
    localVersion = (versionStr or "v0.6.073.8820").split()[0].strip()
    integrity = computeProgramIntegrity(rootDir, versionStr)
    if not (rootDir / ".git").exists():
        return {
            "ok": False,
            "error": "This directory is not a Git repository (.git missing).",
            "integrity": integrity,
        }
    try:
        remRes = _runGit(rootDir, ["remote", "get-url", "origin"], timeout=5.0)
        remoteUrl = remRes.stdout.strip() if remRes.returncode == 0 else ""
        remoteTrusted = isAllowedGitRemote(remoteUrl)
        brRes = _runGit(rootDir, ["rev-parse", "--abbrev-ref", "HEAD"], timeout=5.0)
        branch = brRes.stdout.strip() if brRes.returncode == 0 else "unknown"
        locRes = _runGit(rootDir, ["rev-parse", "--short=10", "HEAD"], timeout=5.0)
        localSha = locRes.stdout.strip() if locRes.returncode == 0 else "unknown"

        if not remoteTrusted:
            return {
                "ok": False,
                "branch": branch,
                "localSha": localSha,
                "remoteUrl": remoteUrl,
                "remoteTrusted": False,
                "error": f"Blocked untrusted Git remote origin: '{remoteUrl}'.",
                "integrity": integrity,
            }

        fetchErr = ""
        if fetchRemote:
            fRes = _runGit(rootDir, ["fetch", "--quiet", "--prune", "origin", "main"], timeout=15.0)
            if fRes.returncode != 0:
                fetchErr = (fRes.stderr or fRes.stdout or "Failed to reach GitHub.").strip()

        remShaRes = _runGit(rootDir, ["rev-parse", "--short=10", "origin/main"], timeout=5.0)
        remoteSha = remShaRes.stdout.strip() if remShaRes.returncode == 0 else localSha

        cntRes = _runGit(rootDir, ["rev-list", "--count", "HEAD..origin/main"], timeout=5.0)
        behindCount = int(cntRes.stdout.strip()) if (cntRes.returncode == 0 and cntRes.stdout.strip().isdigit()) else 0

        aheadRes = _runGit(rootDir, ["rev-list", "--count", "origin/main..HEAD"], timeout=5.0)
        aheadCount = int(aheadRes.stdout.strip()) if (aheadRes.returncode == 0 and aheadRes.stdout.strip().isdigit()) else 0

        remoteVersion = _extractRemoteVersion(rootDir) or localVersion
        versionAhead = _parseVersionTuple(localVersion) > _parseVersionTuple(remoteVersion)
        versionBehind = _parseVersionTuple(localVersion) < _parseVersionTuple(remoteVersion)
        aheadOfRemote = (aheadCount > 0 or versionAhead) and behindCount == 0 and not versionBehind

        commits: List[str] = []
        if behindCount > 0:
            logRes = _runGit(rootDir, ["log", "HEAD..origin/main", "--oneline", "-n", "10"], timeout=5.0)
            if logRes.returncode == 0:
                commits = [ln.strip() for ln in logRes.stdout.splitlines() if ln.strip()]

        return {
            "ok": not bool(fetchErr),
            "error": fetchErr,
            "branch": branch,
            "remoteUrl": remoteUrl,
            "remoteTrusted": True,
            "localSha": localSha,
            "remoteSha": remoteSha,
            "localVersion": localVersion,
            "remoteVersion": remoteVersion,
            "versionAhead": versionAhead,
            "behindCount": behindCount,
            "aheadCount": aheadCount,
            "updateAvailable": behindCount > 0 or versionBehind,
            "aheadOfRemote": aheadOfRemote,
            "upToDate": behindCount == 0 and not versionBehind,
            "commits": commits,
            "integrity": integrity,
        }
    except Exception as exc:
        return {
            "ok": False,
            "error": str(exc),
            "integrity": integrity,
        }


def runProtectedUpdate(rootDir: Path, pyExe: str = sys.executable, versionStr: str = "v0.6.073.8820") -> Dict[str, Any]:
    """Executes a protected fast-forward GitHub update with pre-flight remote verification, auto-stash, syntax & asset validation, and rollback on failure."""
    status = checkRemoteUpdate(rootDir, versionStr=versionStr, fetchRemote=True)
    if not status.get("remoteTrusted"):
        return {
            "ok": False,
            "updated": False,
            "error": status.get("error") or "Untrusted Git remote origin.",
            "status": status,
            "integrity": status.get("integrity"),
        }
    if not status.get("ok"):
        return {
            "ok": False,
            "updated": False,
            "error": status.get("error") or "Could not fetch updates from GitHub.",
            "status": status,
            "integrity": status.get("integrity"),
        }

    fullShaRes = _runGit(rootDir, ["rev-parse", "HEAD"], timeout=5.0)
    if fullShaRes.returncode != 0 or not fullShaRes.stdout.strip():
        return {
            "ok": False,
            "updated": False,
            "error": "Could not determine current HEAD commit SHA.",
            "integrity": status.get("integrity"),
        }
    preSha = fullShaRes.stdout.strip()

    reqPath = rootDir / "core" / "requirements.txt"
    preReqSha = hashFileDigests(reqPath)[0] if reqPath.is_file() else ""

    # Check if already up-to-date or ahead of GitHub
    if status.get("behindCount", 0) == 0:
        SuiteConfig.load(rootDir / "user" / "config.json")
        aheadCount = status.get("aheadCount", 0)
        locVer = status.get("localVersion", "")
        remVer = status.get("remoteVersion", "")
        if status.get("versionAhead") and locVer and remVer and locVer != remVer:
            msg = f"Local build ({locVer}) is ahead of GitHub ({remVer} / {status.get('remoteSha')})."
        elif aheadCount > 0:
            msg = f"Local build ({status.get('localSha')}) is {aheadCount} commit(s) ahead of GitHub ({status.get('remoteSha')})."
        else:
            msg = f"Up to date ({locVer or status.get('localSha')})."
        return {
            "ok": True,
            "updated": False,
            "aheadOfRemote": bool(status.get("aheadOfRemote")),
            "aheadCount": aheadCount,
            "message": msg,
            "msg": msg,
            "status": status,
            "integrity": status.get("integrity"),
        }

    stashed = False
    dirtyRes = _runGit(rootDir, ["status", "--porcelain", "--untracked-files=no"], timeout=5.0)
    if dirtyRes.returncode == 0 and dirtyRes.stdout.strip():
        stashRes = _runGit(rootDir, ["stash", "push", "-m", f"lumiya-auto-backup-{int(time.time())}"], timeout=10.0)
        stashed = stashRes.returncode == 0

    def rollback(reason: str) -> Dict[str, Any]:
        _runGit(rootDir, ["reset", "--hard", preSha], timeout=10.0)
        if stashed:
            _runGit(rootDir, ["stash", "pop"], timeout=10.0)
        return {
            "ok": False,
            "updated": False,
            "rolledBack": True,
            "error": f"Update aborted and rolled back to {preSha[:10]}: {reason}",
        }

    mergeRes = _runGit(rootDir, ["merge", "--ff-only", "origin/main"], timeout=20.0)
    if mergeRes.returncode != 0:
        return rollback(mergeRes.stderr.strip() or mergeRes.stdout.strip() or "Fast-forward merge failed.")

    # Post-update gate 1: syntax check on protect.py and core/*.py
    try:
        py_compile.compile(str(rootDir / "protect.py"), doraise=True)
        for pyFile in (rootDir / "core").glob("*.py"):
            py_compile.compile(str(pyFile), doraise=True)
    except Exception as exc:
        return rollback(f"Post-update syntax verification failed ({exc}).")

    # Post-update gate 2: UI and brand asset check
    uiPath = (rootDir / "core" / "ui.html") if (rootDir / "core" / "ui.html").is_file() else (rootDir / "ui.html")
    if not uiPath.is_file():
        return rollback("Post-update check failed: core/ui.html is missing.")
    brandRep = verifyBrandAssets(rootDir)
    if not brandRep.get("ok", True):
        return rollback("Brand asset SHA-256 verification failed.")

    # Sync non-Torch requirements if core/requirements.txt changed
    depsSynced: List[str] = []
    postReqSha = hashFileDigests(reqPath)[0] if reqPath.is_file() else ""
    if postReqSha and postReqSha != preReqSha:
        safeSpecs = filterSafeRequirements(reqPath.read_text(encoding="utf-8", errors="replace"))
        if safeSpecs:
            pipRes = subprocess.run(
                [pyExe, "-m", "pip", "install", "--upgrade", "--no-cache-dir", *safeSpecs],
                cwd=str(rootDir),
                capture_output=True,
                text=True,
                timeout=180.0,
            )
            if pipRes.returncode == 0:
                depsSynced = safeSpecs

    # Migrate and repopulate user/config.json without replacing existing user preferences
    SuiteConfig.load(rootDir / "user" / "config.json")

    postStatus = checkRemoteUpdate(rootDir, versionStr=versionStr, fetchRemote=False)
    doneMsg = f"Updated from {preSha[:10]} to {postStatus.get('localSha', '')}."
    return {
        "ok": True,
        "updated": True,
        "fromSha": preSha[:10],
        "toSha": postStatus.get("localSha", ""),
        "stashedLocalEdits": stashed,
        "depsSynced": depsSynced,
        "message": doneMsg,
        "msg": doneMsg,
        "status": postStatus,
        "integrity": postStatus.get("integrity"),
    }
