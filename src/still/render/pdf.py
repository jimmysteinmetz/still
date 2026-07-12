"""HTML → print-ready PDF.

WeasyPrint is the primary engine (and the easy dependency for a Linux Cloud Run
image later); headless Chrome is the fallback. Both run as subprocesses with a
timeout so a hung renderer can never brick the daily edition — WeasyPrint's
multicol layout has been known to infinite-loop on bad CSS, which an in-process
try/except cannot recover from.

On macOS, WeasyPrint's pango/gobject dylibs are only found when
DYLD_FALLBACK_LIBRARY_PATH includes /opt/homebrew/lib. We inject that into the
subprocess env automatically (see `_weasyprint_env`), so `still build` uses the
primary engine without the caller exporting anything; Chrome stays as the
fallback if WeasyPrint is genuinely missing or hangs.
"""

import logging
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

logger = logging.getLogger(__name__)

# WeasyPrint's pango/gobject dylibs live here on a Homebrew macOS install and are
# not on the default loader path. Injected only if the dir exists, so Linux
# (Cloud Run) — where the system loader already finds the libs — is untouched.
HOMEBREW_LIB = "/opt/homebrew/lib"

CHROME_CANDIDATES = [
    "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
    "chromium",
    "google-chrome",
]

WEASYPRINT_TIMEOUT_S = 45
CHROME_TIMEOUT_S = 60


def html_to_pdf(html: str, out_path: Path) -> str:
    """Write a PDF; returns the engine used ('weasyprint' or 'chrome')."""
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as tmp:
        src = Path(tmp) / "edition.html"
        src.write_text(html)
        if _weasyprint_pdf(src, out_path):
            return "weasyprint"
        _chrome_pdf(src, out_path)
        return "chrome"


def _weasyprint_env() -> dict[str, str]:
    """Parent env plus the Homebrew libdir on DYLD_FALLBACK_LIBRARY_PATH (macOS),
    so the WeasyPrint subprocess finds its dylibs without the caller exporting it."""
    env = dict(os.environ)
    if Path(HOMEBREW_LIB).is_dir():
        parts = [p for p in env.get("DYLD_FALLBACK_LIBRARY_PATH", "").split(os.pathsep) if p]
        if HOMEBREW_LIB not in parts:
            parts.insert(0, HOMEBREW_LIB)
        env["DYLD_FALLBACK_LIBRARY_PATH"] = os.pathsep.join(parts)
    return env


def _weasyprint_pdf(src: Path, out_path: Path) -> bool:
    """Render via the WeasyPrint CLI. Returns False (so caller falls back) on any
    failure: missing dylibs (non-zero exit) or a layout hang (timeout kill)."""
    try:
        subprocess.run(
            [sys.executable, "-m", "weasyprint", str(src), str(out_path)],
            check=True,
            capture_output=True,
            timeout=WEASYPRINT_TIMEOUT_S,
            env=_weasyprint_env(),
        )
    except subprocess.TimeoutExpired:
        logger.warning("weasyprint exceeded %ss; falling back to Chrome", WEASYPRINT_TIMEOUT_S)
        return False
    except (subprocess.SubprocessError, OSError) as e:
        logger.warning("weasyprint unavailable (%s); falling back to Chrome", e)
        return False
    return out_path.exists()


def _chrome_pdf(src: Path, out_path: Path) -> None:
    chrome = next((c for c in CHROME_CANDIDATES if shutil.which(c) or Path(c).exists()), None)
    if chrome is None:
        raise RuntimeError(
            "No PDF engine: weasyprint failed and Chrome not found. "
            "Try `brew install pango` and run with "
            "DYLD_FALLBACK_LIBRARY_PATH=/opt/homebrew/lib"
        )
    subprocess.run(
        [
            chrome,
            "--headless",
            "--disable-gpu",
            "--no-pdf-header-footer",
            f"--print-to-pdf={out_path}",
            src.as_uri(),
        ],
        check=True,
        capture_output=True,
        timeout=CHROME_TIMEOUT_S,
    )
