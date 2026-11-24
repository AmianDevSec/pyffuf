<div align="center">

# PyFfuf

**Automate the "run ffuf → change `-w` → run again" loop. Feed PyFfuf a list of wordlists; it runs them all against the same URL template, one clean findings file per wordlist, while preserving ffuf's live progress bar and colors.**

[![Python](https://img.shields.io/badge/python-3.10%2B-blue?logo=python&logoColor=white)](https://www.python.org/)
[![License: MIT](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)
[![Platform](https://img.shields.io/badge/platform-Linux%20%7C%20macOS-lightgrey)](#requirements)
[![Made for pentesters](https://img.shields.io/badge/made%20for-pentesters-red)](#)

</div>

---

## The problem it solves

Real fuzzing rarely finishes after one wordlist. The workflow goes like this:

```bash
ffuf -u http://target/FUZZ -w small.txt -t 100 -ac
# too few hits → try another wordlist
ffuf -u http://target/FUZZ -w medium.txt -t 100 -ac
# still not satisfied → try another
ffuf -u http://target/FUZZ -w big.txt -t 100 -ac
# and another…
```

Every iteration means **stopping, editing `-w`, restarting**, and **copy-pasting findings** out of the terminal into a file. Multiply that by ten across a single engagement and you've lost an afternoon to typing paths and scrolling.

**PyFfuf turns that loop into one command.** You give it a **file that lists wordlists** (one path per line), and it runs ffuf once per wordlist against the same URL template — with the same options — collecting a clean findings file for each run.

```bash
# wordlists.txt
/usr/share/wordlists/dirb/common.txt
/usr/share/seclists/Discovery/Web-Content/raft-medium-directories.txt
/usr/share/seclists/Discovery/Web-Content/raft-large-directories.txt
/usr/share/seclists/Discovery/Web-Content/big.txt
```

```bash
pyffuf -f wordlists.txt -u 'http://target.htb/FUZZ' -opt -t 100 -ac
```

One command, four scans, four findings files. No editing `-w` between runs. No copy-paste between runs.

## What PyFfuf adds on top of that

Batching is the point — but it comes with the quality-of-life features you need when you're running several scans back-to-back:

- ✅ **One clean `.txt` per wordlist** — findings only, ANSI stripped, ready to grep or `notify`
- ✅ **A `.raw.txt` per run** — byte-for-byte stream (banner, progress, errors) for debugging
- ✅ **Faithful live output** — ffuf runs on a PTY, so you still see banner, colors, and the animated progress bar exactly like a manual run
- ✅ **Colors forced on** — ffuf doesn't colorize even on a TTY unless you pass `-c`; PyFfuf adds it for you
- ✅ **FUZZ keyword validated up front** — a friendly error before spawning ffuf, instead of "no FUZZ keyword found" × 12
- ✅ **Signal-safe** — `Ctrl+C` / `Ctrl+Z` / `SIGTERM` kill the child process group; no orphaned ffuf
- ✅ **No silent overwrites** — existing files get `_1`, `_2`, … appended
- ✅ **Batch-level summary** — per-run finding counts and a grand total at the end

```text
$ pyffuf -f wordlists.txt -u 'http://target.htb/FUZZ' -opt -t 100 -ac
[+] PyFfuf starting 4 scan(s) against http://target.htb/FUZZ
[1/4] ffuf -u http://target.htb/FUZZ -w /usr/share/wordlists/dirb/common.txt -t 100 -ac -c
        /'___\  /'___\           /'___\
       /\ \__/ /\ \__/  __  __  /\ \__/
       \ \ ,__\\ \ ,__\/\ \/\ \ \ \ ,__\
        \ \ \_/ \ \ \_/\ \ \_\ \ \ \ \_/
         \ \_\   \ \_\  \ \____/  \ \_\
          \/_/    \/_/   \/___/    \/_/

       v2.1.0-dev
________________________________________________

 :: Method           : GET
 :: URL              : http://target.htb/FUZZ
 :: Wordlist         : FUZZ: /usr/share/wordlists/dirb/common.txt
 :: Follow redirects : false
 :: Calibration      : true
 :: Timeout          : 10
 :: Threads          : 100
 :: Matcher          : Response status: 200-299,301,302,307,401,403,405,500
________________________________________________

admin                   [Status: 200, Size: 1234, Words: 123, Lines: 45, Duration: 12ms]
uploads                 [Status: 301, Size: 0, Words: 1, Lines: 1, Duration: 4ms]
:: Progress: [4614/4614] :: Job [1/1] :: 0 req/sec :: Duration: [0:00:05] :: Errors: 0 ::
[1/4] ✓ 2 finding(s)
Saved → pyffuf_out/target.htb_common_20261124_070548.txt
[2/4] ffuf -u http://target.htb/FUZZ -w …/raft-medium-directories.txt -t 100 -ac -c
...
```

---

## Features

| Feature | Description |
|---|---|
| 📚 **Batch wordlists** | `-f` is a file listing **paths** to wordlists; one ffuf run per line. |
| 🎯 **Findings-only `.txt`** | Every ffuf line is classified; only findings are saved to `<host>_<wordlist>_<ts>.txt`. |
| 📼 **Raw stream `.raw.txt`** | Byte-for-byte dump of the whole session (ANSI + `\r` intact) for replay. |
| 🎨 **Faithful live output** | ffuf runs on a PTY; banner, colors, and animated progress bar are preserved. |
| 🌈 **`-c` added by default** | ffuf requires `-c` to colorize; PyFfuf injects it unless you supply your own `-c`/`--color`. |
| 🔤 **FUZZ keyword validated** | URL must be `http(s)://…FUZZ…` — checked before any process is spawned. |
| 🛡️ **Signal-safe** | `SIGINT`, `SIGTSTP`, `SIGTERM` terminate the child process group; no orphaned ffuf. |
| 🗂️ **No silent overwrites** | Existing outputs get `_1`, `_2`, … appended. |
| 🔍 **ANSI-aware classifier** | Findings matched after ANSI stripping, so colorized lines still count. |
| 🧵 **Encoding-safe** | Incremental UTF-8 decoder handles multi-byte characters split across PTY reads. |
| 🪵 **Colorized logging** | Timestamped, colored log lines on stderr using stdlib `logging`. |

---

## Requirements

- **Python 3.10+**
- **Linux or macOS** (uses `pty`; Windows not supported)
- **ffuf 2.x+** on your `PATH`
- Standard library only — **no pip dependencies**

```bash
# Install ffuf
go install github.com/ffuf/ffuf/v2@latest

# or grab a release binary
# https://github.com/ffuf/ffuf/releases

# or via your package manager (Kali / Parrot)
sudo apt install ffuf -y
```

---

## Installation

### One-line installer (recommended)

```bash
git clone https://github.com/AmianDevSec/pyffuf.git
cd pyffuf
chmod +x setup.sh
./setup.sh
```

This copies `pyffuf.py` to `~/.local/bin/pyffuf`, makes it executable, and ensures `~/.local/bin` is on your `PATH`.

Reload your shell:

```bash
source ~/.bashrc     # or ~/.zshrc
```

### Manual install

```bash
chmod +x pyffuf.py
sudo mv pyffuf.py /usr/local/bin/pyffuf
```

### Uninstall

```bash
./setup.sh --uninstall
```

---

## Usage

```
pyffuf -f WORDLIST_FILE -u URL_WITH_FUZZ [-o OUTDIR] [-opt FFUF_FLAGS...]
```

| Flag | Default | Description |
|---|---|---|
| `-f`, `--file` | *(required)* | File listing wordlist **paths**, one per line. |
| `-u`, `--url` | *(required)* | Target URL template **containing `FUZZ`**, e.g. `http://target.htb/FUZZ` |
| `-o`, `--outdir` | `pyffuf_out` | Directory for the `.txt` and `.raw.txt` outputs. |
| `-opt`, `--options` | *(none)* | Everything after `-opt` is forwarded verbatim to ffuf. **Must come last.** |

### The FUZZ keyword

Unlike gobuster, ffuf has no subcommands — the **fuzzing mode is encoded in the URL** via the `FUZZ` keyword. PyFfuf validates this before running:

| URL | What it fuzzes |
|---|---|
| `http://target.htb/FUZZ` | Directory / file paths |
| `http://FUZZ.target.htb` | Virtual hosts / subdomains |
| `http://target.htb/?id=FUZZ` | Query parameters |
| `http://target.htb/api/FUZZ` | Nested paths |

### Examples

**Directory fuzzing across four wordlists:**

```bash
cat > wl.txt <<EOF
/usr/share/wordlists/dirb/common.txt
/usr/share/seclists/Discovery/Web-Content/raft-medium-directories.txt
/usr/share/seclists/Discovery/Web-Content/raft-large-directories.txt
/usr/share/seclists/Discovery/Web-Content/big.txt
EOF

pyffuf -f wl.txt -u 'http://target.htb/FUZZ' -opt -t 100 -ac
```

**Subdomain / vhost enumeration:**

```bash
pyffuf -f subdomains.txt -u 'http://FUZZ.target.htb' -opt -t 100 -ac
```

**Parameter fuzzing with a size filter:**

```bash
pyffuf -f params.txt -u 'http://target.htb/api?id=FUZZ' -opt -X GET -ac -fs 1234
```

**Dir scan with custom output folder and status filter:**

```bash
pyffuf -f dirs.txt -u 'https://target.htb/FUZZ' -o reports/acme \
  -opt -t 100 -ac -fc 404,403
```

**Passthrough to ffuf JSON output for post-processing:**

```bash
pyffuf -f wl.txt -u 'http://target.htb/FUZZ' \
  -opt -ac -of json -o /tmp/ffuf_findings.json
```

---

## Output files

For each wordlist, PyFfuf writes **two** files into `--outdir`:

```
pyffuf_out/
├── target.htb_common_20261124_070548.txt       ← findings only
├── target.htb_common_20261124_070548.raw.txt   ← full stream
├── target.htb_raft-medium_20261124_070549.txt
├── target.htb_raft-medium_20261124_070549.raw.txt
└── …
```

### `.txt` — findings only

Plain text, ANSI stripped, one finding per line:

```
admin                   [Status: 200, Size: 1234, Words: 123, Lines: 45, Duration: 12ms]
uploads                 [Status: 301, Size: 0, Words: 1, Lines: 1, Duration: 4ms]
```

Perfect for grepping, `notify`, `anew`, or pasting into a report.

### `.raw.txt` — full stream

Byte-for-byte dump including banner, progress bar (`\r`), ANSI colors, and errors. `cat` it to replay the session:

```bash
cat pyffuf_out/target.htb_common_*_*.raw.txt
```

---

## How it works (short version)

1. **Read the wordlist list** — one path per line; each becomes one ffuf run.
2. **PTY per run** — `pty.openpty()` gives ffuf a real TTY, so it renders exactly as in a shell.
3. **Read + echo** — the parent reads bytes from the master fd, echoes them to `sys.stdout` unchanged, and appends them to the raw buffer.
4. **Classify** — the stream is split on `\r` and `\n`; each completed line is tested against `FINDING_RE` (after ANSI stripping). Matches go into the findings list.
5. **Default `-c`** — ffuf requires `-c` for color even on a TTY; PyFfuf injects it unless you override.
6. **Signal handling** — `SIGINT`/`SIGTERM`/`SIGTSTP` terminate the child's **process group** (via `start_new_session=True`), so nothing is orphaned.
7. **Repeat** for each wordlist, then print a batch summary.

---

## Differences from PyBuster (gobuster wrapper)

If you also use **[PyBuster](https://github.com/AmianDevSec/pybuster)**, here's what changed and why:

| Aspect | PyBuster (gobuster) | PyFfuf (ffuf) | Why |
|---|---|---|---|
| **`-m/--mode` flag** | `dir`, `dns`, `vhost`, `fuzz`, `s3` | **Removed** | ffuf has no subcommands — mode is encoded in the URL via `FUZZ` |
| **URL validation** | `http(s)://host` | **`http(s)://…FUZZ…`** | ffuf refuses to run without a FUZZ keyword |
| **Finding regex** | `(Status: NNN)` | **`[Status: NNN`** | ffuf uses **brackets** and **no closing paren** |
| **Progress regex** | `Progress: N N` | **`Progress: [N/M]`** | ffuf brackets both counters |
| **Default filters** | `-b 400,404,410` / `--exclude-status` | **None** | ffuf's philosophy is user-controlled filtering; `-fc`, `-ac`, `-fs` are opt-in |
| **Color default** | auto-detects TTY | **`-c` added** | ffuf does **not** colorize without `-c` even on a TTY |
| **Output filename** | `host_mode_wordlist_ts.txt` | **`host_wordlist_ts.txt`** | No mode; `FUZZ` in host becomes `star` |

---

## When should you use PyFfuf?

**Use PyFfuf when** you're running **ffuf against multiple wordlists for the same URL template** — the "let me try another wordlist" loop. That's the exact workflow it was built for.

**Don't use PyFfuf when** you only need a single scan — plain `ffuf` is simpler and has zero wrapper overhead.

**Don't use PyFfuf when** you need multi-target orchestration (one wordlist × many URLs) — that's a different loop, and tools like `httpx` + `xargs`, or ffuf's own multi-wordlist support via `-w wl1:W1 -w wl2:W2`, handle it better. PyFfuf is **one URL template × many wordlists**.

---

## Contributing

Bug reports, feature ideas, and PRs are welcome.

1. **Fork** the repo and create a branch: `git checkout -b feat/my-idea`
2. **Add tests** if you touch the classifier (`FINDING_RE`, `is_finding`) — that's the most fragile part.
3. **Smoke test** against a lab target before opening the PR.
4. **Open a PR** with a short description of the change and the *why*.

### Ideas welcome

- **Multi-target mode** (`-U targets.txt` for one wordlist × many URLs)
- **Resume-from-offset** support
- **Diff mode** comparing two runs against the same target
- **`notify` integration** for Telegram/Discord/Slack on each finding
- **Native JSON parsing** — leverage `-of json` for structured findings instead of regex-matching the text stream
- **Windows support** via ConPTY

---

## Known limitations

- **Windows is not supported** — `pty` is POSIX-only.
- **One URL template × many wordlists is the only batch axis.** PyFfuf doesn't do "one wordlist × many URLs" — pair it with `httpx` / `xargs` if you need that.
- **Verbose mode (`-v`) splits findings across lines.** With `-v`, ffuf prints `[Status: …]` on one line and `| URL | …` on the next. `is_finding()` catches the `[Status:` line, but the follow-up lines are only preserved in `.raw.txt`. If you need full verbose findings parsed cleanly, use ffuf's JSON output via `-opt -of json -o file.json`.
- **Very fast tools** may saturate `os.read()` — buffering is handled, but throughput can lag slightly behind the child.
- **`#` comment lines in the wordlist file are not skipped** — plain paths only.

---

## License

MIT — see [LICENSE](LICENSE).

---

## Credits

- **[ffuf](https://github.com/ffuf/ffuf)** by Joona Hoikkala — the actual engine.
- Built out of the very real frustration of editing `-w` fifteen times in one engagement.
- Sibling project: **[PyBuster](https://github.com/AmianDevSec/pybuster)** — the same idea, for gobuster.

<div align="center">

**If PyFfuf saves you a lap of "change `-w`, run again," drop a ⭐.**

</div>
