import json
from unittest.mock import MagicMock, patch

import pytest
import requests as requests_lib

import archive as archive_module
from archive import (
    download_episode,
    episode_filename,
    fetch_feed,
    format_progress,
    load_state,
    main,
    sanitize_filename,
    save_state,
)

RSS_SAMPLE = b"""<?xml version="1.0"?>
<rss version="2.0">
  <channel>
    <title>Test Podcast</title>
    <item>
      <title>Episode 2 - Newer</title>
      <guid>guid-002</guid>
      <enclosure url="https://example.com/ep002.mp3" type="audio/mpeg" length="1000"/>
    </item>
    <item>
      <title>Episode 1 - Older</title>
      <guid>guid-001</guid>
      <enclosure url="https://example.com/ep001.mp3" type="audio/mpeg" length="500"/>
    </item>
  </channel>
</rss>"""

def test_fetch_feed_returns_chronological_order():
    mock_resp = MagicMock()
    mock_resp.content = RSS_SAMPLE
    mock_resp.raise_for_status = MagicMock()

    with patch("archive.requests.get", return_value=mock_resp) as mock_get:
        episodes = fetch_feed("https://example.com/feed.rss")

    mock_get.assert_called_once_with(
        "https://example.com/feed.rss", timeout=30,
        headers={"User-Agent": "Mozilla/5.0 (compatible; PodcastArchiver/1.0)"},
    )
    assert len(episodes) == 2
    assert episodes[0]["guid"] == "guid-001"
    assert episodes[0]["title"] == "Episode 1 - Older"
    assert episodes[0]["url"] == "https://example.com/ep001.mp3"
    assert episodes[1]["guid"] == "guid-002"

def test_fetch_feed_skips_items_without_enclosure():
    rss = b"""<?xml version="1.0"?>
<rss version="2.0">
  <channel>
    <item>
      <title>No audio here</title>
      <guid>guid-nope</guid>
    </item>
    <item>
      <title>Has audio</title>
      <guid>guid-yes</guid>
      <enclosure url="https://example.com/ep.mp3" type="audio/mpeg" length="100"/>
    </item>
  </channel>
</rss>"""
    mock_resp = MagicMock()
    mock_resp.content = rss
    mock_resp.raise_for_status = MagicMock()

    with patch("archive.requests.get", return_value=mock_resp):
        episodes = fetch_feed("https://example.com/feed.rss")

    assert len(episodes) == 1
    assert episodes[0]["guid"] == "guid-yes"

def test_fetch_feed_warns_on_skipped_items(capsys):
    rss = b"""<?xml version="1.0"?>
<rss version="2.0">
  <channel>
    <item>
      <title>No audio here</title>
      <guid>guid-nope</guid>
    </item>
    <item>
      <title>Has audio</title>
      <guid>guid-yes</guid>
      <enclosure url="https://example.com/ep.mp3" type="audio/mpeg" length="100"/>
    </item>
  </channel>
</rss>"""
    mock_resp = MagicMock()
    mock_resp.content = rss
    mock_resp.raise_for_status = MagicMock()

    with patch("archive.requests.get", return_value=mock_resp):
        fetch_feed("https://example.com/feed.rss")

    captured = capsys.readouterr()
    assert "Warning: skipping" in captured.err
    assert "No audio here" in captured.err

def test_fetch_feed_raises_on_missing_channel():
    rss = b"""<?xml version="1.0"?><rss version="2.0"></rss>"""
    mock_resp = MagicMock()
    mock_resp.content = rss
    mock_resp.raise_for_status = MagicMock()

    with patch("archive.requests.get", return_value=mock_resp), \
         pytest.raises(ValueError, match="No <channel> element"):
        fetch_feed("https://example.com/bad-feed.rss")

def test_sanitize_filename_strips_illegal_chars():
    assert sanitize_filename('Title: "Stuff" / More') == "Title Stuff  More"

def test_sanitize_filename_strips_whitespace():
    assert sanitize_filename("  hello  ") == "hello"

def test_sanitize_filename_all_illegal():
    assert sanitize_filename('/\\:*?"<>|') == ""

def test_episode_filename_basic():
    result = episode_filename(1, "My Episode", "https://example.com/ep.mp3")
    assert result == "0001 - My Episode.mp3"

def test_episode_filename_zero_padding():
    result = episode_filename(42, "Title", "https://example.com/ep.mp3")
    assert result == "0042 - Title.mp3"

def test_episode_filename_extracts_extension():
    result = episode_filename(1, "Title", "https://example.com/ep.m4a?token=abc")
    assert result == "0001 - Title.m4a"

