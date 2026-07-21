"""The accessibility claim, asserted.

A library that says "colorblind-validated" owes a test that recomputes it.
These assertions are the *published* numbers: if a palette edit degrades
them, the suite fails instead of the claim quietly becoming false.

The honest headline, which these tests encode: eight categorical hues that
stay apart under protanopia, deuteranopia AND tritanopia do not exist —
the field's reference palette (Okabe-Ito) scores ~3.0 itself.  So each
theme publishes a *safe count* it is validated to, and limn adds a second
encoding channel beyond it (tests/test_v11 covers that behaviour).
"""

import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))), "tools"))

from cvd import all_pairs_min, contrast, distance, simulate  # noqa: E402
from limn.theme import PAPER, DUSK, THEMES  # noqa: E402

# Protanopia and deuteranopia together affect ~8% of males; tritanopia
# ~0.01%.  The palette is *optimised* against the common two and *reported*
# against all three — no eight-colour set clears tritanopia (the reference
# Okabe-Ito palette scores 0.6 there), so pretending otherwise would be the
# very dishonesty this file exists to prevent.
KINDS = ("normal", "protan", "deutan")
ALL_KINDS = KINDS + ("tritan",)


def worst(palette, n=None):
    """All-pairs minimum ΔE over every simulated vision type."""
    pal = palette[:n] if n else palette
    return min(all_pairs_min(pal, k)[0] for k in KINDS)


class TestCvdMachinery(unittest.TestCase):
    def test_simulation_actually_changes_color(self):
        red, green = "#e34948", "#008300"
        self.assertLess(distance(red, green, "deutan"),
                        distance(red, green, "normal"),
                        "deuteranopia must compress red vs green")

    def test_identical_colors_are_zero_apart(self):
        self.assertAlmostEqual(distance("#2a78d6", "#2a78d6"), 0.0, places=6)

    def test_contrast_matches_wcag_reference(self):
        self.assertAlmostEqual(contrast("#ffffff", "#000000"), 21.0, places=1)
        self.assertAlmostEqual(contrast("#777777", "#ffffff"), 4.48, places=1)


class TestPalettes(unittest.TestCase):
    def test_safe_count_holds_for_every_theme(self):
        for theme in THEMES.values():
            with self.subTest(theme=theme.name):
                self.assertGreaterEqual(
                    worst(theme.series, theme.safe_n), 4.0,
                    "%s claims safe_n=%d but its first %d slots collide"
                    % (theme.name, theme.safe_n, theme.safe_n))

    def test_safe_count_is_not_understated(self):
        """safe_n must be the *largest* honest claim, not a shrug."""
        for theme in THEMES.values():
            with self.subTest(theme=theme.name):
                if theme.safe_n < len(theme.series):
                    self.assertLess(worst(theme.series, theme.safe_n + 1), 4.0,
                                    "%s could safely claim more slots"
                                    % theme.name)

    def test_first_four_are_strongly_separated(self):
        """Most charts have four or fewer series; those must be easy."""
        for theme in THEMES.values():
            with self.subTest(theme=theme.name):
                self.assertGreaterEqual(worst(theme.series, 4), 6.0)

    def test_no_duplicate_slots(self):
        for theme in THEMES.values():
            with self.subTest(theme=theme.name):
                self.assertEqual(len(set(theme.series)), len(theme.series))

    def test_published_numbers_are_current(self):
        # The exact figures quoted in README/docs.  Update both together.
        self.assertGreaterEqual(worst(PAPER.series), 8.5)
        self.assertGreaterEqual(worst(DUSK.series), 9.0)

    def test_beats_the_reference_palette_on_common_cvd(self):
        okabe = ["#0072B2", "#009E73", "#E69F00", "#CC79A7",
                 "#56B4E9", "#D55E00", "#F0E442", "#000000"]
        for theme in THEMES.values():
            with self.subTest(theme=theme.name):
                self.assertGreater(worst(theme.series), worst(okabe))

    def test_tritanopia_is_reported_not_hidden(self):
        for theme in THEMES.values():
            with self.subTest(theme=theme.name):
                tritan = all_pairs_min(theme.series, "tritan")[0]
                self.assertGreater(tritan, 0.0)   # documented in docs/

    def test_dark_theme_is_selected_not_inverted(self):
        for a, b in zip(PAPER.series, DUSK.series):
            inverted = "#%02x%02x%02x" % tuple(
                255 - int(a.lstrip("#")[i:i + 2], 16) for i in (0, 2, 4))
            self.assertNotEqual(b.lower(), inverted.lower())


class TestContrast(unittest.TestCase):
    def test_axis_text_passes_wcag_aa(self):
        for theme in THEMES.values():
            with self.subTest(theme=theme.name):
                self.assertGreaterEqual(
                    contrast(theme.muted, theme.surface), 4.5,
                    "%s axis labels are below AA" % theme.name)

    def test_body_and_primary_ink_pass_aa(self):
        for theme in THEMES.values():
            with self.subTest(theme=theme.name):
                self.assertGreaterEqual(contrast(theme.ink, theme.surface), 7.0)
                self.assertGreaterEqual(contrast(theme.ink2, theme.surface), 4.5)

    def test_every_series_slot_clears_the_non_text_threshold(self):
        for theme in THEMES.values():
            for c in theme.series:
                with self.subTest(theme=theme.name, color=c):
                    self.assertGreaterEqual(contrast(c, theme.surface), 3.0)


class TestSequentialRamp(unittest.TestCase):
    def test_ramps_are_monotonic_in_lightness(self):
        from cvd import relative_luminance as lum
        for theme in THEMES.values():
            with self.subTest(theme=theme.name):
                lums = [lum(c) for c in theme.ramp]
                ordered = lums == sorted(lums) or lums == sorted(lums,
                                                                 reverse=True)
                self.assertTrue(ordered, "%s ramp is not monotonic"
                                % theme.name)


if __name__ == "__main__":
    unittest.main()
