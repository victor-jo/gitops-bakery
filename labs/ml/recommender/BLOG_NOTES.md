# Blog notes: weekend movie recommender

## 2026-11-05 JustWatch collection
- Netflix Korea: 5,047 movies; Disney+ Korea: 1,639 movies (unique justwatch_id in both).
- Fetch time at 0.3 s between requests: about 67 s for Netflix, about 35 s for Disney+ (year slices plus one unfiltered ranking pass).
- Disney+ fits under the ~1,900 paging cap, so its whole ranking comes from JustWatch order; Netflix tail past the cap is ranked by tmdb score.
- Per-day new Netflix movies over three days: 22, 12 and 17.
- Title search works through popularTitles(filter: {searchQuery}): "기생충" 2019 resolved to tmdb 496243. English titles do not match the Korean title ("Parasite" returned None).
