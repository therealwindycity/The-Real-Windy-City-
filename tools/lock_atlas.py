#!/usr/bin/env python3
"""Password-protect the Atlas dataset.

A static site cannot hide a file it serves: anyone who can reach
``atlas/data/atlas.json`` can read it. So protection here means **encryption at
rest** — the shipped files are ciphertext, and only the passphrase turns them
back into data. The browser decrypts in memory with the built-in WebCrypto API
(no libraries), and this tool does the same job from the command line.

    python3 tools/lock_atlas.py newpass                 # generate a passphrase
    python3 tools/lock_atlas.py lock --password '…'     # atlas/data → atlas/enc
    python3 tools/lock_atlas.py unlock --password '…'   # atlas/enc → atlas/data
    python3 tools/lock_atlas.py verify --password '…'   # decrypt + compare hashes

Crypto: PBKDF2-HMAC-SHA256 (600k iterations) → AES-256-GCM, fresh random nonce
per file, plaintext padded to 4 KiB blocks so blob sizes do not leak the shape of
the archive. The file-name table (which blob is which thread) lives *inside* the
encrypted head blob, so the ciphertext directory reveals nothing but sizes.

Requires: pip install cryptography
"""
from __future__ import annotations

import argparse
import base64
import getpass
import hashlib
import json
import os
import secrets
import shutil
import sys
from datetime import datetime, timezone

try:
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
    from cryptography.hazmat.primitives import hashes
except ImportError:  # pragma: no cover - guidance beats a traceback
    sys.exit("This tool needs the 'cryptography' package:\n"
             "    pip install cryptography   (add --break-system-packages on Debian/Ubuntu)")

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)

DEFAULT_SRC = os.path.join(ROOT, "atlas", "data")
DEFAULT_EXPORTS = os.path.join(ROOT, "atlas", "exports")
DEFAULT_OUT = os.path.join(ROOT, "atlas", "enc")
DEFAULT_CATALOG = os.path.join(ROOT, "data", "drive_catalog.json")

ITERATIONS = 600_000
PAD = 4096
MANIFEST_VERSION = 1
HEAD_BLOB = "blobs/head.bin"

# 256 short, unambiguous words → 8 words ≈ 64 bits of entropy before the KDF.
WORDS = """acorn amber anchor apple april arbor archer ashen aspen atlas autumn azure
badge bagel baker balm bamboo banjo barley basin beacon beaver beech beet begin
below bench birch bishop bison bitter blaze bloom boulder bowie bracken bramble
brass breeze brick bridge bright broom bubble bucket buffalo bugle bulb bundle
burrow butter button cabin cactus cadet camel candle canoe canyon carbon cargo
carrot castle cedar cello chalk chapel cherry chess chief chime cider cipher
circus citron clover cobalt cocoa comet compass copper coral corvid cosmos cotton
cougar crane crater crayon cricket crimson crow crystal cypress dahlia daisy damson
delta denim desert diesel digit dingo dipper dockyard dolphin domino donkey donut
dove dragon drift drizzle dune dusk eagle ebony echo eclipse ember emerald engine
envoy epic epoch equinox escape estate fable falcon fennel fern ferry fielder fig
finch fjord flare flint flock flute forest forge fossil fountain foxglove freckle
frost galaxy gander garden garlic garnet gazelle gecko geyser ginger glacier glade
glimmer globe gopher granite grape grove guitar gull gypsum hammer harbor harness
harvest hazel hearth heather heron hickory hillside hollow honey hopper horizon
husky indigo iris island ivory ivy jackal jade jaguar jasmine jasper jigsaw juniper
kaleidoscope kayak kestrel kettle keystone kindle kiosk kiwi koala larch lantern
lark lattice laurel lavender ledger lemon lentil levee lichen lilac lily linen
lobster locket locust lodge lotus lumber lupine lychee lyric magnet magnolia magpie
mahogany mallard mallow mango mantis maple marble marigold marrow meadow medley
mellow mercury mesa meteor midland millet mint mirror mistletoe mitten molar mongoose
monsoon moose moraine mosaic moss mulberry mustard nebula nectar needle nest nettle
nickel nimbus nocturne north oak oasis ochre olive onyx opal orbit orchard orchid
osprey otter ovals oxbow oyster paddle pagoda palette palm pantry papaya parcel
parsley pastel patio pebble pelican pepper petal pewter phoenix picket pigeon pillar
pilot pine pinnacle pioneer piston plateau plum pocket pollen ponderosa poplar poppy
prairie prism puffin pumice quail quartz quill quilt quince quiver rabbit radish
rafter raven redwood reef relay relic reverie rhubarb ribbon ridge rifle ripple
river robin rowan rudder rustic saffron sage saguaro salmon sander sandpiper sardine
satchel savanna scallop sconce seabird sedge sequoia shale shimmer shingle sierra
silver siskin sketch slate sled sloop snowdrop socket solstice sorrel sparrow spindle
spruce squash squill stable stallion stanza starling steeple stencil sterling stork
storm strand summit sundial swallow swan sycamore taffy talon tamarind tangerine
tapir teak teal telescope tempest tern thicket thimble thistle thunder thyme tidal
timber tinder toffee topaz torrent toucan trail trellis trillium triton trout tulip
tundra turbine turnip turtle twilight umber urchin valley vanilla vellum velvet
vervain vessel viaduct violet vireo vista vixen walnut walrus warbler wattle weaver
welcome wheat willow windmill winter wisteria wolverine wombat wren yarrow yew
yucca zebra zephyr zinc""".split()


