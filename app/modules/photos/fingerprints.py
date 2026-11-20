from collections import defaultdict
from hashlib import sha256
from struct import unpack_from
from zlib import crc32

from app.modules.intake.values import InvalidRow

PNG_SIGNATURE = b'\x89PNG\r\n\x1a\n'


def png_hash(content):
    if not content or not content.startswith(PNG_SIGNATURE):
        raise InvalidRow('BAD_PHOTO_FILE')
    pos, seen_data = len(PNG_SIGNATURE), False
    while pos + 12 <= len(content):
        length, kind = unpack_from('>I4s', content, pos)
        start, stop = pos + 8, pos + 8 + length
        if stop + 4 > len(content) or crc32(content[pos + 4:stop]) != unpack_from('>I', content, stop)[0]:
            break
        if pos == len(PNG_SIGNATURE):
            if kind != b'IHDR' or length != 13:
                break
            width, height = unpack_from('>II', content, start)
            if not (1 <= width <= 8192 and 1 <= height <= 8192):
                break
        if kind == b'IDAT' and length:
            seen_data = True
        if kind == b'IEND':
            if seen_data and length == 0 and stop + 4 == len(content):
                return sha256(content).hexdigest()
            break
        pos = stop + 4
    raise InvalidRow('BAD_PHOTO_FILE')


def reused_groups(rows):
    grouped = defaultdict(list)
    for row in rows:
        grouped[row['sha256']].append(row)
    return {digest: group for digest, group in grouped.items()
            if len({(row['visit'], row['slot']) for row in group}) > 1}
