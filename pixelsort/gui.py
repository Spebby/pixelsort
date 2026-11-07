"""GTK4 / libadwaita front-end for pixelsort.

Run from the repository root with:  python -m pixelsort.gui [image]

Requirements beyond pixelsort's own: PyGObject, GTK >= 4.10 (Gtk.FileDialog) and
libadwaita >= 1.4 (Adw.OverlaySplitView, Adw.SpinRow, Adw.SwitchRow).
Nothing else in the library imports this module, so the CLI works without them.
"""

import os
import sys
import threading
from collections.abc import Callable
from dataclasses import dataclass, field, replace

try:
    import gi

    gi.require_version("Gtk", "4.0")
    gi.require_version("Adw", "1")
    from gi.repository import Adw, Gdk, Gio, GLib, Gtk  # noqa: E402
except (ImportError, ValueError) as exc:
    sys.exit(f"pixelsort GUI needs PyGObject, GTK 4 and libadwaita: {exc}")
from PIL import Image, ImageOps  # noqa: E402

from pixelsort import pixelsort  # noqa: E402

INTERVAL_FUNCTIONS = ["threshold", "edges", "random", "waves", "file", "file-edges", "none"]
SORTING_FUNCTIONS = ["lightness", "hue", "saturation", "intensity", "minimum"]

# Which interval-specific controls apply to each interval function.
VISIBLE_CONTROLS = {
    "threshold": {"lower", "upper"},
    "edges": {"lower"},
    "random": {"length"},
    "waves": {"length"},
    "file": {"interval"},
    "file-edges": {"interval", "lower"},
    "none": set(),
}

DEBOUNCE_MS = 250
MIN_GTK = (4, 10)
MIN_ADW = (1, 4)


# --------------------------------------------------------------------------
# State and processing
# --------------------------------------------------------------------------


@dataclass
class PixelSortSettings:
    randomness: float = 0
    char_length: float = 50
    sorting_function: str = "lightness"
    interval_function: str = "threshold"
    lower_threshold: float = 0.25
    upper_threshold: float = 0.8
    angle: float = 0


@dataclass
class PixelSortDocument:
    source: Image.Image | None = None
    mask: Image.Image | None = None
    interval: Image.Image | None = None
    result: Image.Image | None = None
    settings: PixelSortSettings = field(default_factory=PixelSortSettings)


Job = tuple[Image.Image, PixelSortSettings, Image.Image | None, Image.Image | None]


def process_image(
    source: Image.Image,
    settings: PixelSortSettings,
    mask: Image.Image | None = None,
    interval: Image.Image | None = None,
) -> Image.Image:
    """The only place that knows pixelsort's signature."""
    return pixelsort(
        image=source,
        mask_image=mask,
        interval_image=interval,
        randomness=settings.randomness,
        char_length=settings.char_length,
        sorting_function=settings.sorting_function,
        interval_function=settings.interval_function,
        lower_threshold=settings.lower_threshold,
        upper_threshold=settings.upper_threshold,
        angle=settings.angle,
    )


class JobRunner:
    """Runs one pixelsort job at a time on a worker thread.

    Only the most recent request is kept while a job is running; results of
    superseded requests are discarded (the library cannot cancel them).
    """

    def __init__(
        self,
        on_result: Callable[[Image.Image | None, Exception | None], None],
        on_busy: Callable[[bool], None],
    ) -> None:
        self._on_result = on_result  # main thread, latest job only
        self._on_busy = on_busy  # main thread
        self._latest = 0
        self._running = False
        self._pending: tuple[int, Job] | None = None

    @property
    def busy(self) -> bool:
        return self._running or self._pending is not None

    def invalidate(self) -> None:
        """Discard any queued job and the result of any running one."""
        self._latest += 1
        self._pending = None

    def submit(self, job: Job) -> None:
        self._latest += 1
        self._pending = (self._latest, job)
        self._start_next()
        self._on_busy(self.busy)

    def _start_next(self) -> None:
        if self._running or self._pending is None:
            return
        job_id, job = self._pending
        self._pending = None
        self._running = True
        threading.Thread(target=self._work, args=(job_id, job), daemon=True).start()

    def _work(self, job_id: int, job: Job) -> None:
        try:
            result, error = process_image(*job), None
        except Exception as exc:  # noqa: BLE001 - reported to the user
            result, error = None, exc
        GLib.idle_add(self._finish, job_id, result, error)

    def _finish(self, job_id: int, result: Image.Image | None, error: Exception | None) -> bool:
        self._running = False
        if job_id == self._latest:
            self._on_result(result, error)
        self._start_next()
        self._on_busy(self.busy)
        return GLib.SOURCE_REMOVE


