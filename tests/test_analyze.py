"""Behavior checks for changed-line selection, filtering and analyzer setup."""

import importlib.util
import io
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
from zipfile import ZipFile

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "analyze.py"
spec = importlib.util.spec_from_file_location("analyze", SCRIPT)
analyze = importlib.util.module_from_spec(spec)
spec.loader.exec_module(analyze)


class GitRangesTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="sonar-ranges-")
        self.addCleanup(self.temp.cleanup)
        self.repo = Path(self.temp.name)
        self.git("init", "-b", "main")
        self.git("config", "user.name", "Skill tests")
        self.git("config", "user.email", "skill-tests@example.invalid")
        self.git("config", "core.autocrlf", "false")
        self.write("Committed.cs", "a\nb\nc\n")
        self.write("Staged.cs", "a\nb\n")
        self.write("Unstaged.cs", "a\nb\n")
        self.write("Tracked ação.cs", "a\nb\n")
        self.write("Deleted.cs", "a\nb\n")
        self.write(".gitignore", "ignored/\n")
        self.git("add", ".")
        self.git("commit", "-m", "base")
        self.git("checkout", "-b", "feature")

    def git(self, *args):
        return subprocess.run(["git", *args], cwd=self.repo, check=True, capture_output=True)

    def write(self, name, content):
        path = self.repo / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")

    def test_committed_staged_unstaged_untracked_and_exclusions(self):
        self.write("Committed.cs", "a\nchanged\nc\n")
        self.git("add", "Committed.cs")
        self.git("commit", "-m", "committed change")
        self.write("Staged.cs", "a\nstaged\n")
        self.git("add", "Staged.cs")
        self.write("Unstaged.cs", "unstaged\nb\n")
        self.write("Tracked ação.cs", "a\nchanged\n")
        self.write("pasta com espaço/É novo.cs", "first\nlast")
        self.write("Empty.cs", "")
        self.write("Root.Designer.cs", "generated")
        self.write("nested/Other.Designer.cs", "generated")
        self.write("ignored/NotIncluded.cs", "ignored")
        self.write("src/Clients/Client.cs", "generated")
        self.write("Component.razor", "@code {}")
        (self.repo / "Deleted.cs").unlink()
        result = analyze.collect_ranges(self.repo, "main", ["src/Clients/**"])
        self.assertEqual(result["files"], {
            "Committed.cs": [[2, 2]], "Staged.cs": [[2, 2]], "Unstaged.cs": [[1, 1]],
            "Tracked ação.cs": [[2, 2]],
            "pasta com espaço/É novo.cs": [[1, 2]], "Component.razor": [[1, 1]],
        })

    def test_deleted_hunks_are_not_changed_lines(self):
        self.write("Unstaged.cs", "a\n")
        self.assertEqual(analyze.collect_ranges(self.repo)["files"], {})

    def test_no_changes_skips_download_and_build(self):
        with patch.object(analyze, "setup_analyzer") as download, patch.object(analyze.subprocess, "run", wraps=subprocess.run) as run:
            result, code = analyze.run_analysis(self.repo)
        self.assertEqual((result["status"], code), ("no_changed_lines", 0))
        download.assert_not_called()
        self.assertTrue(all(call.args[0][0] == "git" for call in run.call_args_list))

    def test_missing_base_fails_instead_of_selecting_another(self):
        with self.assertRaises(RuntimeError):
            analyze.collect_ranges(self.repo, "does-not-exist")

    def test_agent_invocation_returns_json_without_subcommands(self):
        result = subprocess.run([sys.executable, str(SCRIPT), "--repo", str(self.repo)],
                                capture_output=True, text=True, encoding="utf-8")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout)["status"], "no_changed_lines")


class FilterTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="sonar-filter-")
        self.addCleanup(self.temp.cleanup)
        self.repo = Path(self.temp.name).resolve()
        self.ranges = {"repo": str(self.repo), "files": {"pasta com espaço/É.cs": [[2, 4]]}}
        self.file = self.repo / "pasta com espaço" / "É.cs"

    def test_only_changed_sonar_diagnostics_deduplicated(self):
        warning = f"{self.file}(3,1): warning S112: Use a specific exception. [Demo.csproj]"
        log = "\n".join([
            warning, warning,
            f"{self.file}(1,1): warning S112: Unchanged line.",
            f"{self.file}(3,1): warning CS0219: Compiler warning.",
            f"{self.repo.parent / 'Outside.cs'}(3,1): warning S112: External file.",
            f"{self.file}(4,2,4,9): error S1135: TODO promoted to error.",
        ])
        findings = analyze.filter_diagnostics(log, self.ranges)
        self.assertEqual([(item["line"], item["rule"]) for item in findings], [(3, "S112"), (4, "S1135")])
        self.assertEqual(findings[0]["message"], "Use a specific exception.")

    def test_rules_are_not_silenced_unless_requested(self):
        log = f"{self.file}(2,1): warning S1125: Unnecessary Boolean literal."
        self.assertEqual(len(analyze.filter_diagnostics(log, self.ranges)), 1)
        self.assertEqual(analyze.filter_diagnostics(log, self.ranges, ["S1125"]), [])

    def test_relative_file_paths(self):
        log = "pasta com espaço/É.cs(2,1): warning S112: Message"
        self.assertEqual(analyze.filter_diagnostics(log, self.ranges)[0]["file"], "pasta com espaço/É.cs")


class SetupTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="sonar-setup-")
        self.addCleanup(self.temp.cleanup)
        self.skill = Path(self.temp.name)
        (self.skill / "analyzer").mkdir()
        (self.skill / "analyzer" / "VERSION").write_text("10.34.0.3385\n", encoding="utf-8")

    def test_download_then_reuse_pinned_analyzer(self):
        archive = io.BytesIO()
        with ZipFile(archive, "w") as package:
            package.writestr("analyzers/SonarAnalyzer.CSharp.dll", b"test analyzer")
            package.writestr("../../outside.dll", b"must not be extracted")
        with patch.object(analyze, "urlopen", return_value=io.BytesIO(archive.getvalue())) as download:
            output = analyze.setup_analyzer(self.skill)
            self.assertEqual((output / "SonarAnalyzer.CSharp.dll").read_bytes(), b"test analyzer")
            self.assertEqual(analyze.setup_analyzer(self.skill), output)
        download.assert_called_once()
        self.assertFalse((self.skill.parent / "outside.dll").exists())

    def test_rejects_package_without_expected_analyzer(self):
        archive = io.BytesIO()
        with ZipFile(archive, "w") as package:
            package.writestr("readme.md", "not the analyzer")
        with patch.object(analyze, "urlopen", return_value=io.BytesIO(archive.getvalue())):
            with self.assertRaises(RuntimeError):
                analyze.setup_analyzer(self.skill)
        self.assertFalse(list((self.skill / "analyzer").glob("*.nupkg")))


if __name__ == "__main__":
    unittest.main()
