"""HTTP layer: static files, the live update stream and the JSON API routes. The engine lives in protect.py."""
from __future__ import annotations

import io
import json
import os
import re
import shutil
import socket
import subprocess
import sys
import threading
import time
import urllib.parse
import webbrowser
from dataclasses import dataclass, field
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from core.cleaner import cleanMemoryAndStorage
from core.fonts import FONT_MIME, scanAppFonts, scanSystemFonts
from core.config import APP_NAME, APP_VERSION, BOUNDS, CHOICES, THEME_ID_RE, SuiteConfig, clampSetting, safeFloat, safeInt
from core.loader import AlgoPluginManager
from core.queue import QueueManager, RuntimeState, validateBatchConfig
from core.security import isLoopbackClient, isTrustedRequest, openPathForeground, parseJsonBody, verifyBrandAssets
from core.telemetry import TelemetryMonitor
from core.termlog import TermLog
from core.updater import checkRemoteUpdate, computeProgramIntegrity, runProtectedUpdate
from stego.mark import MarkError, inspectStego, prepareMark

try:
    import psutil
except ImportError:
    psutil = None  # type: ignore

try:
    from PIL import Image
except ImportError:
    Image = None  # type: ignore


@dataclass
class ServerApp:
    """Everything a request handler needs; built once by protect.runServer."""

    cfg: SuiteConfig
    configFile: Path
    deps: Dict[str, Any]
    algoMgr: AlgoPluginManager
    mon: TelemetryMonitor
    qMgr: QueueManager
    engine: Any
    rt: RuntimeState
    rootDir: Path
    resultsRoot: Path
    algosDir: Path
    identityDir: Path
    themesDir: Path
    uiFile: Path
    manifestFile: Path
    brandStatus: Dict[str, Any]
    allowRemote: bool
    authToken: str
    port: int
    executeBatch: Callable[[str], None] = lambda batchId: None
    sseLock: threading.Lock = field(default_factory=threading.Lock)
    sseCount: int = 0


_COLOR_VALUE_REGEX = re.compile(
    r"^#(?:[0-9a-fA-F]{3,4}|[0-9a-fA-F]{6}|[0-9a-fA-F]{8})$|^rgba?\(\s*\d+\s*,\s*\d+\s*,\s*\d+\s*(?:,\s*[\d.]+\s*)?\)$"
)
_ALLOWED_THEME_KEYS = {
    "--bg", "--header-bg", "--brand-bg", "--panel", "--panelAlt", "--panelHover",
    "--panelDark", "--line", "--lineStrong", "--telemetry-bg", "--telemetry-graph-bg",
    "--history-row-bg", "--drop-bg", "--drop-hover-bg", "--dots-bg", "--split-drop-bg",
    "--input-bg", "--tab-bg", "--tab-hover-bg", "--scrollbar-track", "--scrollbar-thumb",
    "--scrollbar-thumb-hover", "--theme-active-border", "--right-divider",
    "--fg", "--muted", "--dim", "--gold", "--blue", "--blueHover", "--green",
    "--yellow", "--red", "--cyan",
    "--inspect-grid",
}


