import struct
from typing import Tuple
import logging

logging.basicConfig(level=logging.INFO)

def find_duration_vint_idx(data: bytes) -> int:
    """
    Parses the binary data and identifies the location of the 0x4489 byte
    which is the EBML element ID for the Duration field in a Matroska/WebM file

    :param data: data stream read from .webm file
    :return: index location of the duration field
    """
    idx = data.find(b'\x44\x89')
    if idx == -1:
        raise RuntimeError(b"Could not find vint idx \x44\x89")
    return idx + 2

def parse_vint(data: bytes, vint_idx: int) -> Tuple[int, int]:
    """
    EBML VINT can have variable number of bytes. The information about how
    many of them is there is determined by the location of the first non-zero
    bit in the VINT sequence.

    The function determines the length of the VINT header and the size of the payload.
    This is needed to precisely replace the duration in the data byte stream without
    the need of recalculating checksums.

    The payload size returned is the size of the duration filed, not
    the actual duration.

    :param data: data stream read from the .webm file
    :param vint_idx: The vint sequence location index
    :return: the length of a VINT sequence in bytes and the payload size
    """
    first_vint_byte = data[vint_idx]
    vint_length = None
    header_mask = None

    for length in range(1, 9):
        header_mask = (1 << (8 - length))
        vint_header = first_vint_byte & header_mask
        if vint_header:
            vint_length = length
            break

    if vint_length is None:
        raise ValueError(f"Couldn't find the VINT length. Probably incorrect location was specified.")

    payload_size = first_vint_byte & (~header_mask)
    # fold in any continuation bytes
    if vint_idx + vint_length > len(data):
        raise ValueError("Truncated VINT")

    for i in range(1, vint_length):
        payload_size = (payload_size << 8) | data[vint_idx + i]
    return vint_length, payload_size

def read_duration(filename: str) -> int:
    """
    Reads and returns the duration of the video in seconds

    :param filename: Existing .webm file to read
    :return: duration in seconds
    """
    with open(filename, "rb") as f:
        data = f.read()
        vint_idx = find_duration_vint_idx(data)
        vint_length, payload_size = parse_vint(data, vint_idx)
        start_idx = vint_idx + vint_length
        duration_field = data[start_idx:start_idx + payload_size]
        if len(duration_field) != payload_size:
            raise ValueError("Unexpected EOF while reading duration")

        if payload_size == 4:
            # big-endian float
            return struct.unpack(">f", duration_field)[0] / 1e3
        elif payload_size == 8:
            # big-endian double
            return struct.unpack(">d", duration_field)[0] / 1e3
        else:
            raise ValueError(f"Unknown duration size: {payload_size} bytes")


def write_duration(filename: str, new_seconds: float) -> None:
    """
    Reads the file and alters the duration field

    :param filename: Name of the existing .webm file
    :param new_seconds: new duration in seconds
    """
    raw_ticks = new_seconds * 1000

    with open(filename, "r+b") as f:
        data = f.read()
        vint_idx =  find_duration_vint_idx(data)
        vint_length, payload_size = parse_vint(data, vint_idx)
        start_idx = vint_idx + vint_length
        f.seek(start_idx)
        if payload_size == 4:
            f.write(struct.pack(">f", raw_ticks))
        elif payload_size == 8:
            f.write(struct.pack(">d", raw_ticks))
        else:
            raise ValueError(f"Cannot patch duration of {payload_size} bytes")


def patch_duration(filename: str, new_seconds: float = 1) -> None:
    """
    High level function to patch the duration of the sticker
    :param filename: Existing .webm file to read and patch
    :param new_seconds: new duration in seconds
    """
    logger = logging.getLogger("patch_duration")
    duration = read_duration(filename)
    logger.info(f"Read the file {filename}. Determined duration: {duration} sec")
    write_duration(filename, new_seconds)
    logger.info(f"Patching the file...")
    duration = read_duration(filename)
    logger.info(f"Reading the file again. Determined duration: {duration} sec")
    logger.info(f"Success!")