def _password(args, *, confirm: bool = False) -> str:
    if args.password:
        pw = args.password
    else:
        pw = getpass.getpass("Passphrase: ")
        if confirm:
            again = getpass.getpass("Repeat: ")
            if pw != again:
                sys.exit("Passphrases did not match.")
    if len(pw) < 12:
        sys.exit("Refusing: use at least 12 characters (a generated passphrase is 8 words).")
    return pw


def _key(password: str, salt: bytes) -> bytes:
    kdf = PBKDF2HMAC(algorithm=hashes.SHA256(), length=32, salt=salt, iterations=ITERATIONS)
    return kdf.derive(password.encode("utf-8"))


def _encrypt(key: bytes, name: str, plain: bytes) -> bytes:
    real = len(plain)
    body = real.to_bytes(4, "big") + plain
    if len(body) % PAD:
        body += b"\x00" * (PAD - (len(body) % PAD))
    nonce = secrets.token_bytes(12)
    return nonce + AESGCM(key).encrypt(nonce, body, name.encode("utf-8"))


def _decrypt(key: bytes, name: str, blob: bytes) -> bytes:
    nonce, ct = blob[:12], blob[12:]
    body = AESGCM(key).decrypt(nonce, ct, name.encode("utf-8"))
    size = int.from_bytes(body[:4], "big")
    return body[4:4 + size]


def _collect(src: str, exports: str | None) -> list[tuple[str, str]]:
    """[(logical name, absolute path)] for everything worth protecting."""
    items: list[tuple[str, str]] = []
    bases = [(src, "")] + ([(exports, "exports/")] if exports else [])
    for base, prefix in bases:
        if not os.path.isdir(base):
            continue
        for dirpath, _dirs, files in os.walk(base):
            for fn in sorted(files):
                if fn.startswith("."):
                    continue
                full = os.path.join(dirpath, fn)
                rel = os.path.relpath(full, base).replace(os.sep, "/")
                items.append((prefix + rel, full))
    return items


