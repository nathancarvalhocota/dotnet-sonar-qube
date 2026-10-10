"""Opt-in real .NET 8 build; creates only an isolated temporary repository."""

import importlib.util
from pathlib import Path
import subprocess
import tempfile


def main():
    script = Path(__file__).resolve().parents[1] / "scripts" / "analyze.py"
    spec = importlib.util.spec_from_file_location("analyze", script)
    analyze = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(analyze)
    # Preserve the fixture/artifacts on failure so its build log can be inspected.
    repo = Path(tempfile.mkdtemp(prefix="sonar-build-smoke-"))

    def run(*args):
        return subprocess.run(args, cwd=repo, check=True, capture_output=True)

    project = repo / "project with spaces"
    project.mkdir()
    csproj = project / "Demo.csproj"
    csproj.write_text('<Project Sdk="Microsoft.NET.Sdk"><PropertyGroup>'
                      '<TargetFramework>net8.0</TargetFramework>'
                      '</PropertyGroup></Project>', encoding="utf-8")
    (repo / ".gitignore").write_text("**/bin/\n**/obj/\n", encoding="utf-8")
    source = project / "Classe ação.cs"
    old = ('namespace Demo;\npublic class Sample\n{\n'
           '    public void Existing()\n    {\n'
           '        throw new System.Exception("existing");\n    }\n')
    source.write_text(old + "}\n", encoding="utf-8")
    run("git", "init", "-b", "main")
    run("git", "config", "user.name", "Skill smoke test")
    run("git", "config", "user.email", "skill-tests@example.invalid")
    run("git", "add", ".")
    run("git", "commit", "-m", "base")
    run("git", "checkout", "-b", "feature")
    source.write_text(old + ('    public void NewIssue()\n    {\n'
                            '        throw new System.Exception("new");\n    }\n}\n'), encoding="utf-8")
    run("dotnet", "restore", str(csproj), "--ignore-failed-sources", "-nologo")
    result, code = analyze.run_analysis(repo, target="project with spaces/Demo.csproj")
    print(f"Fixture: {repo}\nArtifacts: {result.get('artifacts')}")
    assert code == 0, result
    assert any(item["rule"] == "S112" and item["line"] == 10 for item in result["findings"]), result
    assert not any(item["line"] == 6 for item in result["findings"]), result
    log = (Path(result["artifacts"]) / "build.log").read_text(encoding="utf-8")
    assert "S112" in log, "Analyzer did not emit the expected diagnostic"
    assert result["git_status_changed"] is False, result
    print("PASS: real analyzer detects a new S112 and filters the unchanged issue")

    source.write_text("this is not valid C#", encoding="utf-8")
    result, code = analyze.run_analysis(repo, target="project with spaces/Demo.csproj")
    assert code == 1 and result["status"] == "build_failed" and result["errors"], result
    print("PASS: compilation errors return build_failed instead of a clean analysis")


if __name__ == "__main__":
    main()
