# podfetch

A CLI tool to download and archive podcast episodes from RSS feeds.

## Usage

Download all episodes:
```bash
podfetch <rss-url> ~/podcasts/my-show
```

Dry-run to see what would be downloaded:
```bash
podfetch <rss-url> ~/podcasts/my-show --dry-run
```

Download the most recent 5 episodes:
```bash
podfetch <rss-url> ~/podcasts/my-show --limit 5 --offset 0
```

Download in batches of 20:
```bash
podfetch <rss-url> ~/podcasts/my-show --limit 20
```

## Features

- **Resumable downloads** — partial downloads resume via HTTP `Range` headers on the next run
- **Progress bars** — per-episode: MB, percentage, speed, ETA
- **State tracking** — `archive_state.json` in the output directory keyed by episode GUID
- **Graceful Ctrl+C** — saves the partial file and state before exiting
- **Dry-run mode** — preview episodes with `[new]` / `[partial]` / `[done]` markers
- **Pagination** — use `--offset` and `--limit` together to work backwards through episodes
- **Batch downloads** — limit how many episodes to download per run

## Tests

```bash
uv run pytest tests/ -v
```

28 tests, all passing.

## Smoke Test

Tested against `https://feeds.libsyn.com/561260/rss` (69 episodes). Downloaded 2 episodes successfully, re-ran dry-run and confirmed they showed `[done]`.
