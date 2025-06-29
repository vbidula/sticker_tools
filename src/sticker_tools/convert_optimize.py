import logging

import sys
import platform
import os
from pathlib import Path
import subprocess

def run(cmd, **kwargs):
    # on Windows add the no-window flags …
    if sys.platform == "win32":
        kwargs.setdefault("creationflags", subprocess.CREATE_NO_WINDOW)
        si = subprocess.STARTUPINFO()
        si.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        si.wShowWindow = subprocess.SW_HIDE
        kwargs.setdefault("startupinfo", si)

    # only set check once
    kwargs.setdefault("check", True)

    # **don’t** do: kwargs.setdefault("stdout", PIPE) or stderr here
    return subprocess.run(cmd, **kwargs)


if platform.system() == 'Windows':
    if getattr(sys, 'frozen', False):
        base = Path(sys._MEIPASS)
    else:
        # when running from source, project root is two levels up
        base = Path(__file__).resolve().parents[2]
    bin_dir = base / 'bin'
    os.environ['PATH'] = str(bin_dir) + os.pathsep + os.environ.get('PATH', '')

logging.basicConfig(level=logging.INFO)


# 1️⃣ Pass 1 (analyze only)
# ffmpeg -y -i input.ext \
#   -c:v libvpx-vp9 -b:v ${vid_bps} \
#   -pass 1 -an -f null /dev/null
#
# # 2️⃣ Pass 2 (actual encode)
# ffmpeg -i input.ext \
#   -c:v libvpx-vp9 -b:v ${vid_bps} \
#   -pass 2 -an \
#   output.webm

def get_duration(path):
    import json
    import shlex
    cmd = ['ffprobe', '-v', 'error', '-show_entries', 'format=duration', '-of', 'json', path]
    result = run(cmd, capture_output=True, text=True, check=True)
    info = json.loads(result.stdout)
    return float(info["format"]["duration"])

def estimate_bitrate(duration: float, target_size_kb: float) -> float:
    return target_size_kb * 1024 * 8 / duration

def get_scalecrop_filter(path):
    import json
    import shlex
    cmd = ['ffprobe', '-v', 'error', '-select_streams', 'v:0', '-show_entries', 'stream=width,height,avg_frame_rate', '-of', 'json', path]
    result = run(cmd, capture_output=True, text=True, check=True)
    info = json.loads(result.stdout)["streams"][0]
    w = int(info["width"])
    h = int(info["height"])
    # skip unnecessary resampling if already at target resolution
    if w == 512 and h == 512:
        return None
    fr = info.get("avg_frame_rate", "0/1")
    num, den = map(int, fr.split('/'))
    fps = num / den if den else 0

    filters = []

    # scale the smallest dimension to 512, then center-crop the larger to 512
    if w < h:
        # scale width to 512, maintain aspect, then crop height
        filters.append("scale=512:-1,crop=512:512:0:(ih-512)/2")
    else:
        # scale height to 512, maintain aspect, then crop width
        filters.append("scale=-1:512,crop=512:512:(iw-512)/2:0")


    if fps > 30:
        filters.append("fps=30")

    if not filters:
        return None
    return ",".join(filters)

def vp9_pass1(input_path: str, output_path: str, vid_bps: float):
    """
    First pass: analyze video complexity for two-pass VP9 encoding.
    """
    vf = get_scalecrop_filter(input_path)
    cmd = [
        'ffmpeg', '-strict', '-2', '-v', 'quiet', '-hide_banner', '-threads', '0', '-hwaccel', 'auto',
        '-i', input_path,
        '-pass', '1', '-passlogfile', output_path,
        '-c:v', 'libvpx-vp9', '-row-mt', '1',
        '-b:v', str(vid_bps),
        '-speed', '0', '-quality', 'best',
        '-map', 'v:0', '-an', '-pix_fmt', 'yuv420p',
        '-timecode', '01:00:00:00',
        '-sws_flags', 'bicubic',
        '-y', output_path
    ]
    run(cmd)


