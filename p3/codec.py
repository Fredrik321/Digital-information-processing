"""The P2 lossless codec, moved out of p2/codec.ipynb so the P3 pipeline can import it.

The Huffman (codec_id 0) and PNG (codec_id 1) paths are byte-for-byte the P2
code, so P2's reported sizes can be reproduced. The one addition is
codec_id 2: zlib inside the same HFM2 container. That answers the P2
feedback that the zlib baseline did not carry shape and dtype: framed this
way, every variant pays the same 293-byte header and the totals differ only
in payload. "auto" mode does not consider zlib, so P2's auto results are
unchanged.
"""
import heapq
import io
import struct
import zlib
from collections import Counter

import numpy as np
from PIL import Image


def huffman_code_lengths(freqs):
    """freqs: dict symbol(int 0..255) -> count. Returns dict symbol -> bit length."""
    symbols = [s for s, f in freqs.items() if f > 0]
    if not symbols:
        return {}
    if len(symbols) == 1:
        return {symbols[0]: 1}   # single-symbol edge case: 1 bit per symbol

    # Deterministic tie-breaking: (freq, insertion order, node)
    heap = [(freqs[s], i, s) for i, s in enumerate(symbols)]
    heapq.heapify(heap)
    tie = len(symbols)

    while len(heap) > 1:
        f1, _, n1 = heapq.heappop(heap)
        f2, _, n2 = heapq.heappop(heap)
        heapq.heappush(heap, (f1 + f2, tie, (n1, n2)))
        tie += 1

    root = heap[0][2]

    lengths = {}
    stack = [(root, 0)]
    while stack:
        node, depth = stack.pop()
        if isinstance(node, int):
            lengths[node] = depth
        else:
            left, right = node
            stack.append((left, depth + 1))
            stack.append((right, depth + 1))
    return lengths


def canonical_codes(lengths):
    """lengths: dict symbol -> length. Returns dict symbol -> (code_int, length).
    Canonical Huffman: sort by (length, symbol), assign incrementally."""
    items = sorted(lengths.items(), key=lambda kv: (kv[1], kv[0]))
    codes = {}
    code = 0
    prev_len = 0
    for sym, length in items:
        code <<= (length - prev_len)
        codes[sym] = (code, length)
        code += 1
        prev_len = length
    return codes


def encode_symbols(symbols, codes):
    """symbols: iterable of ints. codes: dict sym -> (code, length). MSB-first packing.

    P3 change: after each flush the accumulator is masked down to the bits
    not yet written. Without the mask (encode_symbols_p2) `acc` keeps every
    bit ever written, so each shift copies a Python int that grows to the
    whole payload and encoding is quadratic. The emitted bytes are identical.
    """
    out = bytearray()
    acc = 0
    nbits = 0
    for s in symbols:
        code, length = codes[s]
        acc = (acc << length) | code
        nbits += length
        while nbits >= 8:
            nbits -= 8
            out.append((acc >> nbits) & 0xFF)
        acc &= (1 << nbits) - 1
    if nbits > 0:
        out.append((acc << (8 - nbits)) & 0xFF)
    return bytes(out)


def encode_symbols_p2(symbols, codes):
    """The P2 encoder, unchanged. Kept only for bench.py and the equivalence test."""
    out = bytearray()
    acc = 0
    nbits = 0
    for s in symbols:
        code, length = codes[s]
        acc = (acc << length) | code
        nbits += length
        while nbits >= 8:
            nbits -= 8
            out.append((acc >> nbits) & 0xFF)
    if nbits > 0:
        out.append((acc << (8 - nbits)) & 0xFF)
    return bytes(out)


def decode_bits(payload, codes, n_symbols):
    """Inverse of encode_symbols. Reads exactly n_symbols symbols."""
    by_len = {}
    for sym, (code, length) in codes.items():
        by_len.setdefault(length, {})[code] = sym

    out = bytearray(n_symbols)
    acc = 0
    nbits = 0
    bit_pos = 0
    total_bits = len(payload) * 8

    for i in range(n_symbols):
        while nbits not in by_len or acc not in by_len[nbits]:
            if bit_pos >= total_bits:
                raise ValueError(f"ran out of bits at symbol {i}/{n_symbols}")
            byte = payload[bit_pos >> 3]
            bit = (byte >> (7 - (bit_pos & 7))) & 1
            acc = (acc << 1) | bit
            nbits += 1
            bit_pos += 1
        out[i] = by_len[nbits][acc]
        acc = 0
        nbits = 0
    return bytes(out)


