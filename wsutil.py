"""Minimaler RFC6455-WebSocket ueber asyncio-Streams (ohne Fremdbibliotheken)."""
import asyncio
import base64
import hashlib

WS_GUID = "258EAFA5-E914-47DA-95CA-C5AB0DC85B11"


def accept_key(key: str) -> str:
    return base64.b64encode(
        hashlib.sha1((key + WS_GUID).encode()).digest()
    ).decode()


def encode_frame(payload: bytes, opcode: int = 0x1) -> bytes:
    b1 = 0x80 | opcode
    n = len(payload)
    if n < 126:
        header = bytes([b1, n])
    elif n < 65536:
        header = bytes([b1, 126]) + n.to_bytes(2, "big")
    else:
        header = bytes([b1, 127]) + n.to_bytes(8, "big")
    return header + payload


async def read_message(reader: asyncio.StreamReader):
    """Liefert (opcode, bytes) einer kompletten (evtl. fragmentierten) Nachricht,
    oder None bei Verbindungsende/Close."""
    chunks, first_opcode, total = getattr(reader, '_ws_fragments', ([], None, 0))
    while True:
        try:
            hdr = await reader.readexactly(2)
        except (asyncio.IncompleteReadError, ConnectionError):
            return None
        b1, b2 = hdr[0], hdr[1]
        fin = b1 & 0x80
        opcode = b1 & 0x0F
        masked = b2 & 0x80
        ln = b2 & 0x7F
        if b1 & 0x70 or not masked or opcode not in (0, 1, 2, 8, 9, 10):
            raise ValueError('Invalid WebSocket frame')
        try:
            if ln == 126:
                ln = int.from_bytes(await reader.readexactly(2), "big")
            elif ln == 127:
                ln = int.from_bytes(await reader.readexactly(8), "big")
            if opcode >= 8:
                if not fin or ln > 125:
                    raise ValueError('Invalid control frame')
            elif ln + total > 65536:
                raise ValueError('Message too large')
            mask = await reader.readexactly(4) if masked else None
            data = await reader.readexactly(ln) if ln else b""
        except (asyncio.IncompleteReadError, ConnectionError):
            return None
        if masked:
            data = bytes(b ^ mask[i % 4] for i, b in enumerate(data))
        if opcode == 0x8:      # close
            return (0x8, b"")
        if opcode in (0x9, 0xA):  # ping/pong -> als Steueropcode zurueckgeben
            reader._ws_fragments = (chunks, first_opcode, total)
            return (opcode, data)
        if opcode == 0 and first_opcode is None:
            raise ValueError('Unexpected continuation')
        if opcode != 0x0:
            if first_opcode is not None:
                raise ValueError('Missing continuation')
            first_opcode = opcode
        chunks.append(data)
        total += ln
        if fin:
            reader._ws_fragments = ([], None, 0)
            return (first_opcode or 0x1, b"".join(chunks))
