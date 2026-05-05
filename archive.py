import argparse
import json
import re
import signal
import sys
import time
import xml.etree.ElementTree as ET
from pathlib import Path
from urllib.parse import urlparse

import requests

CHUNK_SIZE = 1024 * 1024  # 1 MB
STATE_FILE = "archive_state.json"
DEFAULT_USER_AGENT = "Mozilla/5.0 (compatible; PodcastArchiver/1.0)"
_shutdown = False


def _handle_sigint(sig, frame):
    global _shutdown
    _shutdown = True
    print("\nInterrupted. Finishing current chunk...", file=sys.stderr)


def sanitize_filename(title: str) -> str:
    return re.sub(r'[/\\:*?"<>|]', "", title).strip()


def episode_filename(number: int, title: str, url: str) -> str:
    path = urlparse(url).path
    ext = Path(path).suffix.lstrip(".") or "mp3"
    clean = sanitize_filename(title)
    return f"{number:04d} - {clean}.{ext}"


def load_state(output_dir: Path) -> dict:
    state_path = output_dir / STATE_FILE
    if not state_path.exists():
        return {}
    return json.loads(state_path.read_text())


def save_state(output_dir: Path, state: dict) -> None:
    (output_dir / STATE_FILE).write_text(json.dumps(state, indent=2))


def fetch_feed(url: str, user_agent: str = DEFAULT_USER_AGENT) -> list[dict]:
    resp = requests.get(url, timeout=30, headers={"User-Agent": user_agent})
    resp.raise_for_status()
    root = ET.fromstring(resp.content)
    channel = root.find("channel")
    if channel is None:
        raise ValueError(f"No <channel> element found in feed: {url}")
    items = channel.findall("item")
    episodes = []
    for item in reversed(items):  # RSS is newest-first; reverse for chronological order
        guid = item.findtext("guid", "").strip()
        title = item.findtext("title", "").strip()
        enclosure = item.find("enclosure")
        if enclosure is None or not guid:
            print(f"Warning: skipping episode item without enclosure or GUID: {title!r}", file=sys.stderr)
            continue
        audio_url = enclosure.get("url", "")
        if not audio_url:
            continue
        episodes.append({"guid": guid, "title": title, "url": audio_url})
    return episodes



def download_episode(
    episode: dict, output_dir: Path, state: dict, on_progress=None, user_agent: str = DEFAULT_USER_AGENT,
) -> str:
    guid = episode["guid"]
    info = state.get(guid, {})

    if info.get("status") == "complete":
        return "skipped"

    filename = info.get("filename") or episode_filename(episode["number"], episode["title"], episode["url"])
    filepath = output_dir / filename

    offset = 0
    if info.get("status") == "partial" and filepath.exists():
        offset = filepath.stat().st_size

    state[guid] = {"status": "partial", "filename": filename, "bytes_downloaded": offset}

    headers = {"User-Agent": user_agent}
    if offset:
        headers["Range"] = f"bytes={offset}-"

    try:
        resp = requests.get(episode["url"], headers=headers, stream=True, timeout=30)
    except requests.RequestException:
        state[guid]["status"] = "pending"
        return "failed"

    if resp.status_code not in (200, 206):
        state[guid]["status"] = "pending"
        return "failed"

    total = int(resp.headers.get("Content-Length", 0)) + offset
    downloaded = offset
    start_time = time.monotonic()

    mode = "ab" if offset else "wb"
    try:
        with filepath.open(mode) as f:
            for chunk in resp.iter_content(CHUNK_SIZE):
                if _shutdown:
                    break
                f.write(chunk)
                downloaded += len(chunk)
                elapsed = max(time.monotonic() - start_time, 0.001)
                speed = (downloaded - offset) / elapsed
                eta = (total - downloaded) / speed if speed and total > downloaded else 0.0
                if on_progress:
                    on_progress(downloaded, total, speed, eta)
    except requests.RequestException:
        state[guid]["bytes_downloaded"] = filepath.stat().st_size if filepath.exists() else downloaded
        return "failed"

    if _shutdown:
        state[guid]["bytes_downloaded"] = filepath.stat().st_size
        return "failed"

    state[guid] = {"status": "complete", "filename": filename, "bytes_downloaded": downloaded}
    return "complete"


