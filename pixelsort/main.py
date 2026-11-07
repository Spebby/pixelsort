import logging
import typing

from PIL import Image

from pixelsort.constants import DEFAULTS
from pixelsort.interval import choices as interval_choices
from pixelsort.sorter import sort_image
from pixelsort.sorting import choices as sorting_choices
from pixelsort.util import crop_to


def pixelsort(
    image: Image.Image,
    mask_image: Image.Image | None = None,
    interval_image: Image.Image | None = None,
    randomness: float = DEFAULTS["randomness"],
    char_length: float = DEFAULTS["char_length"],
    sorting_function: typing.Literal[
        "lightness",
        "hue",
        "saturation",
        "intensity",
        "minimum",
    ] = DEFAULTS["sorting_function"],
    interval_function: typing.Literal[
        "random",
        "threshold",
        "edges",
        "waves",
        "file",
        "file-edges",
        "none",
    ] = DEFAULTS["interval_function"],
    lower_threshold: float = DEFAULTS["lower_threshold"],
    upper_threshold: float = DEFAULTS["upper_threshold"],
    angle: float = DEFAULTS["angle"],
) -> Image.Image:
    """(docstring unchanged)"""
    original = image
    image = image.convert("RGBA").rotate(angle, expand=True)

    mask_image = mask_image or Image.new("1", original.size, color=255)
    mask_image = mask_image.convert("1").rotate(angle, expand=True, fillcolor=0)

    interval_image = (
        (interval_image.convert("1").rotate(angle, expand=True))
        if interval_image
        else None
    )
    logging.debug("Determining intervals...")
    intervals = interval_choices[interval_function](
        image,
        lower_threshold=lower_threshold,
        upper_threshold=upper_threshold,
        char_length=char_length,
        interval_image=interval_image,
    )
    logging.debug("Sorting pixels...")
    output_img = sort_image(
        image,
        mask_image,
        intervals,
        randomness,
        sorting_choices[sorting_function],
    )

    if angle != 0:
        output_img = output_img.rotate(-angle, expand=True)
        output_img = crop_to(output_img, original)

    return output_img
