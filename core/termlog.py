"""Console log lines, progress bar and user/error.log, shared by the launcher, server, queue and worker."""
from __future__ import annotations

import ctypes
import sys
from datetime import datetime
from pathlib import Path

# Lets the Windows console render the ANSI colours below.
if sys.platform == "win32":
    kernel32 = ctypes.windll.kernel32
    stdOutHandle = kernel32.GetStdHandle(-11)
    consoleMode = ctypes.c_ulong()
    if kernel32.GetConsoleMode(stdOutHandle, ctypes.byref(consoleMode)):
        kernel32.SetConsoleMode(stdOutHandle, consoleMode.value | 0x0004)


class TermLog:
    RESET = "\x1b[0m"
    DIM = "\x1b[90m"
    CYAN = "\x1b[96m"
    GREEN = "\x1b[92m"
    YELLOW = "\x1b[93m"
    RED = "\x1b[91m"
    MAGENTA = "\x1b[95m"
    WHITE = "\x1b[97m"
    WIDTH = 102
    ERROR_LOG_PATH = Path(__file__).resolve().parents[1] / "user" / "error.log"

    @classmethod
    def writeErrorLog(cls, context: str, detail: str, module: str = "lumiyaCore.py") -> None:
        try:
            cls.ERROR_LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
            ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            entry = (
                f"[{ts}] [{module}] {context}\n"
                f"  Python : {sys.version.split()[0]} ({sys.executable})\n"
                f"  OS     : {sys.platform}\n"
                f"  Detail : {detail.strip()}\n"
                + ("-" * 88)
                + "\n"
            )
            with cls.ERROR_LOG_PATH.open("a", encoding="utf-8", errors="replace") as fh:
                fh.write(entry)
        except Exception:
            pass

    @classmethod
    def emit(cls, msg: str, module: str = "lumiyaCore.py", level: str = "INFO") -> None:
        lvlColor = {
            "INFO": cls.CYAN,
            "WARNING": cls.YELLOW,
            "ERROR": cls.RED,
            "OK": cls.GREEN,
        }.get(level, cls.CYAN)

        cleanText = msg
        for code in (cls.RESET, cls.DIM, cls.CYAN, cls.GREEN, cls.YELLOW, cls.RED, cls.MAGENTA, cls.WHITE):
            cleanText = cleanText.replace(code, "")

        if level == "ERROR":
            cls.writeErrorLog("Runtime Error", cleanText, module=module)

        rightTag = f"{cls.DIM}{module} :: {lvlColor}{level}{cls.RESET}"
        rightLen = len(f"{module} :: {level}")
        padCount = max(2, cls.WIDTH - 2 - len(cleanText) - rightLen)
        sys.stdout.write(f"\r\x1b[2K  {msg}{' ' * padCount}{rightTag}\n")
        sys.stdout.flush()

    @classmethod
    def progress(cls, step: int, total: int, elapsed: float) -> None:
        pct = int(round((step / max(total, 1)) * 100))
        barWidth = 42
        filled = int(round(barWidth * (step / max(total, 1))))
        barStr = "\u2588" * filled + " " * (barWidth - filled)
        rate = step / max(elapsed, 1e-4)
        rem = (total - step) / max(rate, 1e-4)
        minEl, secEl = divmod(int(elapsed), 60)
        minRem, secRem = divmod(int(rem), 60)
        rateStr = f"{rate:5.2f}it/s" if rate >= 1.0 else f"{1.0 / max(rate, 1e-4):5.2f}s/it"
        line = (
            f"  {pct:3d}%|{cls.WHITE}{barStr}{cls.RESET}| "
            f"{step}/{total} [{minEl:02d}:{secEl:02d}<{minRem:02d}:{secRem:02d}, {rateStr}]"
        )
        sys.stdout.write(f"\r\x1b[2K{line}")
        if step >= total:
            sys.stdout.write("\n")
        sys.stdout.flush()
