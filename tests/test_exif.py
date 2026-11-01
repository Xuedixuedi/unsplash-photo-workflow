from datetime import UTC, datetime

from tests.support import write_jpeg
from upw.adapters.exif import OriginalIndex, load_track, match_track


def test_jpeg_gps_offset_and_manifest(tmp_path) -> None:
    write_jpeg(tmp_path / "abc.jpg", lat=33.215, lon=103.917, when="2026:10:31 10:00:00")
    (tmp_path / "manifest.csv").write_text("photo_id,file\ncustom,abc.jpg\n", encoding="utf-8")
    index = OriginalIndex(tmp_path, timezone_name="Asia/Shanghai", offset_seconds=30)
    record = index.by_photo_id["custom"]
    assert record.captured_at == "2026-10-31T02:00:30Z"
    assert record.location is not None
    assert record.location.latitude is not None
    assert abs(record.location.latitude - 33.215) < 0.01
    assert index.image_path("custom") is not None


def test_gpx_timeline_and_match(tmp_path) -> None:
    (tmp_path / "track.gpx").write_text(
        """<gpx><trk><trkseg>
        <trkpt lat="33.1" lon="103.8"><time>2026-10-31T02:00:00Z</time></trkpt>
        <trkpt lat="33.2" lon="103.9"><time>2026-10-31T02:05:00Z</time></trkpt>
        </trkseg></trk></gpx>""",
        encoding="utf-8",
    )
    points = load_track(tmp_path / "track.gpx")
    assert len(points) == 2
    matched = match_track("2026-10-31T02:04:30Z", points, max_seconds=180)
    assert matched is not None and abs(matched.latitude - 33.2) < 0.001
    assert match_track("2026-10-31T05:00:00Z", points, max_seconds=60) is None
    (tmp_path / "timeline.json").write_text(
        '{"locations":[{"latitudeE7":331000000,"longitudeE7":1038000000,"timestampMs":"1761876000000"}]}',
        encoding="utf-8",
    )
    timeline = load_track(tmp_path / "timeline.json")
    assert len(timeline) == 1
    assert abs(timeline[0].latitude - 33.1) < 0.001
    assert timeline[0].captured_at == datetime.fromtimestamp(1761876000, tz=UTC)
    simple = tmp_path / "simple.json"
    simple.write_text(
        '[{"time":"2026-10-31T02:00:00Z","lat":1.5,"lon":2.5}]',
        encoding="utf-8",
    )
    assert len(load_track(simple)) == 1
    phone = tmp_path / "phone"
    phone.mkdir()
    write_jpeg(phone / "img.jpg", lat=1.25, lon=2.5, when="2026:10:31 02:00:00")
    phone_points = load_track(phone)
    assert len(phone_points) == 1
    assert abs(phone_points[0].latitude - 1.25) < 0.02
