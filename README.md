# JJP Asset Decryptor

A cross-platform GUI application for decrypting and modifying game assets on Jersey Jack Pinball (JJP) machines. Runs on Windows, macOS, and Linux. The encryption algorithm has been fully reverse-engineered — **no USB dongle required**. Turns a complex multi-step process involving filesystem extraction, cryptographic decryption, and ISO rebuilding into a single button click.

## What It Does

JJP pinball machines store encrypted game assets (images, videos, audio, fonts) on their internal drives. Each machine ships with a Clonezilla backup ISO containing the full filesystem image. This tool:

1. **Decrypts** every asset in a game image using a fully reverse-engineered pure Python implementation of the game's custom PRNG and XOR cipher — no dongle or game binary needed
2. **Re-encrypts** modified assets back into the game image with CRC32 forgery so the game's integrity checks pass without touching the file list
3. **Produces a bootable Clonezilla ISO** ready to flash onto the machine via USB

## Supported Games

Confirmed working (26,000+ files decrypted across all four):

- Willy Wonka & the Chocolate Factory
- Guns N' Roses
- Elton John
- The Hobbit

Not yet tested (but should work — same platform and encryption scheme):

- Wizard of Oz
- Dialed In
- Toy Story
- The Godfather
- Avatar
- Harry Potter

## Requirements

**Game image**: Clonezilla ISO backup or raw ext4 filesystem image — download "full installs" from https://marketing.jerseyjackpinball.com/downloads/

No USB dongle, gcc, or usbipd-win required. No additional Python packages needed (uses only the standard library).

