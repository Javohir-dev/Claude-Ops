import os
import tempfile
import unittest
from pathlib import Path

import skillcleanup


class SkillCleanupTest(unittest.TestCase):
    def test_only_dangling_links_into_the_repo(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            repo_skills = root / "repo" / "skills"
            (repo_skills / "kept").mkdir(parents=True)
            other = root / "elsewhere"
            other.mkdir()
            skills = root / "home" / ".claude" / "skills"
            skills.mkdir(parents=True)
            os.symlink(repo_skills / "mr-fix", skills / "mr-fix")
            os.symlink(repo_skills / "kept", skills / "kept")
            os.symlink(other / "gone", skills / "foreign")
            (skills / "own").mkdir()
            self.assertEqual([p.name for p in skillcleanup.stale_links(skills, repo_skills)], ["mr-fix"])


if __name__ == "__main__":
    unittest.main()
