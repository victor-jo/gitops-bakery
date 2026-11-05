# Blog notes: weekend movie recommender

## 2026-11-05 JustWatch collection
- Netflix Korea: 5,047 movies; Disney+ Korea: 1,639 movies (unique justwatch_id in both).
- Fetch time at 0.3 s between requests: about 67 s for Netflix, about 35 s for Disney+ (year slices plus one unfiltered ranking pass).
- Disney+ fits under the ~1,900 paging cap, so its whole ranking comes from JustWatch order; Netflix tail past the cap is ranked by tmdb score.
- Per-day new Netflix movies over three days: 22, 12 and 17.
- Title search works through popularTitles(filter: {searchQuery}): "기생충" 2019 resolved to tmdb 496243. English titles do not match the Korean title ("Parasite" returned None).

## 2026-11-05 Coupang Play collection
- The sitemap lists 17,517 content URLs but only 10,429 are unique (the Korean and English entries repeat); sampling by file order must use the raw list.
- About one in three sampled URLs from the sitemap answered 404 in the first pass; in a second random 24-URL pass none did. Gone pages are cached as `gone`.
- `datePublished` check (22 random movie pages, 1 request per second). Every date is on or after the film's release year, and old films carry recent dates, so it behaves like an "added to Coupang" date. `COUPANG_ADDED_ON_IS_RELIABLE` stays True.

| title | release year | datePublished |
|---|---|---|
| 쿵푸 팬더 3 | 2016 | 2024-12-11 |
| 캡틴 아메리카: 시빌 워 | 2016 | 2024-03-08 |
| 메이즈 러너: 스코치 트라이얼 | 2015 | 2024-04-05 |
| 엽문 | 2008 | 2024-05-31 |
| 인베이젼 | 2007 | 2024-06-21 |
| 어글리 트루스 | 2009 | 2024-05-10 |
| 독재자 | 2012 | 2024-12-31 |
| 오즈 그레이트 앤 파워풀 | 2013 | 2024-12-12 |
| 장르만 로맨스 | 2021 | 2025-02-17 |
| 구룡성채: 무법지대 | 2024 | 2025-03-17 |
| 트위스터(1996), fixture | 1996 | 2023-08-21 |

- Caveat: 15 of the 22 dates fall in 2024, so some may be a bulk import rather than the true arrival day. Treat `added_on` as "on Coupang since", good enough for "new this week" only when it is recent.

## 2026-11-05 KFP pipelines: first live runs
- Image `kfp/recommender-pipeline:0.1.0` rebuilt after adding `.dockerignore` (the Task 1 image had shipped the whole venv in its build context).
- `movie-catalog` with `max_pages=200` (run `542134fd-2a36-44cb-878d-680c7263a201`): SUCCEEDED in 694 s wall clock, mostly pod scheduling plus the steps below.
  - `collect_justwatch`: 2 min 09 s, 6,686 titles (Netflix 5,047, Disney+ 1,639), 88 new in the last 7 days.
  - `collect_coupang`: 4 min 44 s for 200 pages at 1 req/s; the sitemap has 10,429 unique content URLs; 144 of the 200 pages are movies.
  - `match_and_build`: 2 min 34 s, including the one-time MovieLens 25M download (249 MiB in 52 s, 25,000,095 ratings, 62,423 movies). 111 of 144 Coupang movies matched a tmdb id. Catalog: 6,727 movies, 2,363 with a MovieLens id.
- `movie-recommender-training` small first run, `sample_users=20000`, `epochs=5`, `dim=32` (run `2d9f0ff7-fcb1-48bf-8e25-60bc57ca865a`): SUCCEEDED in 151 s.
  - 2,308,605 training rows, 20,002 users (20,000 plus me and wife), 32,912 items; no couple feedback yet. MF plus content model: 27 s on 4 CPU / 8Gi.
  - MLflow run `e35db05a826b465badd5fe60e1f5e9ff`: val_auc 0.8117, precision_10 0.4713, recall_10 0.8339. Registered as `movie-recommender` v1 and promoted to `champion` (gate: "no champion").
  - `features/movies.parquet`: 6,727 rows, `vector` list<float32> of dim 32, `bias` double.
- Full-data run, `sample_users=0`, `epochs=5` (run `17a95430-d03f-4431-883e-e07a1e1b8cd2`): SUCCEEDED in 227 s. 18,750,071 training rows, 162,543 users, 59,047 items, training 100 s, fits in 8Gi.
  - MLflow run `7d4919ae7d484025a38ef74ff0af22bb`: val_auc 0.7631, precision_10 0.4614, recall_10 0.8316. v2 was not promoted ("val_auc dropped by 0.048660 > 0.005"), so v1 stays champion.
  - Caveat: the gate compares numbers measured on different validation sets (the 20k-user sample vs. all users), so the two runs are not like for like. The full run probably overfits at 5 epochs with the same learning rate, because it takes 8 times as many steps per epoch.
- Full Coupang pass started at 04:57 UTC (run `1f2373e3-41e0-40e8-8f68-353dc1d027eb`, about 10,229 uncached pages at 1 req/s, roughly 3 hours or more).
