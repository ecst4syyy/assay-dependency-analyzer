"""Turn raw user input into candidate package names (SPEC §7.1).

Every name that leaves this module has passed the strict name validation,
so it is safe to place (percent-encoded) into a registry URL. Anything that
looks like a path, URL, VCS reference or local file is discarded and counted
as rejected, so the UI can tell the user what was ignored.
"""

import json
import re
import shlex
import sys
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import NamedTuple

from packaging.requirements import InvalidRequirement, Requirement

ECOSYSTEMS = ("pypi", "npm")
MAX_PACKAGES = 200
MAX_INPUT_BYTES = 256 * 1024
MAX_JSON_DEPTH = 20
ALLOWED_UPLOAD_SUFFIXES = (".txt", ".json")

ALIASES_FILE = Path(__file__).resolve().parents[2] / "data" / "aliases.json"

# SPEC §11 name rule, tightened to require a leading letter or digit so that
# names such as "..", ".env" or "-rf" can never reach a URL.
NAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,213}$")
# Scoped npm names (@scope/name), see DECISIONS D-09.
NPM_SCOPED_RE = re.compile(r"^@[a-z0-9][a-z0-9._~-]*/[a-z0-9][a-z0-9._~-]*$")
MAX_NAME_LENGTH = 214

PYPI_VERSION_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9.+!_-]{0,63}$")
NPM_EXACT_VERSION_RE = re.compile(r"^\d+\.\d+\.\d+(?:[-+][0-9A-Za-z.-]{1,40})?$")

# Install commands only count where a command can actually start: the
# beginning of a line, inside backticks, after a shell prompt or notebook
# "!", after && or ;, or after a Dockerfile RUN. Without this, prose such
# as "then pip install the dependencies" yields packages called "the" and
# "dependencies".
_CMD_START = r"(?:^|`|\$|!|%|&&|;|\|\|)[ \t]*(?:RUN[ \t]+)?(?:sudo[ \t]+)?"
# Real install lines are short. The cap keeps shlex (pure Python, one
# character at a time) from chewing on a 256 KB "command".
_CMD_ARGS = r"(?P<args>[^\n;&|`)#]{0,2000})"
PIP_RE = re.compile(
    _CMD_START
    + r"(?:(?:python[\d.]*|py)[ \t]+-m[ \t]+)?(?:uv[ \t]+)?pip[\d.]*[ \t]+install\b"
    + _CMD_ARGS,
    re.IGNORECASE | re.MULTILINE,
)
PY_TOOL_RE = re.compile(
    _CMD_START + r"(?:(?:poetry|uv|pdm)[ \t]+add|pipenv[ \t]+install)\b" + _CMD_ARGS,
    re.IGNORECASE | re.MULTILINE,
)
NPM_RE = re.compile(
    _CMD_START + r"(?:npm[ \t]+(?:install|i|add)|yarn[ \t]+(?:global[ \t]+)?add|"
    r"pnpm[ \t]+(?:add|install|i)|bun[ \t]+(?:add|install|i))\b" + _CMD_ARGS,
    re.IGNORECASE | re.MULTILINE,
)

# Flags whose next token is a value, not a package.
PIP_VALUE_FLAGS = frozenset(
    {
        "-r", "--requirement", "-c", "--constraint", "-e", "--editable", "-i",
        "--index-url", "--extra-index-url", "-f", "--find-links", "-t", "--target",
        "--prefix", "--root", "--src", "--upgrade-strategy", "--python-version",
        "--platform", "--only-binary", "--no-binary", "--progress-bar", "--log",
        "--cache-dir", "--trusted-host", "--proxy", "--retries", "--timeout",
        "--group", "-G", "--source",
    }
)  # fmt: skip
NPM_VALUE_FLAGS = frozenset({"--registry", "--prefix", "--tag", "-w", "--workspace", "--cache"})

# Python imports must be the whole line, which keeps JavaScript's
# `import React from 'react'` and English prose from matching.
PY_IMPORT_RE = re.compile(
    r"^[ \t]*import[ \t]+(?P<mods>[\w.]+(?:[ \t]+as[ \t]+\w+)?"
    r"(?:[ \t]*,[ \t]*[\w.]+(?:[ \t]+as[ \t]+\w+)?)*)[ \t]*;?[ \t]*(?:#.*)?$",
    re.MULTILINE,
)
PY_FROM_RE = re.compile(
    r"^[ \t]*from[ \t]+(?P<mod>\.*[\w.]+)[ \t]+import[ \t]+\(?(?P<names>[\w \t,]*)", re.MULTILINE
)
# For these, the distribution is named after what is imported from them:
# `from google.cloud import storage` needs google-cloud-storage.
NAMESPACE_ROOTS = frozenset({"google", "google.cloud", "azure", "azure.storage", "azure.keyvault"})

