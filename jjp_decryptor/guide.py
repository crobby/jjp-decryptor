"""Audio guide generator — scans decrypted game assets and produces
a structured summary of all audio files, categorized by type.

Used by both the GUI Guides tab and the Claude Code /audio-guide command.
"""

import io
import os
import struct
import wave


# ---------------------------------------------------------------------------
# Low-level format helpers (standalone — no dependency on audio.py so this
# module stays lightweight for the GUI)
# ---------------------------------------------------------------------------

def _wav_info(data):
    """Return (channels, sample_rate, bits, duration_sec, nframes) or None."""
    try:
        with wave.open(io.BytesIO(data), "rb") as w:
            nframes = w.getnframes()
            rate = w.getframerate()
            dur = nframes / rate if rate else 0
            return (w.getnchannels(), rate,
                    w.getsampwidth() * 8, round(dur, 2), nframes)
    except Exception:
        return None


def _ogg_info(data):
    """Return (channels, sample_rate, bitrate_kbps) or None."""
    if len(data) < 4 or data[:4] != b"OggS":
        return None
    marker = b"\x01vorbis"
    idx = data.find(marker)
    if idx < 0 or idx + 7 + 21 > len(data):
        return None
    hdr = idx + 7
    try:
        version = struct.unpack_from("<I", data, hdr)[0]
        if version != 0:
            return None
        channels = data[hdr + 4]
        sample_rate = struct.unpack_from("<I", data, hdr + 5)[0]
        nom_br = struct.unpack_from("<i", data, hdr + 13)[0]
        br_kbps = nom_br // 1000 if nom_br > 0 else 0
        return (channels, sample_rate, br_kbps)
    except (struct.error, IndexError):
        return None


# ---------------------------------------------------------------------------
# Audio file info container
# ---------------------------------------------------------------------------

class AudioFile:
    """Metadata for a single audio file."""
    __slots__ = ("rel_path", "filename", "folder", "ext", "size",
                 "channels", "sample_rate", "bits", "duration",
                 "bitrate_kbps", "category", "prefix")

    def __init__(self, rel_path, size):
        self.rel_path = rel_path.replace("\\", "/")
        self.filename = os.path.basename(self.rel_path)
        self.folder = os.path.dirname(self.rel_path).replace("\\", "/")
        self.ext = os.path.splitext(self.filename)[1].lower()
        self.size = size
        self.channels = 0
        self.sample_rate = 0
        self.bits = 0
        self.duration = 0.0
        self.bitrate_kbps = 0
        self.category = ""  # music / speech / fx / other
        self.prefix = ""    # filename prefix before first _ or digit

    @property
    def format_str(self):
        if self.ext == ".ogg":
            br = f"{self.bitrate_kbps}kbps" if self.bitrate_kbps else "VBR"
            return f"{self.channels}ch/{self.sample_rate}Hz/{br}"
        return f"{self.channels}ch/{self.bits}bit/{self.sample_rate}Hz"

    @property
    def duration_str(self):
        if self.duration <= 0:
            return ""
        m, s = divmod(int(self.duration), 60)
        return f"{m}:{s:02d}"


# ---------------------------------------------------------------------------
# Scanner
# ---------------------------------------------------------------------------

def _classify_prefix(filename):
    """Extract the meaningful prefix from a filename for grouping."""
    name = os.path.splitext(filename)[0]
    # Common JJP prefixes: VO_GIBBS_, FX_, BG_, Fanfare_, VS_
    parts = name.split("_")
    if len(parts) >= 2:
        # For VO_ files, include the speaker name
        if parts[0] == "VO" and len(parts) >= 3:
            return f"VO_{parts[1]}"
        return parts[0]
    return name


def _classify_category(rel_path):
    """Assign a category based on the folder structure."""
    lower = rel_path.lower().replace("\\", "/")
    if "/music/" in lower or "/song" in lower:
        return "music"
    if "/speech/" in lower or "/voice/" in lower or "/vo/" in lower:
        return "speech"
    if "/fx/" in lower or "/sfx/" in lower or "/sound/" in lower:
        # If it's directly in sound/ but not in a subfolder, check filename
        if "/sound/" in lower and lower.count("/") <= 2:
            name = os.path.basename(lower)
            if name.startswith("vo_"):
                return "speech"
            if name.startswith("bg_"):
                return "music"
        return "fx"
    # Fallback: guess from filename
    name = os.path.basename(lower)
    if name.startswith("vo_"):
        return "speech"
    if name.startswith("bg_"):
        return "music"
    if name.startswith("fx_") or name.startswith("fanfare_"):
        return "fx"
    return "other"


