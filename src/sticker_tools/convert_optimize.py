import ffmpeg
import os
import logging

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
    info = ffmpeg.probe(path)
    return float(info["format"]["duration"])

def estimate_bitrate(duration: float, target_size_kb: float) -> float:
    return target_size_kb * 1024 * 8 / duration

def get_scalecrop_filter(path):
    info = ffmpeg.probe(path)["streams"][0]
    w = int(info["width"])
    h = int(info["height"])
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

def vp9_pass1(input_path: str, vid_bps: float):
    """
    First pass: analyze video complexity for two-pass VP9 encoding.
    """
    vf = get_scalecrop_filter(input_path)
    stream = ffmpeg.input(input_path).video
    # build output keyword arguments, adding filter if needed
    output_kwargs = {'format': 'null', 'c:v': 'libvpx-vp9', 'b:v': str(vid_bps)}
    if vf:
        output_kwargs['vf'] = vf
    stream.output(
        'null',
        **output_kwargs
    ).global_args(
        '-y', '-pass', '1', '-an', '-loglevel', 'quiet',
        '-speed', '4'
    ).run()



def vp9_pass2(input_path: str, output_path: str, vid_bps: float):
    """
    Second pass: encode video using two-pass VP9 with file-size guard.
    """
    vf = get_scalecrop_filter(input_path)
    stream = ffmpeg.input(input_path).video
    # build output keyword arguments, adding filter if needed
    output_kwargs = {'c:v': 'libvpx-vp9', 'b:v': str(vid_bps)}
    if vf:
        output_kwargs['vf'] = vf
    stream.output(
        output_path,
        **output_kwargs
    ).global_args(
        '-pass', '2', '-an', '-y', '-loglevel', 'quiet',
        '-deadline', 'best',
        '-cpu-used', '1',
        '-row-mt', '1',
        '-tile-columns', '2'
    ).run()


def cleanup():
    for ext in (".log", ".log.mbtree"):
        fname = f"ffmpeg2pass-0{ext}"
        if os.path.exists(fname):
            os.remove(fname)

def convert(input_path: str, output_path: str, target_size_kb: float = 255):
    duration = get_duration(input_path)
    bitrate = estimate_bitrate(duration, target_size_kb)
    vp9_pass1(input_path, bitrate)
    vp9_pass2(input_path, output_path, bitrate)

def convert_optimize(input_path: str, target_size_kb: float = 255, accuracy_kbps: float = 1, progress_callback=None):
    """
    Binary-search the target size in KB to find the optimal bitrate
    that yields a file just under target_size_kb.
    """
    logger = logging.getLogger("convert_optimize")
    output_path = os.path.splitext(input_path)[0] + ".webm"
    # search bounds in KB
    low = 0.0
    high = estimate_bitrate(get_duration(input_path), target_size_kb)
    best_bitrate = high
    last_loop = False

    # limited iterations to avoid infinite loop
    for iteration in range(10):
        if progress_callback:
            progress_callback(iteration + 1)

        logger.info(f"Encoding with bitrate {best_bitrate/8192:.2f} kbps ...")
        vp9_pass1(input_path, best_bitrate)
        vp9_pass2(input_path, output_path, best_bitrate)
        actual_kb = os.path.getsize(output_path) / 1000
        logger.info(f"Encoded file size: {actual_kb:.2f} kb")
        if last_loop:
            break

        if actual_kb > target_size_kb:
            logger.info(f"Overshoot, setting bitrate top limit to {best_bitrate/8192:.2f} kbps")
            high = best_bitrate
        else:
            logger.info(f"Worked, checking if we can do better...")
            low = best_bitrate

        best_bitrate = (high + low) / 2
        # stop if bounds converge within 1 KB
        if (high - low) / 8192 < accuracy_kbps:
            if actual_kb > target_size_kb:
                best_bitrate = low
                last_loop = True
                logger.info(f"Returning to the best bitrate of: {best_bitrate / 8192:.2f} kbps")
            else:
                break

        if iteration == 9:
            best_bitrate = low
            last_loop = True


    logger.info(f"Success!")
    logger.info(f"Optimal bitrate: {best_bitrate / 8192:.2f} kbps")
    logger.info(f"Final size: {os.path.getsize(output_path) / 1000:.2f} kb")
