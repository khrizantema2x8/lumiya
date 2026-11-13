"""Batch queue state: staged files, per-batch settings, export folders and the run history."""
from __future__ import annotations

import base64
import copy
import hashlib
import io
import json
import shutil
import threading
import uuid
from dataclasses import dataclass, field, fields, replace
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from core.config import VALID_EXTS, SuiteConfig, atomicWrite
from core.loader import AlgoPluginManager
from core.security import sanitizeFilename
from core.termlog import TermLog

try:
    from PIL import Image, ImageOps
except ImportError:
    Image = ImageOps = None  # type: ignore

_DEFAULTS = SuiteConfig()
HISTORY_LIMIT = 100


@dataclass
class QueuedFile:
    fileId: str
    name: str
    ext: str
    sha256: str
    sizeBytes: int
    width: int = 0
    height: int = 0
    valid: bool = True
    errorMsg: str = ""
    status: str = "STAGED"
    rawBytes: bytes = b""
    thumbB64: str = ""
    outPath: str = ""
    hasStego: bool = False
    psnr: float = 0.0
    shift: float = 0.0
    exportRev: int = 0


@dataclass
class BatchQueue:
    batchId: str
    createdAt: str
    exportRoot: Path
    state: str = "STAGED"
    epsilon: float = _DEFAULTS.epsilon
    computeLevel: float = _DEFAULTS.computeLevel
    seed: int = _DEFAULTS.seed
    steps: int = _DEFAULTS.steps
    guidancePrompt: str = _DEFAULTS.guidancePrompt
    geoAnchorLow: float = _DEFAULTS.geoAnchorLow
    geoAnchorHigh: float = _DEFAULTS.geoAnchorHigh
    temporalWeight: float = _DEFAULTS.temporalWeight
    maskAugFactor: float = _DEFAULTS.maskAugFactor
    convertPng: bool = _DEFAULTS.convertPng
    stegoMode: str = _DEFAULTS.stegoMode
    stegoText: str = _DEFAULTS.stegoText
    stegoStrength: float = _DEFAULTS.stegoStrength
    stegoScale: float = _DEFAULTS.stegoScale
    stegoPlacement: str = _DEFAULTS.stegoPlacement
    stegoPayload: str = _DEFAULTS.stegoPayload
    stegoMark: str = _DEFAULTS.stegoMark
    layers: Dict[str, bool] = field(default_factory=lambda: dict(_DEFAULTS.layers))
    files: List[QueuedFile] = field(default_factory=list)

    @property
    def stegoTextActive(self) -> str:
        return self.stegoText if self.stegoPayload in ("text", "binary") else ""

    @property
    def stegoMarkActive(self) -> str:
        return self.stegoMark if self.stegoPayload == "image" else ""

    @property
    def exportDir(self) -> Path:
        return self.exportRoot / self.batchId

    @property
    def hasExported(self) -> bool:
        return any(bool(f.outPath) for f in self.files)


def isLockedFile(f: QueuedFile) -> bool:
    """A processed (or currently processing) file can't be removed or moved; moving copies its original instead."""
    return f.status in ("DONE", "RUNNING")


def validateBatchConfig(batch: BatchQueue, algoMgr: Optional[AlgoPluginManager] = None, requireFiles: bool = False) -> Tuple[bool, str]:
    """Ensures batch parameters, hardware constraints, and algorithm selections are valid before execution or save."""
    if requireFiles:
        validFiles = [f for f in batch.files if f.valid]
        if not validFiles:
            return False, "This batch contains no valid readable images to process."
    if batch.stegoMode != "only":
        enabledIds = [k for k, v in (batch.layers or {}).items() if bool(v)]
        if not enabledIds:
            return False, "At least one AI-Defense Layers algorithm must be enabled when AI-blocking is active."
        if algoMgr is not None:
            runnableCount = 0
            lastBlockReason = ""
            for aid in enabledIds:
                p = algoMgr.plugins.get(aid)
                if not p:
                    continue
                bReason = algoMgr.blockReason(p)
                if bReason:
                    lastBlockReason = f"{p.get('name', aid)}: {bReason}"
                else:
                    runnableCount += 1
            if runnableCount == 0 and lastBlockReason:
                return False, lastBlockReason
    if batch.stegoMode in ("combined", "only"):
        if batch.stegoPayload in ("text", "binary") and not str(batch.stegoTextActive or "").strip():
            return False, "Enter a watermark text payload when text steganography is enabled."
        if batch.stegoPayload == "image" and not batch.stegoMarkActive:
            return False, "Import a transparent PNG mark when Visible Image Mark steganography is enabled."
    return True, ""