JS_REQUIRE_RE = re.compile(r"\brequire\(\s*(['\"])(?P<spec>[^'\"\n]{1,300})\1\s*\)")
JS_FROM_RE = re.compile(
    r"\b(?:import|export)\b[^'\";]{0,500}?\bfrom\s*(['\"])(?P<spec>[^'\"\n]{1,300})\1"
)
JS_BARE_IMPORT_RE = re.compile(r"\bimport\s*\(?\s*(['\"])(?P<spec>[^'\"\n]{1,300})\1")

NODE_BUILTINS = frozenset(
    """assert async_hooks buffer child_process cluster console constants crypto dgram
    diagnostics_channel dns domain events fs http http2 https inspector module net os path
    perf_hooks process punycode querystring readline repl stream string_decoder sys timers
    tls trace_events tty url util v8 vm wasi worker_threads zlib test""".split()
)


class ParseError(ValueError):
    """Input that cannot be parsed at all. The message is safe to show users."""


class PackageRef(NamedTuple):
    ecosystem: str
    name: str
    version: str | None


@dataclass
class ParseResult:
    packages: list[PackageRef] = field(default_factory=list)
    rejected: int = 0
    truncated: bool = False


@lru_cache(maxsize=1)
def _alias_tables():
    data = json.loads(ALIASES_FILE.read_text(encoding="utf-8"))
    return dict(data.get("pypi", {})), dict(data.get("pypi_dotted", {}))


def import_to_distribution(module):
    """Map an imported module path to the PyPI distribution that provides it.

    Returns None for the standard library. Most imports map through their
    top-level name, but a few namespace packages need the dotted path:
    `google.cloud.storage` is google-cloud-storage, not the unrelated
    "google" package.
    """
    parts = module.split(".")
    top = parts[0]
    if not top or top in sys.stdlib_module_names or top == "__future__":
        return None
    aliases, dotted = _alias_tables()
    for length in (2, 3):
        prefix = ".".join(parts[:length])
        if len(parts) >= length and prefix in dotted:
            return dotted[prefix]
    if parts[:2] == ["google", "cloud"] and len(parts) >= 3:
        return f"google-cloud-{parts[2]}"
    return aliases.get(top, top)


def normalise_name(ecosystem, name):
    """Lowercase; for PyPI also apply PEP 503 (runs of -, _ and . become -)."""
    if ecosystem == "pypi":
        return re.sub(r"[-_.]+", "-", name).lower()
    return name.lower()


def is_valid_name(ecosystem, name):
    if not isinstance(name, str) or not name or len(name) > MAX_NAME_LENGTH:
        return False
    if NAME_RE.fullmatch(name):
        return True
    return ecosystem == "npm" and bool(NPM_SCOPED_RE.fullmatch(name))


def _looks_like_location(token):
    """Paths, URLs, VCS references and archives are not registry packages."""
    lowered = token.lower()
    return (
        "://" in token
        or "\\" in token
        or token.startswith((".", "/", "~", "$"))
        or lowered.startswith(("git+", "file:", "http:", "https:", "link:", "github:"))
        or lowered.endswith((".whl", ".zip", ".tar.gz", ".tgz", ".tar.bz2", ".egg"))
    )


def _npm_spec_is_location(spec):
    """True for package.json values that point somewhere other than the registry.

    Not the same test as _looks_like_location: "~1.2.0" is an npm version range,
    while "~/code/lib" is a local path.
    """
    lowered = spec.strip().lower()
    return "://" in lowered or lowered.startswith(
        ("file:", "link:", "git+", "git:", "github:", "workspace:", "./", "../", "/", "~/")
    )


def _tokens(args):
    try:
        return shlex.split(args, comments=False, posix=True)
    except ValueError:  # unbalanced quotes in pasted chat output
        return args.replace('"', " ").replace("'", " ").split()


def _exact_pypi_version(requirement):
    specs = list(requirement.specifier)
    if len(specs) == 1 and specs[0].operator in ("==", "===") and "*" not in specs[0].version:
        version = specs[0].version
        return version if PYPI_VERSION_RE.fullmatch(version) else None
    return None


def _exact_npm_version(spec):
    spec = (spec or "").strip().lstrip("=v")
    return spec if NPM_EXACT_VERSION_RE.fullmatch(spec) else None