def loadThemesFromDisk(themesDir: Path) -> List[Dict[str, Any]]:
    """Dynamically loads and validates .ltheme lookup tables from identity/theme."""
    if not themesDir.exists():
        return []
    themes: List[Dict[str, Any]] = []
    priority = ["carbon", "blue_steel", "tropical", "freshen", "blue_steel_amere", "tropical_amere", "freshen_amere"]

    for themeFile in themesDir.glob("*.ltheme"):
        try:
            resolved = themeFile.resolve()
            if themesDir not in resolved.parents:
                continue
            themeId = themeFile.stem
            if not THEME_ID_RE.match(themeId):
                continue
            raw = json.loads(themeFile.read_text(encoding="utf-8"))
            if not isinstance(raw, dict):
                continue

            safeId = str(raw.get("id") or themeId).strip()
            if not THEME_ID_RE.match(safeId):
                safeId = themeId
            safeName = str(raw.get("name") or safeId.replace("_", " ").title()).strip()
            safeAuthor = str(raw.get("author") or "Lumiya").strip()
            safeVersion = str(raw.get("version") or "1.0").strip()

            thumbName = str(raw.get("thumbnail") or f"{safeId}.jpg").strip()
            if ".." in thumbName or "/" in thumbName or "\\" in thumbName:
                thumbName = f"{safeId}.jpg"
            thumbPath = themesDir / thumbName
            if thumbPath.is_file():
                thumbMtime = int(thumbPath.stat().st_mtime)
                thumbUrl = f"/identity/theme/{thumbName}?t={thumbMtime}"
            else:
                thumbUrl = "/identity/media/workspace.png"

            rawColors = raw.get("colors")
            if not isinstance(rawColors, dict):
                continue
            safeColors: Dict[str, str] = {}
            for k, v in rawColors.items():
                k_str = str(k).strip()
                v_str = str(v).strip()
                if k_str in _ALLOWED_THEME_KEYS and _COLOR_VALUE_REGEX.match(v_str):
                    safeColors[k_str] = v_str

            if not safeColors:
                continue

            themeMtime = int(themeFile.stat().st_mtime)
            themes.append({
                "id": safeId,
                "name": safeName,
                "author": safeAuthor,
                "version": safeVersion,
                "thumbnail": thumbUrl,
                "mtime": themeMtime,
                "colors": safeColors,
            })
        except Exception:
            continue

    def sortKey(t: Dict[str, Any]) -> int:
        tid = t.get("id", "")
        return priority.index(tid) if tid in priority else 100

    themes.sort(key=lambda t: (sortKey(t), t.get("name", "")))
    return themes


def requestFileIds(info: Dict[str, Any]) -> List[str]:
    """File ids from a batch action: a `fileIds` list (multi-select) or a single `fileId`."""
    raw = info.get("fileIds")
    if not isinstance(raw, list):
        raw = [info.get("fileId", "")]
    return [str(x) for x in raw[:5000] if isinstance(x, str) and x]


def findAvailablePort(startPort: int = 7860, maxAttempts: int = 50, host: str = "127.0.0.1") -> int:
    """Automatic Port Selection (APS): probes local sockets to find an available port."""
    probeHost = "127.0.0.1" if host in ("0.0.0.0", "") else host
    for candidate in range(startPort, startPort + maxAttempts):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            try:
                s.bind((probeHost, candidate))
                return candidate
            except OSError:
                continue
    return startPort


def triggerLastTabPurge(app: ServerApp) -> None:
    time.sleep(1.5)
    with app.sseLock:
        stillZero = app.sseCount == 0
    if stillZero and not app.rt.busy:
        rep = cleanMemoryAndStorage(app.rootDir, app.resultsRoot, app.qMgr.batches, app.engine, clearRawBytes=True)
        TermLog.emit(
            f"No active browser tabs — purged caches (VRAM freed: {rep['vramFreedMb']} MB, buffers: {rep['ramBuffersCleared']})",
            "core/cleaner.py",
            "INFO",
        )