# BatchQueue fields that start from the user's saved settings.
BATCH_CFG_KEYS = tuple(f.name for f in fields(BatchQueue) if f.name in SuiteConfig.__dataclass_fields__)


class QueueManager:
    def __init__(self, resultsRoot: Path, cfg: SuiteConfig) -> None:
        self.resultsRoot = resultsRoot
        self.cfg = cfg
        self.resultsRoot.mkdir(parents=True, exist_ok=True)
        self.lock = threading.RLock()
        self.batches: Dict[str, BatchQueue] = {}
        self.batchOrder: List[str] = []
        self.rev: int = 1
        self._cachedTreeRev: int = -1
        self._cachedTree: List[Dict[str, Any]] = []

    def createNewBatch(self) -> BatchQueue:
        # Dashed date, unbroken time: 2026-03-24-190832.
        stamp = datetime.now().strftime("%Y-%m-%d-%H%M%S")
        bid = stamp
        idx = 1
        while bid in self.batches or (self.resultsRoot / bid).exists():
            bid = f"{stamp}-{idx}"
            idx += 1
        batch = BatchQueue(
            batchId=bid,
            createdAt=datetime.now().strftime("%H:%M:%S"),
            exportRoot=self.resultsRoot,
            **{k: copy.deepcopy(getattr(self.cfg, k)) for k in BATCH_CFG_KEYS},
        )
        self.batches[bid] = batch
        self.batchOrder.append(bid)
        self.rev += 1
        TermLog.emit(f"Created staging batch {TermLog.CYAN}{bid}{TermLog.RESET}", "queueManager.py", "INFO")
        return batch

    def createOrGetStagingBatch(self) -> BatchQueue:
        with self.lock:
            for bid in reversed(self.batchOrder):
                b = self.batches[bid]
                if b.state == "STAGED":
                    return b
            return self.createNewBatch()

    def addFile(self, batchId: str, filename: str, data: bytes) -> Dict[str, Any]:
        safeName = sanitizeFilename(filename)
        ext = Path(safeName).suffix.lower()

        if ext not in VALID_EXTS:
            return {
                "accepted": False,
                "duplicate": False,
                "reason": f"Illegal format '{ext}' for '{safeName}'. Allowed: {', '.join(VALID_EXTS)}",
            }
        if not data:
            return {"accepted": False, "duplicate": False, "reason": f"'{safeName}' arrived empty and was skipped."}

        fileHash = hashlib.sha256(data).hexdigest()

        with self.lock:
            batch = self.batches.get(batchId)
            if batch is None or batch.state not in ("STAGED", "PAUSED", "STOPPED"):
                batch = self.createOrGetStagingBatch()

            for existing in batch.files:
                if existing.sha256 == fileHash:
                    return {
                        "accepted": False,
                        "duplicate": True,
                        "reason": f"Duplicate skipped: '{safeName}' is already in batch {batch.batchId}.",
                    }

        validContent = True
        errMsg = ""
        width, height = 0, 0
        thumbStr = ""
        if Image is not None:
            try:
                with Image.open(io.BytesIO(data)) as verifyIm:
                    verifyIm.verify()
                with Image.open(io.BytesIO(data)) as im:
                    im = ImageOps.exif_transpose(im)
                    width, height = im.size
                    if width < 16 or height < 16:
                        raise ValueError(f"Dimensions too small ({width}x{height})")
                    thumb = im.convert("RGB")
                    thumb.thumbnail((220, 220))
                    buf = io.BytesIO()
                    thumb.save(buf, format="JPEG", quality=82)
                    thumbStr = "data:image/jpeg;base64," + base64.b64encode(buf.getvalue()).decode("ascii")
            except Exception as exc:
                validContent = False
                errMsg = f"Corrupted image content: {exc}"
        else:
            width, height = 512, 512

        qfile = QueuedFile(
            fileId=uuid.uuid4().hex[:10],
            name=safeName,
            ext=ext,
            sha256=fileHash,
            sizeBytes=len(data),
            width=width,
            height=height,
            valid=validContent,
            errorMsg=errMsg,
            status="STAGED" if validContent else "CORRUPT",
            rawBytes=data if validContent else b"",
            thumbB64=thumbStr,
        )

        with self.lock:
            batch.files.append(qfile)
            self.rev += 1

        return {"accepted": True, "duplicate": False, "valid": validContent, "name": safeName, "batchId": batch.batchId}

    def moveFiles(self, srcBatchId: str, fileIds: List[str], targetBatchId: str, targetIndex: int) -> Dict[str, Any]:
        """Moves unprocessed files; a processed (or running) file is copied instead, as its original photo, re-staged."""
        with self.lock:
            srcBatch = self.batches.get(srcBatchId)
            if not srcBatch:
                return {"ok": False}
            wanted = set(fileIds)
            picked = [f for f in srcBatch.files if f.fileId in wanted]
            if not picked:
                return {"ok": False}
            isNew = targetBatchId == "NEW_BATCH"
            destBatch = None if isNew else self.batches.get(targetBatchId, srcBatch)
            if destBatch is not None and destBatch is not srcBatch and destBatch.state != "STAGED":
                return {"ok": False, "error": "Files can only be moved into a batch that has not run yet."}

            skipped: List[str] = []
            incoming: List[QueuedFile] = []
            for f in picked:
                if not isLockedFile(f):
                    incoming.append(f)
                elif destBatch is srcBatch:
                    skipped.append(f"{f.name} (already processed, it stays in place)")
                elif not f.rawBytes:
                    skipped.append(f"{f.name} (its original was released from memory)")
                else:
                    incoming.append(replace(f, fileId=uuid.uuid4().hex[:10], status="STAGED", outPath="", hasStego=False, psnr=0.0, shift=0.0, exportRev=0))
            if destBatch is not None and destBatch is not srcBatch:
                have = {f.sha256 for f in destBatch.files}
                dupes = [f for f in incoming if f.sha256 in have]
                skipped += [f"{f.name} (already in {destBatch.batchId})" for f in dupes]
                incoming = [f for f in incoming if f.sha256 not in have]
            if not incoming:
                return {"ok": False, "error": "Nothing was moved: " + "; ".join(skipped)}

            movingIds = {f.fileId for f in incoming}
            srcBatch.files = [f for f in srcBatch.files if f.fileId not in movingIds]
            if destBatch is None:
                destBatch = self.createNewBatch()
            at = max(0, min(targetIndex, len(destBatch.files)))
            destBatch.files[at:at] = incoming

            if len(srcBatch.files) == 0:
                self.deleteBatchUnlocked(srcBatchId)
            self.rev += 1
            return {"ok": True, "skipped": skipped}

    def getFileBytes(self, batchId: str, fileId: str, preferExport: bool = False) -> Optional[Tuple[bytes, str]]:
        mimeMap = {".png": "image/png", ".webp": "image/webp", ".bmp": "image/bmp", ".tiff": "image/tiff"}
        with self.lock:
            b = self.batches.get(batchId)
            if not b:
                return None
            for f in b.files:
                if f.fileId == fileId:
                    hasDisk = bool(f.outPath and Path(f.outPath).exists())
                    if (preferExport or not f.rawBytes) and hasDisk:
                        outPath = Path(f.outPath)
                        return outPath.read_bytes(), mimeMap.get(outPath.suffix.lower(), "image/jpeg")
                    if f.rawBytes:
                        return f.rawBytes, mimeMap.get(f.ext.lower(), "image/jpeg")
            return None

    def removeFiles(self, batchId: str, fileIds: List[str]) -> Dict[str, Any]:
        """Removes unprocessed files; processed or running ones are refused. An emptied batch is deleted."""
        with self.lock:
            batch = self.batches.get(batchId)
            if not batch:
                return {"ok": False}
            wanted = set(fileIds)
            locked = [f.name for f in batch.files if f.fileId in wanted and isLockedFile(f)]
            gone = [f for f in batch.files if f.fileId in wanted and not isLockedFile(f)]
            if not gone:
                return {"ok": False, "error": "Already processed images cannot be removed: " + ", ".join(locked)}
            goneIds = {f.fileId for f in gone}
            batch.files = [f for f in batch.files if f.fileId not in goneIds]
            emptyNow = len(batch.files) == 0
            if emptyNow:
                self.deleteBatchUnlocked(batchId)
            self.rev += 1
            return {"ok": True, "batchDeleted": emptyNow, "skipped": locked}

    def deleteBatchUnlocked(self, batchId: str, deleteExports: bool = False) -> None:
        batch = self.batches.pop(batchId, None)
        if batchId in self.batchOrder:
            self.batchOrder.remove(batchId)
        if deleteExports and batch and batch.exportDir.exists():
            shutil.rmtree(batch.exportDir, ignore_errors=True)
        self.rev += 1

    def deleteBatch(self, batchId: str, keepExports: bool = False) -> bool:
        with self.lock:
            if batchId not in self.batches:
                return False
            self.deleteBatchUnlocked(batchId, deleteExports=not keepExports)
            return True

    def serializeTree(self) -> List[Dict[str, Any]]:
        with self.lock:
            if self._cachedTreeRev == self.rev:
                return self._cachedTree
            out = []
            for bid in reversed(self.batchOrder):
                b = self.batches[bid]
                allPng = len(b.files) > 0 and all(f.ext.lower() == ".png" for f in b.files)
                out.append(
                    {
                        "batchId": b.batchId,
                        "createdAt": b.createdAt,
                        "state": b.state,
                        "hasExported": b.hasExported,
                        "allPng": allPng,
                        "convertPng": b.convertPng,
                        "epsilon": b.epsilon,
                        "computeLevel": b.computeLevel,
                        "seed": b.seed,
                        "stegoStrength": b.stegoStrength,
                        "stegoScale": b.stegoScale,
                        "stegoPlacement": b.stegoPlacement,
                        "stegoPayload": b.stegoPayload,
                        # Id only: the mark can be a large image, and this tree is resent on every status change.
                        "markId": hashlib.sha1(b.stegoMark.encode("ascii", "ignore")).hexdigest()[:12] if b.stegoMark else "",
                        "steps": b.steps,
                        "guidancePrompt": b.guidancePrompt,
                        "geoAnchorLow": b.geoAnchorLow,
                        "geoAnchorHigh": b.geoAnchorHigh,
                        "temporalWeight": b.temporalWeight,
                        "maskAugFactor": b.maskAugFactor,
                        "stegoMode": b.stegoMode,
                        "stegoText": b.stegoText,
                        "layers": dict(b.layers),
                        "files": [
                            {
                                "fileId": f.fileId,
                                "name": f.name,
                                "ext": f.ext,
                                "dims": f"{f.width}x{f.height}" if f.width else "Invalid",
                                "sizeKb": round(f.sizeBytes / 1024.0, 1),
                                "valid": f.valid,
                                "errorMsg": f.errorMsg,
                                "status": f.status,
                                "hasStego": f.hasStego,
                                "hasExport": bool(f.outPath and Path(f.outPath).exists()),
                                "outName": Path(f.outPath).name if f.outPath else "",
                                "exportRev": f.exportRev,
                                "psnr": round(f.psnr, 1),
                                "shift": round(f.shift, 1),
                                "thumb": f.thumbB64,
                            }
                            for f in b.files
                        ],
                    }
                )
            self._cachedTree = out
            self._cachedTreeRev = self.rev
            return out