def _split_npm_token(token):
    """'@scope/pkg@1.2.3' -> ('@scope/pkg', '1.2.3'); 'pkg' -> ('pkg', None)."""
    at = token.find("@", 1)
    if at == -1:
        return token, None
    return token[:at], token[at + 1 :] or None


def _check_size(text):
    if len(text.encode("utf-8")) > MAX_INPUT_BYTES:
        raise ParseError("The input is too large. The limit is 256 KB.")


class _Collector:
    """Validates, normalises and de-duplicates, preserving first-seen order."""

    def __init__(self):
        self.result = ParseResult()
        self._index = {}

    def add(self, ecosystem, raw_name, version=None):
        raw_name = (raw_name or "").strip()
        name = normalise_name(ecosystem, raw_name)
        if not is_valid_name(ecosystem, name):
            self.result.rejected += 1
            return
        key = (ecosystem, name)
        if key in self._index:
            position = self._index[key]
            existing = self.result.packages[position]
            if existing.version is None and version:
                self.result.packages[position] = existing._replace(version=version)
            return
        if len(self.result.packages) >= MAX_PACKAGES:
            self.result.truncated = True
            return
        self._index[key] = len(self.result.packages)
        self.result.packages.append(PackageRef(ecosystem, name, version))

    def reject(self):
        self.result.rejected += 1

    @property
    def found_any(self):
        return bool(self.result.packages) or self.result.rejected > 0


def _add_pypi_requirement(collector, text):
    try:
        requirement = Requirement(text)
    except InvalidRequirement:
        collector.reject()
        return
    collector.add("pypi", requirement.name, _exact_pypi_version(requirement))


def _parse_pip_args(collector, args, value_flags=PIP_VALUE_FLAGS):
    skip_next = False
    for token in _tokens(args):
        if skip_next:
            skip_next = False
            continue
        if token.startswith("-"):
            skip_next = token in value_flags
            continue
        if _looks_like_location(token):
            collector.reject()
            continue
        _add_pypi_requirement(collector, token)


def _parse_npm_args(collector, args):
    skip_next = False
    for token in _tokens(args):
        if skip_next:
            skip_next = False
            continue
        if token.startswith("-"):
            skip_next = token in NPM_VALUE_FLAGS
            continue
        if _looks_like_location(token) or ("/" in token and not token.startswith("@")):
            collector.reject()  # user/repo GitHub shorthand, paths
            continue
        name, version = _split_npm_token(token)
        collector.add("npm", name, _exact_npm_version(version))


def _js_spec_to_package(spec):
    if spec.startswith((".", "/")) or "://" in spec:
        return None
    if spec.startswith("node:"):
        return None
    if spec.startswith("@"):
        name = "/".join(spec.split("/")[:2])
    else:
        name = spec.split("/")[0]
    if name in NODE_BUILTINS:
        return None
    return name


def _parse_requirements_into(collector, text):
    joined = re.sub(r"\\\r?\n", " ", text)  # line continuations
    for raw_line in joined.splitlines():
        line = re.split(r"(?:^|\s)#", raw_line, maxsplit=1)[0].strip()
        if not line or line.startswith("-"):
            continue  # blank, comment, or an option such as -r / -e / --hash
        line = re.split(r"\s+--?[A-Za-z]", line, maxsplit=1)[0].strip()  # per-line options
        if _looks_like_location(line):
            collector.reject()
            continue
        _add_pypi_requirement(collector, line)


def _json_depth_ok(text, limit=MAX_JSON_DEPTH):
    """Reject deeply nested JSON before json.loads can recurse on it."""
    depth = 0
    in_string = escaped = False
    for ch in text:
        if in_string:
            if escaped:
                escaped = False
            elif ch == "\\":
                escaped = True
            elif ch == '"':
                in_string = False
        elif ch == '"':
            in_string = True
        elif ch in "[{":
            depth += 1
            if depth > limit:
                return False
        elif ch in "]}":
            depth -= 1
    return True


def _load_json_object(text):
    if not _json_depth_ok(text):
        raise ParseError("The JSON is nested too deeply.")
    try:
        data = json.loads(text)
    except (ValueError, RecursionError) as exc:
        raise ParseError("The file is not valid JSON.") from exc
    if not isinstance(data, dict):
        raise ParseError("Expected a package.json object.")
    return data


def _parse_package_json_into(collector, data):
    for section in ("dependencies", "devDependencies"):
        deps = data.get(section) or {}
        if not isinstance(deps, dict):
            continue
        for name, spec in deps.items():
            if not isinstance(name, str):
                continue
            if isinstance(spec, str) and _npm_spec_is_location(spec):
                collector.reject()  # file:, git+, link: dependencies are not on npm
                continue
            collector.add("npm", name, _exact_npm_version(spec if isinstance(spec, str) else None))


