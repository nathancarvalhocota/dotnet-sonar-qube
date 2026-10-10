#!/usr/bin/env python3
"""Local C# Sonar analysis of changed lines. Requires Python 3.10+, Git and .NET."""

import argparse
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
from urllib.request import urlopen
from zipfile import BadZipFile, ZipFile


SKILL_DIR = Path(__file__).resolve().parents[1]
DIAGNOSTIC = re.compile(
    r"^\s*(?P<file>.+?)\((?P<line>\d+),\d+(?:,\d+,\d+)?\): "
    r"(?:warning|error) (?P<rule>S\d+): (?P<message>.*?)(?: \[[^\]]+\])?$"
)


def git(repo, *args):
    result = subprocess.run(
        ["git", "-c", "core.quotePath=false", *args], cwd=repo,
        stdout=subprocess.PIPE, stderr=subprocess.PIPE,
    )
    if result.returncode:
        raise RuntimeError(result.stderr.decode("utf-8", errors="replace").strip())
    return result.stdout.decode("utf-8", errors="replace")


def collect_ranges(repo, base="main", excludes=()):
    repo = Path(git(repo, "rev-parse", "--show-toplevel").strip()).resolve()
    # Resolve a revision before passing it to merge-base, including refs with slashes.
    base_commit = git(repo, "rev-parse", "--verify", "--end-of-options", f"{base}^{{commit}}").strip()
    merge_base = git(repo, "merge-base", base_commit, "HEAD").strip()
    paths = ["*.cs", "*.razor", ":(exclude,glob)**/*.Designer.cs"]
    paths.extend(f":(exclude){pattern}" for pattern in excludes)
    diff = git(repo, "diff", "--no-ext-diff", "--no-textconv", "--no-renames",
               "--no-color", "--src-prefix=a/", "--dst-prefix=b/", "-U0", merge_base, "--", *paths)
    files = {}
    current_file = None
    for line in diff.splitlines():
        if line.startswith("+++ b/"):
            current_file = line[6:].split("\t", 1)[0]
        elif line.startswith('+++ "b/'):
            current_file = json.loads(line[4:])[2:]
        elif line == "+++ /dev/null":
            current_file = None
        elif line.startswith("@@") and current_file:
            hunk = re.match(r"@@ -\d+(?:,\d+)? \+(\d+)(?:,(\d+))? @@", line)
            if hunk:
                start, count = int(hunk[1]), int(hunk[2] or 1)
                if count:
                    files.setdefault(current_file, []).append([start, start + count - 1])
    untracked = git(repo, "ls-files", "--others", "--exclude-standard", "-z", "--", *paths)
    for name in filter(None, untracked.split("\0")):
        path = repo / name
        if path.is_file():
            count = len(path.read_bytes().splitlines())
            if count:
                files[name] = [[1, count]]
    return {"repo": str(repo), "base": base, "merge_base": merge_base, "files": files}


def filter_diagnostics(log, ranges, ignored=()):
    repo = Path(ranges["repo"]).resolve()
    findings = []
    seen = set()
    for raw in log.splitlines():
        match = DIAGNOSTIC.match(raw)
        if not match or match["rule"] in ignored:
            continue
        path = Path(match["file"])
        if not path.is_absolute():
            path = repo / path
        try:
            name = path.resolve().relative_to(repo).as_posix()
        except ValueError:
            continue
        line = int(match["line"])
        if not any(start <= line <= end for start, end in ranges["files"].get(name, [])):
            continue
        key = (name, line, match["rule"], match["message"])
        if key not in seen:
            seen.add(key)
            findings.append(dict(zip(("file", "line", "rule", "message"), key)))
    return findings


def setup_analyzer(skill_dir=SKILL_DIR):
    version = (skill_dir / "analyzer" / "VERSION").read_text(encoding="utf-8").strip()
    if not re.fullmatch(r"\d+(?:\.\d+){2,3}", version):
        raise RuntimeError("Invalid analyzer/VERSION")
    package = skill_dir / "analyzer" / f"SonarAnalyzer.CSharp.{version}.nupkg"
    output = skill_dir / "analyzer" / "analyzers"
    marker = output / ".version"
    if (output / "SonarAnalyzer.CSharp.dll").is_file() and marker.is_file():
        if marker.read_text(encoding="utf-8").strip() == version:
            return output
    if not package.exists():
        url = ("https://api.nuget.org/v3-flatcontainer/sonaranalyzer.csharp/"
               f"{version}/sonaranalyzer.csharp.{version}.nupkg")
        with urlopen(url, timeout=120) as response:
            data = response.read()
        # Check the archive before caching it; leave no partial package on failure.
        with tempfile.TemporaryFile() as staging:
            staging.write(data)
            staging.seek(0)
            with ZipFile(staging) as archive:
                if "analyzers/SonarAnalyzer.CSharp.dll" not in archive.namelist():
                    raise RuntimeError("NuGet package does not contain the expected C# analyzer")
        package.write_bytes(data)
    with ZipFile(package) as archive:
        dlls = [name for name in archive.namelist()
                if name.startswith("analyzers/") and name.endswith(".dll")
                and len(Path(name).parts) == 2]
        if "analyzers/SonarAnalyzer.CSharp.dll" not in dlls:
            raise RuntimeError("NuGet package does not contain the expected C# analyzer")
        output.mkdir(parents=True, exist_ok=True)
        for name in dlls:
            (output / Path(name).name).write_bytes(archive.read(name))
    marker.write_text(version + "\n", encoding="utf-8")
    return output