def _stash(src: str, exports: str, stash: str) -> None:
    """Move the plaintext out of the web-served tree after a successful lock.

    A password on the page is worthless while `atlas/data/atlas.json` still sits
    next to it on disk — a static server would hand it to anyone who asks. So the
    plaintext goes to a directory outside the repository, where only `unlock`
    (or the next build) reaches it.
    """
    os.makedirs(stash, exist_ok=True)
    for base in (src, exports):
        if not os.path.isdir(base):
            continue
        dest = os.path.join(stash, os.path.basename(base))
        if os.path.isdir(dest):
            shutil.rmtree(dest)
        shutil.move(base, dest)
    with open(os.path.join(stash, "README.txt"), "w", encoding="utf-8") as fh:
        fh.write("Plaintext copies of the Atlas dataset, moved here by tools/lock_atlas.py\n"
                 "so that the repository (and anything served from it) holds ciphertext only.\n\n"
                 "  restore into the app:  python3 tools/lock_atlas.py unlock --password '…'\n"
                 "  re-lock after a rebuild: python3 tools/lock_atlas.py lock --password '…'\n")


def lock(src: str, exports: str | None, out: str, password: str, *, quiet: bool = False,
         stash: str | None = None) -> dict:
    items = _collect(src, exports)
    if not items:
        sys.exit(f"Nothing to lock — no files under {src} or {exports}. Run tools/build_atlas.py first.")
    salt = secrets.token_bytes(16)
    key = _key(password, salt)

    blobs_dir = os.path.join(out, "blobs")
    if os.path.isdir(out):
        shutil.rmtree(out)
    os.makedirs(blobs_dir, exist_ok=True)

    table: dict[str, str] = {}
    digests: dict[str, str] = {}
    export_rows: list[dict] = []
    total = 0
    for i, (name, path) in enumerate(items, start=1):
        plain = open(path, "rb").read()
        blob_name = f"b{i:05d}.bin"
        blob = _encrypt(key, name, plain)
        with open(os.path.join(blobs_dir, blob_name), "wb") as fh:
            fh.write(blob)
        table[name] = blob_name
        digests[name] = hashlib.sha256(plain).hexdigest()
        total += len(blob)
        if name.startswith("exports/"):
            export_rows.append({"name": name[len("exports/"):], "blob": blob_name, "cipher_bytes": len(blob)})

    head = {
        "version": MANIFEST_VERSION,
        "created": datetime.now(timezone.utc).isoformat(),
        "files": table,
        "sha256": digests,
        "exports": export_rows,
    }
    head_blob = _encrypt(key, "head", json.dumps(head, separators=(",", ":")).encode("utf-8"))
    os.makedirs(os.path.join(out, "blobs"), exist_ok=True)
    with open(os.path.join(out, HEAD_BLOB), "wb") as fh:
        fh.write(head_blob)

    manifest = {
        "version": MANIFEST_VERSION,
        "created": head["created"],
        "cipher": "AES-256-GCM",
        "kdf": {"algorithm": "PBKDF2-HMAC-SHA256", "iterations": ITERATIONS,
                "salt": base64.b64encode(salt).decode("ascii")},
        "head": HEAD_BLOB,
        "files": len(items),
        "plaintext_bytes": sum(os.path.getsize(p) for _n, p in items),
        "ciphertext_bytes": total + len(head_blob),
        "hint": "Passphrase required. Losing it means losing the data — the ciphertext cannot be recovered.",
    }
    with open(os.path.join(out, "manifest.json"), "w", encoding="utf-8") as fh:
        json.dump(manifest, fh, indent=2)

    if stash and exports:
        _stash(src, exports, stash)
        if not quiet:
            print(f"moved plaintext out of the repository → {stash}")

    if not quiet:
        print(f"locked {len(items)} files → {out}")
        print(f"  blobs        {len(items) + 1}")
        print(f"  plaintext    {manifest['plaintext_bytes'] / 1e6:.2f} MB")
        print(f"  ciphertext   {manifest['ciphertext_bytes'] / 1e6:.2f} MB")
        print(f"  kdf          {ITERATIONS:,} × PBKDF2-HMAC-SHA256, AES-256-GCM per file")
    return manifest


def seal(src: str, out: str, password: str, *, quiet: bool = False) -> dict:
    """Encrypt an arbitrary directory (raw Takeout archives, for instance).

    Raw exports are personal and hundreds of megabytes wide, so they cannot be
    committed in the clear — but losing them means losing the ability to rebuild.
    Sealing lets a single ciphertext directory under version control stand in for
    the originals on any machine:

        python3 tools/lock_atlas.py seal --src data/raw --enc sealed/raw
    """
    return lock(src, None, out, password, quiet=quiet)


