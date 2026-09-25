"""Offline fixture world used by `run.py selftest` and `run.py demo`.

A local HTTP server impersonates the kinds of endpoints the engine meets in the
wild: a council agenda index, linked documents, a robots-disallowed packet
path, an RSS feed, a Socrata dataset and a Legistar API. The full pipeline,
including robots refusal -> records request and silent-edit detection, can be
proven with zero network access.

All fixture content is SYNTHETIC and labeled as such in every jurisdiction name.
"""
from __future__ import annotations

import datetime as dt
import json
import threading
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

AGENDA_V1 = """<html><head><title>Agenda Item 22-91 - Council Meeting</title></head><body>
<h1>Agenda Item 22-91: Street Resurfacing Services</h1>
<p>Staff recommends approval of a no-bid contract with Lakeshore Paving LLC in the amount of $4,850,000.</p>
<p>Contractor selection pending competitive bid.</p>
<p>Item 22-92: Zoning variance request for 1847 W 18th St from R-3 to allow mixed commercial use.</p>
<p>The Council will convene in executive session to discuss pending litigation.</p>
</body></html>"""

AGENDA_V2 = AGENDA_V1.replace("<p>Contractor selection pending competitive bid.</p>\n", "")

INDEX = """<html><head><title>City Council - Minutes and Agendas</title></head><body>
<h1>City Council Minutes &amp; Agendas</h1>
<ul>
 <li><a href="/docs/agenda-item-2291.html">Agenda Item 22-91 (Sept 22)</a></li>
 <li><a href="/docs/staff-report-annexation.txt">Staff report: Annexation Petition 2026-04</a></li>
 <li><a href="/private/packet-2026-09-22.pdf">Full agenda packet (PDF)</a></li>
 <li><a href="/about">About the City</a></li>
</ul></body></html>"""

STAFF_REPORT = """STAFF REPORT - Annexation Petition No. 2026-04
The applicant requests annexation of 612 acres and a concurrent zone change to Heavy Industrial
to accommodate a proposed data center campus. Water allocation for cooling is estimated at
1.2 million gallons per day. A tax increment financing district is proposed for the site.
"""

ROBOTS = "User-agent: *\nDisallow: /private/\n"

RSS_ITEMS = [
    ("Pilsen residents protest displacement as rents climb",
     "Neighbors in Pilsen voiced anger and concern over evictions and rent hikes at a packed meeting."),
    ("Pilsen tenants file lawsuit over eviction notices",
     "A lawsuit filed Tuesday alleges illegal evictions in Pilsen. Organizers fear more displacement."),
    ("Council delays vote on Pilsen rezoning",
     "The vote on the Pilsen rezoning was delayed after opposition from residents. Critics cite secrecy."),
    ("New library branch opens in Logan Square",
     "Residents welcomed the new branch in Logan Square, praising the investment in the community."),
]


def months_back(n: int) -> list[str]:
    """n complete months followed by the current (partial) month, as YYYY-MM."""
    first = dt.date.today().replace(day=1)
    out = []
    for i in range(n, -1, -1):
        y, m = first.year, first.month - i
        while m <= 0:
            m += 12
            y -= 1
        out.append(f"{y:04d}-{m:02d}")
    return out


def _rss() -> str:
    items = "".join(
        f"<item><title>{t}</title><link>http://fixture.local/news/{i}</link>"
        f"<description>{d}</description><pubDate>Tue, 22 Sep 2026 12:00:00 GMT</pubDate></item>"
        for i, (t, d) in enumerate(RSS_ITEMS))
    return f'<?xml version="1.0"?><rss version="2.0"><channel><title>Fixture News</title>{items}</channel></rss>'


PERMIT_SERIES = {"31": [12, 15, 22, 4], "8": [10, 9, 11, 2], "24": [5, 6, 6, 1], "1": [100, 98, 104, 20]}


def _permit_rows() -> list[dict]:
    m = months_back(3)
    return [
        {":id": "row-aa11", "issue_date": f"{m[2]}-14T00:00:00.000",
         "permit_type": "PERMIT - NEW CONSTRUCTION",
         "work_description": "ERECT 4-STORY MIXED USE BUILDING PER ZONING VARIANCE APPROVED BY ZBA",
         "community_area": "31", "latitude": "41.8579", "longitude": "-87.6716"},
        {":id": "row-bb22", "issue_date": f"{m[2]}-20T00:00:00.000",
         "permit_type": "PERMIT - RENOVATION/ALTERATION",
         "work_description": "INTERIOR REMODEL OF KITCHEN AND BATH",
         "community_area": "8", "latitude": "41.8990", "longitude": "-87.6320"},
        {":id": "row-cc33", "issue_date": f"{m[1]}-03T00:00:00.000",
         "permit_type": "PERMIT - WRECKING/DEMOLITION",
         "work_description": "EMERGENCY PROCUREMENT DEMOLITION OF CITY-OWNED STRUCTURE",
         "community_area": "24", "latitude": "41.9022", "longitude": "-87.6790"},
    ]


def _permits(params: dict) -> list[dict]:
    if "$group" in params:
        m = months_back(3)
        return [{"month": f"{m[i]}-01T00:00:00.000", "community_area": area, "n": str(v)}
                for area, vals in PERMIT_SERIES.items() for i, v in enumerate(vals)]
    return _permit_rows()