def run_analysis(repo, base="main", excludes=(), ignored=(), target=None):
    ranges = collect_ranges(repo, base, excludes)
    if not ranges["files"]:
        return {"status": "no_changed_lines", "findings": [], "changed_files": 0}, 0
    repo = Path(ranges["repo"])
    artifacts = Path(tempfile.mkdtemp(prefix="dotnet-sonar-qube-"))
    (artifacts / "ranges.json").write_text(json.dumps(ranges, ensure_ascii=False, indent=2), encoding="utf-8")
    setup_analyzer()
    before = git(repo, "status", "--porcelain=v1", "-z")
    command = ["dotnet", "build"]
    if target:
        command.append(str(target))
    command += ["--no-incremental", "--no-restore", "-nologo",
                f"-p:CustomBeforeMicrosoftCommonTargets={SKILL_DIR / 'sonar.targets'}",
                "-p:RunAnalyzers=true", "-p:RunAnalyzersDuringBuild=true"]
    env = os.environ.copy()
    env["DOTNET_CLI_UI_LANGUAGE"] = "en-US"
    with (artifacts / "build.log").open("w", encoding="utf-8") as log:
        build = subprocess.run(command, cwd=repo, env=env, stdout=log, stderr=subprocess.STDOUT)
    after = git(repo, "status", "--porcelain=v1", "-z")
    log = (artifacts / "build.log").read_text(encoding="utf-8", errors="replace")
    findings = filter_diagnostics(log, ranges, ignored)
    result = {
        "status": "complete" if build.returncode == 0 else "build_failed",
        "base": ranges["base"], "merge_base": ranges["merge_base"],
        "changed_files": len(ranges["files"]),
        "files_with_findings": len({finding["file"] for finding in findings}),
        "findings": findings, "artifacts": str(artifacts),
        "build_exit_code": build.returncode, "git_status_changed": before != after,
    }
    if build.returncode:
        result["errors"] = [line.strip() for line in log.splitlines() if ": error " in line][:20]
    (artifacts / "result.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    return result, 0 if build.returncode == 0 else 1


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description=__doc__)
    subcommands = parser.add_subparsers(dest="command", required=True)
    for name in ("ranges", "run"):
        command = subcommands.add_parser(name)
        command.add_argument("--repo", type=Path, default=Path.cwd())
        command.add_argument("--base", default="main")
        command.add_argument("--exclude", action="append", default=[])
        if name == "run":
            command.add_argument("--target", help="Solution or project, relative to the Git root")
            command.add_argument("--ignore-rule", action="append", default=[])
    subcommands.add_parser("setup", help="Download the pinned analyzer without building a project")
    command = subcommands.add_parser("filter", help="Filter an existing build log using ranges JSON")
    command.add_argument("log", type=Path)
    command.add_argument("ranges", type=Path)
    command.add_argument("--ignore-rule", action="append", default=[])
    args = parser.parse_args()
    try:
        if args.command == "ranges":
            result = collect_ranges(args.repo, args.base, args.exclude)
            code = 0
        elif args.command == "setup":
            result, code = {"analyzer_dir": str(setup_analyzer())}, 0
        elif args.command == "filter":
            ranges = json.loads(args.ranges.read_text(encoding="utf-8-sig"))
            log = args.log.read_text(encoding="utf-8-sig", errors="replace")
            result, code = {"findings": filter_diagnostics(log, ranges, args.ignore_rule)}, 0
        else:
            result, code = run_analysis(args.repo, args.base, args.exclude, args.ignore_rule, args.target)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return code
    except (OSError, RuntimeError, ValueError, BadZipFile) as error:
        print(json.dumps({"status": "failed", "error": str(error)}, ensure_ascii=False), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
