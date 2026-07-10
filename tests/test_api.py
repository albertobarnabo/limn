import contextlib
import io
import os
import tempfile
import unittest

import limn
from limn.__main__ import main as cli_main


class TestPlotPicksTheForm(unittest.TestCase):
    def test_temporal_gives_line(self):
        fig = limn.plot({"day": ["2026-01-01", "2026-01-02"],
                         "v": [1, 2]})
        self.assertEqual(fig.kind, "line")

    def test_category_plus_numeric_gives_bar(self):
        fig = limn.plot({"team": ["a", "b"], "points": [1, 2]})
        self.assertEqual(fig.kind, "bar")

    def test_two_numerics_give_scatter(self):
        fig = limn.plot({"height": [1, 2, 3], "weight": [4, 5, 6]})
        self.assertEqual(fig.kind, "scatter")

    def test_noisy_single_numeric_gives_hist(self):
        noisy = [((i * 37) % 23) for i in range(40)]
        self.assertEqual(limn.plot(noisy).kind, "hist")

    def test_trending_single_numeric_gives_line(self):
        self.assertEqual(limn.plot([1, 2, 3, 4, 5]).kind, "line")

    def test_explicit_x_kind_drives_choice(self):
        data = {"cat": ["a", "b"], "v": [1, 2], "w": [3, 4]}
        self.assertEqual(limn.plot(data, x="cat").kind, "bar")
        self.assertEqual(limn.plot(data, x="v", y="w").kind, "scatter")


class TestCli(unittest.TestCase):
    def run_cli(self, *argv):
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = cli_main(list(argv))
        return code, err.getvalue()

    def test_csv_to_svg(self):
        with tempfile.TemporaryDirectory() as tmp:
            csv_path = os.path.join(tmp, "data.csv")
            with open(csv_path, "w") as f:
                f.write("month,sales\n2026-01,\"1,200\"\n2026-02,\"1,900\"\n")
            out_path = os.path.join(tmp, "chart.svg")
            code, err = self.run_cli(csv_path, "-o", out_path,
                                     "--title", "Sales")
            self.assertEqual(code, 0)
            self.assertTrue(os.path.exists(out_path))
            self.assertIn("wrote", err)

    def test_bad_input_fails_politely(self):
        code, err = self.run_cli("/nonexistent/file.csv", "-o", "/tmp/x.svg")
        self.assertEqual(code, 1)
        self.assertIn("limn:", err)


if __name__ == "__main__":
    unittest.main()
