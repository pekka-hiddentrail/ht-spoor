"""The deduplicating screenshot writer (ROADMAP.md §2e, slice 8g).

Slice 8f streamed each capture to disk as it was taken and kept only a filename
reference, so a long run never buffered its images in memory. This is the next layer:
every capture is routed through a `ScreenshotStore` that writes a file only when the
picture is genuinely new. An identical picture (byte-exact) reuses the existing file; a
near-identical one (the same screen re-rendered with only anti-aliasing/cursor noise)
is matched by a perceptual hash within a tight distance and reuses it too. The caller
gets back an `ImageRef` — a filename, plus an optional crop rectangle for a clip that is
a region of a bigger picture (see `explorer` for the containment resolution). Nothing
here decides *containment*; the store's job is "have I already written this whole
picture?" and, if so, "under what name?".

Determinism (§0): the store writes files in the order the explorer discovers states and
elements (a deterministic breadth-first walk), so the first occurrence of a picture wins
its filename identically on every run. The perceptual threshold is a fixed bit count, so
the same pair of images always resolves the same way.

§2h posture is unchanged: the store only ever handles pixels a caller opted into
capturing, an `ImageRef` carries nothing but a filename and integer coordinates, and a
run that captures no screenshots creates no store and writes nothing.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from spoor.core.visual import InvalidImageError, hamming_distance, perceptual_hash
from spoor.exploration.dedup import content_key

# How many bits two 64-bit perceptual (dHash) hashes may differ by and still count as
# the same picture. dHash keys off gradients, so a re-render's anti-aliasing/cursor
# noise moves only a bit or two; a genuinely different screen moves far more.
# Deliberately tight — a near-duplicate merge shares an embedded image between two
# states' pages, so an over-eager threshold would show the wrong picture. Three bits of
# 64 is conservative.
_NEAR_DUPLICATE_BITS = 3


@dataclass(frozen=True)
class ImageRef:
    """A reference to a picture on disk, optionally a crop of it (§2e slices 8f/8g).

    `src` is the subfolder-relative filename the image was written under (e.g.
    `screenshots/state-0.png`), the same relative path the wiki embeds. `box`, when set,
    is the `(x, y, width, height)` rectangle of `src` this reference points at — a clip
    that is a region of a bigger picture, so it needs no file of its own and the wiki
    crops `src` to it. `box` None means the whole file. It holds no pixels and no
    captured text — just a filename and integers — so it is safe to keep in memory in
    bulk and to place on the shared wiki (§2h).
    """

    src: str
    box: tuple[int, int, int, int] | None = None


class ScreenshotStore:
    """Writes screenshot files, reusing one when the picture is already on disk (8g).

    Constructed once per run over the directory captures are written under (the same
    directory the wiki is rendered into, so references resolve). `add` is the whole
    entry point: hand it a capture's bytes and the name it *would* be written under, and
    it returns the `ImageRef` to embed — writing the file only when the picture is new.
    """

    def __init__(
        self, out_dir: Path, *, near_duplicate_bits: int = _NEAR_DUPLICATE_BITS
    ) -> None:
        self._out_dir = out_dir
        self._near_duplicate_bits = near_duplicate_bits
        # content key -> the whole-file ref already written for those exact bytes.
        self._by_content: dict[str, ImageRef] = {}
        # (perceptual hash, ref) for every distinct non-flat picture written, scanned
        # for a near-duplicate match. A flat image (dHash 0) is excluded: it carries no
        # gradient, so every blank screen would collide — those match byte-exactly only.
        self._perceptual: list[tuple[int, ImageRef]] = []

    def add(self, data: bytes, preferred_name: str) -> ImageRef:
        """The `ImageRef` for `data`, writing `preferred_name` only if it is new (8g).

        Byte-exact duplicates reuse the existing file; a non-flat near-duplicate within
        the perceptual threshold reuses it too. Otherwise the bytes are written under
        `preferred_name` (creating the subfolder on first write) and that new file's ref
        is recorded so a later identical capture reuses it. The returned ref is always a
        whole-file ref (no crop box); containment is the explorer's concern, not the
        store's.
        """
        key = content_key(data)
        exact = self._by_content.get(key)
        if exact is not None:
            return exact

        phash = self._perceptual_hash(data)
        if phash is not None:
            for existing_hash, ref in self._perceptual:
                if hamming_distance(phash, existing_hash) <= self._near_duplicate_bits:
                    # A near-duplicate: reuse the earlier file. Remember these exact
                    # bytes map to it, so a re-encounter short-circuits on the key.
                    self._by_content[key] = ref
                    return ref

        path = self._out_dir / preferred_name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        ref = ImageRef(preferred_name)
        self._by_content[key] = ref
        if phash is not None:
            self._perceptual.append((phash, ref))
        return ref

    @staticmethod
    def _perceptual_hash(data: bytes) -> int | None:
        """The picture's dHash for near-duplicate matching, or None to skip it.

        None when the bytes are not a decodable image (a degenerate/fake capture — then
        only byte-exact matching applies) or when the hash is 0 (a flat, gradient-free
        picture, which every blank screen shares — matched byte-exactly only, never
        perceptually, so distinct blank screens are not collapsed together).
        """
        try:
            phash = perceptual_hash(data)
        except InvalidImageError:
            return None
        return phash or None
