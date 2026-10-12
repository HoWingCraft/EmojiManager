import os,json,struct,hashlib

MAGIC = b'PRTSENC1'
ENC_EXT = '.prtsenc'
_KEY = hashlib.sha256(b'PRTS-EMOJI-MANAGER-OBFUSCATE-2024').digest()


def _keystream(length):
    out = bytearray()
    block = _KEY
    while len(out) < length:
        block = hashlib.sha256(block).digest()
        out.extend(block)
    return bytes(out[:length])


def obfuscate(data):
    ks = _keystream(len(data))
    return bytes(a ^ b for a, b in zip(data, ks))


def is_encrypted_path(path):
    return bool(path) and str(path).lower().endswith(ENC_EXT)


def is_encrypted_blob(blob):
    return isinstance(blob, (bytes, bytearray)) and bytes(blob[:8]) == MAGIC


def encrypt_bytes(raw, name, ext):
    ext = (ext or '.png').lower()
    if not ext.startswith('.'):
        ext = '.' + ext
    header = json.dumps({'name': name or '未命名', 'ext': ext}, ensure_ascii=False).encode('utf-8')
    if len(header) > 0xFFFF:
        raise ValueError('名称过长')
    return MAGIC + struct.pack('>H', len(header)) + header + obfuscate(raw)


def decrypt_blob(blob):
    blob = bytes(blob)
    if blob[:8] != MAGIC:
        return None
    if len(blob) < 10:
        return None
    (hlen,) = struct.unpack('>H', blob[8:10])
    end = 10 + hlen
    if end > len(blob):
        return None
    try:
        header = json.loads(blob[10:end].decode('utf-8'))
    except Exception:
        return None
    name = header.get('name') or '未命名'
    ext = header.get('ext') or '.png'
    raw = obfuscate(blob[end:])
    return name, ext, raw


def peek_name(path):
    try:
        with open(path, 'rb') as f:
            head = f.read(10)
        if head[:8] != MAGIC or len(head) < 10:
            return None
        (hlen,) = struct.unpack('>H', head[8:10])
        with open(path, 'rb') as f:
            f.seek(10)
            hdr = f.read(hlen)
        header = json.loads(hdr.decode('utf-8'))
        return header.get('name') or None
    except Exception:
        return None


def encrypt_path(src_abs, name):
    ext = os.path.splitext(src_abs)[1].lower() or '.png'
    with open(src_abs, 'rb') as f:
        raw = f.read()
    return encrypt_bytes(raw, name, ext)