def scan_audio_files(assets_folder, progress_cb=None):
    """Walk *assets_folder* and return a list of AudioFile objects.

    *progress_cb(current, total)* is called periodically if provided.
    Only processes .wav and .ogg files.
    """
    # First pass: collect audio file paths
    audio_paths = []
    for root, _dirs, files in os.walk(assets_folder):
        for f in files:
            ext = os.path.splitext(f)[1].lower()
            if ext in (".wav", ".ogg"):
                audio_paths.append(os.path.join(root, f))

    total = len(audio_paths)
    results = []

    for i, fpath in enumerate(audio_paths):
        if progress_cb and i % 50 == 0:
            progress_cb(i, total)

        rel = os.path.relpath(fpath, assets_folder)
        try:
            size = os.path.getsize(fpath)
        except OSError:
            continue

        af = AudioFile(rel, size)
        af.category = _classify_category(rel)
        af.prefix = _classify_prefix(af.filename)

        # Read just enough bytes for header parsing
        try:
            with open(fpath, "rb") as fp:
                if af.ext == ".ogg":
                    # OGG header is in first ~8KB
                    header = fp.read(8192)
                    info = _ogg_info(header)
                    if info:
                        af.channels, af.sample_rate, af.bitrate_kbps = info
                        # Estimate duration from file size and bitrate
                        if af.bitrate_kbps > 0:
                            af.duration = round(
                                size * 8 / (af.bitrate_kbps * 1000), 1)
                else:
                    # WAV: read entire file for accurate nframes
                    data = fp.read()
                    info = _wav_info(data)
                    if info:
                        af.channels, af.sample_rate, af.bits, af.duration, _ = info
        except OSError:
            pass

        results.append(af)

    if progress_cb:
        progress_cb(total, total)

    return results


# ---------------------------------------------------------------------------
# Summary builder
# ---------------------------------------------------------------------------

def _size_str(nbytes):
    if nbytes >= 1_000_000_000:
        return f"{nbytes / 1_000_000_000:.1f} GB"
    if nbytes >= 1_000_000:
        return f"{nbytes / 1_000_000:.0f} MB"
    if nbytes >= 1_000:
        return f"{nbytes / 1_000:.0f} KB"
    return f"{nbytes} B"


class AudioSummary:
    """Structured summary of a game's audio files."""

    def __init__(self, files):
        self.files = sorted(files, key=lambda f: f.rel_path)
        self.total_count = len(files)
        self.total_size = sum(f.size for f in files)

        # By category
        self.by_category = {}
        for f in files:
            cat = f.category or "other"
            self.by_category.setdefault(cat, []).append(f)

        # By folder
        self.by_folder = {}
        for f in files:
            self.by_folder.setdefault(f.folder, []).append(f)

        # By prefix within each category
        self.by_prefix = {}
        for f in files:
            key = (f.category, f.prefix)
            self.by_prefix.setdefault(key, []).append(f)

    def category_stats(self):
        """Return list of (category, count, size, formats) tuples."""
        stats = []
        for cat in ("music", "speech", "fx", "other"):
            files = self.by_category.get(cat, [])
            if not files:
                continue
            exts = set(f.ext for f in files)
            fmt = "/".join(e.upper().lstrip(".") for e in sorted(exts))
            stats.append((cat, len(files), sum(f.size for f in files), fmt))
        return stats

    def folder_stats(self):
        """Return list of (folder, count, size, format) sorted by path."""
        stats = []
        for folder in sorted(self.by_folder.keys()):
            files = self.by_folder[folder]
            exts = set(f.ext for f in files)
            fmt = "/".join(e.upper().lstrip(".") for e in sorted(exts))
            stats.append((folder, len(files), sum(f.size for f in files), fmt))
        return stats

    def prefix_groups(self, category):
        """Return list of (prefix, count, example_files) for a category."""
        groups = []
        for (cat, prefix), files in sorted(self.by_prefix.items()):
            if cat != category:
                continue
            examples = [f.filename for f in files[:5]]
            groups.append((prefix, len(files), examples))
        return sorted(groups, key=lambda g: -g[1])

    def format_overview(self):
        """Return dict of format_str -> count across all files."""
        fmt_counts = {}
        for f in self.files:
            if f.channels > 0:
                fmt_counts[f.format_str] = fmt_counts.get(f.format_str, 0) + 1
        return sorted(fmt_counts.items(), key=lambda x: -x[1])


