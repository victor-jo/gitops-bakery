# Weekend movie recommender for two: design

Status: draft for review, 2026-11-05. Lives under `labs/ml/recommender/` in the gitops-bakery ML lab.

## Intent

Every weekend the user and their wife spend a long time choosing a movie to watch together on the TV. The problem is not a lack of options; it is that nothing comes to mind. The service exists to surface a short list of "oh, that one looks good" candidates on a phone, quickly, so the choice takes minutes instead of a long search.

It is also the third exercise of the ML lab and the subject of a later velog post covering Evidently, BentoML and the recommender. Every lab component must have a real job, and the work should leave a trail (what was tried, measured and changed) that a blog post can be written from.

Reference project: `practical-mlops/movie-recommender-project` (MovieLens 25M → PyTorch matrix factorization, KFP data and training pipelines, MLflow registry with a `staging` gate on RMS, precision@k and recall@k, a BentoML service, an Evidently notebook simulating preference drift).

## Users

Two people, the user and their wife, each with their own profile. They sit on the sofa, open the page on a phone, pick a movie, and play it on the TV through the streaming app.

## Goals

1. One screen of candidates (5–10 movies) that both of them are likely to enjoy, each with a one-line reason ("similar to X, which you both liked").
2. Candidates come only from what they can watch: **Netflix, Disney+ and Coupang Play in Korea**, available now. Old movies are included. Movies either of them has already marked are excluded.
3. A "new on the services in the last 7 days" signal, so fresh arrivals can surface.
4. Learning in real time: a 👍/👎 changes the next recommendation request without waiting for a retrain.
5. Each lab component has a job:

| Component | Job |
|---|---|
| KFP | Daily catalog collection, the training pipeline, evaluation and the promotion gate |
| MLflow | Experiment tracking and the model registry (aliases as in the reference project) |
| Feast | Movie features and the two users' taste state, served online |
| BentoML | The recommendation API, including the real-time taste update |
| Evidently | Monitoring recommendation quality and drift (see Success) |

## Non-goals (first version)

- Movies that will be released on the services in the next 7 days ("upcoming"). JustWatch Korea returns nothing for upcoming titles (the US returns 258), so this is dropped for v1. Revisit when a source is found.
- Theatrical releases.
- Recommendations for one person watching alone. The model scores each person anyway, so a toggle can come later.
- Series. Movies only.
- Any user beyond these two, sign-up, or exposure outside the home network.

## Anti-goals

- **A movie that is clearly not their style.** This is the failure that would make them stop using it, even if the metrics look fine. It shapes the veto rule and the cold-start onboarding below.
- A candidate that is not actually on one of the three services.

## Experience

Decided with the user (mockup: `.superpowers/brainstorm/15325-1793847089/content/onboarding-flow.html`).

1. **Profile.** Pick "me" or "wife". No age or other personal details are asked (decided with the user).
2. **Genres.** "Which genres do you like?" Multi-select.
3. **Mark what you have seen.** Movies of the chosen genres that are popular in Korea, as a scrolling poster grid. Tap a movie you have seen and two buttons appear, 👍 liked or 👎 did not like (option A). Movies not seen are simply scrolled past. About 20 per person is expected at the start.
4. **This weekend's candidates.** Movies for both of them together, with the service ("Netflix", "Disney+", "Coupang Play"), a "new this week" badge when it applies, and the reason line.
5. After watching, one tap on a candidate records "we watched this together", then each person rates it 👍/👎 under their own profile (my call). Each rating updates that person's taste immediately; the next request reflects it. Joint-watch events are what the success metric is computed from.

Feedback is binary (👍/👎), not a 1–10 score. Decided with the user: easier to enter, and more marked movies beat finer scores at this data size.

## Recommendation rules

- Each person gets their own predicted probability of liking a movie.
- **Veto.** If the model predicts that either person would dislike a movie, it is removed. Decided with the user.
- The rest are ranked by the lower of the two scores (my call: rewards movies both like over movies one loves).
- Lean toward the genres chosen at onboarding and toward 👍 movies; push away from movies similar to 👎 ones.
- Exclude anything either of them has marked, seen or not liked.
- **Too few left.** If fewer than 5 movies survive the veto, loosen the veto threshold just enough to fill 5 and mark each added movie with a "a bit of a gamble" badge (decided with the user). Movies either of them is predicted to strongly dislike are never added back.

## Data

### Catalog

