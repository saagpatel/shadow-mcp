"""Scrub inline secrets out of command args and URLs.

Config collectors only ever keep env var *names*, but process and CLI sightings
carry raw command lines and URLs that can embed a secret (``--api-key XYZ``,
``https://h/mcp?token=XYZ``, ``https://user:pass@h``). A security tool must not
leak a secret into its own inventory, so every ServerSpec runs its args and url
through these before storage.
"""

from __future__ import annotations

import re

_SECRET = re.compile(
    r"(?i)(token|secret|password|passwd|credential|api[-_]?key|access[-_]?key|"
    r"auth[-_]?token|\bkey\b)"
)
_URL_QUERY_SECRET = re.compile(
    r"(?i)([?&](?:token|secret|password|auth|apikey|api[-_]?key|access[-_]?token|key)[^=]*=)[^&\s]*"
)
_URL_USERINFO = re.compile(r"(//[^/@\s]+:)[^/@\s]+@")

# Known credential SHAPES — caught regardless of the surrounding flag name, so a
# bearer token / provider key in a command line is redacted even when its flag
# (e.g. --header) is not in our secret vocabulary. Specific prefixes keep the
# false-positive rate near zero.
_SECRET_VALUE = re.compile(
    r"(?i)(?:bearer\s+[A-Za-z0-9._\-]+"
    r"|sk-[A-Za-z0-9_\-]{12,}"
    r"|gh[posru]_[A-Za-z0-9]{16,}"
    r"|xox[abposr]-[A-Za-z0-9-]{8,}"
    r"|eyJ[A-Za-z0-9_\-]{8,}\.[A-Za-z0-9_\-]{8,}\.[A-Za-z0-9_\-]+"
    r"|AKIA[0-9A-Z]{12,})"
)

_REDACTED = "REDACTED"


def scrub_value_shapes(text: str) -> str:
    """Redact any known credential shape embedded anywhere in a token/string."""
    return _SECRET_VALUE.sub(_REDACTED, text)


def scrub_args(args: list[str]) -> list[str]:
    out: list[str] = []
    redact_next = False
    for a in args:
        if redact_next:
            out.append(_REDACTED)
            redact_next = False
            continue
        if "=" in a:
            key, _, value = a.partition("=")
            if value and _SECRET.search(key.lstrip("-")):
                out.append(f"{key}={_REDACTED}")
                continue
        if a.startswith("-") and _SECRET.search(a):
            # secret value is the following token: `--api-key XYZ`
            redact_next = True
            out.append(a)
            continue
        # value-shape backstop: catch a bearer/provider token regardless of flag
        out.append(scrub_value_shapes(a))
    return out


def scrub_url(url: str) -> str:
    url = _URL_USERINFO.sub(rf"\1{_REDACTED}@", url)
    url = _URL_QUERY_SECRET.sub(rf"\1{_REDACTED}", url)
    return scrub_value_shapes(url)