def format_progress(downloaded: int, total: int, speed: float, eta: float) -> str:
    pct = downloaded / total if total else 0.0
    bar_width = 20
    filled = int(bar_width * pct)
    bar = "█" * filled + "░" * (bar_width - filled)
    dl_mb = downloaded / 1024 / 1024
    total_mb = total / 1024 / 1024
    speed_mb = speed / 1024 / 1024
    eta_str = f"{int(eta)}s" if eta < 3600 else f"{eta / 3600:.1f}h"
    return f"  {dl_mb:.1f} MB / {total_mb:.1f} MB  |{bar}|  {pct * 100:.1f}%  {speed_mb:.1f} MB/s  ETA {eta_str}"


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Archive all episodes of a podcast from an RSS feed."
    )
    parser.add_argument("rss_url", help="URL of the podcast RSS feed")
    parser.add_argument("output_dir", help="Directory to save episodes")
    parser.add_argument("--dry-run", action="store_true", help="Print episodes without downloading")
    parser.add_argument("--latest", type=int, metavar="N", help="Download the N most recent episodes")
    parser.add_argument("--limit", type=int, metavar="N", help="Download at most N undownloaded episodes")
    parser.add_argument(
        "--offset", type=int, metavar="N",
        help="Number of most-recent episodes to skip before processing (use with --limit for pagination)",
    )
    parser.add_argument(
        "--user-agent", default=DEFAULT_USER_AGENT, metavar="UA",
        help="User-Agent header for HTTP requests",
    )
    args = parser.parse_args()

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    print("Fetching RSS feed...", file=sys.stderr)
    episodes = fetch_feed(args.rss_url, user_agent=args.user_agent)

    if not episodes:
        print("No episodes found in feed.", file=sys.stderr)
        sys.exit(1)

    for i, ep in enumerate(episodes, start=1):
        ep["number"] = i

    state = load_state(output_dir)

    if args.dry_run:
        display = episodes[-args.latest:] if args.latest else episodes
        for ep in display:
            info = state.get(ep["guid"], {})
            status = info.get("status", "pending")
            filename = info.get("filename") or episode_filename(ep["number"], ep["title"], ep["url"])
            marker = "[done]   " if status == "complete" else "[partial]" if status == "partial" else "[new]    "
            print(f"{marker} {filename}")
        return

    signal.signal(signal.SIGINT, _handle_sigint)

    candidates = episodes[-args.latest:] if args.latest else episodes

    all_pending = [ep for ep in candidates if state.get(ep["guid"], {}).get("status") != "complete"]
    already_done = len(candidates) - len(all_pending)

    if args.offset:
        all_pending = all_pending[args.offset:]

    pending = all_pending[: args.limit] if args.limit else all_pending

    downloaded = failed = 0
    total_count = len(episodes)

    def on_progress(dl: int, total: int, speed: float, eta: float) -> None:
        print(f"\r{format_progress(dl, total, speed, eta)}", end="", flush=True, file=sys.stderr)

    for ep in pending:
        if _shutdown:
            break

        filename = state.get(ep["guid"], {}).get("filename") or episode_filename(
            ep["number"], ep["title"], ep["url"]
        )
        print(f"\n[{ep['number']:04d}/{total_count:04d}] Downloading: {filename}", file=sys.stderr)

        result = download_episode(ep, output_dir, state, on_progress=on_progress, user_agent=args.user_agent)
        print(file=sys.stderr)
        save_state(output_dir, state)

        if result == "complete":
            downloaded += 1
        elif result == "failed":
            failed += 1

    remaining = len(all_pending) - len(pending)
    print(
        f"\nDone. {downloaded} downloaded, {already_done} skipped, {failed} failed. {remaining} remaining.",
        file=sys.stderr,
    )


if __name__ == "__main__":
    main()
