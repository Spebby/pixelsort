import typing
from random import randint, random as random_range

import numpy as np
import numpy.typing as npt
from PIL import Image, ImageFilter

from pixelsort.sorting import lightness


def _starts(cond: npt.NDArray[np.bool_]) -> list[list[int]]:
    """x positions where cond is True and the previous pixel wasn't (or x == 0)."""
    prev = np.zeros_like(cond)
    prev[:, 1:] = cond[:, :-1]
    return [np.flatnonzero(row).tolist() for row in (cond & ~prev)]


def edge(
    image: Image.Image, lower_threshold: float, **_: typing.Any
) -> list[list[int]]:
    """Performs an edge detection, which is used to define intervals. Tweak threshold with threshold."""
    edge_img = image.filter(ImageFilter.FIND_EDGES).convert("RGBA")
    return _starts(lightness(np.asarray(edge_img)) >= lower_threshold * 255)


def threshold(
    image: Image.Image,
    lower_threshold: float,
    upper_threshold: float,
    **_: typing.Any,
) -> list[list[int]]:
    """Intervals defined by lightness thresholds; only pixels with a lightness between the upper and lower thresholds
    are sorted."""
    lum = lightness(np.asarray(image.convert("RGBA")))
    return [
        np.flatnonzero(
            (row < lower_threshold * 255) | (row > upper_threshold * 255)
        ).tolist()
        for row in lum
    ]


def random(
    image: Image.Image, char_length: float, **_: typing.Any
) -> list[list[int]]:
    """Randomly generate intervals. Distribution of widths is linear by default. Interval widths can be scaled using
    char_length."""
    intervals: list[list[int]] = []

    for y in range(image.size[1]):
        intervals.append([])
        x = 0
        while True:
            x += int(char_length * random_range())
            if x > image.size[0]:
                break
            else:
                intervals[y].append(x)
    return intervals


def waves(
    image: Image.Image, char_length: int, **_: typing.Any
) -> list[list[int]]:
    """Intervals are waves of nearly uniform widths. Control width of waves with char_length."""
    intervals: list[list[int]] = []

    for y in range(image.size[1]):
        intervals.append([])
        x = 0
        while True:
            x += char_length + randint(0, 10)
            if x > image.size[0]:
                break
            else:
                intervals[y].append(x)
    return intervals


def file_mask(
    image: Image.Image, interval_image: Image.Image, **_: typing.Any
) -> list[list[int]]:
    """Intervals taken from another specified input image. Must be black and white, and the same size as the input
    image."""
    return _starts(np.asarray(interval_image.convert("L")) == 0)


def file_edges(
    image: Image.Image,
    interval_image: Image.Image,
    lower_threshold: float,
    **_: typing.Any,
) -> list[list[int]]:
    """Intervals defined by performing edge detection on the file specified by -f. Must be the same size as the input
    image."""
    edge_img = interval_image.filter(ImageFilter.FIND_EDGES).convert("RGBA")
    return _starts(lightness(np.asarray(edge_img)) >= lower_threshold * 255)


def none(image: Image.Image, **_: typing.Any) -> list[list[int]]:
    """Sort whole rows, only stopping at image borders."""
    return [[] for _ in range(image.size[1])]


choices: dict[str, typing.Callable[..., list[list[int]]]] = {
    "random": random,
    "threshold": threshold,
    "edges": edge,
    "waves": waves,
    "file": file_mask,
    "file-edges": file_edges,
    "none": none,
}
