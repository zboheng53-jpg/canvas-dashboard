"""Create and restore encrypted, integrity-checked Canvas Dashboard data backups."""
import argparse
import base64
import hashlib
import io
import json
import os
import secrets
import struct
import sys
import tarfile
import tempfile
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath

from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding, rsa
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes

MAGIC = b"CDBAK1\n"
TAG_SIZE = 16
CHUNK_SIZE = 1024 * 1024


def _is_excluded(relative: PurePosixPath) -> bool:
    parts = relative.parts
    name = relative.name
    return (
        "zhihuishu_chromium_profile" in parts
        or name.endswith("_cache.json")
        or name in {
            "holiday_cache.json",
            "term_cache.json",
            "zhihuishu_status.json",
            "zhihuishu_login_session.json",
            "zhihuishu_worker.lock",
        }
        or name.startswith("server.log")
        or ".corrupt-" in name
    )


def _included_files(data_dir: Path) -> list[Path]:
    files = []
    for path in data_dir.rglob("*"):
        relative = PurePosixPath(path.relative_to(data_dir).as_posix())
        if _is_excluded(relative):
            continue
        if path.is_symlink():
            raise ValueError(f"Symlinks are not allowed in backups: {relative}")
        if path.is_file():
            files.append(path)
    return sorted(files, key=lambda path: path.relative_to(data_dir).as_posix())


def _build_manifest(data_dir: Path, files: list[Path]) -> dict:
    entries = []
    for path in files:
        relative = path.relative_to(data_dir).as_posix()
        digest = hashlib.sha256()
        with path.open("rb") as source:
            while chunk := source.read(CHUNK_SIZE):
                digest.update(chunk)
        if path.suffix.lower() == ".json":
            try:
                json.loads(path.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, UnicodeDecodeError) as exc:
                raise ValueError(f"Refusing to back up malformed JSON: {relative}") from exc
        entries.append({"path": f"data/{relative}", "size": path.stat().st_size, "sha256": digest.hexdigest()})
    return {
        "version": 1,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "file_count": len(entries),
        "files": entries,
    }


class _EncryptWriter:
    def __init__(self, output, encryptor):
        self.output = output
        self.encryptor = encryptor

    def write(self, data):
        encrypted = self.encryptor.update(data)
        if encrypted:
            self.output.write(encrypted)
        return len(data)

    def flush(self):
        self.output.flush()


class _DecryptReader:
    def __init__(self, source, decryptor, remaining: int):
        self.source = source
        self.decryptor = decryptor
        self.remaining = remaining
        self.finalized = False

    def read(self, size=-1):
        if self.remaining <= 0:
            if not self.finalized:
                self.decryptor.finalize()
                self.finalized = True
            return b""
        if size is None or size < 0:
            size = self.remaining
        encrypted = self.source.read(min(size, self.remaining))
        if not encrypted:
            raise ValueError("Encrypted backup is truncated")
        self.remaining -= len(encrypted)
        plaintext = self.decryptor.update(encrypted)
        if self.remaining == 0 and not self.finalized:
            plaintext += self.decryptor.finalize()
            self.finalized = True
        return plaintext


def _tar_filter(data_dir: Path):
    def include(info: tarfile.TarInfo):
        relative = PurePosixPath(info.name).relative_to("data")
        if relative.parts and _is_excluded(relative):
            return None
        if info.issym() or info.islnk():
            raise ValueError(f"Symlinks are not allowed in backups: {info.name}")
        info.uid = 0
        info.gid = 0
        info.uname = ""
        info.gname = ""
        return info

    return include


def _atomic_write_key(path: Path, payload: bytes, mode: int) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        raise FileExistsError(f"Refusing to replace existing key: {path}")
    fd, temp_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(fd, "wb") as output:
            output.write(payload)
            output.flush()
            os.fsync(output.fileno())
        os.chmod(temp_name, mode)
        os.replace(temp_name, path)
    except Exception:
        try:
            os.unlink(temp_name)
        except FileNotFoundError:
            pass
        raise