def test_episode_filename_defaults_to_mp3():
    result = episode_filename(1, "Title", "https://example.com/ep")
    assert result == "0001 - Title.mp3"

def test_load_state_returns_empty_dict_when_missing(tmp_path):
    assert load_state(tmp_path) == {}

def test_load_state_reads_existing_file(tmp_path):
    data = {"guid-001": {"status": "complete", "filename": "0001 - Ep.mp3", "bytes_downloaded": 100}}
    (tmp_path / "archive_state.json").write_text(json.dumps(data))
    assert load_state(tmp_path) == data

def test_save_state_writes_json(tmp_path):
    data = {"guid-001": {"status": "complete", "filename": "0001 - Ep.mp3", "bytes_downloaded": 100}}
    save_state(tmp_path, data)
    written = json.loads((tmp_path / "archive_state.json").read_text())
    assert written == data

def test_save_and_load_roundtrip(tmp_path):
    data = {"guid-002": {"status": "partial", "filename": "0002 - Ep.mp3", "bytes_downloaded": 50}}
    save_state(tmp_path, data)
    assert load_state(tmp_path) == data

def test_format_progress_shows_percentage():
    line = format_progress(downloaded=50 * 1024 * 1024, total=100 * 1024 * 1024, speed=2 * 1024 * 1024, eta=25.0)
    assert "50.0%" in line

def test_format_progress_shows_speed():
    line = format_progress(downloaded=50 * 1024 * 1024, total=100 * 1024 * 1024, speed=2 * 1024 * 1024, eta=25.0)
    assert "2.0 MB/s" in line

def test_format_progress_handles_zero_total():
    line = format_progress(downloaded=0, total=0, speed=0.0, eta=0.0)
    assert "0.0%" in line

def _make_episode(guid="ep-001", number=1, title="Test Episode", url="https://example.com/ep001.mp3"):
    return {"guid": guid, "number": number, "title": title, "url": url}

def _mock_response(status=200, content_length="11", chunks=None):
    mock_resp = MagicMock()
    mock_resp.status_code = status
    mock_resp.headers = {"Content-Length": content_length}
    mock_resp.iter_content.return_value = chunks or [b"hello world"]
    return mock_resp

def test_download_episode_fresh(tmp_path):
    episode = _make_episode()
    state = {}

    with patch("archive.requests.get", return_value=_mock_response()):
        result = download_episode(episode, tmp_path, state)

    assert result == "complete"
    assert state["ep-001"]["status"] == "complete"
    assert (tmp_path / "0001 - Test Episode.mp3").read_bytes() == b"hello world"

def test_download_episode_skips_complete(tmp_path):
    episode = _make_episode()
    state = {"ep-001": {"status": "complete", "filename": "0001 - Test Episode.mp3", "bytes_downloaded": 11}}

    with patch("archive.requests.get") as mock_get:
        result = download_episode(episode, tmp_path, state)

    mock_get.assert_not_called()
    assert result == "skipped"

def test_download_episode_resumes_partial(tmp_path):
    episode = _make_episode()
    partial_file = tmp_path / "0001 - Test Episode.mp3"
    partial_file.write_bytes(b"hello ")

    state = {"ep-001": {"status": "partial", "filename": "0001 - Test Episode.mp3", "bytes_downloaded": 6}}

    captured = {}
    def mock_get(url, headers=None, **kwargs):
        captured["headers"] = headers
        return _mock_response(status=206, content_length="5", chunks=[b"world"])

    with patch("archive.requests.get", side_effect=mock_get):
        result = download_episode(episode, tmp_path, state)

    assert result == "complete"
    assert captured["headers"].get("Range") == "bytes=6-"
    assert partial_file.read_bytes() == b"hello world"

def test_download_episode_marks_pending_on_http_error(tmp_path):
    episode = _make_episode()
    state = {}

    with patch("archive.requests.get", return_value=_mock_response(status=404)):
        result = download_episode(episode, tmp_path, state)

    assert result == "failed"
    assert state["ep-001"]["status"] == "pending"

def test_download_episode_marks_pending_on_network_error(tmp_path):
    episode = _make_episode()
    state = {}

    with patch("archive.requests.get", side_effect=requests_lib.RequestException("timeout")):
        result = download_episode(episode, tmp_path, state)

    assert result == "failed"
    assert state["ep-001"]["status"] == "pending"

def test_download_episode_calls_on_progress(tmp_path):
    episode = _make_episode()
    state = {}
    progress_calls = []

    def capture_progress(dl, total, speed, eta):
        progress_calls.append((dl, total))

    with patch("archive.requests.get", return_value=_mock_response(chunks=[b"hello", b" world"])):
        result = download_episode(episode, tmp_path, state, on_progress=capture_progress)

    assert result == "complete"
    assert len(progress_calls) == 2
    assert progress_calls[-1][0] == 11  # total bytes downloaded