### Windows
- **Windows 10/11** with WSL2 enabled
- **WSL2** with Ubuntu (or similar): `wsl --install`
- **partclone** in WSL: `wsl -u root -- apt install partclone`
- **xorriso** in WSL: `wsl -u root -- apt install xorriso`
- **Rufus** (for writing modified ISOs to USB): [rufus.ie](https://rufus.ie/)

### macOS
- **Docker Desktop**: [docker.com/products/docker-desktop](https://www.docker.com/products/docker-desktop/)
- The app auto-builds a lightweight Alpine container with partclone/xorriso on first run
- **balenaEtcher** (for writing modified ISOs to USB): [etcher.balena.io](https://etcher.balena.io/)

### Linux
- **partclone**: `sudo apt install partclone`
- **xorriso**: `sudo apt install xorriso`
- **pigz**: `sudo apt install pigz`
- Requires `sudo` for loop-mounting ext4 images
- **dd** or **balenaEtcher** for writing modified ISOs to USB

## Installation

### Option 1: Pre-built Package (Recommended)

Download from the [Releases page](https://github.com/davidvanderburgh/jjp-decryptor/releases):

- **Windows**: `JJP_Asset_Decryptor_Setup.exe` — includes bundled Python runtime
- **macOS**: `JJP_Asset_Decryptor.dmg` — drag to Applications
- **Linux**: `JJP_Asset_Decryptor.AppImage` — make executable and run

**Windows installer note**: When prompted, check **Install prerequisites** to set up WSL2, partclone, and xorriso. If WSL2 was just enabled, reboot and re-run the prerequisites installer from the Start Menu.

**macOS note**: Docker Desktop must be installed and running. The app auto-builds a lightweight Alpine container with partclone and xorriso on first run.

The app checks for updates automatically on startup and will notify you when a new version is available.

### Option 2: Run from Source

1. Install [Python 3.10+](https://www.python.org/downloads/)
2. Clone the repository:
   ```
   git clone https://github.com/davidvanderburgh/jjp-decryptor.git
   cd jjp-decryptor
   ```
3. Install prerequisites manually (see Requirements above)
4. Launch:
   ```
   python -m jjp_decryptor
   ```
   On Windows, you can also double-click `JJP Asset Decryptor.pyw` to launch without a console window, or run `create_shortcut.bat` to create a desktop shortcut.

## Usage

### Decrypting Assets

1. Launch the app
2. Prerequisites are checked automatically on startup (Docker on macOS, WSL2 on Windows, native tools on Linux)
3. Click **Browse** to select your game image (ISO or ext4)
4. Click **Browse** to select an output folder for decrypted assets
5. Click **Start Decryption**

The first run for a game will scan the filesystem and auto-detect filler sizes for every encrypted file. This generates an `fl_decrypted.dat` in the output folder which makes subsequent runs faster. The app remembers your last-used paths between sessions.

### Modifying Assets

After decrypting, you can replace game assets and re-encrypt them:

1. Switch to the **Modify Assets** tab
2. Ensure the **Game Image** points to the **original Clonezilla ISO** and the output folder contains your decrypted files
3. Replace files in the output folder (PNGs, WebMs, OGGs, WAVs, etc.)
4. Click **Apply Modifications** — the tool detects changed files via checksums, re-encrypts only what changed, forges CRC32 checksums to match the original file list, and builds a new bootable Clonezilla ISO
5. The output `<name>_modified.iso` is saved to your output folder

### Installing on the Machine

1. Write the `_modified.iso` to a USB drive:
   - **Windows**: Use [Rufus](https://rufus.ie/) — **select ISO mode (not DD mode)** when prompted
   - **macOS/Linux**: Use [balenaEtcher](https://etcher.balena.io/) or `dd`
2. Boot the pinball machine from the USB drive
3. Clonezilla restores the image automatically

Detailed instructions: [Windows (PDF)](https://marketing.jerseyjackpinball.com/general/install-full/JJP_USB_UPDATE_PC_instructions.pdf) | [Mac (PDF)](https://marketing.jerseyjackpinball.com/general/install-full/JJP_USB_UPDATE_MAC_instructions.pdf)

### File Format Notes

- Images: **PNG** (same dimensions as originals)
- Videos: **WebM** (same codec/resolution as originals)
- Audio: **WAV** or **OGG** (matching the original format)
- Format or dimension mismatches won't corrupt the image but may crash or glitch the game at runtime

## Architecture

```
jjp_decryptor/
├── __main__.py      # Entry point (python -m jjp_decryptor)
├── app.py           # Application controller — wires GUI ↔ pipeline via thread-safe queue
├── gui.py           # Tkinter GUI with dark/light theme, tabs, progress tracking
├── pipeline.py      # StandaloneDecryptPipeline and StandaloneModPipeline
├── crypto.py        # Pure Python PRNG, XOR cipher, filler detection, CRC32 forgery
├── filelist.py      # fl.dat parser/generator and filesystem scanner
├── resources.py     # Embedded C sources (legacy dongle-based hooks, kept for reference)
├── config.py        # Constants (paths, timeouts, known games, phase names)
├── executor.py      # Platform-aware command executor (WSL/Docker/Native)
├── wsl.py           # Backward-compat wrapper (imports from executor.py)
└── updater.py       # Auto-update checker (GitHub releases API)
```

The app uses a **background thread + queue** pattern: the pipeline runs in a worker thread and posts `LogMsg`, `PhaseMsg`, `ProgressMsg`, and `DoneMsg` objects to a queue. The main thread polls the queue at 100ms intervals to update the GUI.

## How the Encryption Works

JJP games encrypt all assets (PNG, WebM, WAV, OGG, TTF, TXT) using a custom scheme:

1. **`fl.dat`** (the file list) is encrypted with the HASP dongle's hardware crypto. The decrypted content is CSV with one entry per line:
   ```
   /full/path/to/file.png,filler_size,crc32_encrypted,crc32_decrypted
   ```
   This tool bypasses `fl.dat` entirely by scanning the filesystem and auto-detecting filler sizes using magic byte signatures and text heuristics.

2. **Each asset file** is encrypted by:
   - Seeding a custom PRNG with the file's full absolute path (BKDR hash, multiplier=131)
   - The PRNG combines an LCG, xorshift64, and 128-bit counter to produce a 64-bit keystream
   - XOR-ing the entire file with the keystream in **little-endian** byte order
   - Prepending `filler_size` random bytes before the actual content

3. **Filler size detection** (dongle-free): The filler is random bytes prepended to the real content. Without `fl.dat`, the tool detects where the filler ends using:
   - Magic byte signatures for known binary formats (PNG, WebM, WAV, OGG, TTF, etc.)
   - A two-phase text heuristic for text files: non-printable density scoring to find the transition zone, then word-score refinement to pinpoint the exact content start
   - 100% accuracy across 26,000+ files from all four tested games

4. **Integrity checking** at boot: the game computes CRC32 of each encrypted file on disk (must match `n2`) and CRC32 of the decrypted content after filler removal (must match `n3`). Any mismatch triggers `FILE CHECK ERROR`.

### CRC32 Forgery

Rather than modifying `fl.dat` (which would require the dongle's hardware crypto), the tool uses **CRC32 forgery** to make modified files produce the exact same checksums as the originals:

- **N3 forgery**: 4 bytes are appended to the decrypted content so its CRC32 equals the original `n3`
- **N2 forgery**: 4 bytes within the random filler are adjusted so the encrypted file's CRC32 equals the original `n2`

This means `fl.dat` is restored byte-for-byte from its original encrypted form — no dongle needed at any point.

## Pipeline Details

### End-to-End Flow

```mermaid
flowchart LR
    subgraph Your PC
        ISO1[Clonezilla ISO] --> DEC[Decrypt Pipeline]
        DEC --> FILES[Decrypted Assets]
        FILES --> EDIT[Edit files]
        EDIT --> MOD[Modify Pipeline]
        ISO2[Clonezilla ISO] --> MOD
        MOD --> MISO[Modified ISO]
    end
    MISO --> FLASH[Flash to USB]
    FLASH --> MACHINE[Pinball Machine]
```

### Decrypt Pipeline

```mermaid
flowchart TD
    A[Start] --> B[Extract]
    B --> C[Mount]
    C --> D[Decrypt]
    D --> E[Cleanup]
    E --> F[Done]

    B -.- B1["ISO → gunzip → partclone.restore → raw ext4"]
    C -.- C1["Loop-mount ext4 image"]
    D -.- D1["Deploy crypto.py\nScan filesystem, detect filler sizes\nXOR-decrypt each file directly to output folder\nGenerate fl_decrypted.dat and .checksums.md5"]
    E -.- E1["Unmount ext4 and ISO\nDelete raw image from /tmp"]
```

| Phase | What Happens |
|-------|-------------|
| **Extract** | Decompresses Clonezilla ISO's partclone image to raw ext4 |
| **Mount** | Loop-mounts the ext4 image read-only (via WSL2, Docker, or native depending on platform) |
| **Decrypt** | Deploys `crypto.py` and `filelist.py`, scans the encrypted filesystem, auto-detects filler sizes, XOR-decrypts every file directly to the output folder, and generates `fl_decrypted.dat` + `.checksums.md5` |
| **Cleanup** | Unmounts ext4 and ISO images, deletes the raw image from `/tmp` |

### Modify Pipeline

```mermaid
flowchart TD
    A[Start] --> B[Scan]
    B --> C[Extract]
    C --> D[Mount]
    D --> E[Encrypt]
    E --> F[Convert]
    F --> G[Build ISO]
    G --> H[Cleanup]
    H --> I[Done]

    B -.- B1["Compare output folder against .checksums.md5\nto find modified files"]
    C -.- C1["Fresh extraction from original ISO"]
    E -.- E1["For each changed file:\n1. Pad with filler + CRC32-forged suffix\n2. XOR-encrypt with same keystream\n3. Forge filler bytes for encrypted CRC match\n4. Verify both CRC32s\n5. Restore original fl.dat unmodified"]
    F -.- F1["Unmount → e2fsck → partclone.ext4 -c\npigz --fast -b 1024 --rsyncable\nSplit into 1GB chunks"]
    G -.- G1["xorriso splices new partition chunks\ninto original ISO preserving boot records"]
```

| Phase | What Happens |
|-------|-------------|
| **Scan** | Compares output folder against `.checksums.md5` baseline to identify modified files |
| **Extract** | Extracts a **fresh** ext4 image from the original ISO (never reuses previous images) |
| **Mount** | Loop-mounts the fresh ext4 image read-write |
| **Encrypt** | For each changed file: reads replacement content, encrypts with pure Python crypto, forges both CRC32 checksums, writes encrypted file back into the ext4 image. Restores original `fl.dat` unmodified |
| **Convert** | Unmounts ext4, runs `e2fsck -fy`, converts to partclone format with `pigz --fast -b 1024 --rsyncable`, splits into ~1GB chunks matching the original layout |
| **Build ISO** | Uses `xorriso` to splice the new partition chunks into the original ISO, preserving all boot records (MBR, El Torito, EFI, Syslinux) |
| **Cleanup** | Unmounts everything, removes temp files and raw images |

## Troubleshooting

### FILE CHECK ERROR on the machine
If the machine shows errors for ALL files after flashing:
- **Windows**: Ensure the ISO was written with Rufus in **ISO mode** (not DD mode)
- **macOS/Linux**: Ensure the ISO was written with balenaEtcher or `dd` (not a drag-and-drop file copy)
- Check that the compression flags match the original (`pigz --fast -b 1024 --rsyncable`)

### Stale mounts from a previous crash
The app detects and cleans up stale mounts automatically on startup. If you have issues, you can manually clean up:
```
wsl -u root -- bash -c "findmnt -rn -o TARGET | grep /mnt/jjp_ | sort -r | xargs -r umount -lf; rmdir /mnt/jjp_* 2>/dev/null"
```

### Mount fails with "bad superblock"
This can happen if partclone.restore produces a truncated image. The tool automatically detects and fixes this by reading the ext4 superblock and extending the image to full filesystem size. If it still fails, delete cached images and retry:
```
wsl -u root -- rm -f /tmp/jjp_raw_*.img
```

## Building the Installer

### Windows

Requires [Inno Setup 6](https://jrsoftware.org/isinfo.php).

```powershell
cd installer
powershell -NoProfile -ExecutionPolicy Bypass -File build.ps1
```

Output: `installer/Output/JJP_Asset_Decryptor_Setup_v<version>.exe`

### macOS

Requires Python 3.10+ with tkinter and PyInstaller.

```bash
bash installer/build_macos.sh
```

Output: `installer/Output/JJP_Asset_Decryptor_v<version>.dmg`

### Versioning

The version number lives in `jjp_decryptor/__init__.py` as `__version__`. To release a new version:

1. Bump `__version__` in `jjp_decryptor/__init__.py`
2. Build installers: `installer/build.ps1` (Windows) and/or `installer/build_macos.sh` (macOS)
3. Commit, tag `v<version>`, push
4. Create a GitHub release and attach the installer(s)

Users running older versions will see an update notification on their next launch.

## License

MIT License. See [LICENSE](LICENSE) for details.
