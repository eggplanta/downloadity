import os
import tempfile
import urllib.request

from kivy.core.image import ImageLoader

RAMP = ".:-=+*#%@"
COLOR_STEP = 24


def cover_markup(info: dict, cols: int, rows: int) -> str:
    """
    Colored ASCII of the item's cover, as Kivy markup
    """
    url = _cover_url(info)
    if not url:
        return ""

    with urllib.request.urlopen(url, timeout=10) as response:
        data = response.read()

    fd, path = tempfile.mkstemp(suffix=".jpg")
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(data)
        image = ImageLoader.load(path, keep_data=True)._data[0]
    finally:
        os.remove(path)

    return _to_markup(image, cols, rows)


# Internal helpers

def _cover_url(info: dict):
    thumbs = [
        t for t in info.get("thumbnails") or []
        if ".jpg" in t.get("url", "") and t.get("width")
    ]
    if not thumbs:
        return info.get("thumbnail")

    # Smallest jpg that still looks good
    big = [t for t in thumbs if t["width"] >= 300]
    if big:
        return min(big, key=lambda t: t["width"])["url"]
    return max(thumbs, key=lambda t: t["width"])["url"]


def _to_markup(image, cols: int, rows: int) -> str:
    width, height, pixels = image.width, image.height, image.data
    bpp = 4 if image.fmt in ("rgba", "bgra") else 3
    stride = len(pixels) // height
    bgr = image.fmt in ("bgr", "bgra")

    # Square center crop
    side = min(width, height)
    left = (width - side) // 2
    top = (height - side) // 2

    lines = []
    for row in range(rows):
        runs = []
        for col in range(cols):
            r, g, b = _cell_color(pixels, stride, bpp, left, top, side, cols, rows, col, row)
            if bgr:
                r, b = b, r

            lum = 0.299 * r + 0.587 * g + 0.114 * b
            char = RAMP[min(len(RAMP) - 1, int(lum / 256 * len(RAMP)))]
            color = "".join(f"{_quantize(c):02x}" for c in (r, g, b))

            if runs and runs[-1][0] == color:
                runs[-1][1].append(char)
            else:
                runs.append((color, [char]))

        lines.append("".join(f"[color=#{c}]{''.join(chars)}[/color]" for c, chars in runs))

    return "\n".join(lines)


def _cell_color(pixels, stride, bpp, left, top, side, cols, rows, col, row):
    # Average a 3x3 grid inside the cell
    total = [0, 0, 0]
    for dy in (0.25, 0.5, 0.75):
        for dx in (0.25, 0.5, 0.75):
            x = left + int((col + dx) * side / cols)
            y = top + int((row + dy) * side / rows)
            i = y * stride + x * bpp
            total[0] += pixels[i]
            total[1] += pixels[i + 1]
            total[2] += pixels[i + 2]

    return [c // 9 for c in total]


def _quantize(value: int) -> int:
    return min(255, round(value / COLOR_STEP) * COLOR_STEP)