| Service | Source | What it gives | Verified |
|---|---|---|---|
| Netflix | JustWatch GraphQL `popularTitles`, country KR, package `nfx` | 5,047 movies; title, original title, release date, runtime, genres, IMDb/TMDB scores, `tmdbId` for 5,033 | Yes; deep paging stops near 1,900, so fetch in release-year slices (a throwaway probe script did this; the real collector is rewritten under `labs/ml/recommender/`) |
| Disney+ | same, package `dnp` | 1,639 movies | Count only |
| Coupang Play | Official site: `sitemap.xml` → `/content/<uuid>` pages, JSON-LD | About 12,800 movies estimated (17,517 pages; sample of 30: 22 movies, 1 series, 7 gone with 404). Title, genres (Korean), description, actors, poster, Coupang rating and rating count, `datePublished` | Sample only |
| New in the last 7 days | JustWatch `newTitles(pageType: NEW, date: D)` per day; Coupang `datePublished` | Netflix 4–22 movies a day; Disney+ sparse | Netflix yes |
| Popular in Korea | JustWatch popularity order per service; Coupang rating count | Ordering for the onboarding grid | Partly |

Constraints on collection:

- JustWatch's GraphQL API is unofficial. Space requests and credit the source in the blog.
- Coupang Play `robots.txt`: `/api` is disallowed; user-requested AI retrieval (`Claude-User`) is allowed on `/content`; it carries a `Content-Signal: ai-train=no`. The user was told and chose to read the content pages anyway, **one request per second**, a full pass once (about 5 hours) and then only changed or new pages. Never touch `/api`.
- Coupang's sitemap may be stale (every `lastmod` is `2026-01-24`, a quarter of sampled pages are gone). Movies added after it may be missing.
- Coupang's `datePublished` looks like the date it was added to Coupang (e.g. Twister, 1996, shows `2023-08-21`). Confirm on more titles before using it as "new this week".
- Coupang pages have no TMDB/IMDb ID. Link them by title and year, accepting some mismatches.
- The user also approved using Coupang descriptions and cast as model input (content features for placing new movies), knowing the `ai-train=no` signal.

### Training data

MovieLens 25M as in the reference project (non-commercial research licence, which fits a personal lab). Its `links.csv` maps `movieId` to `tmdbId`, which joins to the JustWatch catalog. It ends in 2019, so newer movies have no collaborative signal and need a content-based position (see below).

## Model and "real-time learning"

My calls, which the builder may refine:

- **Base model.** Follow the reference project: a matrix-factorization model on MovieLens 25M, trained by a KFP pipeline, logged to MLflow, promoted through an alias gate on validation metrics. Binary target (MovieLens rating ≥ 4 as 👍), matching the user's binary feedback.
- **New users (the couple).** The base model only knows user IDs it was trained on. Each person's taste vector is solved from their 👍/👎 against the frozen item embeddings (fold-in), seeded by the chosen genres. This fold-in is the real-time learning: it runs in the BentoML service on every feedback event and writes the new vector to Feast's online store. The base model is retrained on a schedule, not per click.
- **What the retrain learns from** (my call). MovieLens 25M plus the couple's accumulated 👍/👎 as two extra users, so each retrain actually changes with their history. The promotion gate evaluates on a held-out slice of the couple's own ratings next to the reference project's MovieLens precision@k / recall@k, so a model that is better on MovieLens but worse for them is not promoted.
- **New movies (after 2019, and unmatched Coupang titles).** Place them in the embedding space from content features (genres, description, cast) so they can be scored. The method is left to the builder; a reason line must still be producible.
- **Reasons.** "Similar to X, which you both liked" from nearest 👍 movies in the embedding space.

## Success

Decided with the user: the weekend's movie, found through this service, was one they enjoyed. Measured as the share of watched candidates where both pressed 👍. Evidently tracks this weekly, together with drift in the couple's taste vectors and in the catalog's genre mix. Offline, the training pipeline keeps the reference project's precision@k / recall@k gate.

## Environment constraints

- Runs on the existing kind lab (`honeyed-bagel`) on the Mac, with OrbStack and cloud-provider-kind. After an OrbStack restart the gateway IPs change and the gateways must be recreated (memory note `orbstack-restart-gateway-recovery`); the service has to survive that without code changes.
- The phone reaches the service over the home Wi-Fi. The `192.168.165.x` sslip names only work from the Mac, so a LAN-reachable entry point is needed. The Mac must be on.
- The existing income-classifier exercise and its BentoML container (`income-clf-drift`, port 3001) stay as they are.
- No secrets in git or images; credentials come from cluster Secrets at run time, as in `labs/ml/serving/run.sh`.

## Left to the builder

- Web front-end stack and how it is deployed (in-cluster through Argo CD like other lab apps, or a container on the kind network like the existing BentoML service), and the LAN entry point.
- Profile "login": two fixed profiles with no password is enough on the home network (my call).
- Exact Feast entities and feature views, schedules, embedding size, the content-based placement method, the fold-in solver.
- Matching catalog titles to MovieLens and across services.
- Ports, names and directory layout under `labs/ml/recommender/`.
- Notes for the blog: keep a running log of decisions, numbers and screenshots alongside the code.