def keygen(private_key_path: Path, public_key_path: Path) -> None:
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=4096)
    private_payload = private_key.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption(),
    )
    public_payload = private_key.public_key().public_bytes(
        serialization.Encoding.PEM,
        serialization.PublicFormat.SubjectPublicKeyInfo,
    )
    _atomic_write_key(private_key_path, private_payload, 0o600)
    try:
        _atomic_write_key(public_key_path, public_payload, 0o644)
    except Exception:
        private_key_path.unlink(missing_ok=True)
        raise


def create_backup(data_dir: Path, output_dir: Path, public_key_path: Path, retention: int) -> Path:
    if not data_dir.is_dir():
        raise FileNotFoundError(f"Data directory does not exist: {data_dir}")
    files = _included_files(data_dir)
    manifest = _build_manifest(data_dir, files)
    public_key = serialization.load_pem_public_key(public_key_path.read_bytes())
    content_key = secrets.token_bytes(32)
    nonce = secrets.token_bytes(12)
    wrapped_key = public_key.encrypt(
        content_key,
        padding.OAEP(mgf=padding.MGF1(algorithm=hashes.SHA256()), algorithm=hashes.SHA256(), label=None),
    )
    header = json.dumps(
        {
            "version": 1,
            "algorithm": "RSA-OAEP-SHA256+AES-256-GCM",
            "wrapped_key": base64.b64encode(wrapped_key).decode("ascii"),
            "nonce": base64.b64encode(nonce).decode("ascii"),
        },
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    prefix = MAGIC + struct.pack(">I", len(header)) + header
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / f"canvas-dashboard-data-{timestamp}-{secrets.token_hex(4)}.cdbak"
    fd, temp_name = tempfile.mkstemp(prefix=f".{output_path.name}.", suffix=".tmp", dir=output_dir)
    try:
        with os.fdopen(fd, "wb") as output:
            output.write(prefix)
            encryptor = Cipher(algorithms.AES(content_key), modes.GCM(nonce)).encryptor()
            encryptor.authenticate_additional_data(prefix)
            encrypted_output = _EncryptWriter(output, encryptor)
            with tarfile.open(fileobj=encrypted_output, mode="w|gz", format=tarfile.PAX_FORMAT) as archive:
                manifest_payload = json.dumps(manifest, sort_keys=True, separators=(",", ":")).encode("utf-8")
                manifest_info = tarfile.TarInfo("backup-manifest.json")
                manifest_info.size = len(manifest_payload)
                manifest_info.mtime = int(datetime.now(timezone.utc).timestamp())
                archive.addfile(manifest_info, io.BytesIO(manifest_payload))
                archive.add(data_dir, arcname="data", recursive=True, filter=_tar_filter(data_dir))
            encryptor.finalize()
            output.write(encryptor.tag)
            output.flush()
            os.fsync(output.fileno())
        os.replace(temp_name, output_path)
    except Exception:
        try:
            os.unlink(temp_name)
        except FileNotFoundError:
            pass
        raise

    backups = sorted(output_dir.glob("canvas-dashboard-data-*.cdbak"), key=lambda path: path.stat().st_mtime, reverse=True)
    for expired in backups[max(1, retention) :]:
        expired.unlink()
    return output_path


def _open_archive(input_path: Path, private_key_path: Path):
    source = input_path.open("rb")
    try:
        magic = source.read(len(MAGIC))
        if magic != MAGIC:
            raise ValueError("Not a Canvas Dashboard encrypted backup")
        raw_length = source.read(4)
        if len(raw_length) != 4:
            raise ValueError("Encrypted backup header is truncated")
        header_length = struct.unpack(">I", raw_length)[0]
        if header_length > 64 * 1024:
            raise ValueError("Encrypted backup header is too large")
        header_payload = source.read(header_length)
        if len(header_payload) != header_length:
            raise ValueError("Encrypted backup header is truncated")
        prefix = magic + raw_length + header_payload
        header = json.loads(header_payload.decode("utf-8"))
        private_key = serialization.load_pem_private_key(private_key_path.read_bytes(), password=None)
        content_key = private_key.decrypt(
            base64.b64decode(header["wrapped_key"], validate=True),
            padding.OAEP(mgf=padding.MGF1(algorithm=hashes.SHA256()), algorithm=hashes.SHA256(), label=None),
        )
        nonce = base64.b64decode(header["nonce"], validate=True)
        ciphertext_start = source.tell()
        file_size = input_path.stat().st_size
        if file_size <= ciphertext_start + TAG_SIZE:
            raise ValueError("Encrypted backup payload is missing")
        source.seek(file_size - TAG_SIZE)
        tag = source.read(TAG_SIZE)
        source.seek(ciphertext_start)
        decryptor = Cipher(algorithms.AES(content_key), modes.GCM(nonce, tag)).decryptor()
        decryptor.authenticate_additional_data(prefix)
        reader = _DecryptReader(source, decryptor, file_size - ciphertext_start - TAG_SIZE)
        archive = tarfile.open(fileobj=reader, mode="r|gz")
        return source, archive
    except Exception:
        source.close()
        raise


def _safe_member_path(output_dir: Path, member_name: str) -> Path:
    relative = PurePosixPath(member_name)
    if relative.is_absolute() or ".." in relative.parts:
        raise ValueError(f"Unsafe archive path: {member_name}")
    target = output_dir.joinpath(*relative.parts)
    target.resolve().relative_to(output_dir.resolve())
    return target


def _consume_archive(input_path: Path, private_key_path: Path, output_dir: Path | None = None) -> dict:
    source, archive = _open_archive(input_path, private_key_path)
    manifest = None
    actual = {}
    try:
        for member in archive:
            if member.name == "backup-manifest.json":
                extracted = archive.extractfile(member)
                if extracted is None:
                    raise ValueError("Backup manifest is unreadable")
                manifest = json.loads(extracted.read().decode("utf-8"))
                continue
            if member.issym() or member.islnk() or not (member.isfile() or member.isdir()):
                raise ValueError(f"Unsupported archive entry: {member.name}")
            target = _safe_member_path(output_dir, member.name) if output_dir is not None else None
            if member.isdir():
                if target is not None:
                    target.mkdir(parents=True, exist_ok=True)
                continue
            extracted = archive.extractfile(member)
            if extracted is None:
                raise ValueError(f"Backup entry is unreadable: {member.name}")
            digest = hashlib.sha256()
            size = 0
            destination = None
            try:
                if target is not None:
                    target.parent.mkdir(parents=True, exist_ok=True)
                    destination = target.open("wb")
                while chunk := extracted.read(CHUNK_SIZE):
                    digest.update(chunk)
                    size += len(chunk)
                    if destination is not None:
                        destination.write(chunk)
            finally:
                if destination is not None:
                    destination.close()
            actual[member.name] = {"size": size, "sha256": digest.hexdigest()}
    finally:
        archive.close()
        source.close()
    if manifest is None:
        raise ValueError("Backup manifest is missing")
    expected = {entry["path"]: {"size": entry["size"], "sha256": entry["sha256"]} for entry in manifest["files"]}
    if actual != expected:
        raise ValueError("Backup manifest does not match the decrypted payload")
    return {"ok": True, "file_count": len(actual), "created_at": manifest["created_at"]}


def main(argv=None) -> int:
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="command", required=True)
    key_parser = subparsers.add_parser("keygen")
    key_parser.add_argument("--private-key", type=Path, required=True)
    key_parser.add_argument("--public-key", type=Path, required=True)
    create_parser = subparsers.add_parser("create")
    create_parser.add_argument("--data-dir", type=Path, required=True)
    create_parser.add_argument("--output-dir", type=Path, required=True)
    create_parser.add_argument("--public-key", type=Path, required=True)
    create_parser.add_argument("--retention", type=int, default=14)
    for name in ("verify", "restore"):
        command_parser = subparsers.add_parser(name)
        command_parser.add_argument("--input", type=Path, required=True)
        command_parser.add_argument("--private-key", type=Path, required=True)
        if name == "restore":
            command_parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        if args.command == "keygen":
            keygen(args.private_key, args.public_key)
            result = {"ok": True}
        elif args.command == "create":
            path = create_backup(args.data_dir, args.output_dir, args.public_key, args.retention)
            result = {"ok": True, "backup": str(path)}
        else:
            output_dir = args.output_dir if args.command == "restore" else None
            if output_dir is not None:
                output_dir.mkdir(parents=True, exist_ok=False)
            result = _consume_archive(args.input, args.private_key, output_dir)
        print(json.dumps(result, ensure_ascii=False))
        return 0
    except Exception as exc:
        print(f"{type(exc).__name__}: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
