from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import unquote, urlparse
from urllib.request import Request, url2pathname, urlopen


DEFAULT_CHANNEL = "stable"
DEFAULT_DOWNLOAD_URL = "https://github.com/ViniciusNoetzold/MezzoldConnect/releases"
MAX_MANIFEST_BYTES = 256 * 1024


@dataclass(frozen=True)
class UpdateCheckResult:
    status: str
    current_version: str
    latest_version: str = ""
    download_url: str = DEFAULT_DOWNLOAD_URL
    release_notes: str = ""
    manifest_url: str = ""
    channel: str = DEFAULT_CHANNEL
    error: str = ""
    auto_update_ready: bool = False
    sha256: str = ""

    @property
    def has_update(self) -> bool:
        return self.status == "available"


def check_for_updates(
    current_version: str,
    manifest_url: str,
    download_url: str = DEFAULT_DOWNLOAD_URL,
    channel: str = DEFAULT_CHANNEL,
    timeout: float = 8.0,
) -> UpdateCheckResult:
    fallback_download_url = download_url.strip() or DEFAULT_DOWNLOAD_URL
    selected_channel = channel.strip() or DEFAULT_CHANNEL
    source_url = manifest_url.strip()

    if not source_url:
        return UpdateCheckResult(
            status="no_manifest",
            current_version=current_version,
            latest_version=current_version,
            download_url=fallback_download_url,
            channel=selected_channel,
        )

    try:
        manifest = fetch_manifest(source_url, timeout=timeout)
        release = select_release(manifest, selected_channel)
        latest_version = str(
            release.get("latest_version") or release.get("version") or release.get("latest") or ""
        ).strip()
        if not latest_version:
            raise ValueError("Manifesto de atualizacao sem latest_version.")

        selected_download_url = str(
            release.get("download_url")
            or release.get("installer_url")
            or release.get("release_url")
            or fallback_download_url
        ).strip()
        release_notes = str(release.get("release_notes") or release.get("notes") or "").strip()
        sha256 = str(release.get("sha256") or release.get("installer_sha256") or "").strip()
        status = "available" if is_newer_version(latest_version, current_version) else "current"
        return UpdateCheckResult(
            status=status,
            current_version=current_version,
            latest_version=latest_version,
            download_url=selected_download_url or fallback_download_url,
            release_notes=release_notes,
            manifest_url=source_url,
            channel=selected_channel,
            auto_update_ready=False,
            sha256=sha256,
        )
    except Exception as exc:
        return UpdateCheckResult(
            status="error",
            current_version=current_version,
            download_url=fallback_download_url,
            manifest_url=source_url,
            channel=selected_channel,
            error=str(exc),
        )


def fetch_manifest(source_url: str, timeout: float = 8.0) -> dict[str, Any]:
    raw: bytes | None = None
    if re.match(r"^[A-Za-z]:[\\/]", source_url):
        raw = Path(source_url).read_bytes()

    parsed = urlparse(source_url)
    if raw is not None:
        pass
    elif parsed.scheme in {"http", "https"}:
        request = Request(source_url, headers={"User-Agent": "Mezzold Connect Updater"})
        with urlopen(request, timeout=timeout) as response:
            raw = response.read(MAX_MANIFEST_BYTES + 1)
    elif parsed.scheme == "file":
        raw = Path(url2pathname(unquote(parsed.path))).read_bytes()
    elif not parsed.scheme:
        raw = Path(source_url).read_bytes()
    else:
        raise ValueError("Use uma URL http(s), file:// ou um caminho local para o manifesto.")

    if len(raw) > MAX_MANIFEST_BYTES:
        raise ValueError("Manifesto de atualizacao maior que o permitido.")

    data = json.loads(raw.decode("utf-8"))
    if not isinstance(data, dict):
        raise ValueError("Manifesto de atualizacao precisa ser um objeto JSON.")
    return data


def select_release(manifest: dict[str, Any], channel: str) -> dict[str, Any]:
    base = {key: value for key, value in manifest.items() if key != "channels"}
    channels = manifest.get("channels")
    if isinstance(channels, dict):
        selected = channels.get(channel) or channels.get(DEFAULT_CHANNEL)
        if isinstance(selected, dict):
            return {**base, **selected}
    return base


def is_newer_version(candidate: str, current: str) -> bool:
    if not candidate.strip():
        return False
    return _version_key(candidate) > _version_key(current)


def _version_key(version: str) -> tuple[int, int, int, int, int, str]:
    cleaned = version.strip().lstrip("vV").split("+", 1)[0]
    numbers = [int(part) for part in re.findall(r"\d+", cleaned)[:4]]
    while len(numbers) < 4:
        numbers.append(0)
    stable = 0 if re.search(r"(alpha|beta|rc|dev|preview)", cleaned, re.IGNORECASE) else 1
    return (numbers[0], numbers[1], numbers[2], numbers[3], stable, cleaned.lower())
