from __future__ import annotations

import textwrap
from pathlib import Path

from ingestion.parse_gpx import parse_gpx

GPX = textwrap.dedent(
    """\
    <?xml version="1.0" encoding="UTF-8"?>
    <gpx version="1.1" creator="test"
         xmlns="http://www.topografix.com/GPX/1/1"
         xmlns:gpxtpx="http://www.garmin.com/xmlschemas/TrackPointExtension/v1">
      <trk>
        <name>Course test</name>
        <type>running</type>
        <trkseg>
          <trkpt lat="48.8000" lon="2.3000"><ele>35</ele><time>2026-06-02T08:00:00Z</time>
            <extensions><gpxtpx:TrackPointExtension><gpxtpx:hr>120</gpxtpx:hr>
            <gpxtpx:cad>85</gpxtpx:cad></gpxtpx:TrackPointExtension></extensions></trkpt>
          <trkpt lat="48.8010" lon="2.3010"><ele>40</ele><time>2026-06-02T08:00:30Z</time>
            <extensions><gpxtpx:TrackPointExtension><gpxtpx:hr>140</gpxtpx:hr>
            </gpxtpx:TrackPointExtension></extensions></trkpt>
          <trkpt lat="48.8020" lon="2.3020"><ele>38</ele><time>2026-06-02T08:01:00Z</time>
            <extensions><gpxtpx:TrackPointExtension><gpxtpx:hr>150</gpxtpx:hr>
            </gpxtpx:TrackPointExtension></extensions></trkpt>
        </trkseg>
      </trk>
    </gpx>
    """
)


def test_parse_gpx_basic(tmp_path: Path):
    f = tmp_path / "course.gpx"
    f.write_text(GPX, encoding="utf-8")

    norm = parse_gpx(f)

    assert norm["sport"] == "course"
    assert norm["source_format"] == "gpx"
    assert norm["source_file"] == "course.gpx"
    assert norm["duree_s"] == 60
    assert str(norm["date"]) == "2026-06-02"
    assert len(norm["points"]) == 3
    assert norm["hr_moy"] == round((120 + 140 + 150) / 3)
    assert norm["hr_max"] == 150
    # distance cumulee inferee depuis lat/lon
    assert norm["points"][-1]["distance_cum_m"] > 200
    assert norm["distance_m"] > 200
    # d+ = 5 (35->40), la descente 40->38 ne compte pas
    assert abs(norm["d_plus_m"] - 5) < 1e-6
    assert norm["points"][0]["cadence"] == 85


def test_parse_gpx_points_have_speed(tmp_path: Path):
    f = tmp_path / "c.gpx"
    f.write_text(GPX, encoding="utf-8")
    norm = parse_gpx(f)
    speeds = [p["vitesse"] for p in norm["points"] if p["vitesse"] is not None]
    assert speeds and all(s >= 0 for s in speeds)
