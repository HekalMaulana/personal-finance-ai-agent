"""Linux-only foreground fixture endpoint; no CLI, service installer or secrets.

The kernel authenticates both ends. The agent must run under a THIRD UID,
not the gateway UID; subprocesses inherit their parent's privileges.
"""

import json
import os
import socket
import stat
import struct
import sys

from finance_telegram_bridge import LedgerRequests, _unique_object

_LIMIT = 32768
_TIMEOUT = 2
_PEER = struct.Struct('3i')


def _check_platform(peer_uid):
    if not sys.platform.startswith('linux') or not hasattr(socket, 'SO_PEERCRED'):
        raise OSError('Linux SO_PEERCRED required')
    uid = os.geteuid()  # pyright: ignore[reportAttributeAccessIssue]
    if type(peer_uid) is not int or peer_uid <= 0 or uid in (0, peer_uid):
        raise OSError('distinct unprivileged identities required')
    return uid


def _peer_uid(conn):
    return _PEER.unpack(conn.getsockopt(socket.SOL_SOCKET, socket.SO_PEERCRED, _PEER.size))[1]


def _send(conn, obj):
    data = json.dumps(obj, ensure_ascii=True, allow_nan=False).encode('ascii')
    if len(data) > _LIMIT:
        raise ValueError('frame too large')
    conn.sendall(data + b'\n')


def _receive(conn):
    with conn.makefile('rb') as stream:
        data = stream.readline(_LIMIT + 2)
    if len(data) > _LIMIT + 1 or not data.endswith(b'\n'):
        raise ValueError('invalid frame')
    return json.loads(data.decode('ascii'), object_pairs_hook=_unique_object)


def request(endpoint, service_uid, envelope):
    """Gateway-only client. Authenticate server before sending sensitive fields."""
    try:
        _check_platform(service_uid)
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as conn:
            conn.settimeout(_TIMEOUT)
            conn.connect(str(endpoint))
            if _peer_uid(conn) != service_uid:
                raise OSError('unexpected service identity')
            _send(conn, envelope)
            result = _receive(conn)
            if type(result) is not dict:
                raise ValueError('invalid result')
            return result
    except (OSError, ValueError, RecursionError):
        return {'error': 'ledger_unavailable'}


def _check_path(path, uid, kind, forbidden):
    if not path.is_absolute() or path.resolve() != path:
        raise OSError('canonical absolute path required')
    info = path.stat()
    if info.st_uid != uid or not kind(info.st_mode) or info.st_mode & forbidden:
        raise OSError('unsafe ownership or permissions')


def serve(endpoint, ledger, *, owner, gateway_uid):
    """Run only in a dedicated operator-controlled process on a native Linux FS."""
    uid = _check_platform(gateway_uid)
    _check_path(ledger.parent, uid, stat.S_ISDIR, 0o077)
    _check_path(ledger, uid, stat.S_ISREG, 0o077)
    _check_path(endpoint.parent, uid, stat.S_ISDIR, 0o027)
    if not endpoint.parent.stat().st_mode & stat.S_ISGID:
        raise OSError('socket directory must inherit its restricted group')
    if not endpoint.is_absolute() or endpoint.resolve() != endpoint:
        raise OSError('canonical socket path required')
    os.umask(0o077)  # Also protects SQLite sidecars. This is a dedicated process.
    actions = LedgerRequests(ledger, owner)
    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as server:
        server.bind(str(endpoint))  # Never replace a pre-existing name.
        try:
            # Restrict socket access to the operator-assigned gateway group;
            # membership alone still cannot pass the exact peer UID check.
            endpoint.chmod(0o660)
            server.listen(4)
            while True:
                conn, _ = server.accept()
                with conn:
                    conn.settimeout(_TIMEOUT)
                    try:
                        if _peer_uid(conn) != gateway_uid:
                            continue
                        _send(conn, actions.dispatch(_receive(conn)))
                    except (OSError, ValueError, RecursionError):
                        continue
        finally:
            endpoint.unlink()