MAGIC = b"HFM2"
CODEC_NAMES = {0: "huffman", 1: "png", 2: "zlib"}


def pack_header(dtype_str, shape, original_n_bytes, code_lengths, crc, codec_id, predictor=0):
    """Pack the self-describing header. Byte layout, little-endian integers:

    [0:4]        magic "HFM2"
    [4]          dtype string length
    [5:5+len]    dtype string (ascii)
    +1           ndim
    +4*ndim      shape, one uint32 per dimension
    +8           original byte count (uint64)
    +256         Huffman code lengths, one byte per symbol
    +4           CRC32 of the original bytes (uint32)
    +1           codec id: 0 = Huffman, 1 = PNG, 2 = zlib
    +1           predictor: 0 = none, 1 = horizontal, 2 = vertical
    everything after the header is the payload (Huffman bits, PNG image or zlib stream)

    A 224x224x3 uint8 image has a 5-char dtype and ndim 3, so its header is
    4+1+5+1+12+8+256+4+1+1 = 293 bytes.
    """
    assert len(code_lengths) == 256
    dtype_bytes = dtype_str.encode("ascii")
    out = bytearray()
    out += MAGIC
    out.append(len(dtype_bytes))
    out += dtype_bytes
    out.append(len(shape))
    for d in shape:
        out += struct.pack("<I", d)
    out += struct.pack("<Q", original_n_bytes)
    out += bytes(code_lengths)
    out += struct.pack("<I", crc)
    out.append(codec_id)
    out.append(predictor)
    return bytes(out)


def unpack_header(buf):
    """Inverse of pack_header. Returns (dtype_str, shape, original_n_bytes,
    code_lengths, crc, codec_id, predictor, payload)."""
    if buf[:4] != MAGIC:
        raise ValueError("bad magic or unsupported codec version")
    pos = 4
    dtype_len = buf[pos]
    pos += 1
    dtype_str = buf[pos:pos + dtype_len].decode("ascii")
    pos += dtype_len
    ndim = buf[pos]
    pos += 1
    shape = []
    for _ in range(ndim):
        shape.append(struct.unpack_from("<I", buf, pos)[0])
        pos += 4
    shape = tuple(shape)
    original_n_bytes = struct.unpack_from("<Q", buf, pos)[0]
    pos += 8
    code_lengths = list(buf[pos:pos + 256])
    pos += 256
    crc = struct.unpack_from("<I", buf, pos)[0]
    pos += 4
    codec_id = buf[pos]
    pos += 1
    predictor = buf[pos]
    pos += 1
    return dtype_str, shape, original_n_bytes, code_lengths, crc, codec_id, predictor, buf[pos:]


# Delta pre-processing for the Huffman path: the transform is applied to the
# samples before byte counting / Huffman coding. The PNG path never uses it.
# uint8 arithmetic wraps mod 256, so encoder and decoder are exact inverses.
PREDICTOR_IDS = {"none": 0, "horizontal": 1, "vertical": 2}
PREDICTOR_NAMES = {v: k for k, v in PREDICTOR_IDS.items()}


def delta_horizontal(arr):
    """Horizontal delta: each sample minus its left neighbour (axis 1).
    The first column is stored verbatim; uint8 subtraction wraps mod 256."""
    out = np.empty_like(arr)
    out[:, 0] = arr[:, 0]
    out[:, 1:] = arr[:, 1:] - arr[:, :-1]
    return out


def delta_vertical(arr):
    """Vertical delta: each sample minus its upper neighbour (axis 0).
    The first row is stored verbatim; uint8 subtraction wraps mod 256."""
    out = np.empty_like(arr)
    out[0, :] = arr[0, :]
    out[1:, :] = arr[1:, :] - arr[:-1, :]
    return out


