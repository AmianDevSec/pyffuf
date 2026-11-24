#!/usr/bin/env python3
"""PyFfuf — a colorized ffuf wrapper that batches wordlists in one command.

Solves the "run ffuf -> change -w -> run again" loop: feed it a file listing
multiple wordlists, and it runs ffuf once per wordlist against the same URL
template, saving a clean findings file for each run.

Differences from PyBuster (gobuster wrapper):
  * ffuf has no subcommands — the "mode" is encoded in the URL via FUZZ:
        http://target.com/FUZZ          -> directory brute
        http://FUZZ.target.com          -> vhost / subdomain brute
        http://target.com/?id=FUZZ      -> parameter fuzzing
  * ffuf does NOT colorize by default; we add -c unless the user overrides.
  * ffuf finding format is  [Status: 200, Size: 1234, ...]  (brackets, no parens).
"""

from __future__ import annotations

import argparse as arg
import codecs
import logging
import os
import pty
import re
import select
import shutil
import signal
import subprocess as sub
import sys
from datetime import datetime
from pathlib import Path
from urllib.parse import urlparse


# ─────────────────────────── Colors ───────────────────────────
class C:
    """ANSI colors; auto-disabled when not a TTY or NO_COLOR is set."""
    _on = sys.stdout.isatty() and os.environ.get("NO_COLOR") is None

    RESET   = "\033[0m"  if _on else ""
    BOLD    = "\033[1m"  if _on else ""
    DIM     = "\033[2m"  if _on else ""
    RED     = "\033[31m" if _on else ""
    GREEN   = "\033[32m" if _on else ""
    YELLOW  = "\033[33m" if _on else ""
    BLUE    = "\033[34m" if _on else ""
    MAGENTA = "\033[35m" if _on else ""
    CYAN    = "\033[36m" if _on else ""


# ─────────────────────────── Logging ──────────────────────────
class ColorFormatter(logging.Formatter):
    LEVEL_COLORS = {
        logging.DEBUG:    C.DIM,
        logging.INFO:     C.CYAN,
        logging.WARNING:  C.YELLOW,
        logging.ERROR:    C.RED,
        logging.CRITICAL: C.BOLD + C.RED,
    }

    def format(self, record: logging.LogRecord) -> str:
        color = self.LEVEL_COLORS.get(record.levelno, "")
        record.levelname = f"{color}{record.levelname:<8}{C.RESET}"
        return super().format(record)


logger = logging.getLogger("pyffuf")
_handler = logging.StreamHandler(sys.stderr)
_handler.setFormatter(ColorFormatter(
    f"{C.DIM}%(asctime)s{C.RESET} %(levelname)s %(message)s",
    datefmt="%H:%M:%S",
))
logger.addHandler(_handler)
logger.setLevel(logging.INFO)


# ────────────────────── Finding classifiers ───────────────────
ANSI_RE = re.compile(r"\x1b\[[0-9;]*[A-Za-z]")

# ffuf finding formats (both match):
#   Default : admin     [Status: 200, Size: 1234, Words: 123, Lines: 45, Duration: 12ms]
#   Verbose : [Status: 200, Size: 1234, Words: 123, Lines: 45, Duration: 12ms]
#             | URL | http://target.com/admin
FINDING_RE = re.compile(r"\[Status:\s*\d{3}", re.IGNORECASE)

# ffuf progress line:
#   :: Progress: [4614/4614] :: Job [1/1] :: 0 req/sec :: Duration: [0:00:05] :: Errors: 0 ::
PROGRESS_RE = re.compile(r"Progress:\s*\[\s*\d+\s*/\s*\d+\s*\]", re.IGNORECASE)


def _strip_ansi(s: str) -> str:
    return ANSI_RE.sub("", s)


def is_finding(line: str) -> bool:
    return bool(FINDING_RE.search(_strip_ansi(line)))


def is_progress(line: str) -> bool:
    return bool(PROGRESS_RE.search(_strip_ansi(line)))


# ────────────────────────── Helpers ───────────────────────────
def is_ffuf_url(s: str | None) -> bool:
    """URL is valid http(s) AND contains the FUZZ keyword."""
    if not s or "FUZZ" not in s:
        return False
    try:
        r = urlparse(s)
        return r.scheme in ("http", "https") and bool(r.netloc)
    except (ValueError, AttributeError):
        return False


def is_file_exists(filename: str | None) -> bool:
    return bool(filename) and os.path.isfile(filename)


def read_wordlist(filename: str) -> list[str]:
    with open(filename, "r", encoding="utf-8", errors="replace") as f:
        return [line.strip() for line in f if line.strip()]


