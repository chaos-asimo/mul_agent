# -*- coding: utf-8 -*-
"""Package Linux Docker deploy tar.gz (exclude by .dockerignore, keep slim).

Usage:  python package-deploy.py
Output: mul_agent-linux-deploy.tar.gz (~3MB, no venv/wheels/data)

Bypasses PowerShell 5.1 encoding quirks by doing the copy in Python and
invoking the system `tar` for compression.
"""
import os
import shutil
import subprocess
import sys
import time

ROOT = os.path.dirname(os.path.abspath(__file__))
STAGING = os.path.join(ROOT, "mul_agent")
DEST = os.path.join(ROOT, "mul_agent-linux-deploy.tar.gz")

# Top-level dirs to exclude
EX_DIRS = {
    "packages", "node_modules", ".venv", "venv", "ENV", "data", "logs",
    "uploads", "__pycache__", ".git", ".idea", ".vscode", ".trae",
    ".pytest_cache", "wheels", "mul_agent", "_extract_test2", "_verify_tar",
}
# Top-level files to exclude
EX_FILES = {
    "mul_agent-linux-deploy.tar.gz", "package-deploy.ps1", "package-deploy.py",
    "test-notin.ps1",
}
# Subdir names to always skip when recursing
SKIP_SUBDIRS = {"__pycache__", "uploads", "lobster-claw-files", "mu-files"}
# File extensions to always skip
SKIP_EXTS = {".pyc", ".pyo", ".tmp", ".bak", ".cache"}


def copy_tree(src_dir, dst_dir):
    """Recursively copy src_dir into dst_dir applying exclusion rules."""
    copied_files = 0
    for entry in os.listdir(src_dir):
        s = os.path.join(src_dir, entry)
        d = os.path.join(dst_dir, entry)
        if os.path.isdir(s):
            if entry in SKIP_SUBDIRS:
                continue
            os.makedirs(d, exist_ok=True)
            copied_files += copy_tree(s, d)
        else:
            if os.path.splitext(entry)[1].lower() in SKIP_EXTS:
                continue
            shutil.copy2(s, d)
            copied_files += 1
    return copied_files


def _rmtree_retry(path, tries=16, delay=0.5):
    """重试删除目录：规避 Windows 文件锁瞬态占用（如 .gitignore 被杀软/索引器持有）"""
    for i in range(tries):
        try:
            shutil.rmtree(path)
            return
        except (PermissionError, OSError):
            if i == tries - 1:
                raise
            time.sleep(delay)


def main():
    # Clean old staging / dest
    if os.path.isdir(STAGING):
        _rmtree_retry(STAGING)
    if os.path.isfile(DEST):
        os.remove(DEST)
    os.makedirs(STAGING)

    total_files = 0
    for name in sorted(os.listdir(ROOT)):
        path = os.path.join(ROOT, name)
        if os.path.isdir(path):
            if name in EX_DIRS:
                continue
            target = os.path.join(STAGING, name)
            os.makedirs(target, exist_ok=True)
            total_files += copy_tree(path, target)
        else:
            if name in EX_FILES:
                continue
            shutil.copy2(path, os.path.join(STAGING, name))
            total_files += 1

    print("staged files:", total_files)

    # Compress: tar entries will be 'mul_agent/...' so extracting produces a
    # top-level mul_agent/ directory (e.g. ./mul_agent/web/routes/...)
    subprocess.run(
        ["tar", "-czf", DEST, "-C", ROOT, "mul_agent"],
        check=True,
    )

    # Cleanup staging（重试，规避 Windows 文件锁）
    _rmtree_retry(STAGING)

    size = os.path.getsize(DEST)
    print("=" * 50)
    print("Done: mul_agent-linux-deploy.tar.gz")
    print("  size: {:.1f} KB ({:.3f} MB)".format(size / 1024, size / 1024 / 1024))
    print("=" * 50)


if __name__ == "__main__":
    sys.exit(main())
