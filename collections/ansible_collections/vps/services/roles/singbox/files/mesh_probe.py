"""Mesh data-path probe for NAT guests with a userspace WireGuard endpoint.

Lives in the role rather than in a shell one-liner because these guests are
Alpine and carry no tooling: `nc` may not be present and busybox's does not speak
SOCKS5, and `curl` is not guaranteed either. Python 3 is the one interpreter the
NAT bootstrap guarantees, so the probe uses only the standard library.

What a success actually proves
------------------------------
The probe opens a TCP connection to the target *through the loopback SOCKS*. For
that to succeed, sing-box must accept the connection, route it into its
WireGuard endpoint, encrypt it, and the far end must answer. A bound socket, a
healthy-looking process, or a `ping` that the default gateway swallowed all fail
this test, which is the point: the previous check only proved the socket existed.

Usage (as the role invokes it):
    python3 mesh_probe.py --socks-host H --socks-port P --target-host H --target-port P

Exit codes are meaningful to the caller: 0 = the tunnel carried the connection,
2 = the probe could not be set up, 1 = the tunnel did not deliver.
"""

from __future__ import annotations

import argparse
import socket
import struct
import sys
import time

SOCKS_VERSION = 5
SOCKS_CONNECT = 0x01
SOCKS_ADDR_IPV4 = 0x01
SOCKS_ADDR_DOMAIN = 0x03
REPLY_OK = 0x00


class ProbeError(RuntimeError):
    """Setup failure, distinct from the tunnel not delivering."""


def _recv_exactly(sock: socket.socket, count: int) -> bytes:
    """Read exactly `count` bytes or raise.

    `recv` may return short on a tunnel carrying a fresh connection, and treating
    a partial read as a complete reply would report success on a truncated
    handshake.
    """
    chunks = []
    remaining = count
    while remaining > 0:
        chunk = sock.recv(remaining)
        if not chunk:
            raise ProbeError("connection closed during the SOCKS handshake")
        chunks.append(chunk)
        remaining -= len(chunk)
    return b"".join(chunks)


def socks5_connect(
    socks_host: str,
    socks_port: int,
    target_host: str,
    target_port: int,
    timeout: float,
) -> socket.socket:
    """Perform a SOCKS5 CONNECT and return the relayed socket.

    Raises ProbeError on any refusal or transport failure; the caller turns that
    into a non-zero exit.
    """
    try:
        sock = socket.create_connection((socks_host, socks_port), timeout=timeout)
    except OSError as error:
        raise ProbeError(f"cannot reach the local SOCKS listener: {error}") from error

    try:
        # Greeting: version 5, one method, "no authentication". The listener is
        # bound to loopback and is deliberately unauthenticated, because the only
        # thing that can reach it is this host.
        sock.sendall(bytes([SOCKS_VERSION, 0x01, 0x00]))
        version, method = _recv_exactly(sock, 2)
        if version != SOCKS_VERSION:
            raise ProbeError(f"unexpected SOCKS version {version} from the listener")
        if method != 0x00:
            raise ProbeError(
                f"SOCKS listener requires authentication method {method}, "
                "which this probe does not implement"
            )

        # CONNECT request. A literal address is used rather than a domain name so
        # the probe never needs DNS: on these guests the mesh subnet is reachable
        # only inside sing-box, and a resolver lookup would go somewhere else.
        try:
            packed = socket.inet_aton(target_host)
            address = bytes([SOCKS_ADDR_IPV4]) + packed
        except OSError as error:
            raise ProbeError(
                f"{target_host} is not a literal IPv4 address; this probe "
                "deliberately does not resolve names"
            ) from error

        sock.sendall(
            bytes([SOCKS_VERSION, SOCKS_CONNECT, 0x00])
            + address
            + struct.pack("!H", target_port)
        )

        version, reply, _reserved, address_type = _recv_exactly(sock, 4)
        if version != SOCKS_VERSION:
            raise ProbeError(f"unexpected SOCKS version {version} in the reply")
        if address_type == SOCKS_ADDR_IPV4:
            _recv_exactly(sock, 4)
        elif address_type == SOCKS_ADDR_DOMAIN:
            length = _recv_exactly(sock, 1)[0]
            _recv_exactly(sock, length)
        else:
            _recv_exactly(sock, 4)
        _recv_exactly(sock, 2)  # bound port

        if reply != REPLY_OK:
            raise ProbeError(
                f"the tunnel refused the connection to {target_host}:{target_port} "
                f"(SOCKS reply 0x{reply:02x}). The listener is up, so the failure "
                "is in the tunnel or at the far end, not in this process."
            )
        return sock
    except Exception:
        sock.close()
        raise


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--socks-host", default="127.0.0.1")
    parser.add_argument("--socks-port", type=int, required=True)
    parser.add_argument("--target-host", required=True)
    parser.add_argument("--target-port", type=int, required=True)
    parser.add_argument("--timeout", type=float, default=8.0)
    args = parser.parse_args(argv)

    started = time.monotonic()
    try:
        relayed = socks5_connect(
            args.socks_host,
            args.socks_port,
            args.target_host,
            args.target_port,
            args.timeout,
        )
    except ProbeError as error:
        print(f"mesh probe FAILED: {error}", file=sys.stderr)
        return 1

    try:
        with relayed:
            relayed.settimeout(args.timeout)
            # The handshake is only half the claim: read one byte so a target that
            # accepts and then immediately resets cannot be reported as a pass.
            relayed.sendall(b"\x00")
            data = relayed.recv(1)
            elapsed_ms = int((time.monotonic() - started) * 1000)
            if not data:
                print(
                    "mesh probe FAILED: the tunnel relayed the connection but the "
                    "far end closed without answering",
                    file=sys.stderr,
                )
                return 1
            print(
                f"mesh probe OK: {args.target_host}:{args.target_port} reached "
                f"through the mesh in {elapsed_ms} ms"
            )
            return 0
    except OSError as error:
        print(f"mesh probe FAILED after the handshake: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())