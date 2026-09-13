"""Unit tests for the tier-3 perceptual-hash visual signal (ROADMAP.md §2, §5.3).

Exercises the from-scratch difference-hash engine directly: determinism (identical
bytes hash identically), that a re-encode of the same picture stays identical, that
visually different pictures diverge, the similarity metric's `[0,1]` bounds and its
endpoints (a hash vs itself = 1.0, vs its complement = 0.0), and that undecodable
bytes raise rather than silently hash to something. Real PNG bytes are synthesized
with Pillow so nothing here depends on a browser.
"""

from __future__ import annotations

import io

import numpy as np
import pytest
from PIL import Image

from spoor.core.visual import (
    InvalidImageError,
    perceptual_hash,
    visual_similarity,
)

_HASH_BITS = 64
_ALL_ONES = (1 << _HASH_BITS) - 1


def _png(pixels: np.ndarray) -> bytes:
    """Encode a grayscale numpy array (H x W, uint8) as PNG bytes."""
    buffer = io.BytesIO()
    Image.fromarray(pixels.astype(np.uint8), mode="L").save(buffer, format="PNG")
    return buffer.getvalue()


def _horizontal_gradient(width: int = 64, height: int = 64) -> np.ndarray:
    """A left-to-right brightness ramp — real gradients, so dHash bits vary."""
    row = np.linspace(0, 255, width)
    return np.tile(row, (height, 1))


def test_hash_is_deterministic_for_identical_bytes() -> None:
    png = _png(_horizontal_gradient())
    assert perceptual_hash(png) == perceptual_hash(png)


def test_hash_fits_in_64_bits() -> None:
    value = perceptual_hash(_png(_horizontal_gradient()))
    assert 0 <= value <= _ALL_ONES


def test_a_re_encode_of_the_same_picture_hashes_identically() -> None:
    pixels = _horizontal_gradient()
    # Same picture, encoded twice independently: dHash is about content, not bytes.
    assert perceptual_hash(_png(pixels)) == perceptual_hash(_png(pixels.copy()))


def test_a_gradient_and_its_mirror_are_less_than_fully_similar() -> None:
    grad = perceptual_hash(_png(_horizontal_gradient()))
    mirrored = perceptual_hash(_png(np.fliplr(_horizontal_gradient())))
    # A left-right flip inverts every "brighter than my right neighbour" bit, so
    # the mirror is the maximally-different picture for a pure horizontal ramp.
    assert visual_similarity(grad, mirrored) < 0.5


def test_a_flat_image_hashes_to_zero() -> None:
    # Documented dHash caveat: a uniform crop has no gradients, so every
    # adjacent-pixel comparison is False and the hash is 0.
    flat = np.full((64, 64), 128)
    assert perceptual_hash(_png(flat)) == 0


def test_similarity_of_a_hash_with_itself_is_one() -> None:
    value = perceptual_hash(_png(_horizontal_gradient()))
    assert visual_similarity(value, value) == 1.0


def test_similarity_of_a_hash_with_its_complement_is_zero() -> None:
    value = perceptual_hash(_png(_horizontal_gradient()))
    assert visual_similarity(value, value ^ _ALL_ONES) == 0.0


def test_similarity_is_commutative_and_bounded() -> None:
    a = perceptual_hash(_png(_horizontal_gradient()))
    b = perceptual_hash(_png(np.flipud(_horizontal_gradient())))
    assert visual_similarity(a, b) == visual_similarity(b, a)
    assert 0.0 <= visual_similarity(a, b) <= 1.0


def test_a_stray_high_bit_cannot_push_distance_past_the_bit_count() -> None:
    # The metric masks to 64 bits, so a value with bits above bit 63 still yields
    # a similarity in [0,1] rather than a negative number.
    assert visual_similarity(0, (1 << 200) | _ALL_ONES) == 0.0


def test_undecodable_bytes_raise_invalid_image_error() -> None:
    with pytest.raises(InvalidImageError):
        perceptual_hash(b"not a png at all")