def build_summary(assets_folder, progress_cb=None):
    """Scan a game folder and return an AudioSummary."""
    files = scan_audio_files(assets_folder, progress_cb)
    return AudioSummary(files)


# ---------------------------------------------------------------------------
# Markdown export (used by the Claude Code /audio-guide command)
# ---------------------------------------------------------------------------

def summary_to_markdown(summary, game_name="Unknown Game"):
    """Convert an AudioSummary to a markdown string."""
    lines = []
    lines.append(f"# {game_name} — Audio File Guide\n")
    lines.append("A reference for modders who want to customize audio "
                 f"in JJP's {game_name} pinball.\n")
    lines.append(f"**Total: {summary.total_count:,} audio files "
                 f"({_size_str(summary.total_size)})**\n")

    # Overview table
    lines.append("| Folder | Files | Format | Size |")
    lines.append("|--------|-------|--------|------|")
    for folder, count, size, fmt in summary.folder_stats():
        lines.append(f"| `{folder}/` | {count:,} | {fmt} | {_size_str(size)} |")
    lines.append("")

    # Format breakdown
    fmt_overview = summary.format_overview()
    if fmt_overview:
        lines.append("### Audio Formats\n")
        lines.append("| Format | Files |")
        lines.append("|--------|-------|")
        for fmt, count in fmt_overview:
            lines.append(f"| {fmt} | {count:,} |")
        lines.append("")

    lines.append("---\n")

    # Per-category sections
    cat_labels = {
        "music": "Music",
        "speech": "Speech / Voice",
        "fx": "Sound Effects",
        "other": "Other Audio",
    }

    for cat in ("music", "speech", "fx", "other"):
        cat_files = summary.by_category.get(cat, [])
        if not cat_files:
            continue

        exts = set(f.ext for f in cat_files)
        fmt = "/".join(e.upper().lstrip(".") for e in sorted(exts))
        label = cat_labels.get(cat, cat.title())
        lines.append(f"## {label} ({len(cat_files):,} {fmt} files)\n")

        # Prefix groups
        groups = summary.prefix_groups(cat)
        if groups:
            lines.append("### File Groups\n")
            lines.append("| Prefix | Files | Examples |")
            lines.append("|--------|-------|----------|")
            for prefix, count, examples in groups:
                ex_str = ", ".join(f"`{e}`" for e in examples[:3])
                if count > 3:
                    ex_str += f" ... (+{count - 3} more)"
                lines.append(f"| `{prefix}_*` | {count:,} | {ex_str} |")
            lines.append("")

        # Full file listing (only for music — typically small enough)
        if cat == "music":
            lines.append("### All Music Files\n")
            lines.append("| File | Format | Duration |")
            lines.append("|------|--------|----------|")
            for f in sorted(cat_files, key=lambda x: x.filename):
                dur = f.duration_str or "—"
                lines.append(f"| `{f.filename}` | {f.format_str} | {dur} |")
            lines.append("")

        lines.append("---\n")

    # Modding tips
    lines.append("## Modding Tips\n")
    lines.append("- **Music** files are the easiest to replace — "
                 "swap in any audio and the app auto-converts format/duration.")
    lines.append("- **Speech** files are short voice clips — match the "
                 "original format for best results.")
    lines.append("- **Sound effects** are tightly timed to game events — "
                 "keep replacements close to the original duration.")
    lines.append("- Use the **Write** tab to write modified files "
                 "back to the game SSD or build a USB ISO.")
    lines.append("")

    return "\n".join(lines)
