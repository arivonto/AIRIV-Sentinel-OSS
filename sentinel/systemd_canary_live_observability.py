"""Read-only projections of canonical live facts; never consumed for execution."""
import json
import math
import os
from pathlib import Path
import uuid


def process_identity(pid=None):
    """Linux boot + PID + kernel start ticks distinguish PID reuse and restart."""
    pid = os.getpid() if pid is None else pid
    status = Path(f"/proc/{pid}/stat").read_text()
    return {"pid": pid,
            "boot_id": Path("/proc/sys/kernel/random/boot_id").read_text().strip(),
            "start_ticks": status.rsplit(")", 1)[1].split()[19]}


def valid_idle_projection(record, *, expected_process, now, max_age=5.0):
    """Validate proof against independently observed live process identity/time.

    This is evidence validation only, never permission to execute a request.
    """
    try:
        return bool(
            type(record) is dict
            and type(record["schema_version"]) is int and record["schema_version"] == 1
            and record["schema"] == "systemd-canary-live-state"
            and expected_process == process_identity(expected_process["pid"])
            and record["process"] == expected_process
            and type(record["generation"]) is int and record["generation"] > 0
            and type(record["timestamp"]) in (float, int)
            and math.isfinite(record["timestamp"])
            and 0 <= now - record["timestamp"] <= max_age
            and record["phase"] == "IDLE"
            and record["inbox_pending"] is False
            and record["active_request_id"] is None
            and record["active_approval_id"] is None
            and record["cleanup_uncertain"] is False
            and all(record[key] is True for key in (
                "activation_empty", "policy_activation_empty",
                "catalog_activation_empty", "bound_activation_empty"))
        )
    except (KeyError, TypeError, ValueError, OSError, IndexError):
        return False


def atomic_write(root, name, record):
    """Private temporary file, fsync, atomic replace, directory fsync."""
    root.mkdir(mode=0o700, parents=True, exist_ok=True)
    directory = os.open(root, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    temporary = ".live-projection-" + uuid.uuid4().hex
    try:
        info = os.fstat(directory)
        if info.st_uid != os.getuid() or info.st_mode & 0o022:
            raise ValueError("unsafe_projection_directory")
        fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                     0o600, dir_fd=directory)
        with os.fdopen(fd, "w") as stream:
            json.dump(record, stream, sort_keys=True, allow_nan=False)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, name, src_dir_fd=directory, dst_dir_fd=directory)
        os.fsync(directory)
    finally:
        try:
            os.unlink(temporary, dir_fd=directory)
        except FileNotFoundError:
            pass
        os.close(directory)
