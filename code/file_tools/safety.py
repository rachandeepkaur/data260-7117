"""Safety gate for the bash tool (HW7 Part 6.I) - pure Python, no model needed.

    SAFE_PREFIXES                     allow-list of read-only command prefixes
    is_destructive(command) -> bool   independent deny-list check
    confirm_bash(command, auto_approve=False) -> GateDecision(allowed, decision, reason)

The deny-list is checked FIRST and independently of the allow-list, so a
destructive command is blocked even when it starts with a safe prefix
(`ls > /etc/hosts`, `ls; rm -fr build`). Destructive categories:

    recursive_deletion     rm -r/-R/--recursive (any flag order), find -delete / -exec rm, git clean -d
    privilege_escalation   sudo, su, doas, pkexec
    permission_change      chmod, chown, chgrp, chflags, setfacl, chattr
    raw_device_write       dd of=/dev/..., redirect or tee into /dev/<device>
    filesystem_creation    mkfs*, newfs*, mke2fs, mkswap, fdisk/sfdisk/parted/wipefs, diskutil erase*/partition*
    root_redirection       > / >> / tee into an absolute path (outside the sandbox), except /dev/null etc.

Compound commands are split on ; && || | & and newlines, and $(...) / backtick
substitutions are checked too, so each piece must pass on its own.
"""
from __future__ import annotations

import re
import shlex
from dataclasses import dataclass, field

SAFE_PREFIXES: tuple[str, ...] = (
    "ls", "pwd", "cat", "head", "tail", "wc", "grep", "rg", "find", "echo", "sort", "uniq", "diff",
    "stat", "file", "which", "date", "whoami", "tree",
    "git status", "git diff", "git log", "git show",
    "python --version", "python3 --version",
)

# & is a separator except inside a redirection such as 2>&1 or &>file.
_SPLIT_RE = re.compile(r"\|\||&&|[;|\n]|(?<![>&])&(?!>)")
_SUBST_RE = re.compile(r"\$\(([^()]*)\)|`([^`]*)`")
_HARMLESS_DEVICES = ("/dev/null", "/dev/stdout", "/dev/stderr", "/dev/tty", "/dev/zero", "/dev/random", "/dev/urandom")
_REDIRECT_RE = re.compile(r"(?:\d?>>?|&>)\s*(\S+)")
_TEE_RE = re.compile(r"\btee\s+(?:-\w+\s+)*(\S+)")


@dataclass(frozen=True)
class GateDecision:
    allowed: bool
    reason: str
    categories: tuple[str, ...] = field(default_factory=tuple)

    @property
    def decision(self) -> str:
        """'allow' or 'block'."""
        return "allow" if self.allowed else "block"

    def to_dict(self) -> dict:
        """JSON-serializable form."""
        return {"decision": self.decision, "allowed": self.allowed, "reason": self.reason,
                "categories": list(self.categories)}


def split_command(command: str) -> list[str]:
    """Every simple command inside `command`, including $(...) / `...` substitutions."""
    pieces = [command]
    for m in _SUBST_RE.finditer(command):
        pieces.append(m.group(1) or m.group(2) or "")
    segments: list[str] = []
    for piece in pieces:
        segments.extend(s.strip() for s in _SPLIT_RE.split(_SUBST_RE.sub(" ", piece)) if s.strip())
    return segments


def _tokens(segment: str) -> list[str]:
    try:
        return shlex.split(segment)
    except ValueError:  # unbalanced quotes - fall back to whitespace
        return segment.split()


def _strip_wrappers(tokens: list[str]) -> list[str]:
    """Drop env assignments and `env`/`command`/`nohup`/`time` wrappers before the real command."""
    i = 0
    wrappers = ("env", "command", "nohup", "time", "exec")
    while i < len(tokens) and (re.match(r"^\w+=", tokens[i]) or tokens[i] in wrappers):
        i += 1
    return tokens[i:]