def test_download_episode_shutdown_leaves_partial(tmp_path):
    episode = _make_episode()
    state = {}

    def chunks_then_shutdown():
        yield b"hello "
        archive_module._shutdown = True
        yield b"world"

    mock_resp = _mock_response(chunks=None)
    mock_resp.iter_content.return_value = chunks_then_shutdown()

    try:
        with patch("archive.requests.get", return_value=mock_resp):
            result = download_episode(episode, tmp_path, state)
    finally:
        archive_module._shutdown = False  # always reset

    assert result == "failed"
    assert state["ep-001"]["status"] == "partial"
    assert (tmp_path / "0001 - Test Episode.mp3").read_bytes() == b"hello "

def test_download_episode_marks_partial_on_chunk_error(tmp_path):
    episode = _make_episode()
    state = {}

    mock_resp = _mock_response(chunks=None)
    def chunk_then_error():
        yield b"hello "
        raise requests_lib.exceptions.ChunkedEncodingError("Connection broken")
    mock_resp.iter_content.return_value = chunk_then_error()

    with patch("archive.requests.get", return_value=mock_resp):
        result = download_episode(episode, tmp_path, state)

    assert result == "failed"
    assert state["ep-001"]["status"] == "partial"
    assert (tmp_path / "0001 - Test Episode.mp3").read_bytes() == b"hello "

def test_sigint_sets_shutdown_flag():
    archive_module._shutdown = False
    archive_module._handle_sigint(None, None)
    assert archive_module._shutdown is True
    archive_module._shutdown = False  # reset for other tests

def test_dry_run_prints_episodes(tmp_path, capsys):
    mock_resp = MagicMock()
    mock_resp.content = RSS_SAMPLE
    mock_resp.raise_for_status = MagicMock()

    with patch("archive.requests.get", return_value=mock_resp), \
         patch("sys.argv", ["archive.py", "https://example.com/feed.rss", str(tmp_path), "--dry-run"]):
        main()

    captured = capsys.readouterr()
    assert "0001 - Episode 1 - Older.mp3" in captured.out
    assert "0002 - Episode 2 - Newer.mp3" in captured.out

def test_limit_flag_restricts_downloads(tmp_path):
    mock_feed_resp = MagicMock()
    mock_feed_resp.content = RSS_SAMPLE
    mock_feed_resp.raise_for_status = MagicMock()

    mock_dl_resp = MagicMock()
    mock_dl_resp.status_code = 200
    mock_dl_resp.headers = {"Content-Length": "5"}
    mock_dl_resp.iter_content.return_value = [b"audio"]

    def mock_get(url, **kwargs):
        if "feed" in url:
            return mock_feed_resp
        return mock_dl_resp

    with patch("archive.requests.get", side_effect=mock_get), \
         patch("sys.argv", ["archive.py", "https://example.com/feed.rss", str(tmp_path), "--limit", "1"]):
        main()

    downloaded = list(tmp_path.glob("*.mp3"))
    assert len(downloaded) == 1
    assert downloaded[0].name == "0001 - Episode 1 - Older.mp3"

def test_latest_flag_downloads_most_recent(tmp_path):
    mock_feed_resp = MagicMock()
    mock_feed_resp.content = RSS_SAMPLE
    mock_feed_resp.raise_for_status = MagicMock()

    mock_dl_resp = MagicMock()
    mock_dl_resp.status_code = 200
    mock_dl_resp.headers = {"Content-Length": "5"}
    mock_dl_resp.iter_content.return_value = [b"audio"]

    def mock_get(url, **kwargs):
        if "feed" in url:
            return mock_feed_resp
        return mock_dl_resp

    with patch("archive.requests.get", side_effect=mock_get), \
         patch("sys.argv", ["archive.py", "https://example.com/feed.rss", str(tmp_path), "--latest", "1"]):
        main()

    downloaded = list(tmp_path.glob("*.mp3"))
    assert len(downloaded) == 1
    assert downloaded[0].name == "0002 - Episode 2 - Newer.mp3"

def test_latest_flag_dry_run(tmp_path, capsys):
    mock_resp = MagicMock()
    mock_resp.content = RSS_SAMPLE
    mock_resp.raise_for_status = MagicMock()

    with patch("archive.requests.get", return_value=mock_resp), \
         patch("sys.argv", ["archive.py", "https://example.com/feed.rss", str(tmp_path), "--dry-run", "--latest", "1"]):
        main()

    captured = capsys.readouterr()
    assert "Episode 2 - Newer" in captured.out
    assert "Episode 1 - Older" not in captured.out
