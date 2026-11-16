"""Content-based file checks. Nothing here trusts a file extension or opens a file for execution."""

from __future__ import annotations

import re
import stat
import zipfile
from pathlib import Path, PurePosixPath
from typing import Final

from obsidian_ledger.ingest.errors import IngestError

ZIP_MAGIC: Final = b"PK\x03\x04"
ZIP_EOCD: Final = b"PK\x05\x06"
OLE_MAGIC: Final = bytes.fromhex("d0cf11e0a1b11ae1")

MAX_ARCHIVE_UNCOMPRESSED: Final = 500 * 1024 * 1024
MAX_MEMBER_UNCOMPRESSED: Final = 300 * 1024 * 1024
MAX_COMPRESSION_RATIO: Final = 100
MAX_ARCHIVE_MEMBERS: Final = 5000
MAX_ROWS: Final = 5_000_000
MAX_COLUMNS: Final = 1000
SCAN_CHUNK: Final = 1024 * 1024
SCAN_OVERLAP: Final = 256

# Formats that can never be trade files, recognised by their first bytes whatever the extension.
FORBIDDEN_SIGNATURES: Final[tuple[tuple[bytes, str], ...]] = (
    (b"MZ", "Windows executable"),
    (b"\x7fELF", "Linux executable"),
    (b"\xcf\xfa\xed\xfe", "macOS executable"),
    (b"\xca\xfe\xba\xbe", "Java or macOS executable"),
    (b"#!", "script"),
    (b"%PDF", "PDF document"),
    (b"\x89PNG", "PNG image"),
    (b"\xff\xd8\xff", "JPEG image"),
    (b"GIF8", "GIF image"),
    (b"\x1f\x8b", "gzip archive"),
    (b"7z\xbc\xaf\x27\x1c", "7-Zip archive"),
    (b"Rar!", "RAR archive"),
    (b"BZh", "bzip2 archive"),
    (b"\xfd7zXZ", "xz archive"),
    (b"RIFF", "RIFF media"),
    (b"{\\rtf", "RTF document"),
    (b"MSCF", "cabinet archive"),
    (b"\x00asm", "WebAssembly module"),
)
MARKUP_START: Final = re.compile(rb"^\s*(?:<\?|<!|<[a-zA-Z])")

# Parts of an OOXML workbook that carry code or other embedded content.
FORBIDDEN_PARTS: Final[tuple[tuple[str, str, str], ...]] = (
    ("vbaproject", "macro_enabled", "Workbooks with macros are not accepted."),
    ("macrosheets/", "macro_enabled", "Workbooks with macro sheets are not accepted."),
    ("dialogsheets/", "macro_enabled", "Workbooks with dialog sheets are not accepted."),
    ("activex", "embedded_object", "Workbooks with ActiveX controls are not accepted."),
    ("embeddings/", "embedded_object", "Workbooks with embedded objects are not accepted."),
    ("oleobject", "embedded_object", "Workbooks with embedded objects are not accepted."),
    ("externallinks/", "external_link", "Workbooks with external links are not accepted."),
)

DDE_TEXT: Final = re.compile(
    rb"(?i)(?:^|[,;\t\"|\r\n])[ \t]*[=+\-@][ \t]*(?:cmd|powershell|mshta|msexcel|dde\w*)[ \t]*\|"
)
DDE_XML: Final = re.compile(
    rb"(?i)<f[^>]{0,200}>[ \t]*(?:cmd|powershell|mshta|msexcel|dde\w*)[ \t]*\||<ddeLink"
)
OLE_BAD_MARKERS: Final[tuple[tuple[bytes, str, str], ...]] = (
    ("_VBA_PROJECT".encode("utf-16-le"), "macro_enabled", "Workbooks with macros are not accepted."),
    (b"_VBA_PROJECT", "macro_enabled", "Workbooks with macros are not accepted."),
    (
        "Ole10Native".encode("utf-16-le"),
        "embedded_object",
        "Workbooks with embedded objects are not accepted.",
    ),
    (
        "ObjectPool".encode("utf-16-le"),
        "embedded_object",
        "Workbooks with embedded objects are not accepted.",
    ),
)


def scan_file(path: Path, pattern: re.Pattern[bytes] | bytes) -> bool:
    """True when `pattern` occurs anywhere in the file. Reads in chunks with a small overlap."""
    tail = b""
    with path.open("rb") as handle:
        while chunk := handle.read(SCAN_CHUNK):
            window = tail + chunk
            found = (
                pattern.search(window) is not None
                if isinstance(pattern, re.Pattern)
                else pattern in window
            )
            if found:
                return True
            tail = window[-SCAN_OVERLAP:]
    return False


def reject_forbidden_signature(head: bytes) -> None:
    for signature, label in FORBIDDEN_SIGNATURES:
        if head.startswith(signature):
            raise IngestError(
                "unsupported_file_type", f"A {label} cannot be imported.", status=415
            )