def _segment_categories(segment: str) -> set[str]:
    cats: set[str] = set()
    tokens = _tokens(segment)
    words = _strip_wrappers(tokens)
    prog = words[0].rsplit("/", 1)[-1].lower() if words else ""
    args = words[1:]

    if prog in ("sudo", "su", "doas", "pkexec"):
        cats.add("privilege_escalation")
        inner = list(args)
        while inner and inner[0].startswith("-"):  # sudo's own options (-u/-g take a value)
            inner = inner[2:] if inner[0] in ("-u", "-g", "-C") else inner[1:]
        if inner:
            cats |= _segment_categories(" ".join(shlex.quote(a) for a in inner))
    if prog == "rm" and any(a == "--recursive" or (re.match(r"^-[a-zA-Z]+$", a) and "r" in a.lower()) for a in args):
        cats.add("recursive_deletion")
    if prog == "find" and any(a in ("-delete",) for a in args):
        cats.add("recursive_deletion")
    if prog == "find" and "-exec" in args and any(a.rsplit("/", 1)[-1] in ("rm", "shred") for a in args):
        cats.add("recursive_deletion")
    if prog == "git" and args[:1] == ["clean"] and any(re.match(r"^-\w*d", a) for a in args[1:]):
        cats.add("recursive_deletion")
    if prog in ("chmod", "chown", "chgrp", "chflags", "setfacl", "chattr"):
        cats.add("permission_change")
    if prog == "dd" and any(a.startswith("of=/dev/") and not a[3:].startswith(_HARMLESS_DEVICES) for a in args):
        cats.add("raw_device_write")
    if prog.startswith(("mkfs", "newfs")) or prog in ("mke2fs", "mkswap", "fdisk", "sfdisk", "parted", "wipefs"):
        cats.add("filesystem_creation")
    if prog == "diskutil" and args and re.match(r"^(erase|partition|reformat|zerodisk|randomdisk)", args[0], re.I):
        cats.add("filesystem_creation")

    for target in _REDIRECT_RE.findall(segment) + _TEE_RE.findall(segment):
        target = target.strip("'\"")
        if target.startswith("&") or not target.startswith(("/", "~")):
            continue  # fd duplication (2>&1) or a path relative to the sandbox
        if target.startswith(_HARMLESS_DEVICES):
            continue
        cats.add("raw_device_write" if target.startswith("/dev/") else "root_redirection")
    return cats


def destructive_categories(command: str) -> list[str]:
    """Sorted deny-list categories matched anywhere in `command`."""
    cats: set[str] = set()
    for segment in split_command(command):
        cats |= _segment_categories(segment)
    return sorted(cats)


def is_destructive(command: str) -> bool:
    """Deny-list check, independent of SAFE_PREFIXES."""
    return bool(destructive_categories(command))


def matches_safe_prefix(command: str) -> bool:
    """True only if EVERY simple command starts with an allow-listed prefix (on a word boundary)."""
    segments = split_command(command)
    if not segments:
        return False
    for segment in segments:
        words = " ".join(_strip_wrappers(_tokens(segment)))
        if not any(words == p or words.startswith(p + " ") for p in SAFE_PREFIXES):
            return False
    return True


def confirm_bash(command: str, auto_approve: bool = False) -> GateDecision:
    """Allow/block decision with a short reason.

    auto_approve=True is the explicit confirmation: it is the only way a
    destructive or non-allow-listed command is allowed."""
    if not command or not command.strip():
        return GateDecision(False, "empty command")
    cats = destructive_categories(command)
    if cats:
        if auto_approve:
            return GateDecision(True, f"destructive ({', '.join(cats)}) - allowed only because confirmation "
                                "was supplied", tuple(cats))
        return GateDecision(False, f"destructive ({', '.join(cats)}) - requires explicit confirmation", tuple(cats))
    if matches_safe_prefix(command):
        return GateDecision(True, "read-only command matching SAFE_PREFIXES")
    if auto_approve:
        return GateDecision(True, "not in SAFE_PREFIXES - allowed by explicit confirmation")
    return GateDecision(False, "not in SAFE_PREFIXES - requires explicit confirmation")
