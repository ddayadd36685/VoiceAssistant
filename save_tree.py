from __future__ import annotations

import argparse
import fnmatch
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, List, Optional, Sequence, Tuple


DEFAULT_IGNORED_DIR_NAMES = {
    ".git",
    ".hg",
    ".svn",
    ".venv",
    "venv",
    "env",
    "__pycache__",
    ".pytest_cache",
    ".mypy_cache",
    ".ruff_cache",
    "node_modules",
    "dist",
    "build",
    ".idea",
    ".vscode",
    ".trae",
}


@dataclass(frozen=True)
class IgnoreRules:
    root: Path
    ignored_dir_names: frozenset[str]
    patterns: Tuple[str, ...]
    include_hidden: bool

    def is_ignored(self, path: Path, *, is_dir: bool) -> bool:
        try:
            rel = path.relative_to(self.root)
        except ValueError:
            rel = path

        name = path.name
        if not self.include_hidden and name.startswith("."):
            return True

        if is_dir and name in self.ignored_dir_names:
            return True

        rel_posix = rel.as_posix()
        basename = name

        for raw in self.patterns:
            if not raw:
                continue
            if raw.startswith("!"):
                continue

            anchored = raw.startswith("/")
            pattern = raw.lstrip("/")
            is_dir_pattern = pattern.endswith("/")
            pattern = pattern.rstrip("/")

            if is_dir_pattern and not is_dir:
                continue

            if "/" in pattern:
                candidate = rel_posix
                if not anchored:
                    if fnmatch.fnmatch(candidate, pattern) or fnmatch.fnmatch(f"**/{candidate}", f"**/{pattern}"):
                        return True
                else:
                    if fnmatch.fnmatch(candidate, pattern):
                        return True
            else:
                if fnmatch.fnmatch(basename, pattern):
                    return True

        return False


def load_gitignore_patterns(root: Path) -> List[str]:
    gitignore = root / ".gitignore"
    if not gitignore.exists():
        return []

    patterns: List[str] = []
    try:
        text = gitignore.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return []

    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        patterns.append(line)
    return patterns


def iter_dir_entries_sorted(path: Path) -> List[os.DirEntry]:
    entries: List[os.DirEntry] = []
    with os.scandir(path) as it:
        for entry in it:
            entries.append(entry)

    def sort_key(e: os.DirEntry) -> Tuple[int, str]:
        try:
            is_dir = e.is_dir(follow_symlinks=False)
        except OSError:
            is_dir = False
        return (0 if is_dir else 1, e.name.lower())

    entries.sort(key=sort_key)
    return entries


def build_tree_lines(
    root: Path,
    rules: IgnoreRules,
    *,
    max_depth: Optional[int],
    follow_symlinks: bool,
) -> List[str]:
    lines: List[str] = [root.name]

    def walk(current: Path, prefix: str, depth: int) -> None:
        if max_depth is not None and depth > max_depth:
            return

        try:
            entries = iter_dir_entries_sorted(current)
        except OSError:
            return

        visible: List[os.DirEntry] = []
        for e in entries:
            p = Path(e.path)
            try:
                is_dir = e.is_dir(follow_symlinks=follow_symlinks)
            except OSError:
                is_dir = False

            if rules.is_ignored(p, is_dir=is_dir):
                continue
            visible.append(e)

        for i, e in enumerate(visible):
            is_last = i == len(visible) - 1
            connector = "└── " if is_last else "├── "

            p = Path(e.path)
            lines.append(f"{prefix}{connector}{e.name}")

            try:
                is_dir = e.is_dir(follow_symlinks=follow_symlinks)
            except OSError:
                is_dir = False

            if is_dir:
                next_prefix = f"{prefix}{'    ' if is_last else '│   '}"
                walk(p, next_prefix, depth + 1)

    walk(root, "", 1)
    return lines


def parse_args(argv: Optional[Sequence[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="生成并保存项目文件树（tree）到文件")
    parser.add_argument(
        "root",
        nargs="?",
        default=".",
        help="项目根目录（默认：当前目录）",
    )
    parser.add_argument(
        "-o",
        "--output",
        default=None,
        help="输出文件路径（默认：<root>/project_tree.txt）",
    )
    parser.add_argument(
        "--max-depth",
        type=int,
        default=0,
        help="最大遍历深度，0 表示不限（默认：0）",
    )
    parser.add_argument(
        "--include-hidden",
        action="store_true",
        help="包含以 . 开头的隐藏文件/目录",
    )
    parser.add_argument(
        "--follow-symlinks",
        action="store_true",
        help="跟随符号链接（默认：否）",
    )
    parser.add_argument(
        "--no-gitignore",
        action="store_true",
        help="不读取 .gitignore",
    )
    parser.add_argument(
        "--ignore",
        action="append",
        default=[],
        help="额外忽略规则（可重复；支持 glob；如：--ignore '*.wav'）",
    )
    parser.add_argument(
        "--quiet",
        action="store_true",
        help="不向控制台输出树内容，仅保存文件",
    )
    return parser.parse_args(argv)


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = parse_args(argv)

    root = Path(args.root).resolve()
    if not root.exists() or not root.is_dir():
        raise SystemExit(f"root 不是有效目录：{root}")

    output_path = Path(args.output).resolve() if args.output else (root / "project_tree.txt")

    gitignore_patterns: List[str] = []
    if not args.no_gitignore:
        gitignore_patterns = load_gitignore_patterns(root)

    extra_patterns: List[str] = list(args.ignore or [])
    patterns = tuple(gitignore_patterns + extra_patterns)

    max_depth: Optional[int]
    if args.max_depth and args.max_depth > 0:
        max_depth = args.max_depth
    else:
        max_depth = None

    rules = IgnoreRules(
        root=root,
        ignored_dir_names=frozenset(DEFAULT_IGNORED_DIR_NAMES),
        patterns=patterns,
        include_hidden=bool(args.include_hidden),
    )

    lines = build_tree_lines(
        root,
        rules,
        max_depth=max_depth,
        follow_symlinks=bool(args.follow_symlinks),
    )
    content = "\n".join(lines) + "\n"

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(content, encoding="utf-8", errors="ignore")

    if not args.quiet:
        print(content, end="")

    print(f"\n已保存：{output_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
