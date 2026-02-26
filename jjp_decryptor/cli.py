"""CLI entry point for running jjp_decryptor in headless / Docker mode.

Usage:
    python -m jjp_decryptor.cli decrypt -i /data/game.iso -o /data/output
    python -m jjp_decryptor.cli mod -i /data/game.iso -a /data/output
"""

import argparse
import os
import sys
import threading

from . import __version__
from . import config
from .executor import NativeExecutor
from .pipeline import StandaloneDecryptPipeline, StandaloneModPipeline


def _timestamp():
    from datetime import datetime
    return datetime.now().strftime("[%H:%M:%S]")


class CLICallbacks:
    """Simple print-based callbacks for headless pipeline execution."""

    def __init__(self, phases):
        self._phases = phases
        self._success = None
        self._summary = ""
        self._done = threading.Event()

    def log(self, text, level="info"):
        if not text:
            return
        prefix = _timestamp()
        if level == "error":
            print(f"{prefix} ERROR: {text}", file=sys.stderr)
        elif level == "success":
            print(f"{prefix} {text}")
        else:
            print(f"{prefix} {text}")

    def phase(self, index):
        if 0 <= index < len(self._phases):
            name = self._phases[index]
            print(f"\n{_timestamp()} === Phase {index + 1}/{len(self._phases)}: {name} ===")

    def progress(self, current, total, desc=""):
        if total > 0:
            pct = current * 100 // total
            bar_len = 30
            filled = bar_len * current // total
            bar = "#" * filled + "-" * (bar_len - filled)
            extra = f" {desc}" if desc else ""
            print(f"\r  [{bar}] {pct}%{extra}  ", end="", flush=True)
            if current >= total:
                print()  # newline after completion

    def done(self, success, summary):
        self._success = success
        self._summary = summary
        self._done.set()

    def wait(self):
        self._done.wait()
        return self._success, self._summary


def cmd_decrypt(args):
    """Run the decrypt pipeline."""
    image_path = os.path.abspath(args.image)
    output_path = os.path.abspath(args.output)

    if not os.path.isfile(image_path):
        print(f"Error: Image file not found: {image_path}", file=sys.stderr)
        return 1

    os.makedirs(output_path, exist_ok=True)

    # Look for cached fl_decrypted.dat
    fl_dat_path = None
    fl_candidate = os.path.join(output_path, "fl_decrypted.dat")
    if os.path.isfile(fl_candidate):
        fl_dat_path = fl_candidate
        print(f"{_timestamp()} Using cached file list: {fl_dat_path}")
    else:
        print(f"{_timestamp()} No cached file list. Will scan filesystem and auto-detect filler sizes.")

    cb = CLICallbacks(config.STANDALONE_PHASES)
    pipeline = StandaloneDecryptPipeline(
        image_path, output_path, fl_dat_path,
        cb.log, cb.phase, cb.progress, cb.done,
    )

    # Override the executor with NativeExecutor (we're inside the container)
    pipeline.executor = NativeExecutor()

    print(f"{_timestamp()} JJP Asset Decryptor v{__version__} (CLI)")
    print(f"{_timestamp()} Image: {image_path}")
    print(f"{_timestamp()} Output: {output_path}")
    print()

    # Run pipeline on current thread
    pipeline.run()

    success, summary = cb.wait()
    print()
    if success:
        print(f"{_timestamp()} SUCCESS: {summary}")
        return 0
    else:
        print(f"{_timestamp()} FAILED: {summary}", file=sys.stderr)
        return 1


def cmd_mod(args):
    """Run the mod pipeline."""
    image_path = os.path.abspath(args.image)
    assets_folder = os.path.abspath(args.assets)

    if not os.path.isfile(image_path):
        print(f"Error: Image file not found: {image_path}", file=sys.stderr)
        return 1

    if not os.path.isdir(assets_folder):
        print(f"Error: Assets folder not found: {assets_folder}", file=sys.stderr)
        return 1

    # fl_decrypted.dat must exist in the assets folder
    fl_dat_path = os.path.join(assets_folder, "fl_decrypted.dat")
    if not os.path.isfile(fl_dat_path):
        print(f"Error: fl_decrypted.dat not found in {assets_folder}", file=sys.stderr)
        print("Run decrypt first to generate the file list.", file=sys.stderr)
        return 1

    print(f"{_timestamp()} Using file list: {fl_dat_path}")

    cb = CLICallbacks(config.STANDALONE_MOD_PHASES)
    pipeline = StandaloneModPipeline(
        image_path, assets_folder, fl_dat_path,
        cb.log, cb.phase, cb.progress, cb.done,
    )

    # Override the executor with NativeExecutor (we're inside the container)
    pipeline.executor = NativeExecutor()
    pipeline.log_link = lambda text, url: cb.log(f"{text}: {url}")

    print(f"{_timestamp()} JJP Asset Decryptor v{__version__} (CLI)")
    print(f"{_timestamp()} Image: {image_path}")
    print(f"{_timestamp()} Assets: {assets_folder}")
    print()

    pipeline.run()

    success, summary = cb.wait()
    print()
    if success:
        print(f"{_timestamp()} SUCCESS: {summary}")
        return 0
    else:
        print(f"{_timestamp()} FAILED: {summary}", file=sys.stderr)
        return 1


def main():
    parser = argparse.ArgumentParser(
        prog="jjp-decryptor",
        description="JJP Asset Decryptor — decrypt and modify Jersey Jack Pinball game assets",
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    subparsers = parser.add_subparsers(dest="command", required=True)

    # decrypt subcommand
    p_decrypt = subparsers.add_parser("decrypt", help="Decrypt game assets from ISO")
    p_decrypt.add_argument("-i", "--image", required=True, help="Path to game ISO or .img file")
    p_decrypt.add_argument("-o", "--output", required=True, help="Output directory for decrypted files")

    # mod subcommand
    p_mod = subparsers.add_parser("mod", help="Modify assets and rebuild ISO")
    p_mod.add_argument("-i", "--image", required=True, help="Path to original game ISO")
    p_mod.add_argument("-a", "--assets", required=True, help="Assets folder with modified files")

    args = parser.parse_args()

    if args.command == "decrypt":
        sys.exit(cmd_decrypt(args))
    elif args.command == "mod":
        sys.exit(cmd_mod(args))


if __name__ == "__main__":
    main()