def _scan_free_text(collector, text):
    for match in PIP_RE.finditer(text):
        _parse_pip_args(collector, match.group("args"))
    for match in PY_TOOL_RE.finditer(text):
        _parse_pip_args(collector, match.group("args"))
    for match in NPM_RE.finditer(text):
        _parse_npm_args(collector, match.group("args"))

    for module in _python_imports(text):
        distribution = import_to_distribution(module)
        if distribution:
            collector.add("pypi", distribution)

    for pattern in (JS_REQUIRE_RE, JS_FROM_RE, JS_BARE_IMPORT_RE):
        for match in pattern.finditer(text):
            package = _js_spec_to_package(match.group("spec"))
            if package:
                collector.add("npm", package)


def _python_imports(text):
    """Yield imported module paths in the order they appear in the text."""
    found = []
    for match in PY_IMPORT_RE.finditer(text):
        for part in match.group("mods").split(","):
            found.append((match.start(), part.strip().split()[0]))  # drop any "as alias"
    for match in PY_FROM_RE.finditer(text):
        module = match.group("mod")
        if module.startswith("."):  # relative imports are the user's own code
            continue
        if module in NAMESPACE_ROOTS:
            names = [n.split()[0] for n in match.group("names").split(",") if n.strip()]
            found.extend((match.start(), f"{module}.{name}") for name in names)
        else:
            found.append((match.start(), module))
    for _, module in sorted(found, key=lambda item: item[0]):
        yield module


def _parse_bare_lines(collector, text, ecosystem):
    """A plain list of names, one per line (used when nothing else matched)."""
    if ecosystem == "npm":
        for raw_line in text.splitlines():
            line = raw_line.split("#", 1)[0].strip().strip(",")
            if line:
                name, version = _split_npm_token(line)
                collector.add("npm", name, _exact_npm_version(version))
    else:
        _parse_requirements_into(collector, text)


def parse_text(text, ecosystem=None):
    """Parse pasted text: AI chat output, code, a requirements list or package.json."""
    if ecosystem is not None and ecosystem not in ECOSYSTEMS:
        raise ParseError("Unknown ecosystem.")
    text = (text or "").replace("\x00", "")
    _check_size(text)
    collector = _Collector()

    stripped = text.strip()
    if stripped.startswith("{"):
        try:
            data = _load_json_object(stripped)
        except ParseError:
            data = None
        if data is not None:
            _parse_package_json_into(collector, data)
            return collector.result

    _scan_free_text(collector, text)
    if not collector.found_any:
        _parse_bare_lines(collector, text, ecosystem or "pypi")
    return collector.result


def parse_requirements(text):
    _check_size(text)
    collector = _Collector()
    _parse_requirements_into(collector, text)
    return collector.result


def parse_package_json(text):
    _check_size(text)
    collector = _Collector()
    _parse_package_json_into(collector, _load_json_object(text))
    return collector.result


def parse_upload(filename, data):
    """Parse an uploaded requirements.txt or package.json.

    The extension is only a first filter. The content decides the format,
    and content that is binary, not UTF-8, or not the format it claims is
    refused.
    """
    suffix = Path(filename or "").suffix.lower()
    if suffix not in ALLOWED_UPLOAD_SUFFIXES:
        raise ParseError("Only .txt and .json files are accepted.")
    if len(data) > MAX_INPUT_BYTES:
        raise ParseError("The file is too large. The limit is 256 KB.")
    if b"\x00" in data:
        raise ParseError("The file looks binary, not text.")
    try:
        text = data.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise ParseError("The file is not UTF-8 text.") from exc

    looks_like_json = text.lstrip().startswith("{")
    if suffix == ".json" or looks_like_json:
        return parse_package_json(text)
    return parse_requirements(text)


def parse_single(ecosystem, name, version=None):
    if ecosystem not in ECOSYSTEMS:
        raise ParseError("Unknown ecosystem.")
    name = normalise_name(ecosystem, (name or "").strip())
    if not is_valid_name(ecosystem, name):
        raise ParseError("That is not a valid package name.")
    version = (version or "").strip() or None
    if version is not None:
        if ecosystem == "pypi":
            version = version if PYPI_VERSION_RE.fullmatch(version) else None
        else:
            version = _exact_npm_version(version)
        if version is None:
            raise ParseError("That is not a valid exact version.")
    return ParseResult(packages=[PackageRef(ecosystem, name, version)])