def reject_markup(head: bytes) -> None:
    """HTML, SVG, and XML payloads are not trade data, and they are how polyglots hide script."""
    if MARKUP_START.match(head):
        raise IngestError(
            "unsupported_file_type", "Markup files (HTML, XML, SVG) cannot be imported.", status=415
        )


def reject_polyglot(path: Path, head: bytes) -> None:
    """A text or JSON file must not also be a valid archive or document."""
    size = path.stat().st_size
    with path.open("rb") as handle:
        handle.seek(max(0, size - 66_000))
        tail = handle.read()
    if ZIP_EOCD in tail or b"%PDF-" in head[:1024] or OLE_MAGIC in head[:1024]:
        raise IngestError(
            "polyglot_file", "The file is also a valid archive or document and was refused."
        )


def reject_dde_text(path: Path) -> None:
    if scan_file(path, DDE_TEXT):
        raise IngestError("dde_formula", "The file contains a DDE command formula.")


def check_ole_workbook(path: Path) -> None:
    for marker, code, message in OLE_BAD_MARKERS:
        if scan_file(path, marker):
            raise IngestError(code, message)


def _is_symlink(info: zipfile.ZipInfo) -> bool:
    mode = info.external_attr >> 16
    return bool(mode) and stat.S_ISLNK(mode)


def check_archive(path: Path) -> None:
    """Refuse zip files that expand too much, escape their folder, nest, or carry code."""
    try:
        with zipfile.ZipFile(path) as archive:
            infos = archive.infolist()
            names = {info.filename for info in infos}
            _check_members(archive, infos)
            if "[Content_Types].xml" in names:
                content_types = archive.read("[Content_Types].xml")[:1_000_000].lower()
                if b"macroenabled" in content_types or b"vbaproject" in content_types:
                    raise IngestError("macro_enabled", "Workbooks with macros are not accepted.")
            _check_sheets_for_dde(archive, infos)
    except zipfile.BadZipFile as exc:
        raise IngestError(
            "bad_archive", "The file looks like a zip archive but cannot be read."
        ) from exc
    except (NotImplementedError, RuntimeError, OSError) as exc:
        raise IngestError("bad_archive", "The archive uses an unsupported feature.") from exc
    if "xl/workbook.xml" not in names:
        raise IngestError("unsupported_archive", "Zip files are accepted only as XLSX workbooks.")


def _check_members(archive: zipfile.ZipFile, infos: list[zipfile.ZipInfo]) -> None:
    if len(infos) > MAX_ARCHIVE_MEMBERS:
        raise IngestError("archive_too_many_members", "The archive has too many entries.")
    total = sum(info.file_size for info in infos)
    if total > MAX_ARCHIVE_UNCOMPRESSED:
        raise IngestError("archive_too_large", "The archive would expand beyond 500 MB.")
    compressed = sum(info.compress_size for info in infos)
    if total and (compressed == 0 or total / compressed > MAX_COMPRESSION_RATIO):
        raise IngestError(
            "archive_compression_ratio", "The archive has a suspicious compression ratio."
        )
    for info in infos:
        name = info.filename
        posix = PurePosixPath(name.replace("\\", "/"))
        if posix.is_absolute() or ".." in posix.parts or name.startswith(("/", "\\")) or (
            len(name) > 1 and name[1] == ":"
        ):
            raise IngestError("archive_path_traversal", "The archive contains illegal member paths.")
        if _is_symlink(info):
            raise IngestError("archive_symlink", "The archive contains a symbolic link.")
        if info.file_size > MAX_MEMBER_UNCOMPRESSED:
            raise IngestError("archive_too_large", "An archive entry is too large.")
        if info.file_size and (
            info.compress_size == 0 or info.file_size / info.compress_size > MAX_COMPRESSION_RATIO
        ):
            raise IngestError(
                "archive_compression_ratio", "The archive has a suspicious compression ratio."
            )
        lowered = name.lower()
        for fragment, code, message in FORBIDDEN_PARTS:
            if fragment in lowered:
                raise IngestError(code, message)
        if info.is_dir() or info.file_size < 8:
            continue
        with archive.open(info) as member:
            first = member.read(8)
        if first.startswith((ZIP_MAGIC, OLE_MAGIC)):
            raise IngestError("archive_nested", "The archive contains another archive.")


def _check_sheets_for_dde(archive: zipfile.ZipFile, infos: list[zipfile.ZipInfo]) -> None:
    for info in infos:
        if not info.filename.lower().startswith("xl/worksheets/") or info.is_dir():
            continue
        tail = b""
        with archive.open(info) as member:
            while chunk := member.read(SCAN_CHUNK):
                window = tail + chunk
                if DDE_XML.search(window):
                    raise IngestError("dde_formula", "The workbook contains a DDE command formula.")
                tail = window[-SCAN_OVERLAP:]