def save_output(filename: str, contents: str) -> Path:
    """Write contents to filename, never overwriting silently."""
    p = Path(filename)
    if p.exists():
        stem, suffix = p.stem, p.suffix
        i = 1
        while p.exists():
            p = p.with_name(f"{stem}_{i}{suffix}")
            i += 1
        logger.warning("Output already existed; writing to %s",
                       C.YELLOW + str(p) + C.RESET)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(contents, encoding="utf-8")
    return p


def _sanitize_host(url: str) -> str:
    """Derive a filesystem-safe prefix from the ffuf URL (FUZZ -> 'star')."""
    netloc = urlparse(url).netloc or "target"
    return netloc.replace(":", "_").replace("FUZZ", "star")


# ────────────────────── Active-child handles ──────────────────
_active_proc: sub.Popen | None = None
_active_fd: int | None = None


def _terminate_active(signum=None, frame=None) -> None:
    """Kill the running ffuf (whole process group) if any."""
    global _active_proc, _active_fd

    if _active_proc is not None and _active_proc.poll() is None:
        try:
            os.killpg(os.getpgid(_active_proc.pid), signal.SIGTERM)
        except (ProcessLookupError, PermissionError):
            try:
                _active_proc.terminate()
            except Exception:
                pass

        try:
            _active_proc.wait(timeout=2)
        except sub.TimeoutExpired:
            try:
                os.killpg(os.getpgid(_active_proc.pid), signal.SIGKILL)
            except (ProcessLookupError, PermissionError):
                try:
                    _active_proc.kill()
                except Exception:
                    pass

    if _active_fd is not None:
        try:
            os.close(_active_fd)
        except OSError:
            pass
        _active_fd = None

    _active_proc = None


# ──────────────────────── Live runner ─────────────────────────
def run_live(command: list[str]) -> tuple[str, str, int]:
    """
    Run command attached to a PTY so ffuf renders its banner, progress bar
    and colors exactly like in a real terminal.

    Returns (findings_text, raw_text, exit_code).
    """
    global _active_proc, _active_fd

    master_fd, slave_fd = pty.openpty()
    proc = sub.Popen(
        command,
        stdin=sub.DEVNULL,
        stdout=slave_fd,
        stderr=slave_fd,
        close_fds=True,
        start_new_session=True,     # own process group → killable as a unit
    )
    os.close(slave_fd)
    _active_proc = proc
    _active_fd = master_fd

    raw_parts: list[str] = []
    findings: list[str] = []
    decoder = codecs.getincrementaldecoder("utf-8")("replace")
    buf = ""

    def process_text(text: str) -> None:
        nonlocal buf
        raw_parts.append(text)
        sys.stdout.write(text)
        sys.stdout.flush()
        for ch in text:
            if ch in ("\r", "\n"):
                line = buf
                buf = ""
                if line and is_finding(line):
                    findings.append(_strip_ansi(line).rstrip() + "\n")
            else:
                buf += ch

    try:
        while True:
            r, _, _ = select.select([master_fd], [], [], 0.1)
            if master_fd in r:
                try:
                    chunk = os.read(master_fd, 4096)
                except OSError:
                    chunk = b""
                if not chunk:
                    break
                process_text(decoder.decode(chunk))

            if proc.poll() is not None:
                while True:
                    try:
                        chunk = os.read(master_fd, 4096)
                    except OSError:
                        chunk = b""
                    if not chunk:
                        break
                    process_text(decoder.decode(chunk))
                tail = decoder.decode(b"", final=True)
                if tail:
                    process_text(tail)
                break
    finally:
        if buf and is_finding(buf):
            findings.append(_strip_ansi(buf).rstrip() + "\n")
        try:
            os.close(master_fd)
        except OSError:
            pass

        if proc.poll() is None:
            try:
                os.killpg(os.getpgid(proc.pid), signal.SIGTERM)
            except (ProcessLookupError, PermissionError):
                try:
                    proc.terminate()
                except Exception:
                    pass

        try:
            proc.wait(timeout=2)
        except sub.TimeoutExpired:
            try:
                os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
            except (ProcessLookupError, PermissionError):
                try:
                    proc.kill()
                except Exception:
                    pass
            proc.wait()

        _active_proc = None
        _active_fd = None

    return "".join(findings), "".join(raw_parts), proc.returncode


# ──────────────────────────── CLI ─────────────────────────────
def build_parser() -> arg.ArgumentParser:
    p = arg.ArgumentParser(
        prog="pyffuf",
        description="PyFfuf — a colorized ffuf wrapper that batches wordlists in one command.",
        epilog=(
            "The URL must contain the FUZZ keyword. Examples:\n"
            "  http://target.com/FUZZ       (directory brute)\n"
            "  http://FUZZ.target.com       (vhost / subdomain brute)\n"
            "  http://target.com/?id=FUZZ   (parameter fuzzing)\n"
            "\n"
            "Anything after -opt is forwarded verbatim to ffuf, e.g.:\n"
            "  pyffuf -f wl.txt -u http://t/FUZZ -opt -t 100 -ac -fc 404"
        ),
        formatter_class=arg.ArgumentDefaultsHelpFormatter,
    )
    p.add_argument("-f", "--file", required=True,
                   help="File listing wordlist paths, one per line.")
    p.add_argument("-u", "--url", required=True,
                   help="Target URL template containing the FUZZ keyword.")
    p.add_argument("-o", "--outdir", default="pyffuf_out",
                   help="Directory where per-wordlist outputs are saved.")
    p.add_argument("-opt", "--options", nargs=arg.REMAINDER,
                   help="Extra flags forwarded to ffuf (must come last).")
    return p


