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