class RequestHandler(BaseHTTPRequestHandler):
    def handle(self) -> None:
        try:
            super().handle()
        except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError, OSError):
            pass

    def log_message(self, fmt: str, *args: Any) -> None:
        return

    def _sendSecurityHeaders(self) -> None:
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("X-Frame-Options", "DENY")
        self.send_header("Referrer-Policy", "no-referrer")

    def _extractReqToken(self, qs: Dict[str, List[str]]) -> str:
        hdr = self.headers.get("X-Lumiya-Token") or self.headers.get("Authorization") or ""
        if hdr.lower().startswith("bearer "):
            hdr = hdr[7:].strip()
        return hdr or (qs.get("token", [""])[0] if "token" in qs else "")

    def do_GET(self) -> None:
        app: ServerApp = self.server.app  # type: ignore[attr-defined]
        parsed = urllib.parse.urlparse(self.path)
        qs = urllib.parse.parse_qs(parsed.query)

        if parsed.path.startswith("/api/") and not isTrustedRequest(
            self.headers.get("Host"),
            self.headers.get("Origin"),
            app.port,
            allowRemote=app.allowRemote,
            authToken=app.authToken,
            reqToken=self._extractReqToken(qs),
        ):
            self.send_error(HTTPStatus.FORBIDDEN)
            return

        if parsed.path == "/":
            body = app.uiFile.read_bytes()
            self.send_response(HTTPStatus.OK)
            self._sendSecurityHeaders()
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        elif (
            parsed.path.startswith("/identity/")
            or parsed.path in (
                "/lumiya_blk.ico",
                "/lumiya_t.ico",
                "/logo.png",
            )
        ):
            # Font files keep their published names, e.g. "IBMPlexSans[wdth,wght].ttf", so the path arrives percent-encoded.
            rel = urllib.parse.unquote(parsed.path).lstrip("/")
            if rel.startswith("identity/"):
                sub = rel[len("identity/"):]
                assetPath = (app.identityDir / sub).resolve()
            else:
                assetPath = app.identityDir / rel
            if not assetPath.exists() and (app.rootDir / rel).exists():
                assetPath = app.rootDir / rel
            if not assetPath.exists() and (app.rootDir / "assets" / rel).exists():
                assetPath = app.rootDir / "assets" / rel
            if (
                assetPath.is_file()
                and (
                    app.identityDir in assetPath.parents
                    or (app.rootDir / "assets") in assetPath.parents
                    or assetPath.parent == app.rootDir
                )
            ):
                if assetPath.name in ("logo.png", "lumiya_blk.ico", "lumiya_t.ico"):
                    verifyBrandAssets(app.rootDir)
                data = assetPath.read_bytes()
                ext = assetPath.suffix.lower()
                mimeMap = {
                    ".png": "image/png",
                    ".jpg": "image/jpeg",
                    ".jpeg": "image/jpeg",
                    ".ico": "image/x-icon",
                    ".gif": "image/gif",
                    ".webp": "image/webp",
                    **FONT_MIME,
                }
                mime = mimeMap.get(ext, "application/octet-stream")
                self.send_response(HTTPStatus.OK)
                self._sendSecurityHeaders()
                self.send_header("Content-Type", mime)
                self.send_header("Content-Length", str(len(data)))
                if parsed.path.startswith(("/identity/theme/", "/identity/media/", "/identity/fonts/")):
                    self.send_header("Cache-Control", "no-cache, must-revalidate")
                    self.send_header("ETag", f'"{int(assetPath.stat().st_mtime)}"')
                else:
                    self.send_header("Cache-Control", "public, max-age=86400")
                self.end_headers()
                self.wfile.write(data)
            else:
                self.send_error(HTTPStatus.NOT_FOUND)
        elif parsed.path == "/api/stream":
            self.send_response(HTTPStatus.OK)
            self.send_header("Content-Type", "text/event-stream")
            self.send_header("Cache-Control", "no-cache")
            self.send_header("Connection", "keep-alive")
            self.end_headers()
            with app.sseLock:
                app.sseCount += 1
            sentAlgoRev = -1
            sentBatchRev = -1
            try:
                while True:
                    majorReady = app.engine.majorDepsReady or app.rt.emulateExecution
                    curAlgoRev = app.algoMgr.rev
                    curBatchRev = app.qMgr.rev
                    payload: Dict[str, Any] = {
                        "appName": APP_NAME,
                        "appVersion": APP_VERSION,
                        "resultsRoot": str(app.resultsRoot),
                        "brandIntegrity": app.brandStatus,
                        "hw": app.mon.read().__dict__,
                        "cfg": app.cfg.snapshotForStream(),
                        "deps": app.deps,
                        "bounds": BOUNDS,
                        "computeLevels": CHOICES["computeLevel"],
                        "majorReady": majorReady,
                        "ui": {
                            "busy": app.rt.busy,
                            "paused": app.rt.paused,
                            "debugMode": app.rt.debugMode,
                            "emulateExecution": app.rt.emulateExecution,
                            "activeBatch": app.rt.activeBatch,
                            "file": app.rt.currentFile,
                            "idx": app.rt.idx,
                            "total": app.rt.total,
                            "step": app.rt.step,
                            "steps": app.rt.steps,
                            "eta": app.rt.eta,
                            "stepRate": app.rt.stepRate,
                            "history": list(app.rt.history[:40]),
                        },
                    }
                    if curAlgoRev != sentAlgoRev:
                        payload["algos"] = app.algoMgr.listMetadata()
                        sentAlgoRev = curAlgoRev
                    if curBatchRev != sentBatchRev:
                        payload["batches"] = app.qMgr.serializeTree()
                        sentBatchRev = curBatchRev
                    self.wfile.write(f"data: {json.dumps(payload)}\n\n".encode("utf-8"))
                    self.wfile.flush()
                    # Wake early when the queue changes (remove, move, new batch) so the UI follows at once;
                    # 0.15s floor keeps a run's frequent progress bumps from flooding the stream.
                    time.sleep(0.15)
                    deadline = time.monotonic() + max(0.25, app.cfg.pollMs / 1000.0) - 0.15
                    while time.monotonic() < deadline and app.qMgr.rev == sentBatchRev:
                        time.sleep(0.05)
            except (BrokenPipeError, ConnectionResetError, OSError):
                pass
            finally:
                with app.sseLock:
                    app.sseCount = max(0, app.sseCount - 1)
                    nowZero = app.sseCount == 0
                if nowZero:
                    threading.Thread(target=triggerLastTabPurge, args=(app,), daemon=True).start()
        elif parsed.path == "/api/preview_image":
            bid = qs.get("batch", [""])[0]
            fid = qs.get("file", [""])[0]
            preferExport = qs.get("export", ["0"])[0] == "1"
            found = app.qMgr.getFileBytes(bid, fid, preferExport=preferExport)
            if not found:
                self.send_error(HTTPStatus.NOT_FOUND)
                return
            imgBytes, mime = found
            self.send_response(HTTPStatus.OK)
            self.send_header("Content-Type", mime)
            self.send_header("Cache-Control", "no-store, max-age=0")
            self.send_header("Content-Length", str(len(imgBytes)))
            self.end_headers()
            self.wfile.write(imgBytes)
        elif parsed.path == "/api/batch_mark":
            b = app.qMgr.batches.get(qs.get("batch", [""])[0])
            self.sendJson({"ok": bool(b), "mark": b.stegoMark if b else ""})
        elif parsed.path == "/api/check_stego":
            bid = qs.get("batch", [""])[0]
            fid = qs.get("file", [""])[0]
            found = app.qMgr.getFileBytes(bid, fid, preferExport=True)
            if not found:
                self.sendJson({"ok": False, "found": False, "error": "Processed file not found on disk or memory."})
                return
            imgBytes, _ = found
            res = inspectStego(imgBytes)
            self.sendJson({"ok": True, **res})
        elif parsed.path == "/api/manifest":
            manifestPath = app.manifestFile if app.manifestFile.exists() else (app.rootDir / "install_manifest.log")
            text = manifestPath.read_text(encoding="utf-8") if manifestPath.exists() else "No user/install_manifest.log found."
            self.sendJson({"manifest": text})
        elif parsed.path == "/api/themes":
            themes = loadThemesFromDisk(app.themesDir)
            self.sendJson({"ok": True, "themes": themes})
        elif parsed.path == "/api/fonts":
            self.sendJson({"ok": True, "app": scanAppFonts(app.identityDir / "fonts")})
        elif parsed.path == "/api/fonts/system":
            faces = scanSystemFonts(refresh=qs.get("refresh", ["0"])[0] == "1")
            self.sendJson({"ok": True, "system": [{k: v for k, v in f.items() if k != "postscript"} for f in faces]})
        else:
            self.send_error(HTTPStatus.NOT_FOUND)

    def do_POST(self) -> None:
        app: ServerApp = self.server.app  # type: ignore[attr-defined]
        parsed = urllib.parse.urlparse(self.path)
        qs = urllib.parse.parse_qs(parsed.query)
        if not isTrustedRequest(
            self.headers.get("Host"),
            self.headers.get("Origin"),
            app.port,
            allowRemote=app.allowRemote,
            authToken=app.authToken,
            reqToken=self._extractReqToken(qs),
        ):
            self.send_error(HTTPStatus.FORBIDDEN)
            return
        length = safeInt(self.headers.get("Content-Length", "0"), 0, 0, 200_000_000)
        rawBody = self.rfile.read(length) if length > 0 else b""
        clientIp = self.client_address[0] if self.client_address else ""

        if parsed.path == "/api/create_batch":
            b = app.qMgr.createOrGetStagingBatch()
            self.sendJson({"batchId": b.batchId})

        elif parsed.path == "/api/upload":
            bid = qs.get("batch", [""])[0]
            fname = qs.get("name", ["upload.jpg"])[0]
            res = app.qMgr.addFile(bid, fname, rawBody)
            self.sendJson(res)

        elif parsed.path == "/api/check_stego_raw":
            if not rawBody:
                self.sendJson({"ok": False, "error": "No image was received."})
                return
            res = inspectStego(rawBody)
            self.sendJson({"ok": True, **res})

        elif parsed.path == "/api/stego_prepare":
            try:
                mark, compressed = prepareMark(rawBody)
                self.sendJson({"ok": True, "mark": mark, "compressed": compressed})
            except MarkError as exc:
                self.sendJson({"ok": False, "error": str(exc)})
            except (OSError, ValueError):
                self.sendJson({"ok": False, "error": "This file could not be read as an image."})

        elif parsed.path == "/api/open_result":
            if not isLoopbackClient(clientIp):
                self.sendJson({"ok": False, "error": "Opening local OS folders is restricted to localhost."})
                return
            name = qs.get("batch", [""])[0]
            folder = app.resultsRoot / name
            if not name or folder.resolve().parent != app.resultsRoot.resolve() or not folder.is_dir():
                self.sendJson({"ok": False})
                return
            openPathForeground(folder)
            self.sendJson({"ok": True})

        elif parsed.path == "/api/batch_action":
            info = parseJsonBody(rawBody)
            act = info.get("action", "")
            bid = info.get("batchId", "")
            b = app.qMgr.batches.get(bid)

            if act == "run" and not app.rt.busy and b and (app.engine.majorDepsReady or app.rt.emulateExecution or b.stegoMode == "only"):
                okCfg, errCfg = validateBatchConfig(b, app.algoMgr, requireFiles=True)
                if not okCfg:
                    self.sendJson({"ok": False, "error": errCfg})
                    return
                threading.Thread(target=app.executeBatch, args=(bid,), daemon=True).start()
                self.sendJson({"ok": True})
            elif act == "stop" and app.rt.busy and app.rt.activeBatch == bid:
                app.rt.stopRequested = True
                self.sendJson({"ok": True})
            elif act == "restart" and not app.rt.busy and b:
                okCfg, errCfg = validateBatchConfig(b, app.algoMgr, requireFiles=True)
                if not okCfg:
                    self.sendJson({"ok": False, "error": errCfg})
                    return
                if any(f.valid and not f.rawBytes for f in b.files):
                    self.sendJson(
                        {"ok": False, "error": "Originals were released from memory. Add the photos again to redo this batch."}
                    )
                    return
                for f in b.files:
                    if f.valid:
                        f.status = "STAGED"
                        f.hasStego = False
                b.state = "STAGED"
                app.qMgr.rev += 1
                threading.Thread(target=app.executeBatch, args=(bid,), daemon=True).start()
                self.sendJson({"ok": True})
            elif act == "update_params" and b and b.state != "RUNNING":
                # Same limits and allowed values as the saved config (core/config.py BOUNDS / CHOICES).
                for key, val in info.items():
                    if key in BOUNDS and hasattr(b, key):
                        setattr(b, key, clampSetting(key, val, getattr(b, key)))
                    elif key in CHOICES and hasattr(b, key):
                        if val in CHOICES[key]:
                            setattr(b, key, val)
                    elif key in ("stegoMark", "guidancePrompt", "stegoText") and isinstance(val, str):
                        setattr(b, key, val)
                if "convertPng" in info:
                    b.convertPng = bool(info["convertPng"])
                if "layers" in info and isinstance(info["layers"], dict):
                    b.layers = {str(k): bool(v) for k, v in info["layers"].items()}
                app.qMgr.rev += 1
                okCfg, errCfg = validateBatchConfig(b, app.algoMgr, requireFiles=False)
                self.sendJson({"ok": okCfg, "error": errCfg})
            elif act == "reorder_file":
                res = app.qMgr.moveFiles(
                    srcBatchId=bid,
                    fileIds=requestFileIds(info),
                    targetBatchId=str(info.get("targetBatchId", bid)),
                    targetIndex=safeInt(info.get("targetIndex", 0), 0),
                )
                self.sendJson(res)
            elif act == "open_batch_export" and b:
                if isLoopbackClient(clientIp) and b.exportDir.exists():
                    openPathForeground(b.exportDir)
                self.sendJson({"ok": True})
            elif act == "delete_batch":
                if app.rt.busy and app.rt.activeBatch == bid:
                    app.rt.stopRequested = True
                    time.sleep(0.4)
                keepExp = bool(info.get("keepExports"))
                app.qMgr.deleteBatch(bid, keepExports=keepExp)
                if not keepExp:
                    app.rt.removeBatchHistory(bid)
                self.sendJson({"ok": True})
            elif act == "remove_file":
                self.sendJson(app.qMgr.removeFiles(bid, requestFileIds(info)))
            else:
                self.sendJson({"ok": False})

        elif parsed.path == "/api/clear_history":
            app.rt.history.clear()
            app.rt.saveHistory()
            self.sendJson({"ok": True})

        elif parsed.path == "/api/debug_action":
            if not app.rt.debugMode:
                self.sendJson({"ok": False, "error": "Debug mode is only available via debug.bat (--debug)."})
                return
            info = parseJsonBody(rawBody)
            cmd = info.get("cmd", "")
            if cmd == "toggle_emulate":
                app.rt.emulateExecution = not app.rt.emulateExecution
            elif cmd == "mock_deps":
                stateVal = bool(info.get("state", True))
                for k in ("torch", "cuda", "diffusers", "transformers", "pil", "psutil"):
                    app.deps[k] = stateVal
                app.deps["psutil"] = stateVal and psutil is not None
                app.deps["pil"] = stateVal and Image is not None
            elif cmd == "sim_thermal":
                app.mon.debugOverride["tempState"] = info.get("state", "normal")
                app.mon.debugOverride["tempC"] = safeFloat(info.get("tempC", 50.0), 50.0)
            elif cmd == "inject_sample":
                b = app.qMgr.createOrGetStagingBatch()
                if app.deps["pil"]:
                    im = Image.new("RGB", (640, 480), color=(32, 64, 128))
                    buf = io.BytesIO()
                    im.save(buf, format="JPEG", quality=92)
                    sampleBytes = buf.getvalue()
                else:
                    sampleBytes = b"\xff\xd8\xff\xe0" + os.urandom(2048)
                app.qMgr.addFile(b.batchId, f"DebugSample_{int(time.time()) % 10000}.jpg", sampleBytes)
            self.sendJson({"ok": True})

        elif parsed.path == "/api/algo_action":
            info = parseJsonBody(rawBody)
            if info.get("action") == "delete":
                res = app.algoMgr.deleteCustomAlgo(str(info.get("algoId", "")))
                self.sendJson({**res, "algos": app.algoMgr.listMetadata()})
            else:
                self.sendJson({"ok": False})

        elif parsed.path == "/api/save_config":
            newCfg = parseJsonBody(rawBody)
            app.cfg.applyDict(newCfg)
            app.cfg.save(app.configFile)
            if "overrideHardware" in newCfg or "protectionMode" in newCfg:
                app.algoMgr.rev += 1
            self.sendJson({"ok": True})

        elif parsed.path == "/api/rescan_algos":
            algos = app.algoMgr.scanAlgos()
            self.sendJson({"ok": True, "algos": algos})

        elif parsed.path == "/api/system_maint":
            cmdType = qs.get("cmd", [""])[0]
            if cmdType in (
                "install",
                "uninstall",
                "purge",
                "open_results",
                "open_algos",
                "verify_integrity",
                "check_update",
                "self_update",
            ) and not isLoopbackClient(clientIp):
                self.sendJson({"ok": False, "error": "Local system maintenance is restricted to localhost."})
                return

            def launchDetachedTerminal(winTitle: str, winCmd: List[str], shArgs: List[str]) -> None:
                if sys.platform == "win32":
                    subprocess.Popen(["cmd.exe", "/c", "start", winTitle, "cmd.exe", *winCmd])
                else:
                    shPath = str(app.rootDir / "run.sh")
                    hasDisplay = bool(os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY"))
                    term = None
                    if hasDisplay:
                        for tName in (
                            "x-terminal-emulator",
                            "ptyxis",
                            "gnome-terminal",
                            "konsole",
                            "xfce4-terminal",
                            "kitty",
                            "alacritty",
                            "wezterm",
                            "foot",
                            "tilix",
                            "mate-terminal",
                            "xterm",
                        ):
                            foundTerm = shutil.which(tName)
                            if foundTerm:
                                term = foundTerm
                                break
                    cmd = ["bash", "-c", 'bash "$1" "${@:2}"; echo; read -n 1 -s -r -p "Press any key to close...";', "_", shPath, *shArgs]
                    tBase = Path(term).name if term else ""
                    if term and tBase in ("gnome-terminal", "ptyxis"):
                        subprocess.Popen([term, "--", *cmd])
                    elif term and tBase == "wezterm":
                        subprocess.Popen([term, "start", "--", *cmd])
                    elif term and tBase == "foot":
                        subprocess.Popen([term, *cmd])
                    elif term:
                        subprocess.Popen([term, "-e", *cmd])
                    else:
                        subprocess.Popen(["bash", shPath, *shArgs])

            if cmdType == "install":
                launchDetachedTerminal("PORTtralica Installer", ["/k", str(app.rootDir / "install.bat")], ["--install"])
                self.sendJson({"ok": True})
            elif cmdType == "run_cleaner":
                rep = cleanMemoryAndStorage(app.rootDir, app.resultsRoot, app.qMgr.batches, app.engine)
                self.sendJson({"ok": True, "report": rep})
            elif cmdType == "tab_closed":
                with app.sseLock:
                    noTabs = app.sseCount <= 1
                if noTabs and not app.rt.busy:
                    rep = cleanMemoryAndStorage(app.rootDir, app.resultsRoot, app.qMgr.batches, app.engine, clearRawBytes=True)
                    self.sendJson({"ok": True, "report": rep})
                else:
                    self.sendJson({"ok": True})
            elif cmdType == "restart_service":
                if app.rt.busy:
                    app.rt.stopRequested = True
                    time.sleep(0.3)
                cleanMemoryAndStorage(app.rootDir, app.resultsRoot, app.qMgr.batches, app.engine, clearRawBytes=True)
                self.sendJson({"ok": True, "restarting": True})

                def performRestart() -> None:
                    time.sleep(0.35)
                    TermLog.emit("Restarting PORTtralica Lumiya service...", "bootstrap.py", "INFO")
                    os._exit(42)

                threading.Thread(target=performRestart, daemon=True).start()
            elif cmdType == "open_results":
                openPathForeground(app.resultsRoot)
                self.sendJson({"ok": True})
            elif cmdType == "open_algos":
                openPathForeground(app.algosDir)
                self.sendJson({"ok": True})
            elif cmdType == "verify_integrity":
                self.sendJson({"ok": True, "integrity": computeProgramIntegrity(app.rootDir, APP_VERSION)})
            elif cmdType == "check_update":
                self.sendJson(checkRemoteUpdate(app.rootDir, APP_VERSION, fetchRemote=True))
            elif cmdType == "self_update":
                if app.rt.busy:
                    self.sendJson({"ok": False, "error": "Cannot self-update while a protection batch is actively running."})
                    return
                res = runProtectedUpdate(app.rootDir, sys.executable, APP_VERSION)
                self.sendJson(res)
                if res.get("ok") and res.get("updated"):
                    def _restartAfterUpdate() -> None:
                        time.sleep(0.5)
                        TermLog.emit("Applying self-update and restarting PORTtralica Lumiya service...", "updater.py", "OK")
                        os._exit(42)

                    threading.Thread(target=_restartAfterUpdate, daemon=True).start()
            elif cmdType in ("uninstall", "purge"):
                modeFlag = "--purge" if cmdType == "purge" else "--manifest"
                if app.rt.busy:
                    app.rt.stopRequested = True
                    time.sleep(0.3)
                cleanMemoryAndStorage(app.rootDir, app.resultsRoot, app.qMgr.batches, app.engine, clearRawBytes=True)
                launchDetachedTerminal(f"PORTtralica Lumiya ({cmdType.upper()})", ["/c", str(app.rootDir / "uninstall.bat"), modeFlag, "-y"], ["uninstall", modeFlag, "-y"])
                self.sendJson({"ok": True, "action": cmdType, "msg": f"{cmdType.capitalize()} initiated in detached window. Service shutting down."})

                def performShutdown() -> None:
                    time.sleep(0.6)
                    os._exit(0)

                threading.Thread(target=performShutdown, daemon=True).start()
            else:
                self.sendJson({"ok": False})
        else:
            self.send_error(HTTPStatus.NOT_FOUND)

    def sendJson(self, obj: Dict[str, Any]) -> None:
        try:
            raw = json.dumps(obj).encode("utf-8")
            self.send_response(HTTPStatus.OK)
            self._sendSecurityHeaders()
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(raw)))
            self.end_headers()
            self.wfile.write(raw)
        except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError, OSError):
            pass