def _ffuf_defaults(user_opts: list[str]) -> list[str]:
    """Sane defaults ffuf doesn't apply itself."""
    defaults: list[str] = []
    # ffuf disables colors by default even on a TTY — force them on.
    if "-c" not in user_opts and "--color" not in user_opts:
        defaults.append("-c")
    return defaults


# ────────────────────────── Signals ───────────────────────────
def _install_signal_handlers() -> None:
    def _sigint(signum, frame):
        logger.warning("Interrupted (SIGINT) — terminating ffuf…")
        _terminate_active(signum, frame)
        sys.exit(130)

    def _sigterm(signum, frame):
        logger.warning("Terminated (SIGTERM) — shutting down…")
        _terminate_active(signum, frame)
        sys.exit(143)

    def _sigtstp(signum, frame):
        logger.warning("Suspended (SIGTSTP) — terminating ffuf to avoid orphan.")
        _terminate_active(signum, frame)
        signal.signal(signal.SIGTSTP, signal.SIG_DFL)
        os.kill(os.getpid(), signal.SIGTSTP)

    signal.signal(signal.SIGINT,  _sigint)
    signal.signal(signal.SIGTERM, _sigterm)
    signal.signal(signal.SIGTSTP, _sigtstp)


# ─────────────────────────── Main ─────────────────────────────
def main() -> int:
    _install_signal_handlers()

    args = build_parser().parse_args()

    # Fail fast before touching anything else
    if not shutil.which("ffuf"):
        logger.error("ffuf not found on PATH")
        return 2
    if not is_file_exists(args.file):
        logger.error("Wordlist list not found: %s", args.file)
        return 2
    if not is_ffuf_url(args.url):
        logger.error(
            "Invalid ffuf URL: %s\n"
            "  • must be http(s)\n"
            "  • must contain the FUZZ keyword (e.g. http://target.com/FUZZ)",
            args.url,
        )
        return 2

    try:
        wordlists = read_wordlist(args.file)
    except OSError as e:
        logger.error("Cannot read wordlist list: %s", e)
        return 2

    if not wordlists:
        logger.warning("Wordlist list %s is empty.", args.file)
        return 1

    out_dir = Path(args.outdir)
    out_dir.mkdir(parents=True, exist_ok=True)

    user_opts = args.options or []
    options = [*_ffuf_defaults(user_opts), *user_opts]

    total = len(wordlists)
    logger.info("%s Starting %d scan(s) against %s",
                C.BOLD + C.MAGENTA + "PyFfuf" + C.RESET,
                total, C.CYAN + args.url + C.RESET)

    failures = 0
    grand_total_findings = 0
    host = _sanitize_host(args.url)

    for idx, wordlist in enumerate(wordlists, 1):
        wordlist = os.path.expanduser(wordlist)
        if not is_file_exists(wordlist):
            logger.warning("[%d/%d] Skipping missing wordlist: %s",
                           idx, total, wordlist)
            failures += 1
            continue

        cmd = ["ffuf", "-u", args.url, "-w", wordlist, *options]
        logger.info("[%d/%d] %s", idx, total, C.DIM + " ".join(cmd) + C.RESET)

        findings_text, raw_text, code = run_live(cmd)

        n = findings_text.count("\n")
        grand_total_findings += n

        if code != 0:
            logger.error("ffuf exited with code %d for %s", code, wordlist)
            failures += 1

        logger.info("[%d/%d] %s %d finding(s)",
                    idx, total, C.GREEN + "✓" + C.RESET, n)

        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        base = Path(wordlist).stem
        prefix = out_dir / f"{host}_{base}_{stamp}"

        saved = save_output(str(prefix) + ".txt", findings_text)
        save_output(str(prefix) + ".raw.txt", raw_text)
        logger.info("Saved → %s", C.GREEN + str(saved) + C.RESET)

    if failures:
        logger.warning("Done with %d failure(s); %d finding(s) total.",
                       failures, grand_total_findings)
        return 1

    logger.info("%s All scans completed successfully — %d finding(s) total.",
                C.GREEN + C.BOLD + "✓" + C.RESET, grand_total_findings)
    return 0


if __name__ == "__main__":
    sys.exit(main())