@dataclass
class RuntimeState:
    historyFile: Path
    busy: bool = False
    paused: bool = False
    stopRequested: bool = False
    debugMode: bool = False
    emulateExecution: bool = False
    activeBatch: str = "-"
    currentFile: str = "Idle"
    idx: int = 0
    total: int = 0
    step: int = 0
    steps: int = _DEFAULTS.steps
    eta: float = 0.0
    stepRate: float = 0.0
    history: List[Dict[str, Any]] = field(default_factory=list)

    def loadHistory(self) -> None:
        # Older builds kept history.json in the program root, next to user/.
        target = self.historyFile if self.historyFile.exists() else (self.historyFile.parent.parent / "history.json")
        if target.exists():
            try:
                self.history = json.loads(target.read_text(encoding="utf-8"))
            except Exception:
                self.history = []

    def saveHistory(self) -> None:
        # Only the newest 100 rows are kept on disk; trimming memory too stops a long session growing it forever.
        del self.history[HISTORY_LIMIT:]
        try:
            atomicWrite(self.historyFile, json.dumps(self.history, indent=2))
        except Exception:
            pass

    def removeBatchHistory(self, batchId: str) -> None:
        beforeLen = len(self.history)
        self.history = [h for h in self.history if h.get("batch") != batchId]
        if len(self.history) != beforeLen:
            self.saveHistory()
