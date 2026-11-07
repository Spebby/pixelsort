import typing

import numpy as np
import numpy.typing as npt

PixelArray = npt.NDArray[np.integer[typing.Any]]  # shape (..., 4)
KeyArray = npt.NDArray[np.floating[typing.Any]]
SortingFunction = typing.Callable[[PixelArray], KeyArray]


def _rgb(pixels: PixelArray) -> tuple[KeyArray, KeyArray, KeyArray]:
    return (
        pixels[..., 0].astype(np.float64),
        pixels[..., 1].astype(np.float64),
        pixels[..., 2].astype(np.float64),
    )


def lightness(pixels: PixelArray) -> KeyArray:
    """Sort by the lightness of a pixel according to a HLS representation."""
    r, g, b = _rgb(pixels)
    return (np.minimum(np.minimum(r, g), b) + np.maximum(np.maximum(r, g), b)) / 2.0


def hue(pixels: PixelArray) -> KeyArray:
    """Sort by the hue of a pixel according to a HLS representation."""
    r, g, b = _rgb(pixels)
    maxc = np.maximum(np.maximum(r, g), b)
    minc = np.minimum(np.minimum(r, g), b)
    d = maxc - minc
    zero = d == 0
    d = np.where(zero, 1.0, d)
    rc, gc, bc = (maxc - r) / d, (maxc - g) / d, (maxc - b) / d
    h = np.where(r == maxc, bc - gc, np.where(g == maxc, 2.0 + rc - bc, 4.0 + gc - rc))
    return np.where(zero, 0.0, np.mod(h / 6.0, 1.0))


def saturation(pixels: PixelArray) -> KeyArray:
    """Sort by the saturation of a pixel according to a HLS representation."""
    r, g, b = _rgb(pixels)
    maxc = np.maximum(np.maximum(r, g), b)
    minc = np.minimum(np.minimum(r, g), b)
    sumc, diffc = minc + maxc, maxc - minc
    sdiv = 2.0 - diffc
    zero = (minc == maxc) | (sumc == 0) | (sdiv == 0)
    with np.errstate(divide="ignore", invalid="ignore"):
        s = np.where(sumc / 2.0 <= 0.5, diffc / sumc, diffc / sdiv)
    return np.where(zero, 0.0, s)


def intensity(pixels: PixelArray) -> KeyArray:
    """Sort by the intensity of a pixel, i.e. the sum of all the RGB values."""
    r, g, b = _rgb(pixels)
    return r + g + b


def minimum(pixels: PixelArray) -> KeyArray:
    """Sort on the minimum RGB value of a pixel (either the R, G or B)."""
    r, g, b = _rgb(pixels)
    return np.minimum(np.minimum(r, g), b)


choices: dict[str, SortingFunction] = {
    "lightness": lightness,
    "hue": hue,
    "intensity": intensity,
    "minimum": minimum,
    "saturation": saturation,
}