def _matters() -> list[dict]:
    return [
        {"MatterId": 6291002, "MatterGuid": "FIX-0001", "MatterFile": "CB26-0917",
         "MatterName": "Sole-source agreement for body-worn camera storage",
         "MatterTitle": "A bill approving a sole source contract with Axon for evidence storage.",
         "MatterTypeName": "Bill", "MatterStatusName": "Referred", "MatterBodyName": "Safety Committee",
         "MatterIntroDate": "2026-09-14T00:00:00"},
        {"MatterId": 6291003, "MatterGuid": "FIX-0002", "MatterFile": "CR26-0450",
         "MatterName": "Proclamation honoring library volunteers",
         "MatterTitle": "A proclamation honoring library volunteers.",
         "MatterTypeName": "Proclamation", "MatterStatusName": "Adopted", "MatterBodyName": "City Council",
         "MatterIntroDate": "2026-09-14T00:00:00"},
    ]


def _elms(params: dict) -> dict:
    rows = [
        {"matterId": "FIX-ELMS-0001", "recordNumber": "O2026-0031001", "type": "Ordinance",
         "title": "Emergency contract with Midwest Towing Inc. for city vehicle impound services",
         "shortTitle": "Contract(s) - Emergency", "matterCategory": "CONTRACTS | Emergency",
         "status": "4-In Committee", "subStatus": "Referred", "controllingBody": "Committee on Finance",
         "filingSponsor": "Demo Sponsor", "keyLegislation": "YES", "economicDisclosure": "YES",
         "introductionDate": "2026-09-22T15:00:00+00:00"},
    ]
    return {"data": rows if int(params.get("skip", 0)) == 0 else [], "meta": {"count": len(rows)}}


class FixtureWorld:
    """Context manager: starts the fixture server; `mutate()` makes the silent edit."""

    def __init__(self):
        self.agenda = AGENDA_V1
        world = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *a):  # keep test output clean
                pass

            def do_GET(self):
                parts = urllib.parse.urlsplit(self.path)
                params = dict(urllib.parse.parse_qsl(parts.query))
                routes = {
                    "/robots.txt": ("text/plain", ROBOTS),
                    "/agendas": ("text/html; charset=utf-8", INDEX),
                    "/docs/agenda-item-2291.html": ("text/html; charset=utf-8", world.agenda),
                    "/docs/staff-report-annexation.txt": ("text/plain; charset=utf-8", STAFF_REPORT),
                    "/feed.xml": ("application/rss+xml", _rss()),
                    "/resource/permits.json": ("application/json", json.dumps(_permits(params))),
                    "/legistar/matters": ("application/json", json.dumps(_matters())),
                    "/elms/matter": ("application/json", json.dumps(_elms(params))),
                }
                if parts.path.startswith("/private/"):
                    # Only reached if a client ignores robots.txt — the engine never should.
                    world.private_hits += 1
                if parts.path not in routes:
                    self.send_response(404)
                    self.end_headers()
                    return
                ctype, body = routes[parts.path]
                data = body.encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Type", ctype)
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)

        self.private_hits = 0
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.base = f"http://127.0.0.1:{self.server.server_address[1]}"
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)

    def __enter__(self):
        self.thread.start()
        return self

    def __exit__(self, *exc):
        self.server.shutdown()
        self.server.server_close()

    def mutate(self):
        """Publish the silently edited agenda (removes the competitive-bid line)."""
        self.agenda = AGENDA_V2

    def config(self, base_cfg: dict) -> dict:
        return demo_config(base_cfg, self.base)


def demo_config(base_cfg: dict, b: str = "http://fixture.local") -> dict:
    """A config pointing two SYNTHETIC jurisdictions at the fixture server."""
    cfg = {k: v for k, v in base_cfg.items() if k != "jurisdictions"}
    cfg["identity"] = {**base_cfg["identity"], "delay_seconds_per_host": 0, "timeout_seconds": 10}
    cfg["jurisdictions"] = {
        "demo_chicago": {
            "label": "DEMO · Chicago (synthetic fixtures)", "state": "IL",
            "agency": "Demo City of Chicago", "custodian": "FOIA Officer, Demo City Clerk",
            "center": [41.8781, -87.6298],
            "sources": [
                {"name": "council_agendas", "method": "html", "url": f"{b}/agendas", "refetch_hours": 0},
                {"name": "building_permits", "method": "api", "api": "socrata",
                 "url": f"{b}/resource/permits.json", "date_field": "issue_date",
                 "group_field": "community_area", "group_label": "Community Area",
                 "text_fields": ["work_description", "permit_type"], "title_field": "permit_type",
                 "lat_field": "latitude", "lon_field": "longitude", "lookback_days": 150,
                 "trend": {"series": "permits_per_month", "min_slope": 3.0, "min_points": 3}},
                {"name": "neighborhood_news", "method": "rss", "url": f"{b}/feed.xml", "sentiment": True},
                {"name": "city_council_elms", "method": "elms", "url": f"{b}/elms", "lookback_days": 14},
            ],
        },
        "demo_denver": {
            "label": "DEMO · Denver (synthetic fixtures)", "state": "CO",
            "agency": "Demo City and County of Denver", "custodian": "Records Custodian, Demo Clerk",
            "center": [39.7392, -104.9903],
            "sources": [
                {"name": "council_matters", "method": "legistar", "client": "demo",
                 "url": f"{b}/legistar/matters", "lookback_days": 30},
                {"name": "packet_portal", "method": "pra_only", "url": f"{b}/private/packets",
                 "records_description": "All council agenda packets and minutes on the demo packet portal"},
            ],
        },
    }
    cfg["watchlist"] = {**base_cfg["watchlist"],
                        "sentiment_topics": {"demo_chicago": ["Pilsen", "Logan Square"]}}
    return cfg