def undelta_horizontal(arr):
    """Exact inverse of delta_horizontal: cumulative sum along axis 1.
    The uint8 accumulator wraps mod 256, mirroring the subtraction."""
    return np.cumsum(arr, axis=1, dtype=np.uint8)


def undelta_vertical(arr):
    """Exact inverse of delta_vertical: cumulative sum along axis 0."""
    return np.cumsum(arr, axis=0, dtype=np.uint8)


def _is_png_image(arr):
    return (arr.dtype == np.uint8 and arr.ndim in (2, 3)
            and (arr.ndim == 2 or arr.shape[2] in (3, 4)))


def _is_predictable(arr):
    """The delta predictors are defined for 2-D or 3-D uint8 arrays."""
    return arr.dtype == np.uint8 and arr.ndim in (2, 3)


def _huffman_container(arr, raw, n, predictor_id):
    """Build one complete Huffman container using a given predictor.

    The predictor transforms the samples first; Huffman then codes the
    transformed bytes. The CRC always covers the *original* bytes so it can
    be checked after decoding and inverting the predictor."""
    if predictor_id == 0:
        stream = raw
    else:
        predicted = delta_horizontal(arr) if predictor_id == 1 else delta_vertical(arr)
        stream = np.ascontiguousarray(predicted).tobytes()
    freqs = Counter(stream)
    lengths = huffman_code_lengths(freqs)
    codes = canonical_codes(lengths)
    payload = encode_symbols(stream, codes)
    code_lengths = [lengths.get(s, 0) for s in range(256)]
    header = pack_header(str(arr.dtype), arr.shape, n, code_lengths,
                         zlib.crc32(raw) & 0xFFFFFFFF, 0, predictor_id)
    return header + payload


def compress(data, settings=None):
    """Return a self-contained, lossless compressed representation of a NumPy array.

    settings:
      "image_codec": "auto" (default) | "huffman" | "png" | "zlib"
      "predictor":   "none" (default) | "horizontal" | "vertical" | "auto"
        Delta pre-processing for the Huffman path only; the PNG and zlib
        paths ignore it. On non-image arrays horizontal/vertical are ignored
        (the header then records "none"); "auto" tries all applicable
        variants and keeps the smallest container.
      "zlib_level":  0-9 (default 6), used only by the zlib path.
    """
    arr = np.ascontiguousarray(data)
    raw = arr.tobytes()
    n = len(raw)
    settings = settings or {}
    image_codec = settings.get("image_codec", "auto")
    predictor = settings.get("predictor", "none")
    if image_codec not in ("auto", "huffman", "png", "zlib"):
        raise ValueError(f"unknown image_codec: {image_codec!r}")
    if predictor not in ("none", "horizontal", "vertical", "auto"):
        raise ValueError(f"unknown predictor: {predictor!r}")

    # Empty array: only header needed (nothing to predict)
    if n == 0:
        crc = zlib.crc32(raw) & 0xFFFFFFFF
        return pack_header(str(arr.dtype), arr.shape, 0, [0] * 256, crc, 0, 0)

    # zlib baseline in our container: same header as every other path, so
    # the comparison carries the same shape/dtype/CRC side information.
    if image_codec == "zlib":
        payload = zlib.compress(raw, level=settings.get("zlib_level", 6))
        header = pack_header(str(arr.dtype), arr.shape, n, [0] * 256,
                             zlib.crc32(raw) & 0xFFFFFFFF, 2, 0)
        return header + payload

    # Which delta variants the Huffman path should try. Explicit predictors
    # are only defined on image-shaped arrays; elsewhere they are ignored,
    # and "auto" degenerates to "none" as well.
    if _is_predictable(arr) and predictor == "auto":
        candidates = ("none", "horizontal", "vertical")
    elif _is_predictable(arr) and predictor in ("horizontal", "vertical"):
        candidates = (predictor,)
    else:
        candidates = ("none",)

    # --- Compute Huffman results if needed (one per predictor candidate) ---
    huffman_results = None
    if image_codec != "png":          # "huffman" or "auto"
        huffman_results = {
            name: _huffman_container(arr, raw, n, PREDICTOR_IDS[name])
            for name in candidates
        }

    # --- Compute PNG result if needed (predictor never applies here) ---
    png_result = None
    if image_codec != "huffman" and _is_png_image(arr):
        image = Image.fromarray(arr)
        output = io.BytesIO()
        image.save(output, format="PNG", optimize=True, compress_level=9)
        payload = output.getvalue()
        header = pack_header(str(arr.dtype), arr.shape, n, [0] * 256,
                             zlib.crc32(raw) & 0xFFFFFFFF, 1, 0)
        png_result = header + payload

    # --- Select the output ---
    if image_codec == "png":
        if png_result is None:
            raise ValueError("PNG codec requested but array is not a valid PNG image")
        return png_result
    elif image_codec == "huffman":
        return min(huffman_results.values(), key=len)
    else:  # auto
        built = [r for r in (png_result, *huffman_results.values()) if r is not None]
        # If PNG is not applicable, fall back to the best Huffman container
        return min(built, key=len) if built else min(huffman_results.values(), key=len)