# --------------------------------------------------------------------------
# Helpers
# --------------------------------------------------------------------------


def load_image(path: str, mode: str | None = None) -> Image.Image:
    with Image.open(path) as im:
        im = ImageOps.exif_transpose(im)
        im.load()
        return im.convert(mode) if mode else im.copy()


def to_texture(img: Image.Image) -> Gdk.MemoryTexture:
    img = img.convert("RGBA")
    w, h = img.size
    return Gdk.MemoryTexture.new(
        w, h, Gdk.MemoryFormat.R8G8B8A8, GLib.Bytes.new(img.tobytes()), w * 4
    )


def image_dialog(title: str) -> Gtk.FileDialog:
    dialog = Gtk.FileDialog(title=title)
    images = Gtk.FileFilter()
    images.set_name("Images")
    images.add_pixbuf_formats()
    everything = Gtk.FileFilter()
    everything.set_name("All files")
    everything.add_pattern("*")
    filters = Gio.ListStore.new(Gtk.FileFilter)
    filters.append(images)
    filters.append(everything)
    dialog.set_filters(filters)
    dialog.set_default_filter(images)
    return dialog


# --------------------------------------------------------------------------
# Window
# --------------------------------------------------------------------------


class MainWindow(Adw.ApplicationWindow):
    def __init__(self, app):
        super().__init__(application=app, title="PixelSort", default_width=1200, default_height=780)
        self.doc = PixelSortDocument()
        self._source_name = None
        self._source_texture = None
        self._result_texture = None
        self._stale = True
        self._debounce_id = 0
        self._aux_rows = {}
        self.runner = JobRunner(self._on_result, self._on_busy)
        self._build_ui()
        self._update_visibility()
        self._update_actions()

    # ---- UI construction -------------------------------------------------

    def _build_ui(self):
        header = Adw.HeaderBar()

        open_btn = Gtk.Button(label="Open…")
        open_btn.connect("clicked", lambda *_: self._choose("Open image", self.load_source))
        header.pack_start(open_btn)

        self.spinner = Gtk.Spinner()
        header.pack_start(self.spinner)

        self.save_btn = Gtk.Button(label="Save…")
        self.save_btn.add_css_class("suggested-action")
        self.save_btn.connect("clicked", self._on_save)
        header.pack_end(self.save_btn)

        self.compare_btn = Gtk.ToggleButton(label="Original")
        self.compare_btn.set_tooltip_text("Show the unprocessed image")
        self.compare_btn.connect("toggled", lambda *_: self._show())
        header.pack_end(self.compare_btn)

        # Preview area
        self.picture = Gtk.Picture(content_fit=Gtk.ContentFit.CONTAIN, can_shrink=True)
        self.picture.set_hexpand(True)
        self.picture.set_vexpand(True)
        empty = Adw.StatusPage(
            title="No image",
            description="Open an image to start sorting pixels.",
            icon_name="image-x-generic-symbolic",
        )
        self.stack = Gtk.Stack()
        self.stack.add_named(empty, "empty")
        self.stack.add_named(self.picture, "preview")
        self.stack.set_vexpand(True)

        self.banner = Adw.Banner.new("")
        content = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        content.append(self.banner)
        content.append(self.stack)
        drop = Gtk.DropTarget.new(Gdk.FileList, Gdk.DragAction.COPY)
        drop.connect("drop", self._on_drop)
        content.add_controller(drop)

        # Sidebar
        split = Adw.OverlaySplitView(
            sidebar=self._build_sidebar(),
            content=content,
            min_sidebar_width=320,
            max_sidebar_width=420,
        )

        toolbar = Adw.ToolbarView()
        toolbar.add_top_bar(header)
        toolbar.set_content(split)
        self.toasts = Adw.ToastOverlay()
        self.toasts.set_child(toolbar)
        self.set_content(self.toasts)

    def _build_sidebar(self):
        s = self.doc.settings
        page = Adw.PreferencesPage()

        # Images
        images = Adw.PreferencesGroup(title="Images")
        images.add(self._aux_row("mask", "Mask"))
        images.add(self._aux_row("interval", "Interval image"))
        page.add(images)

        # Sorting
        sorting = Adw.PreferencesGroup(title="Sorting")
        self.row_interval_fn = self._combo("Interval function", INTERVAL_FUNCTIONS, s.interval_function, "interval_function")
        self.row_sorting_fn = self._combo("Sorting function", SORTING_FUNCTIONS, s.sorting_function, "sorting_function")
        self.row_angle = self._spin("Angle", s.angle, -360, 360, 1, 1, "angle", "Degrees; 90 sorts vertically")
        self.row_randomness = self._spin("Randomness", s.randomness, 0, 100, 1, 1, "randomness", "Percent of intervals left unsorted")
        for row in (self.row_interval_fn, self.row_sorting_fn, self.row_angle, self.row_randomness):
            sorting.add(row)
        page.add(sorting)

        # Interval-specific
        interval = Adw.PreferencesGroup(title="Interval settings")
        self.row_lower = self._spin("Lower threshold", s.lower_threshold, 0, 1, 0.01, 2, "lower_threshold")
        self.row_upper = self._spin("Upper threshold", s.upper_threshold, 0, 1, 0.01, 2, "upper_threshold")
        self.row_length = self._spin("Characteristic length", s.char_length, 1, 10000, 1, 0, "char_length", "Pixels")
        for row in (self.row_lower, self.row_upper, self.row_length):
            interval.add(row)
        page.add(interval)

        # Preview
        preview = Adw.PreferencesGroup(title="Preview")
        self.live = Adw.SwitchRow(title="Live preview", active=True)
        self.live.connect("notify::active", self._on_live_toggled)
        apply_row = Adw.ActionRow(title="Update preview", activatable=True)
        apply_row.add_suffix(Gtk.Image.new_from_icon_name("view-refresh-symbolic"))
        apply_row.connect("activated", lambda *_: self._changed(immediate=True, force=True))
        preview.add(self.live)
        preview.add(apply_row)
        page.add(preview)
        return page

    def _combo(self, title, options, current, key):
        row = Adw.ComboRow(title=title, model=Gtk.StringList.new(options))
        row.set_selected(options.index(current))

        def on_selected(r, _pspec):
            setattr(self.doc.settings, key, options[r.get_selected()])
            if key == "interval_function":
                self._update_visibility()
            self._changed()

        row.connect("notify::selected", on_selected)
        return row

    def _spin(self, title, value, lo, hi, step, digits, key, subtitle=""):
        adj = Gtk.Adjustment(value=value, lower=lo, upper=hi, step_increment=step, page_increment=step * 10)
        row = Adw.SpinRow(title=title, subtitle=subtitle, adjustment=adj, digits=digits)

        def on_value(r, _pspec):
            setattr(self.doc.settings, key, r.get_value())
            self._changed()

        row.connect("notify::value", on_value)
        return row

    def _aux_row(self, kind, title):
        row = Adw.ActionRow(title=title, subtitle="None")
        choose = Gtk.Button(icon_name="document-open-symbolic", valign=Gtk.Align.CENTER, tooltip_text="Choose…")
        clear = Gtk.Button(icon_name="edit-clear-symbolic", valign=Gtk.Align.CENTER, tooltip_text="Clear", sensitive=False)
        for b in (choose, clear):
            b.add_css_class("flat")
        choose.connect("clicked", lambda *_: self._choose(title, lambda p: self._set_aux(kind, p)))
        clear.connect("clicked", lambda *_: self._clear_aux(kind))
        row.add_suffix(choose)
        row.add_suffix(clear)
        self._aux_rows[kind] = (row, clear)
        return row

    # ---- Visibility / actions --------------------------------------------

    def _update_visibility(self):
        show = VISIBLE_CONTROLS[self.doc.settings.interval_function]
        self.row_lower.set_visible("lower" in show)
        self.row_upper.set_visible("upper" in show)
        self.row_length.set_visible("length" in show)
        self._aux_rows["interval"][0].set_visible("interval" in show)

    def _update_actions(self):
        has_result = self.doc.result is not None
        self.save_btn.set_sensitive(has_result and not self._stale and not self.runner.busy)
        self.compare_btn.set_sensitive(has_result)

    def _on_busy(self, busy):
        self.spinner.set_spinning(busy)
        self._update_actions()

    def _on_live_toggled(self, *_) -> None:
        if self.live.get_active():
            self._changed(immediate=True)
        elif self._debounce_id:  # drop a scheduled preview; manual update still works
            GLib.source_remove(self._debounce_id)
            self._debounce_id = 0

    # ---- File handling ---------------------------------------------------

    def _dialog_failed(self, err: GLib.Error) -> None:
        """Cancelling a dialog is silent; anything else is reported."""
        quark = Gtk.DialogError.quark()
        if err.matches(quark, Gtk.DialogError.DISMISSED) or err.matches(quark, Gtk.DialogError.CANCELLED):
            return
        self._toast(f"File dialog failed: {err.message}")

    def _on_drop(self, _target, value, _x, _y) -> bool:
        files = value.get_files()
        path = files[0].get_path() if files else None
        if not path:
            return False
        self.load_source(path)
        return True

    def _choose(self, title, callback):
        dialog = image_dialog(title)

        def done(dlg, res):
            try:
                gfile = dlg.open_finish(res)
            except GLib.Error as err:
                self._dialog_failed(err)
                return
            path = gfile.get_path()
            if path:
                callback(path)

        dialog.open(self, None, done)

    def load_source(self, path):
        try:
            img = load_image(path, "RGBA")
        except Exception as exc:  # noqa: BLE001
            self._toast(f"Couldn't open image: {exc}")
            return
        doc = self.doc
        had_source = doc.source is not None
        doc.source, doc.result = img, None
        self._source_name = os.path.basename(path)
        self._source_texture = to_texture(img)
        self._result_texture = None
        self.set_title(f"PixelSort — {self._source_name}")

        for kind in ("mask", "interval"):
            aux = getattr(doc, kind)
            # Replacing an existing source drops its mask/interval image; a mask
            # chosen before any source is kept unless its size is wrong.
            if aux is not None and (had_source or aux.size != img.size):
                self._clear_aux(kind, notify=False)
                self._toast(f"Cleared the {kind} image")

        self.compare_btn.set_active(False)
        self.stack.set_visible_child_name("preview")
        self._show()
        self._changed(immediate=True)

    def _set_aux(self, kind, path):
        try:
            img = load_image(path)
        except Exception as exc:  # noqa: BLE001
            self._toast(f"Couldn't open image: {exc}")
            return
        src = self.doc.source
        if src is not None and img.size != src.size:
            self._toast(
                f"The {kind} image must be {src.width}×{src.height}px to match the source "
                f"(got {img.width}×{img.height})"
            )
            return
        setattr(self.doc, kind, img)
        row, clear = self._aux_rows[kind]
        row.set_subtitle(f"{os.path.basename(path)} ({img.width}×{img.height})")
        clear.set_sensitive(True)
        self._changed(immediate=True)

    def _clear_aux(self, kind, notify=True):
        setattr(self.doc, kind, None)
        row, clear = self._aux_rows[kind]
        row.set_subtitle("None")
        clear.set_sensitive(False)
        if notify:
            self._changed(immediate=True)

    def _on_save(self, *_) -> None:
        if self.doc.result is None or self._stale or self.runner.busy:
            return
        img = self.doc.result.copy()  # the preview that was current when Save was clicked
        stem = os.path.splitext(self._source_name or "image")[0]
        dialog = Gtk.FileDialog(title="Save image")
        dialog.set_initial_name(f"{stem}-sorted.png")

        def done(dlg, res):
            try:
                gfile = dlg.save_finish(res)
            except GLib.Error as err:
                self._dialog_failed(err)
                return
            path = gfile.get_path()
            if not path:
                return
            if not os.path.splitext(path)[1]:
                path += ".png"
            threading.Thread(target=self._save_worker, args=(img, path), daemon=True).start()

        dialog.save(self, None, done)

    def _save_worker(self, img: Image.Image, path: str) -> None:
        try:
            try:
                img.save(path)
            except (OSError, ValueError):
                img.convert("RGB").save(path)  # formats without alpha, e.g. JPEG
        except Exception as exc:  # noqa: BLE001
            GLib.idle_add(self._toast, f"Couldn't save image: {exc}")
            return
        GLib.idle_add(self._toast, f"Saved {os.path.basename(path)}")

    # ---- Processing ------------------------------------------------------

    def _changed(self, immediate=False, force=False):
        """Settings or inputs changed: invalidate in-flight work and schedule a preview."""
        self._stale = True
        self.runner.invalidate()
        if self._debounce_id:
            GLib.source_remove(self._debounce_id)
            self._debounce_id = 0
        self._update_actions()
        if not (force or self.live.get_active()):
            return
        if immediate:
            self._submit()
        else:
            self._debounce_id = GLib.timeout_add(DEBOUNCE_MS, self._debounce_fire)

    def _debounce_fire(self):
        self._debounce_id = 0
        self._submit()
        return GLib.SOURCE_REMOVE

    def _submit(self):
        doc = self.doc
        if doc.source is None:
            return
        if doc.settings.interval_function in ("file", "file-edges") and doc.interval is None:
            self._set_banner("Choose an interval image to use this interval function.")
            return
        self.runner.submit((doc.source, replace(doc.settings), doc.mask, doc.interval))

    def _on_result(self, result, error):
        if error is not None:
            note = " The preview shown is the last successful result." if self.doc.result is not None else ""
            self._set_banner(f"Processing failed: {error}.{note}")
            return
        self._set_banner(None)
        self.doc.result = result
        self._result_texture = to_texture(result)
        self._stale = False
        self._show()
        self._update_actions()

    # ---- Display ---------------------------------------------------------

    def _show(self):
        use_original = self.compare_btn.get_active() or self._result_texture is None
        self.picture.set_paintable(self._source_texture if use_original else self._result_texture)

    def _set_banner(self, message):
        self.banner.set_title(message or "")
        self.banner.set_revealed(bool(message))

    def _toast(self, message):
        self.toasts.add_toast(Adw.Toast.new(message))


# --------------------------------------------------------------------------
# Application
# --------------------------------------------------------------------------


class PixelSortApp(Adw.Application):
    def __init__(self):
        super().__init__(application_id="io.github.spebby.pixelsort", flags=Gio.ApplicationFlags.HANDLES_OPEN)

    def _window(self):
        return self.props.active_window or MainWindow(self)

    def do_activate(self):
        self._window().present()

    def do_open(self, files, n_files, hint):
        win = self._window()
        if n_files:
            path = files[0].get_path()
            if path:
                win.load_source(path)
        win.present()


def main() -> int:
    if (Gtk.get_major_version(), Gtk.get_minor_version()) < MIN_GTK or (
        Adw.get_major_version(),
        Adw.get_minor_version(),
    ) < MIN_ADW:
        sys.exit("pixelsort GUI needs GTK >= %d.%d and libadwaita >= %d.%d" % (*MIN_GTK, *MIN_ADW))
    return PixelSortApp().run(sys.argv)


if __name__ == "__main__":
    sys.exit(main())