def _read_head(enc: str, password: str) -> tuple[bytes, dict]:
    manifest = json.load(open(os.path.join(enc, "manifest.json"), encoding="utf-8"))
    salt = base64.b64decode(manifest["kdf"]["salt"])
    key = _key(password, salt)
    with open(os.path.join(enc, manifest["head"]), "rb") as fh:
        head = json.loads(_decrypt(key, "head", fh.read()).decode("utf-8"))
    return key, head


def unlock(enc: str, dest: str, password: str, *, exports_dest: str | None = None) -> int:
    key, head = _read_head(enc, password)
    n = 0
    for name, blob_name in head["files"].items():
        with open(os.path.join(enc, "blobs", blob_name), "rb") as fh:
            plain = _decrypt(key, name, fh.read())
        if name.startswith("exports/") and exports_dest:
            target = os.path.join(exports_dest, name[len("exports/"):])
        else:
            target = os.path.join(dest, name)
        os.makedirs(os.path.dirname(target), exist_ok=True)
        with open(target, "wb") as fh:
            fh.write(plain)
        n += 1
    print(f"unlocked {n} files → {dest}")
    return n


def verify(enc: str, password: str) -> bool:
    key, head = _read_head(enc, password)
    bad = 0
    for name, blob_name in head["files"].items():
        with open(os.path.join(enc, "blobs", blob_name), "rb") as fh:
            plain = _decrypt(key, name, fh.read())
        if hashlib.sha256(plain).hexdigest() != head["sha256"][name]:
            print(f"  MISMATCH {name}")
            bad += 1
    print(f"verified {len(head['files'])} files, {bad} mismatches")
    return bad == 0


def newpass(n: int = 8) -> str:
    words = list(dict.fromkeys(WORDS))  # de-dupe, keep order
    return "-".join(secrets.choice(words) for _ in range(n))


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("command", choices=["lock", "unlock", "verify", "newpass", "info", "seal"])
    ap.add_argument("--password", help="passphrase (omit to be prompted; nothing is written to disk)")
    ap.add_argument("--src", default=DEFAULT_SRC, help="plaintext dataset directory")
    ap.add_argument("--exports", default=DEFAULT_EXPORTS, help="handoff packets directory")
    ap.add_argument("--enc", default=DEFAULT_OUT, help="ciphertext directory")
    ap.add_argument("--dest", default=DEFAULT_SRC, help="where 'unlock' writes plaintext")
    ap.add_argument("--exports-dest", default=DEFAULT_EXPORTS, help="where 'unlock' writes the packets")
    ap.add_argument("--stash", default=os.path.join(os.path.dirname(ROOT), "atlas-plaintext"),
                    help="where 'lock' moves the plaintext afterwards (default: outside the repository)")
    ap.add_argument("--no-stash", action="store_true", help="leave the plaintext dataset in place")
    ap.add_argument("--words", type=int, default=8, help="words in a generated passphrase")
    args = ap.parse_args()

    if args.command == "newpass":
        for _ in range(3):
            print(newpass(args.words))
        return
    if args.command == "info":
        m = json.load(open(os.path.join(args.enc, "manifest.json"), encoding="utf-8"))
        print(json.dumps({k: v for k, v in m.items() if k != "hint"}, indent=2))
        return
    if args.command == "seal":
        pw = _password(args, confirm=True)
        seal(args.src, args.enc, pw)
    elif args.command == "lock":
        pw = _password(args, confirm=True)
        lock(args.src, args.exports, args.enc, pw,
             stash=None if args.no_stash else args.stash)
    elif args.command == "unlock":
        unlock(args.enc, args.dest, _password(args), exports_dest=args.exports_dest)
    elif args.command == "verify":
        sys.exit(0 if verify(args.enc, _password(args)) else 1)


if __name__ == "__main__":
    main()