def decompress(compressed, settings_or_metadata=None):
    """Return the original array from a losslessly compressed byte string."""
    (dtype_str, shape, original_n_bytes, code_lengths, crc,
     codec_id, predictor, payload) = unpack_header(compressed)

    if predictor not in PREDICTOR_NAMES:
        raise ValueError(f"unknown predictor id: {predictor}")
    if codec_id in (1, 2) and predictor != 0:
        raise ValueError(f"{CODEC_NAMES[codec_id]} containers do not use a predictor")

    if original_n_bytes == 0:
        raw = b""
    elif codec_id == 1:
        with Image.open(io.BytesIO(payload)) as image:
            decoded = np.asarray(image)
        if decoded.dtype != np.uint8 or decoded.shape != shape:
            raise ValueError("PNG payload does not match the stored array metadata")
        raw = np.ascontiguousarray(decoded).tobytes()
    elif codec_id == 2:
        try:
            raw = zlib.decompress(payload)
        except zlib.error as exc:
            raise ValueError(f"zlib payload corrupted: {exc}") from exc
    elif codec_id == 0:
        lengths = {s: L for s, L in enumerate(code_lengths) if L > 0}
        if not lengths:
            raise ValueError("no code lengths in header")
        stream = decode_bits(payload, canonical_codes(lengths), original_n_bytes)
        # Rebuild the (possibly predicted) array, invert the predictor, and
        # only then check length and CRC against the *original* bytes.
        arr = np.frombuffer(stream, dtype=np.dtype(dtype_str)).reshape(shape)
        if predictor != 0 and not _is_predictable(arr):
            raise ValueError("predictor byte set on a non-image-shaped array")
        if predictor == 1:
            arr = undelta_horizontal(arr)
        elif predictor == 2:
            arr = undelta_vertical(arr)
        raw = np.ascontiguousarray(arr).tobytes()
    else:
        raise ValueError(f"unknown codec id: {codec_id}")

    if len(raw) != original_n_bytes:
        raise ValueError("decoded byte count does not match metadata")
    if (zlib.crc32(raw) & 0xFFFFFFFF) != crc:
        raise ValueError("CRC mismatch - payload corrupted")

    return np.frombuffer(raw, dtype=np.dtype(dtype_str)).reshape(shape).copy()


def describe_compressed(compressed):
    """Name the codec a container actually used, read from its header."""
    *_, codec_id, _predictor, _payload = unpack_header(compressed)
    return CODEC_NAMES.get(codec_id, f"unknown codec id {codec_id}")


def describe_predictor(compressed):
    """Name the delta predictor a container actually used, read from its header."""
    *_, predictor, _payload = unpack_header(compressed)
    return PREDICTOR_NAMES.get(predictor, f"unknown predictor id {predictor}")


def container_sizes(compressed):
    """Split one of our containers into header (side info) and payload."""
    *_, payload = unpack_header(compressed)
    return len(compressed) - len(payload), len(payload)
