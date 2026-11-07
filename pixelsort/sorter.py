import random
import typing
import numpy as np
import numpy.typing as npt
from PIL import Image


Pixel = tuple[int, int, int, int]
Coordinate = tuple[int, int]


class PixelAccess(typing.Protocol):
    def __getitem__(self, xy: Coordinate) -> Pixel: ...

    def __setitem__(self, xy: Coordinate, value: Pixel) -> None: ...


class MaskAccess(typing.Protocol):
    def __getitem__(self, xy: Coordinate) -> int: ...
from pixelsort.sorting import SortingFunction


def sort_image(
    image: Image.Image,
    mask: Image.Image,
    intervals: list[list[int]],
    randomness: float,
    sorting_function: SortingFunction,
) -> Image.Image:
    w, h = image.size
    pix: npt.NDArray[np.uint8] = np.asarray(image.convert("RGBA"))  # (h, w, 4)
    m: npt.NDArray[np.bool_] = np.asarray(mask.convert("L")) != 0  # (h, w)

    # Global interval id per pixel: the number of bounds <= x, offset per row.
    lens = np.fromiter((len(r) for r in intervals), dtype=np.int64, count=h)
    flags = np.zeros((h, w + 1), dtype=np.int64)
    if lens.sum():
        ys = np.repeat(np.arange(h), lens)
        xs = np.fromiter((x for r in intervals for x in r), dtype=np.int64)
        np.add.at(flags, (ys, xs), 1)
    local_id = np.cumsum(flags, axis=1)[:, :w]
    row_offset = np.concatenate(([0], np.cumsum(lens + 1)[:-1]))
    gid = local_id + row_offset[:, None]

    # One draw per interval (including empty and final), same order as the original.
    n_intervals = int((lens + 1).sum())
    skip = np.fromiter(
        (random.random() * 100 < randomness for _ in range(n_intervals)),
        dtype=np.bool_,
        count=n_intervals,
    )

    selected = pix[m]  # (n, 4), row-major
    selected_gid = gid[m]
    keys = sorting_function(selected)
    keys[skip[selected_gid]] = 0  # constant key + stable sort keeps original order

    order = np.lexsort((keys, selected_gid))  # primary: interval, secondary: key
    out = pix.copy()
    out[m] = selected[order]
    return Image.fromarray(out, "RGBA")


def sort_interval(
    interval: list[Pixel],
    sorting_function: typing.Callable[[Pixel], float],
) -> list[Pixel]:
    return [] if not interval else sorted(interval, key=sorting_function)
