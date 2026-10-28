# Toy Torrent

A small Python command-line client for learning how BitTorrent downloads files from peers. Inspired by the [CodeCrafters BitTorrent challenge](https://app.codecrafters.io/courses/bittorrent), it implements the steps from reading metadata and finding peers to requesting blocks and assembling a file.

## Features

- Decode bencoded strings, integers, lists, and dictionaries.
- Inspect torrent metadata, including tracker URL, file size, info hash, and piece hashes.
- Discover peers through a tracker and perform TCP peer handshakes.
- Retrieve magnet metadata using the `ut_metadata` extension.
- Download individual pieces or complete single-file torrents, requesting blocks up to 16 KiB and checking each piece's SHA-1 hash.

## Setup

Requires **Python 3.14+** and [uv](https://docs.astral.sh/uv/getting-started/installation/).

```sh
git clone https://github.com/nduonofitdavid/toy-torrent.git
cd toy-torrent
uv sync
```

## Usage

Run commands from the repository root. The included `sample.torrent` describes a 92,063-byte file split into three pieces.

```sh
# Decode bencoded data and inspect a torrent
./your_program.sh decode '5:water'
./your_program.sh info sample.torrent

# Find peers, then replace PEER_IP:PORT with a returned address
./your_program.sh peers sample.torrent
./your_program.sh handshake sample.torrent 'PEER_IP:PORT'

# Download piece 0 or the complete file
./your_program.sh download_piece -o piece-0.bin sample.torrent 0
./your_program.sh download -o sample.txt sample.torrent
```

Magnet links can also provide metadata and downloads without a local `.torrent` file:

```sh
# Example link used by the repository's scripts
MAGNET='magnet:?xt=urn:btih:ad42ce8109f54c99613ce38f9b4d87e70f24a165&dn=magnet1.gif&tr=http%3A%2F%2Fbittorrent-test-tracker.codecrafters.io%2Fannounce'

./your_program.sh magnet_parse "$MAGNET"
./your_program.sh magnet_handshake "$MAGNET"
./your_program.sh magnet_info "$MAGNET"
./your_program.sh magnet_download_piece -o magnet-piece-0.bin "$MAGNET" 0
./your_program.sh magnet_download -o magnet1.gif "$MAGNET"
```

Piece indexes start at **0**. All download commands require `-o OUTPUT`. Choose a fresh output path: downloaded pieces are appended to existing files. Network commands depend on a reachable tracker and available peers.

## Source layout

- `app/main.py` — command dispatch and download orchestration.
- `app/decoder.py`, `app/encoder.py` — bencoding, metadata encoding, and info hashes.
- `app/utils.py` — tracker requests, peer communication, magnet metadata, and piece downloads.
- `app/aliases.py` — command types, protocol message IDs, and constants.
- `your_program.sh` — launcher; `pyproject.toml` and `uv.lock` define dependencies.
- `tests/` — manual shell examples. Run them from the repository root, for example `sh tests/test_bstring.sh`.

## Limitations

This is an educational implementation with simplifying assumptions about peer behavior and message order.

- Supports single-file torrents, HTTP(S) trackers, and compact IPv4 peer lists. Multi-file torrents, UDP trackers, DHT, and seeding are not implemented.
- Magnet commands require a tracker URL and a hexadecimal `btih` info hash; metadata is assumed to fit in one metadata piece.
- Downloads are sequential, opening a new connection for each piece. Parallel downloads, reliable recovery from failed pieces, and resume support remain future improvements.
