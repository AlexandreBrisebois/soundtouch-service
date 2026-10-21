"""Bounded SoundTouch transports with no implicit command or observation retries."""

import time
import xml.etree.ElementTree as ET

import requests
from requests.adapters import HTTPAdapter
from requests.exceptions import Timeout
from urllib3.util.retry import Retry


MAX_XML_RESPONSE_BYTES = 64 * 1024


def _build_session() -> requests.Session:
    session = requests.Session()
    # allowed_methods does not prevent urllib3 from retrying connect failures for
    # POST. Disable every retry category: a timeout never proves a command was not
    # delivered. Fresh observations are retried only by the bounded operation loop.
    retry = Retry(total=0, connect=0, read=0, redirect=0, status=0, other=0)
    adapter = HTTPAdapter(max_retries=retry, pool_connections=20, pool_maxsize=20)
    session.mount("http://", adapter)
    session.mount("https://", adapter)
    return session


def read_response_body(response: requests.Response, *, deadline: float | None = None) -> bytes:
    """Read a small XML response, refusing redirects, HTTP failures, and large bodies.

    Callers pass stream=True and always close the response, including on errors.
    The per-request socket timeout is set by the caller; no transport retries occur.
    The deadline is checked for every decoded byte; a blocked read can exceed it
    by at most the current socket read timeout. Callers request identity encoding.
    """
    if not 200 <= response.status_code < 300:
        raise ValueError("Speaker HTTP request failed")
    body = bytearray()
    if deadline is not None and time.monotonic() >= deadline:
        raise Timeout("Speaker response deadline exceeded")
    # One-byte chunks ensure a slow trickle cannot defer the deadline check
    # until an entire block fills. Responses are small and capped at 64 KiB.
    for chunk in response.iter_content(chunk_size=1):
        if deadline is not None and time.monotonic() >= deadline:
            raise Timeout("Speaker response deadline exceeded")
        if len(body) + len(chunk) > MAX_XML_RESPONSE_BYTES:
            raise ValueError("Speaker response too large")
        body.extend(chunk)
    if deadline is not None and time.monotonic() >= deadline:
        raise Timeout("Speaker response deadline exceeded")
    return bytes(body)


def parse_speaker_xml(body: str | bytes, expected_root: str) -> ET.Element:
    """Parse a protocol document, not arbitrary HTML or a Bose error response."""
    encoded = body.encode("utf-8") if isinstance(body, str) else body
    if len(encoded) > MAX_XML_RESPONSE_BYTES:
        raise ValueError("Speaker response too large")
    # SoundTouch responses do not need DTDs/entities. Reject them rather than
    # expanding device-supplied content or accidentally exposing it in an error.
    upper = encoded.replace(b"\x00", b"").upper()
    if b"<!DOCTYPE" in upper or b"<!ENTITY" in upper:
        raise ValueError("Unexpected XML declaration")
    root = ET.fromstring(encoded)
    validate_speaker_element(root, expected_root)
    return root


def validate_speaker_element(root: ET.Element, expected_root: str) -> None:
    if root.tag != expected_root:
        raise ValueError("Unexpected speaker XML root")
    if any(element.tag.rsplit("}", 1)[-1].lower() in {"error", "errors"} for element in root.iter()):
        raise ValueError("Speaker reported a protocol error")


session = _build_session()
command_session = _build_session()
