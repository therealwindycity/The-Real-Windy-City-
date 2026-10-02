# Exact missing source recordings — Phase 6 unblock list

**Prepared:** 2026-10-02 · **Production environment:** Arena agent sandbox (`arena/01a0fe75-the-real-windy-city` branch of `therealwindycity/The-Real-Windy-City-`).

Every URL below is an **official City of Cheyenne publication** (City YouTube channel `@TheCityofCheyenne` or the City's Granicus system). None of these hosts is reachable from the production sandbox — TLS connections are closed by the network before any media byte is received (see [`connectivity_test_2026-10-02.log`](connectivity_test_2026-10-02.log)). No recordings were downloaded, and per the handoff rules no substitute footage was fabricated.

Machine-readable version: [`source_acquisition_manifest.json`](source_acquisition_manifest.json). One-command fetch kit: [`fetch_source_recordings.sh`](fetch_source_recordings.sh).

## Tier 1 — unblocks videos 1, 2, and the core of 10 (7 recordings)

| Meeting | Phase 1 windows | Official source | Direct Granicus MP4 (if verified) |
|---|---|---|---|
| 2026-05-11 City Council | L-01 (videos 1–2) | [YouTube vBJi7WeZ4C0](https://www.youtube.com/watch?v=vBJi7WeZ4C0) | [mp4](https://archive-video.granicus.com/cheyenne/cheyenne_0cf4c381-4e0b-11f1-9b4d-005056a89546.mp4) |
| 2026-06-15 Public Services Committee | L-02 (videos 1–2) | [YouTube e8pByyWP7RE](https://www.youtube.com/watch?v=e8pByyWP7RE) | — |
| 2026-06-22 City Council | W-01 (videos 1–2) | [YouTube RjSGlhh4q9s](https://www.youtube.com/watch?v=RjSGlhh4q9s) | — |
| 2026-07-06 Public Services Committee | W-02A, W-02B (videos 1–2) | [YouTube 7BwdzgyTD2Y](https://www.youtube.com/watch?v=7BwdzgyTD2Y) | — |
| 2026-08-28 Work Session | W-03, L-03 (videos 1–2) | [YouTube MG6Zaw7ATGA](https://www.youtube.com/watch?v=MG6Zaw7ATGA) | — |
| 2026-09-14 City Council | W-04, L-04 (videos 1–2) | [YouTube -zBOAUpDE3E](https://www.youtube.com/watch?v=-zBOAUpDE3E) | — |
| 2026-09-28 City Council | third reading (video 10) | [Granicus player clip 1137](https://cheyenne.granicus.com/player/clip/1137?view_id=5&redirect=true) | — |

These seven masters plus the Phase 1 cut manifest are everything needed to render videos 1 (`01_wolfe_positions.mp4`) and 2 (`02_laybourn_positions.mp4`) and to begin video 10.

## Tier 2 — legacy Miller-index / Phase 2 candidate meetings, videos 3, 11–13, 15–17 (27 recordings)

| Meeting | Official YouTube | Direct Granicus MP4 | P2 cues |
|---|---|---|---|
| 2026-01-12 city-council | [https://www.youtube.com/watch?v=Dfqmg--DVPE](https://www.youtube.com/watch?v=Dfqmg--DVPE) | [mp4](https://archive-video.granicus.com/cheyenne/cheyenne_fc57ddc3-d766-412e-9940-66459ea16b52.mp4) | 26 |
| 2026-01-14 work-session | [https://www.youtube.com/watch?v=tUTtHJp87Iw](https://www.youtube.com/watch?v=tUTtHJp87Iw) | — | 5 |
| 2026-01-20 public-services-committee | [https://www.youtube.com/watch?v=PkDZ5ELlJB4](https://www.youtube.com/watch?v=PkDZ5ELlJB4) | — | 5 |
| 2026-01-26 city-council | [https://www.youtube.com/watch?v=x6Veeticz3Q](https://www.youtube.com/watch?v=x6Veeticz3Q) | [mp4](https://archive-video.granicus.com/cheyenne/cheyenne_d5d0cd14-5d48-4a1d-a7f0-4a26b4d3dc0a.mp4) | 12 |
| 2026-02-03 finance-committee | [https://www.youtube.com/watch?v=h987qM-Q1os](https://www.youtube.com/watch?v=h987qM-Q1os) | — | 11 |
| 2026-02-09 city-council | [https://www.youtube.com/watch?v=OxeCnRnBLkU](https://www.youtube.com/watch?v=OxeCnRnBLkU) | [mp4](https://archive-video.granicus.com/cheyenne/cheyenne_d7fc0fd0-ac85-4676-8f5a-d7ff97fe05f6.mp4) | 51 |
| 2026-02-10 historic-preservation-board | [https://www.youtube.com/watch?v=HfCsT5yBHNs](https://www.youtube.com/watch?v=HfCsT5yBHNs) | — | 5 |
| 2026-03-09 city-council | [https://www.youtube.com/watch?v=19tQtLA8klo](https://www.youtube.com/watch?v=19tQtLA8klo) | [mp4](https://archive-video.granicus.com/cheyenne/cheyenne_b8b4e031-f557-48f6-9d95-f20827d12bd1.mp4) | 51 |
| 2026-03-10 historic-preservation-board | [https://www.youtube.com/watch?v=BwYXlrkLdKg](https://www.youtube.com/watch?v=BwYXlrkLdKg) | — | 5 |
| 2026-04-13 city-council | [https://www.youtube.com/watch?v=mPv73_3Clls](https://www.youtube.com/watch?v=mPv73_3Clls) | [mp4](https://archive-video.granicus.com/cheyenne/cheyenne_70e51848-551f-4877-a951-af3ba281ef8a.mp4) | 29 |
| 2026-04-20 public-services-committee | [https://www.youtube.com/watch?v=t17ft4xMMx4](https://www.youtube.com/watch?v=t17ft4xMMx4) | — | 78 |
| 2026-04-21 finance-committee | [https://www.youtube.com/watch?v=9pXvzw-Aut4](https://www.youtube.com/watch?v=9pXvzw-Aut4) | — | 94 |
| 2026-04-27 city-council | [https://www.youtube.com/watch?v=y9vnXtjZpR0](https://www.youtube.com/watch?v=y9vnXtjZpR0) | [mp4](https://archive-video.granicus.com/cheyenne/cheyenne_d2778ec1-4334-11f1-bb28-005056a89546.mp4) | 167 |
| 2026-05-05 finance-committee | [https://www.youtube.com/watch?v=F2sLPjc1rgY](https://www.youtube.com/watch?v=F2sLPjc1rgY) | — | 46 |
| 2026-05-26 city-council | [https://www.youtube.com/watch?v=bGt1XMfaTTw](https://www.youtube.com/watch?v=bGt1XMfaTTw) | [mp4](https://archive-video.granicus.com/cheyenne/cheyenne_cd1d772e-6046-40f0-ba52-164b7e9cc954.mp4) | 131 |
| 2026-06-01 public-services-committee | [https://www.youtube.com/watch?v=AEKufmR2Dc0](https://www.youtube.com/watch?v=AEKufmR2Dc0) | — | 37 |
| 2026-06-01 planning-commission | [https://www.youtube.com/watch?v=GcTnJFfrApg](https://www.youtube.com/watch?v=GcTnJFfrApg) | — | 37 |
| 2026-06-08 city-council | [https://www.youtube.com/watch?v=69FQxIr9sJA](https://www.youtube.com/watch?v=69FQxIr9sJA) | [mp4](https://archive-video.granicus.com/cheyenne/cheyenne_19b59235-f7f4-4274-9aca-c19a21c54031.mp4) | 171 |
| 2026-06-09 historic-preservation-board | [https://www.youtube.com/watch?v=wMjM4JjqDwU](https://www.youtube.com/watch?v=wMjM4JjqDwU) | — | 6 |
| 2026-07-06 planning-commission | [https://www.youtube.com/watch?v=encf6QzJoVM](https://www.youtube.com/watch?v=encf6QzJoVM) | — | 164 |
| 2026-07-07 finance-committee | [https://www.youtube.com/watch?v=cJlhV-SshmA](https://www.youtube.com/watch?v=cJlhV-SshmA) | — | 15 |
| 2026-07-13 city-council | [https://www.youtube.com/watch?v=6dPLuulCpbI](https://www.youtube.com/watch?v=6dPLuulCpbI) | [mp4](https://archive-video.granicus.com/cheyenne/cheyenne_4e312fa5-44f7-41ff-acf7-91e8a7511436.mp4) | 277 |
| 2026-07-27 city-council | [https://www.youtube.com/watch?v=S49bb5GfUro](https://www.youtube.com/watch?v=S49bb5GfUro) | [mp4](https://archive-video.granicus.com/cheyenne/cheyenne_526429bc-8a88-11f1-bb61-005056a89546.mp4) | 149 |
| 2026-08-04 finance-committee | [https://www.youtube.com/watch?v=NiKtP__UiSw](https://www.youtube.com/watch?v=NiKtP__UiSw) | — | 38 |
| 2026-08-10 city-council | [https://www.youtube.com/watch?v=7tVKl_N80dE](https://www.youtube.com/watch?v=7tVKl_N80dE) | [mp4](https://archive-video.granicus.com/cheyenne/cheyenne_a6f9f4cb-9596-11f1-bb61-005056a89546.mp4) | 33 |
| 2026-08-18 finance-committee | [https://www.youtube.com/watch?v=tZKp5g6g4EQ](https://www.youtube.com/watch?v=tZKp5g6g4EQ) | — | 30 |
| 2026-08-24 city-council | [https://www.youtube.com/watch?v=HX3_qn0rw_Q](https://www.youtube.com/watch?v=HX3_qn0rw_Q) | [mp4](https://archive-video.granicus.com/cheyenne/cheyenne_dfb5f093-463f-4fb7-97a5-bef9c54ca023.mp4) | 43 |

## Tier 3 — remaining corpus with Phase 3/4 candidate cues, videos 4–9, 14 (48 recordings)

| Meeting | Official YouTube | Direct Granicus MP4 | P2/P3/P4 cues |
|---|---|---|---|
| 2026 work-session | [https://www.youtube.com/watch?v=Hq26nwpjs2k](https://www.youtube.com/watch?v=Hq26nwpjs2k) | — | 0/9/0 |
| 2026-01-05 public-services-committee | [https://www.youtube.com/watch?v=ZBXk97c5xDg](https://www.youtube.com/watch?v=ZBXk97c5xDg) | — | 0/11/0 |
| 2026-01-05 planning-commission | [https://www.youtube.com/watch?v=DpyCQEaEWQ0](https://www.youtube.com/watch?v=DpyCQEaEWQ0) | — | 0/11/0 |
| 2026-01-06 finance-committee | [https://www.youtube.com/watch?v=zCfBIiT1iLw](https://www.youtube.com/watch?v=zCfBIiT1iLw) | — | 0/10/0 |
| 2026-01-15 work-session | [https://www.youtube.com/watch?v=Ro4BGPNnMMM](https://www.youtube.com/watch?v=Ro4BGPNnMMM) | — | 0/3/2 |
| 2026-01-15 board-of-adjustment | [https://www.youtube.com/watch?v=zAHof-zK-kg](https://www.youtube.com/watch?v=zAHof-zK-kg) | — | 0/3/2 |
| 2026-01-21 finance-committee | [https://www.youtube.com/watch?v=Jieyg3nuDhM](https://www.youtube.com/watch?v=Jieyg3nuDhM) | — | 0/18/0 |
| 2026-02-02 public-services-committee | [https://www.youtube.com/watch?v=pO5K8gfvy0g](https://www.youtube.com/watch?v=pO5K8gfvy0g) | — | 0/39/0 |
| 2026-02-02 planning-commission | [https://www.youtube.com/watch?v=cfntL7Dif4o](https://www.youtube.com/watch?v=cfntL7Dif4o) | — | 0/39/0 |
| 2026-02-17 public-services-committee | [https://www.youtube.com/watch?v=1maylWhrY2Q](https://www.youtube.com/watch?v=1maylWhrY2Q) | — | 0/22/2 |
| 2026-02-17 planning-commission | [https://www.youtube.com/watch?v=kVMKxgaCPSQ](https://www.youtube.com/watch?v=kVMKxgaCPSQ) | — | 0/22/2 |
| 2026-02-18 finance-committee | [https://www.youtube.com/watch?v=Mb5CLvC5XMg](https://www.youtube.com/watch?v=Mb5CLvC5XMg) | — | 0/31/0 |
| 2026-02-19 board-of-adjustment | [https://www.youtube.com/watch?v=YZp8nOWtFsk](https://www.youtube.com/watch?v=YZp8nOWtFsk) | — | 0/2/0 |
| 2026-02-23 city-council | [https://www.youtube.com/watch?v=rgnKyKmx3JU](https://www.youtube.com/watch?v=rgnKyKmx3JU) | [mp4](https://archive-video.granicus.com/cheyenne/cheyenne_443994e8-08e0-4d61-8dce-7841c9ce20fc.mp4) | 0/17/4 |
| 2026-03-02 public-services-committee | [https://www.youtube.com/watch?v=o5zAVk1HSh8](https://www.youtube.com/watch?v=o5zAVk1HSh8) | — | 0/46/0 |
| 2026-03-02 planning-commission | [https://www.youtube.com/watch?v=mkZEFuoNUPI](https://www.youtube.com/watch?v=mkZEFuoNUPI) | — | 0/46/0 |
| 2026-03-02 planning-commission | [https://www.youtube.com/watch?v=8QhiMDr6aoY](https://www.youtube.com/watch?v=8QhiMDr6aoY) | — | 0/46/0 |
| 2026-03-03 finance-committee | [https://www.youtube.com/watch?v=CbxmKEdhA0I](https://www.youtube.com/watch?v=CbxmKEdhA0I) | — | 0/31/0 |
| 2026-03-16 public-services-committee | [https://www.youtube.com/watch?v=7KLyD7KU1ms](https://www.youtube.com/watch?v=7KLyD7KU1ms) | — | 0/12/0 |
| 2026-03-17 finance-committee | [https://www.youtube.com/watch?v=ZIcVQwZEnqA](https://www.youtube.com/watch?v=ZIcVQwZEnqA) | — | 0/14/0 |
| 2026-03-23 city-council | [https://www.youtube.com/watch?v=ey_oCFcK7Cs](https://www.youtube.com/watch?v=ey_oCFcK7Cs) | [mp4](https://archive-video.granicus.com/cheyenne/cheyenne_6dcd7f0d-d260-4113-86a3-ed78761059bf.mp4) | 0/3/3 |
| 2026-04-06 public-services-committee | [https://www.youtube.com/watch?v=-KV5z3Rg8Ss](https://www.youtube.com/watch?v=-KV5z3Rg8Ss) | — | 0/38/3 |
| 2026-04-06 planning-commission | [https://www.youtube.com/watch?v=KMsoAcN7S2o](https://www.youtube.com/watch?v=KMsoAcN7S2o) | — | 0/38/3 |
| 2026-04-07 finance-committee | [https://www.youtube.com/watch?v=eYat3pcO3Ko](https://www.youtube.com/watch?v=eYat3pcO3Ko) | — | 0/23/0 |
| 2026-04-14 historic-preservation-board | [https://www.youtube.com/watch?v=fhozD8bp7RI](https://www.youtube.com/watch?v=fhozD8bp7RI) | — | 0/5/2 |
| 2026-04-16 board-of-adjustment | [https://www.youtube.com/watch?v=dp7BxPMiBc8](https://www.youtube.com/watch?v=dp7BxPMiBc8) | — | 0/6/0 |
| 2026-05-04 public-services-committee | [https://www.youtube.com/watch?v=gJq4LbGUFfA](https://www.youtube.com/watch?v=gJq4LbGUFfA) | — | 0/18/0 |
| 2026-05-04 planning-commission | [https://www.youtube.com/watch?v=vW30wgRV2jo](https://www.youtube.com/watch?v=vW30wgRV2jo) | — | 0/18/0 |
| 2026-05-07 urban-renewal-authority | [https://www.youtube.com/watch?v=iIEQrKRojPU](https://www.youtube.com/watch?v=iIEQrKRojPU) | — | 0/2/1 |
| 2026-05-12 historic-preservation-board | [https://www.youtube.com/watch?v=MjwalalTdp8](https://www.youtube.com/watch?v=MjwalalTdp8) | — | 0/6/0 |
| 2026-05-18 public-services-committee | [https://www.youtube.com/watch?v=eyf-DZyuDis](https://www.youtube.com/watch?v=eyf-DZyuDis) | — | 0/42/0 |
| 2026-05-18 planning-commission | [https://www.youtube.com/watch?v=erIc1_2tYk0](https://www.youtube.com/watch?v=erIc1_2tYk0) | — | 0/42/0 |
| 2026-05-19 finance-committee | [https://www.youtube.com/watch?v=1s2dyUEGMAo](https://www.youtube.com/watch?v=1s2dyUEGMAo) | — | 0/58/0 |
| 2026-05-21 board-of-adjustment | [https://www.youtube.com/watch?v=klmSqd148Og](https://www.youtube.com/watch?v=klmSqd148Og) | — | 0/4/0 |
| 2026-06-02 finance-committee | [https://www.youtube.com/watch?v=jLS2k1mavBc](https://www.youtube.com/watch?v=jLS2k1mavBc) | — | 0/31/0 |
| 2026-06-16 finance-committee | [https://www.youtube.com/watch?v=LGBEPwIW_L8](https://www.youtube.com/watch?v=LGBEPwIW_L8) | — | 0/34/0 |
| 2026-06-25 board-of-adjustment | [https://www.youtube.com/watch?v=FnQgytLIkTY](https://www.youtube.com/watch?v=FnQgytLIkTY) | — | 0/1/0 |
| 2026-07-14 historic-preservation-board | [https://www.youtube.com/watch?v=YMsVe6JHm3k](https://www.youtube.com/watch?v=YMsVe6JHm3k) | — | 0/5/1 |
| 2026-07-16 board-of-adjustment | [https://www.youtube.com/watch?v=fNwLJO6tX4g](https://www.youtube.com/watch?v=fNwLJO6tX4g) | — | 0/3/0 |
| 2026-07-20 public-services-committee | [https://www.youtube.com/watch?v=qayvEfzkIT8](https://www.youtube.com/watch?v=qayvEfzkIT8) | — | 0/9/0 |
| 2026-07-21 finance-committee | [https://www.youtube.com/watch?v=Q3CI--6YUDY](https://www.youtube.com/watch?v=Q3CI--6YUDY) | — | 0/80/0 |
| 2026-07-29 work-session | [https://www.youtube.com/watch?v=CNvVfCztL_c](https://www.youtube.com/watch?v=CNvVfCztL_c) | — | 0/0/1 |
| 2026-08-03 public-services-committee | [https://www.youtube.com/watch?v=IM0VKGNplhA](https://www.youtube.com/watch?v=IM0VKGNplhA) | — | 0/7/0 |
| 2026-08-21 work-session | [https://www.youtube.com/watch?v=kAPVTM1oJTo](https://www.youtube.com/watch?v=kAPVTM1oJTo) | — | 0/2/0 |
| 2026-09-08 public-services-committee | [https://www.youtube.com/watch?v=znfsfJ9O0mo](https://www.youtube.com/watch?v=znfsfJ9O0mo) | — | 0/26/0 |
| 2026-09-09 finance-committee | [https://www.youtube.com/watch?v=TJArdO5j0Oc](https://www.youtube.com/watch?v=TJArdO5j0Oc) | — | 0/11/0 |
| 2026-09-21 public-services-committee | [https://www.youtube.com/watch?v=BPUJeNwgjoE](https://www.youtube.com/watch?v=BPUJeNwgjoE) | — | 0/44/7 |
| 2026-09-22 finance-committee | [https://www.youtube.com/watch?v=AED7FDEZ-5k](https://www.youtube.com/watch?v=AED7FDEZ-5k) | — | 0/38/1 |

## Catalog entries with no current candidate need (4)

- 2026-01-13 historic-preservation-board — [https://www.youtube.com/watch?v=1QYWOV-WVCI](https://www.youtube.com/watch?v=1QYWOV-WVCI) (no Phase 1 window, no Phase 2–4 cues; fetch only if later review requires)
- 2026-01-30 work-session — [https://www.youtube.com/watch?v=uxdbgW5oXIE](https://www.youtube.com/watch?v=uxdbgW5oXIE) (no Phase 1 window, no Phase 2–4 cues; fetch only if later review requires)
- 2026-02-05 urban-renewal-authority — [https://www.youtube.com/watch?v=STAKNzVKU60](https://www.youtube.com/watch?v=STAKNzVKU60) (no Phase 1 window, no Phase 2–4 cues; fetch only if later review requires)
- 2026-06-18 board-of-adjustment — [https://www.youtube.com/watch?v=c-rdM6D4RMo](https://www.youtube.com/watch?v=c-rdM6D4RMo) (no Phase 1 window, no Phase 2–4 cues; fetch only if later review requires)

## Uncataloged special sessions (2026) — exist on Granicus, absent from the transcript corpus

The legacy Granicus index also shows **seven 2026 special City Council sessions that are not in the transcript catalog** — no transcript, no Phase 2–4 scan coverage. If any exhaustive-scope video claims "every" interruption/mention (videos 12, 13), these sessions must be reviewed too (or the scope limitation stated on screen).

| Date | Granicus clip | Direct MP4 | Agenda |
|---|---|---|---|
| 2026-01-23 | 1052 | [mp4](https://archive-video.granicus.com/cheyenne/cheyenne_6b88ce0e-fd61-11f0-bb28-005056a89546.mp4) | [agenda](https://cheyenne.granicus.com/AgendaViewer.php?view_id=2&clip_id=1052) |
| 2026-02-23 | 1063 | [mp4](https://archive-video.granicus.com/cheyenne/cheyenne_a3f24875-1719-11f1-bb28-005056a89546.mp4) | [agenda](https://cheyenne.granicus.com/AgendaViewer.php?view_id=2&clip_id=1063) |
| 2026-03-05 | 1069 | [mp4](https://archive-video.granicus.com/cheyenne/cheyenne_0a284898-197b-11f1-bb28-005056a89546.mp4) | [agenda](https://cheyenne.granicus.com/AgendaViewer.php?view_id=2&clip_id=1069) |
| 2026-03-12 | 1073 | [mp4](https://archive-video.granicus.com/cheyenne/cheyenne_3bbc7b15-1ee8-11f1-bb28-005056a89546.mp4) | [agenda](https://cheyenne.granicus.com/AgendaViewer.php?view_id=2&clip_id=1073) |
| 2026-03-16 | 1075 | [mp4](https://archive-video.granicus.com/cheyenne/cheyenne_6d600b3f-38b3-4805-aa9b-cc4fee18f924.mp4) | [agenda](https://cheyenne.granicus.com/AgendaViewer.php?view_id=2&clip_id=1075) |
| 2026-03-17 | 1081 | [mp4](https://archive-video.granicus.com/cheyenne/cheyenne_574126e6-f220-44cd-87a4-b59f13413666.mp4) | [agenda](https://cheyenne.granicus.com/AgendaViewer.php?view_id=2&clip_id=1081) |
| 2026-03-23 | 1087 | [mp4](https://archive-video.granicus.com/cheyenne/cheyenne_64802b09-32c2-4214-85c5-3280da166665.mp4) | [agenda](https://cheyenne.granicus.com/AgendaViewer.php?view_id=2&clip_id=1087) |

## Notes

- Direct Granicus MP4 links were recovered from the legacy pipeline index (`pipeline/meetings.json` at `therealwindycity/therealwindycity` main `b6e707a`, generated before 2026-08-24; its feed covered City Council recordings only). A link is attached only where a **regular** City Council Granicus recording matches the catalog date; special sessions and all committee/board meetings must be fetched from their official YouTube links. Two wrong-meeting attachments made in an earlier draft of this manifest (March 16 PSC and March 17 Finance rows pointing at special-session recordings) were corrected on 2026-10-02.
- The September 28, 2026 third-reading recording exists on the City's Granicus player (per the Phase 5 source register, entry C3) but has no YouTube ID in the transcript catalog; its agenda is at the GeneratedAgendaViewer link in the manifest. The reported 8–2 vote remains secondary until certified minutes are obtained.
- All YouTube IDs come from the transcript catalog `cheyenne-2026-transcripts/meetings.json` and each transcript header (source: City of Cheyenne official YouTube channel).
