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
- Gate fix: the champion is now re-scored on the new run's own holdout, through its own user and movie index maps, and only rows both models know are compared. Rerun of the full-data training (KFP run `c35866a9-f066-49d0-99e6-a90736e59e63`, MLflow run `74004e04fc9e4551aec9b4ab0761db35`, 257 s) on 770,406 shared rows:
  - new: val_auc 0.7637, precision_10 0.4634, recall_10 0.8295;
  - champion v1: val_auc 0.8226, precision_10 0.4731, recall_10 0.8368.
  - v3 was not promoted, and v1 stays champion.
  - v1 scores higher here than on its own holdout (0.8117), because many of the shared rows were in v1's training split. A sampled champion against a full-data candidate is still not a clean comparison.
- Champion reset (once): v1 was a bootstrap model trained on a 20k-user dev sample. Most of the shared gate rows were in its training data, so it was not a fair incumbent. I deleted the `champion` alias (all versions kept) and reran the full-data training (KFP run `8778a3c7-06b9-4d80-8147-6fe13895896c`, MLflow run `b3ba5917b1e64cf19bf0d184e855385b`, 258 s, train step 120 s).
  - The run promoted itself as v4 ("no champion"): val_auc 0.7631, precision_10 0.4614, recall_10 0.8316.
  - `features/movies.parquet` was rewritten from v4 at 05:14:28 UTC: 6,727 rows, vector dim 32.

## 2026-11-05 Schedules and end-to-end check
- Recurring runs (all ENABLED, `max_concurrency=1`, no catch-up):
  - `movie-catalog` `be3f8d75-fd34-4f01-94c6-15048b369c57`, daily 05:00 KST = `0 0 20 * * *` UTC;
  - `movie-recommender-training` `73d8b878-4b75-4e2c-803f-d69b9c33d1d3`, Monday 06:00 KST = `0 0 21 * * 0`;
  - `movie-recommender-monitoring` `ac744b6f-d7de-4a80-86e4-f0b498c09f7c`, Monday 07:00 KST = `0 0 22 * * 0`. Its first id was `15c5b01b-...`; running the command again replaced it, which showed the idempotency (one run per name afterwards).
- End-to-end through the API at `http://192.168.1.60:3100`, with synthetic marks (no phone): `me` and `wife` each marked 20 onboarding posters (14 thumbs up, 6 down), plus genre choices. 45 event objects were written (40 marks, 1 watched, 2 ratings, 2 genre events); all took under 3 s in total.
- `/api/recommendations` answered in 10 ms with 10 items, none marked, lowest `min(p_me, p_wife)` 0.602, no gamble. Titles in order: 쇼생크 탈출 (0.730), 중경삼림, 대부, 아가씨, 그을린 사랑, 대부 2, 파이트 클럽, 양들의 침묵, 반딧불의 묘, 센과 치히로의 행방불명 (0.602). Reasons read like "둘 다 좋아한 '모아나'과 비슷해요". A reason built from a movie like "Seobeuseuteonseu" shows that a few catalog titles still carry romanised names.
- Marking the first one as watched and rating it 👍 for both removed it from the next request (still 10 items).
- `docker restart movie-rec`: ready after 6 s, the list was identical and no marked or watched movie came back.
- Cleanup: the 45 synthetic event objects were deleted from `s3://recommender/feedback/events/` (the prefix was empty before), and the container restarted so the couple starts clean.

## 2026-11-05 What Feast does here
- Feast is a write-through mirror. The authoritative record is the event log in `s3://recommender/feedback/events/`; the service replays it at start-up and keeps both tastes in memory.
- The service pushes each viewer's folded taste to Feast's online store (Valkey `db=2`, `viewer_taste`) after every mark and materializes the movie features after each catalog reload, so other consumers can read them.
- Nothing in the app reads them back yet. A reader inside the cluster would also need the Valkey secret in the `kubeflow` namespace.

## 2026-11-05 — newer movies first (after the first real use)

After trying it, the owner wanted recent releases to come up more. Two changes:
- Weekend picks: the ranking score gets `RECENCY_BONUS = 0.3` (later popularity-weighted, see below) for a movie released this year, fading linearly to 0 at 5 years old (`RECENCY_YEARS`). The veto still uses the raw probabilities, so a recent movie one of them is predicted to dislike is not let through.
- "Mark what you've seen" grid: newest release year first, then the more popular one; movies with no known year go last.
- Tuned on the owner's 17 real marks: at 0.15 all ten picks were still 1972–2010 classics; at 0.3 the list mixes about half 2026 releases with the top classics; at 0.5 every pick is a 2026 release. Set to 0.3. Why the bonus has to be this large: post-2019 movies have no MovieLens ratings and their Ridge-placed vectors sit near the average, so their best lower score is about 0.56 against 0.86 for the best classic.
- Then weighted by popularity: the bonus became `RECENCY_BONUS × recency × popularity_kr` with `RECENCY_BONUS = 0.33`, because at a flat 0.3 the recent picks were obscure titles (every placed post-2019 vector scores about the same). On the same 17 marks the list became five classics (쇼생크 탈출, 대부, 파이트 클럽, 양들의 침묵, 대부 2) and five 2026 titles high in the Korean charts.

## 2026-11-05 — fair places for each OTT

Checked first: Korean popularity was already even between services (2026 releases average 0.60 on Netflix, 0.59 on Disney+; 토이 스토리 5 is 0.997). Disney+ family titles were missing from the picks because the marks so far lean to action/crime, and Coupang had only 144 movies (the full crawl is still running) with a release year for 22 of them.
- Each service now keeps `MIN_PER_SERVICE = 2` places among the ten picks, filled only with movies that pass the veto, and the list is still shown in score order.
- Coupang titles take their release year from the JustWatch/TMDB match (the match cache now stores `{tmdb_id, release_year}`; entries cached before this are searched once more), so recent Coupang movies get the recency bonus too.
