# Daily movie catalog pipeline: JustWatch (Netflix, Disney+) -> Coupang Play pages -> tmdb matching and merge
import sys
from pathlib import Path

from kfp import compiler, dsl

sys.path[:0] = [str(Path(__file__).parent), str(Path(__file__).parent / "src")]
from components import collect_coupang, collect_justwatch, match_and_build  # noqa: E402
from wiring import wire  # noqa: E402


@dsl.pipeline(name="movie-catalog", description="Collect Netflix, Disney+ and Coupang Play movies into s3://recommender/catalog/movies.parquet")
def movie_catalog(
    # 0 crawls every Coupang page not yet cached (about 5 hours on the first pass); a positive value caps a test run
    max_pages: int = 0,
    # Coupang Play is read at most once per second
    pause: float = 1.0,
):
    jw = wire(collect_justwatch())
    cp = wire(collect_coupang(max_pages=max_pages, pause=pause), memory="2Gi").after(jw)
    # The first run also unpacks MovieLens 25M for the tmdb -> movieId links, which needs the larger limit
    wire(match_and_build(), memory="6Gi").after(cp)


if __name__ == "__main__":
    compiler.Compiler().compile(movie_catalog, str(Path(__file__).with_name("movie_catalog.yaml")))
    print("compiled movie_catalog.yaml")
