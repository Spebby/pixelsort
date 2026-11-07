import random
import typing


Pixel = tuple[int, int, int, int]
Coordinate = tuple[int, int]


class PixelAccess(typing.Protocol):
    def __getitem__(self, xy: Coordinate) -> Pixel: ...

    def __setitem__(self, xy: Coordinate, value: Pixel) -> None: ...


class MaskAccess(typing.Protocol):
    def __getitem__(self, xy: Coordinate) -> int: ...


def sort_image(
    size: tuple[int, int],
    image_data: PixelAccess,
    mask_data: MaskAccess,
    intervals: list[list[int]],
    randomness: float,
    sorting_function: typing.Callable[[Pixel], float],
) -> list[list[Pixel]]:
    sorted_pixels = []

    for y in range(size[1]):
        row = []
        x_min = 0
        for x_max in intervals[y] + [size[0]]:
            interval = []
            for x in range(x_min, x_max):
                if mask_data[x, y]:
                    interval.append(image_data[x, y])
            if random.random() * 100 < randomness:
                row += interval
            else:
                row += sort_interval(interval, sorting_function)
            x_min = x_max
        sorted_pixels.append(row)
    return sorted_pixels


def sort_interval(
    interval: list[Pixel],
    sorting_function: typing.Callable[[Pixel], float],
) -> list[Pixel]:
    return [] if not interval else sorted(interval, key=sorting_function)
