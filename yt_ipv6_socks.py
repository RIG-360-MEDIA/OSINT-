"""Rotating-IPv6 SOCKS5 proxy for YouTube extraction.

The Hetzner host has 256 IPv6 addresses bound on eth0 (2a01:4f8:1c18:c8ba::1000..10ff).
The containerised collector can't bind them directly (separate netns), and microsocks
won't force IPv6 egress. This tiny SOCKS5 server runs on the host (host network), and
for every CONNECT it: resolves the target to AAAA (forces IPv6), picks a RANDOM pool
address, binds it as the source, and connects — so YouTube sees a rotating origin IP
out of the /64, and the container just points yt-dlp / youtube-transcript-api at it.

No auth (bound to the host; reach it from containers via the bridge gateway).
"""
from __future__ import annotations

import asyncio
import logging
import random
import socket
import struct

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("yt-ipv6-socks")

POOL_BASE = "2a01:4f8:1c18:c8ba"
POOL_LO, POOL_HI = 0x1000, 0x10ff   # 256 addresses bound on the host
LISTEN_PORT = 4417


def _pick_source() -> str:
    return f"{POOL_BASE}::{random.randint(POOL_LO, POOL_HI):x}"


async def _pipe(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
    try:
        while True:
            chunk = await reader.read(65536)
            if not chunk:
                break
            writer.write(chunk)
            await writer.drain()
    except Exception:  # noqa: BLE001
        pass
    finally:
        try:
            writer.close()
        except Exception:  # noqa: BLE001
            pass


async def _handle(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
    loop = asyncio.get_event_loop()
    try:
        # SOCKS5 greeting
        ver, nmethods = struct.unpack("!BB", await reader.readexactly(2))
        await reader.readexactly(nmethods)
        writer.write(b"\x05\x00")  # version 5, no-auth
        await writer.drain()

        ver, cmd, _rsv, atyp = struct.unpack("!BBBB", await reader.readexactly(4))
        if cmd != 1:  # only CONNECT
            writer.write(b"\x05\x07\x00\x01\x00\x00\x00\x00\x00\x00")
            await writer.drain()
            writer.close()
            return
        if atyp == 1:      # IPv4 literal
            host = socket.inet_ntoa(await reader.readexactly(4))
        elif atyp == 3:    # domain
            ln = (await reader.readexactly(1))[0]
            host = (await reader.readexactly(ln)).decode("idna")
        elif atyp == 4:    # IPv6 literal
            host = socket.inet_ntop(socket.AF_INET6, await reader.readexactly(16))
        else:
            writer.close()
            return
        port = struct.unpack("!H", await reader.readexactly(2))[0]

        # Force IPv6 egress: resolve AAAA, bind a random pool address, connect.
        infos = await loop.getaddrinfo(host, port, family=socket.AF_INET6, type=socket.SOCK_STREAM)
        target = infos[0][4]
        src = _pick_source()
        sock = socket.socket(socket.AF_INET6, socket.SOCK_STREAM)
        sock.setblocking(False)
        sock.bind((src, 0))
        await loop.sock_connect(sock, target)
        up_r, up_w = await asyncio.open_connection(sock=sock)

        writer.write(b"\x05\x00\x00\x01\x00\x00\x00\x00\x00\x00")  # success
        await writer.drain()
        await asyncio.gather(_pipe(reader, up_w), _pipe(up_r, writer))
    except Exception as exc:  # noqa: BLE001
        try:
            writer.write(b"\x05\x01\x00\x01\x00\x00\x00\x00\x00\x00")  # general failure
            await writer.drain()
        except Exception:  # noqa: BLE001
            pass
        try:
            writer.close()
        except Exception:  # noqa: BLE001
            pass
        log.debug("conn failed: %s", exc)


async def main() -> None:
    server = await asyncio.start_server(_handle, "0.0.0.0", LISTEN_PORT)
    log.info("yt-ipv6-socks listening on :%d | pool %s::%x-%x (rotating per connection)",
             LISTEN_PORT, POOL_BASE, POOL_LO, POOL_HI)
    async with server:
        await server.serve_forever()


if __name__ == "__main__":
    asyncio.run(main())
