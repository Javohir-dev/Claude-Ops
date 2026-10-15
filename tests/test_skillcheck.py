import unittest

import skillcheck
from tests import ROOT


class SkillCheckTest(unittest.TestCase):
    def test_example_follows_the_contract(self):
        text = (ROOT / "examples" / "fix-skill" / "SKILL.md").read_text()
        self.assertEqual([label for label, test in skillcheck.CHECKS if not test(text)], [])

    def test_missing_words_are_reported(self):
        text = "---\nname: x\ndescription: y\n---\nfix things"
        missing = [label for label, test in skillcheck.CHECKS[: skillcheck.REQUIRED] if not test(text)]
        self.assertEqual(len(missing), skillcheck.REQUIRED - 1)


if __name__ == "__main__":
    unittest.main()