class QuietThreadingHTTPServer(ThreadingHTTPServer):
    allow_reuse_address = True
    daemon_threads = True

    def handle_error(self, request: Any, client_address: Any) -> None:
        _, exc, _ = sys.exc_info()
        if isinstance(exc, (BrokenPipeError, ConnectionResetError, ConnectionAbortedError, OSError)):
            return
        super().handle_error(request, client_address)


def serve(app: ServerApp, host: str, port: int, noBrowser: bool) -> None:
    """Binds the first free port from `port` up, then serves until Ctrl+C or a restart exit."""
    server: Optional[QuietThreadingHTTPServer] = None
    maxAttempts = 50
    for offset in range(maxAttempts):
        candidatePort = port + offset
        try:
            server = QuietThreadingHTTPServer((host, candidatePort), RequestHandler)
            app.port = candidatePort
            server.app = app  # type: ignore[attr-defined]
            break
        except OSError:
            if offset == 0:
                TermLog.emit(f"Port {port} is occupied. Engaging Automatic Port Selection (APS)...", "server.py", "WARNING")
            continue

    if server is None:
        TermLog.emit(f"Fatal: Could not acquire any socket in range {port}-{port + maxAttempts - 1}", "server.py", "ERROR")
        raise RuntimeError(f"All ports from {port} to {port + maxAttempts - 1} are occupied.")

    # Read the installed fonts while the page loads, so the font browser's first request is answered from the cache.
    threading.Thread(target=scanSystemFonts, name="font-scan", daemon=True).start()

    if app.port != port:
        TermLog.emit(
            f"APS Socket Fallback: Listening on port {TermLog.CYAN}{app.port}{TermLog.RESET} (preferred {port} was busy)",
            "server.py",
            "INFO",
        )

    displayHost = "127.0.0.1" if host in ("0.0.0.0", "") else host
    url = f"http://{displayHost}:{app.port}" + (f"/?token={app.authToken}" if app.authToken else "")
    gpuTarget = app.deps.get("gpuName") or "CPU Only"
    cudaVer = app.deps.get("versions", {}).get("cuda") or "Not Available"
    hwStatus = f"{gpuTarget} (CUDA: {cudaVer})" if app.deps.get("cuda") else f"{gpuTarget} [CUDA: {cudaVer}]"
    TermLog.emit(f"Hardware Compute Target: {TermLog.CYAN}{hwStatus}{TermLog.RESET}", "engine.py", "INFO")
    TermLog.emit(f"WebUI listening on {TermLog.GREEN}\"{url}\"{TermLog.RESET}", "server.py", "OK")
    print("  " + "=" * 100, flush=True)
    if not noBrowser:
        canOpen = True
        if sys.platform != "win32":
            if not os.environ.get("DISPLAY") and not os.environ.get("WAYLAND_DISPLAY"):
                canOpen = False
            elif os.environ.get("SSH_CLIENT") or os.environ.get("SSH_TTY") or os.environ.get("SSH_CONNECTION"):
                canOpen = False
        if canOpen:
            def _openBrowserAsync() -> None:
                try:
                    time.sleep(0.4)
                    webbrowser.open(url)
                except Exception:
                    pass

            threading.Thread(target=_openBrowserAsync, daemon=True).start()

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n  [SHUTDOWN] Exiting Lumiya service (Ctrl+C)...", flush=True)
        try:
            cleanMemoryAndStorage(app.rootDir, app.resultsRoot, app.qMgr.batches, app.engine, clearRawBytes=True)
        except Exception:
            pass
        server.server_close()
        os._exit(0)
    except Exception as exc:
        TermLog.emit(f"Server runtime exception: {exc}", "server.py", "ERROR")
        server.server_close()
        os._exit(1)