def vp9_pass2(input_path: str, output_path: str, vid_bps: float):
    """
    Second pass: encode video using two-pass VP9 with file-size guard.
    """
    vf = get_scalecrop_filter(input_path)
    cmd = [
        'ffmpeg', '-strict', '-2', '-v', 'quiet', '-hide_banner', '-threads', '0', '-hwaccel', 'auto',
        '-i', input_path,
        '-pass', '2', '-passlogfile', output_path,
        '-c:v', 'libvpx-vp9', '-row-mt', '1',
        '-b:v', str(vid_bps),
        '-speed', '0', '-quality', 'best',
        '-map', 'v:0', '-an', '-pix_fmt', 'yuv420p',
        '-timecode', '01:00:00:00',
        '-sws_flags', 'bicubic',
        '-y', output_path
    ]
    run(cmd)


def cleanup(path='.'):
    """
    Remove all files in `path` that end with .log or .log.mbtree
    """
    logger = logging.getLogger("cleanup")

    logger.info(f"Cleaning res=idual files in {path}")
    for fname in os.listdir(path):
        if fname.endswith(('.log', '.log.mbtree', '.webm-0')):
            try:
                logger.info(f"Removing {fname}")
                os.remove(os.path.join(path, fname))
            except OSError:
                logger.info(f"Could not remove {fname}")
                pass

def convert(input_path: str, output_path: str, target_size_kb: float = 255):
    duration = get_duration(input_path)
    bitrate = estimate_bitrate(duration, target_size_kb)
    vp9_pass1(input_path, output_path, bitrate)
    vp9_pass2(input_path, output_path, bitrate)

def convert_optimize(input_path: str, target_size_kb: float = 255, accuracy_kb: float = 5, progress_callback=None):
    """
    Binary-search the target size in KB to find the optimal bitrate
    that yields a file just under target_size_kb.
    """
    logger = logging.getLogger("convert_optimize")
    output_path = os.path.splitext(input_path)[0] + ".webm"
    # search bounds in KB
    test_bitrate = estimate_bitrate(get_duration(input_path), target_size_kb)
    logger.info(f"Doing a test run with bitrate {test_bitrate / 1000:.2f} kbps ...")
    if progress_callback:
        progress_callback(1)
    vp9_pass1(input_path, output_path, test_bitrate)
    vp9_pass2(input_path, output_path, test_bitrate)
    actual_kb = os.path.getsize(output_path) / 1024

    if actual_kb > target_size_kb:
        logger.info(f"Exceeded target file size with {actual_kb}, starting a search")
    else:
        logger.info(f"Worked, staying at {test_bitrate:.2f} kbps")
        logger.info(f"Final size: {os.path.getsize(output_path) / 1024:.2f} kb")
        return

    scale_coef = 255 / actual_kb
    high = test_bitrate * scale_coef
    low = high - test_bitrate * (1 - scale_coef)
    best_bitrate = (high + low) / 2
    last_loop = False


    # limited iterations to avoid infinite loop
    for iteration in range(1, 9):
        if progress_callback:
            progress_callback(iteration + 1)

        logger.info(f"Encoding with bitrate {best_bitrate/1000:.2f} kbps. Iteration {iteration} / 9")
        vp9_pass1(input_path, output_path, best_bitrate)
        vp9_pass2(input_path, output_path, best_bitrate)
        actual_kb = os.path.getsize(output_path) / 1024
        logger.info(f"Encoded file size: {actual_kb:.2f} kb")
        if last_loop:
            break

        if actual_kb > target_size_kb:
            logger.info(f"Exceeded target file size with {actual_kb}, setting bitrate top limit to {best_bitrate/1000:.2f} kbps")
            high = best_bitrate
        else:
            logger.info(f"Worked!")
            low = best_bitrate

        if 0 < (target_size_kb - actual_kb) < accuracy_kb:
            logger.info(f"{target_size_kb - accuracy_kb} kb < [{actual_kb} kb] < {target_size_kb} kb")
            logger.info(f"Breaking the loop")
            break
        else:
            if iteration == 9:
                last_loop = True
            best_bitrate = (high + low) / 2
            low = low - 2 * target_size_kb
            logger.info(f"Trying bitrate: {best_bitrate / 1000:.2f} kbps")




    logger.info(f"Success!")
    logger.info(f"Optimal bitrate: {best_bitrate / 1000:.2f} kbps")
    logger.info(f"Final size: {os.path.getsize(output_path) / 1024:.2f} kb")
