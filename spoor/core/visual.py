"""Perceptual-hash visual similarity for tier-3 self-healing (ROADMAP.md §2, §0).

The last signal from the §2 tier table: a "perceptual-hash on a cropped
screenshot", paired with the DOM fingerprint, with **no model call** (§2). It is
the identity a *leaf* element keeps when its markup churns but its pixels do not:
an icon, a logo, an image thumbnail carries almost no inner text and only a class
or two, so a class rename tanks its DOM-only score — yet it re-renders the same,
and its appearance still identifies it.

The hash is a **difference hash (dHash)**, written from scratch here (§2, like the
DOM scorer — no vendored code): decode the PNG, convert to grayscale, resize to a
9x8 thumbnail, and emit one bit per adjacent-pixel comparison across each row
(8 rows x 8 comparisons = 64 bits). dHash keys off *gradients* — "is this pixel
brighter than the one to its right?" — so it is robust to the small
brightness/scale/anti-aliasing differences a re-render introduces while staying
sensitive to a real change in what is drawn. Similarity is `1 - hamming/64`, in
`[0.0, 1.0]`, so it blends into the weighted heal score exactly like every other
signal. A caveat inherent to dHash: a flat, single-colour crop has no gradients,
so every uniform region hashes to 0 and such elements are visually
indistinguishable — the signal earns its keep on elements with internal visual
structure (a drawn logo, a photo), not solid blocks.

Pillow decodes and resizes the pixels; numpy does the bit math; the hash
*algorithm* itself is ours. ROADMAP §7's dependency table names OpenCV for this;
the substitution to the already-present, lighter Pillow + numpy is recorded in the
§2 tier-3 decision note (sufficient for perceptual hashing; OpenCV deferred to
whenever template matching is actually built). §0: the same generic hashing runs
for every target — nothing here is site-specific.
"""

from __future__ import annotations

import io

import numpy as np
from PIL import Image, UnidentifiedImageError

# A 9-wide x 8-tall grayscale thumbnail yields 8 adjacent-pixel comparisons per
# row over 8 rows: a 64-bit hash, the standard dHash size.
_HASH_WIDTH = 9
_HASH_HEIGHT = 8
_HASH_BITS = (_HASH_WIDTH - 1) * _HASH_HEIGHT  # 64
_HASH_MASK = (1 << _HASH_BITS) - 1


class InvalidImageError(ValueError):
    """The bytes handed to `perceptual_hash` were not a decodable image.

    Raised (not swallowed) so the pure engine stays honest about its input; the
    tier-2 capture wrapper catches it and treats a failed screenshot as "no visual
    signal" (None), never failing the extraction it rode along with (§2c).
    """


def perceptual_hash(png_bytes: bytes) -> int:
    """A 64-bit difference hash (dHash) of an encoded screenshot image (§2).

    Decodes the image, reduces it to a 9x8 grayscale thumbnail, and sets one bit
    per "brighter than the pixel to my right" comparison across each row. The
    result is deterministic: identical bytes always hash identically, and a
    re-render of the same content hashes near-identically. Raises
    `InvalidImageError` if the bytes are not a decodable image.
    """
    try:
        with Image.open(io.BytesIO(png_bytes)) as image:
            thumb = image.convert("L").resize(
                (_HASH_WIDTH, _HASH_HEIGHT), Image.Resampling.BILINEAR
            )
    except (UnidentifiedImageError, OSError, ValueError) as exc:
        raise InvalidImageError("not a decodable image") from exc
    pixels = np.asarray(thumb, dtype=np.int16)
    # Each pixel vs its right neighbour, row-major: shape (8, 8) -> 64 bits.
    bits = (pixels[:, 1:] > pixels[:, :-1]).flatten()
    value = 0
    for bit in bits:
        value = (value << 1) | int(bit)
    return value


def visual_similarity(a: int, b: int) -> float:
    """Similarity of two 64-bit dHashes in `[0.0, 1.0]`: `1 - hamming/64`.

    Identical hashes score 1.0; a hash and its bitwise complement score 0.0. The
    XOR is masked to 64 bits so a stray high bit can never push the distance past
    the bit count. Deterministic and commutative.
    """
    distance = ((a ^ b) & _HASH_MASK).bit_count()
    return 1.0 - distance / _HASH_BITS
