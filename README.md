# podfetch

> Download and archive podcast episodes from any RSS feed.

```
brew tap Kallbrig/podfetch
brew install podfetch
```

---

Podcasts disappear. Shows get pulled, feeds go dark, hosting lapses. podfetch lets you keep a local archive of any podcast you care about - resumable, scriptable, and hands-off.

## Install

**Homebrew (macOS/Linux)**
```bash
brew tap Kallbrig/podfetch
brew install podfetch
```

**From source (requires Python 3.12+)**
```bash
git clone https://github.com/Kallbrig/podfetch.git
cd podfetch
uv run python archive.py --help
```

## Usage

```bash
# Archive everything
podfetch <rss-url> ~/podcasts/my-show

# Preview what would be downloaded
podfetch <rss-url> ~/podcasts/my-show --dry-run

# Grab only the 5 most recent episodes
podfetch <rss-url> ~/podcasts/my-show --latest 5

# Download in batches of 20 (safe for large back-catalogues)
podfetch <rss-url> ~/podcasts/my-show --limit 20

# Paginate through a large back-catalogue (episodes 21-40)
podfetch <rss-url> ~/podcasts/my-show --limit 20 --offset 20

# Custom user-agent (useful if a CDN blocks default requests)
podfetch <rss-url> ~/podcasts/my-show --user-agent "MyArchiver/1.0"
```

## Features

- **Resumable** - interrupted downloads pick up where they left off via HTTP `Range` headers
- **Idempotent** - re-running never re-downloads completed episodes; state is tracked in `archive_state.json`
- **Progress bars** - per-episode: MB downloaded, percentage, speed, ETA
- **Graceful Ctrl+C** - partial file and state are saved cleanly on interrupt
- **Dry-run mode** - preview the full episode list with `[new]` / `[partial]` / `[done]` markers before committing
- **Latest N** - `--latest N` downloads only the N most recent episodes
- **Batch pagination** - `--limit` and `--offset` for working through large back-catalogues incrementally

## How it works

podfetch fetches the RSS feed, parses all `<item>` elements, and downloads the audio file from each `<enclosure>` tag. Episodes are named `0001 - Episode Title.mp3` (chronological order). A state file in the output directory tracks completed and partial downloads so runs are safe to interrupt and repeat.

## Options

| Flag | Description |
|------|-------------|
| `--dry-run` | Print episode list without downloading |
| `--latest N` | Download only the N most recent episodes |
| `--limit N` | Download at most N episodes per run |
| `--offset N` | Skip the first N pending episodes (use with `--limit` for pagination) |
| `--user-agent UA` | Override the HTTP User-Agent header |

## License

MIT
