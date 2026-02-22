"""
Local SOCKS5 proxy tunnels (no auth) that forward to authenticated upstream proxies.
Chrome can't pass credentials via --proxy-server, so we strip auth locally.

Usage: python3 proxy_tunnel.py
       Starts tunnels on 127.0.0.1:11080-11089, writes proxies_local.txt
"""
import asyncio
import struct
import sys

UPSTREAMS = [
    # US proxies first — cleared Cloudflare cleanly
    ("23.95.150.145",   6114,  "fjhcddxl", "q0wad2e3iwlx"),  # US Buffalo
    ("198.23.239.134",  6540,  "fjhcddxl", "q0wad2e3iwlx"),  # US Buffalo
    ("107.172.163.27",  6543,  "fjhcddxl", "q0wad2e3iwlx"),  # US Bloomingdale
    ("198.105.121.200", 6462,  "fjhcddxl", "q0wad2e3iwlx"),  # UK London (worked)
    ("64.137.96.74",    6641,  "fjhcddxl", "q0wad2e3iwlx"),  # ES Madrid
    ("216.10.27.159",   6837,  "fjhcddxl", "q0wad2e3iwlx"),  # US Dallas
    ("142.111.67.146",  5611,  "fjhcddxl", "q0wad2e3iwlx"),  # US
    ("23.26.53.37",     6003,  "fjhcddxl", "q0wad2e3iwlx"),  # JP Tokyo
    # UK/problem proxies last
    ("31.59.20.176",    6754,  "fjhcddxl", "q0wad2e3iwlx"),  # UK London
    ("45.38.107.97",    6014,  "fjhcddxl", "q0wad2e3iwlx"),  # UK London
]
BASE_PORT = 11080


async def socks5_connect(upstream_host, upstream_port, user, password, dst_host, dst_port):
    """Connect to upstream SOCKS5 proxy with auth, request tunnel to dst."""
    reader, writer = await asyncio.open_connection(upstream_host, upstream_port)

    # --- Greeting: offer username/password auth ---
    writer.write(b"\x05\x01\x02")
    await writer.drain()
    resp = await reader.readexactly(2)
    if resp[1] != 0x02:
        raise ConnectionError(f"Upstream rejected auth method: {resp}")

    # --- Username/password auth ---
    u = user.encode()
    p = password.encode()
    writer.write(bytes([0x01, len(u)]) + u + bytes([len(p)]) + p)
    await writer.drain()
    resp = await reader.readexactly(2)
    if resp[1] != 0x00:
        raise ConnectionError(f"Upstream auth failed: {resp}")

    # --- Connect request ---
    host_bytes = dst_host.encode()
    writer.write(
        b"\x05\x01\x00\x03"
        + bytes([len(host_bytes)]) + host_bytes
        + struct.pack(">H", dst_port)
    )
    await writer.drain()
    resp = await reader.readexactly(4)
    if resp[1] != 0x00:
        raise ConnectionError(f"Upstream CONNECT failed: {resp}")
    # Consume the bound address
    atyp = resp[3]
    if atyp == 0x01:
        await reader.readexactly(4 + 2)
    elif atyp == 0x03:
        n = (await reader.readexactly(1))[0]
        await reader.readexactly(n + 2)
    elif atyp == 0x04:
        await reader.readexactly(16 + 2)

    return reader, writer


async def pipe(reader, writer):
    try:
        while True:
            data = await reader.read(65536)
            if not data:
                break
            writer.write(data)
            await writer.drain()
    except Exception:
        pass
    finally:
        writer.close()


async def handle_client(client_reader, client_writer, upstream_host, upstream_port, user, password):
    """Handle one incoming SOCKS5 connection (no auth required from client)."""
    try:
        # Greeting from client
        header = await client_reader.readexactly(2)
        nmethods = header[1]
        await client_reader.readexactly(nmethods)
        # Tell client: no auth required
        client_writer.write(b"\x05\x00")
        await client_writer.drain()

        # Request from client
        req = await client_reader.readexactly(4)
        cmd, atyp = req[1], req[3]
        if cmd != 0x01:
            client_writer.write(b"\x05\x07\x00\x01" + b"\x00" * 6)
            client_writer.close()
            return

        if atyp == 0x01:
            raw = await client_reader.readexactly(4)
            dst_host = ".".join(str(b) for b in raw)
        elif atyp == 0x03:
            n = (await client_reader.readexactly(1))[0]
            dst_host = (await client_reader.readexactly(n)).decode()
        else:
            client_writer.write(b"\x05\x08\x00\x01" + b"\x00" * 6)
            client_writer.close()
            return
        port_bytes = await client_reader.readexactly(2)
        dst_port = struct.unpack(">H", port_bytes)[0]

        # Connect upstream
        up_reader, up_writer = await socks5_connect(
            upstream_host, upstream_port, user, password, dst_host, dst_port
        )

        # Tell client: success
        client_writer.write(b"\x05\x00\x00\x01" + b"\x00" * 4 + b"\x00\x00")
        await client_writer.drain()

        # Pipe both directions
        await asyncio.gather(
            pipe(client_reader, up_writer),
            pipe(up_reader, client_writer),
        )
    except Exception as e:
        try:
            client_writer.close()
        except Exception:
            pass


async def main():
    servers = []
    with open("proxies_local.txt", "w") as f:
        for i, (host, port, user, pwd) in enumerate(UPSTREAMS):
            local_port = BASE_PORT + i

            def make_handler(h=host, p=port, u=user, pw=pwd):
                async def handler(r, w):
                    await handle_client(r, w, h, p, u, pw)
                return handler

            server = await asyncio.start_server(make_handler(), "127.0.0.1", local_port)
            servers.append(server)
            f.write(f"socks5://127.0.0.1:{local_port}\n")
            print(f"  Tunnel {i+1}: 127.0.0.1:{local_port} -> {host}:{port}")

    print(f"\n{len(UPSTREAMS)} tunnels ready. proxies_local.txt written.")
    print("Press Ctrl+C to stop.\n")

    async with asyncio.TaskGroup() as tg:
        for server in servers:
            tg.create_task(server.serve_forever())


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nStopped.")
