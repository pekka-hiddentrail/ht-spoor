"""Pure image-comparison primitives for screenshot dedup (ROADMAP.md §2e, slice 8g).

Slice 8f streamed every capture to disk as it was taken; a comprehensive run then
showed the redundancy left to remove — the same picture written many times, and small
element clips that are just regions of the page they came from. This module is the pure,
deterministic maths that dedup builds on (`screenshot_store.ScreenshotStore` is the
stateful writer that uses it): a content key for byte-exact matching, a decoder to a
pixel array, and an exact sub-image locator for finding a clip inside a bigger picture.

Everything here is deterministic and generic (§0): identical bytes always key
identically, and `find_subimage` returns the topmost-leftmost exact match (or None),
never a fuzzy guess and never anything site-specific. Perceptual (near-duplicate)
matching is not here — it lives in the store, which reuses `core.visual.perceptual_hash`
— because a near-match is a *policy* (a distance threshold), while these are exact
operations with a single correct answer.
"""

from __future__ import annotations

import hashlib
import io

import numpy as np
from PIL import Image, UnidentifiedImageError

# find_subimage prefilters candidate positions by a single matching pixel, then verifies
# the full block. A flat region (e.g. a white page background) can make almost every
# position a candidate, so the scan is capped: past this many candidate positions it
# gives up and reports "not found". A miss here is safe — the caller simply stores the
# clip as its own file instead of a crop reference — so the cap trades a rare missed
# dedup for a hard bound on work, never a wrong crop. Candidates are visited in
# row-major (topmost-leftmost) order, so the bound keeps the earliest matches.
_MAX_CANDIDATES = 8192


class UndecodableImage(ValueError):
    """The bytes handed to `decode` were not a decodable image.

    Raised, not swallowed, so containment stays honest about its input; the store
    catches it and treats an undecodable capture as "not contained" (store it as its
    own file) rather than failing the run.
    """


def content_key(data: bytes) -> str:
    """A stable content key for a capture's bytes: the SHA-256 hex digest.

    Two byte-identical captures share a key, so the store writes the file once and
    every later identical capture reuses it. Deterministic and collision-safe for this
    use — a hash match means the bytes are the same picture.
    """
    return hashlib.sha256(data).hexdigest()


def decode(data: bytes) -> np.ndarray:
    """Decode encoded image bytes to an `(H, W, 3)` uint8 RGB pixel array.

    RGB (alpha dropped) so two captures compare on visible colour alone, and the array
    is what `find_subimage` scans. Raises `UndecodableImage` when the bytes are not a
    decodable image (a fake/degenerate capture), so the caller can fall back rather than
    crash.
    """
    try:
        with Image.open(io.BytesIO(data)) as image:
            return np.asarray(image.convert("RGB"), dtype=np.uint8)
    except (UnidentifiedImageError, OSError, ValueError) as exc:
        raise UndecodableImage("not a decodable image") from exc


def find_subimage(small: np.ndarray, big: np.ndarray) -> tuple[int, int] | None:
    """The top-left `(x, y)` where `small` appears exactly in `big`, or None.

    An exact pixel match: the clip must be a byte-for-byte contiguous region of the
    bigger picture (which it is when both were rendered from the same page at the same
    device scale). Prefilters candidate positions by the clip's top-left pixel — cheap
    and vectorised — then verifies the full block at each, in row-major order, so the
    first hit is the topmost-leftmost one and the result is deterministic. A `small`
    larger than `big` in either dimension, or an empty array, yields None. The candidate
    scan is bounded (`_MAX_CANDIDATES`); a flat region that blows past the bound reports
    None, and the caller stores the clip as its own file — a missed dedup, not a wrong
    crop.
    """
    if small.ndim != 3 or big.ndim != 3:
        return None
    sh, sw = small.shape[:2]
    bh, bw = big.shape[:2]
    if sh == 0 or sw == 0 or sh > bh or sw > bw:
        return None
    # Positions whose top-left pixel equals the clip's top-left pixel, within the range
    # where a full sh x sw block still fits: a single-pixel prefilter, then verify.
    top_left = small[0, 0]
    region = big[: bh - sh + 1, : bw - sw + 1]
    candidates = np.all(region == top_left, axis=-1)
    ys, xs = np.nonzero(candidates)
    for count, (y, x) in enumerate(zip(ys, xs, strict=True)):
        if count >= _MAX_CANDIDATES:
            return None
        if np.array_equal(big[y : y + sh, x : x + sw], small):
            return int(x), int(y)
    return None
