# Shared genre vocabulary with mappings from JustWatch, Coupang Play and MovieLens labels
CANONICAL: tuple[str, ...] = (
    "action", "adventure", "animation", "comedy", "crime", "documentary", "drama",
    "family", "fantasy", "history", "horror", "music", "mystery", "romance",
    "scifi", "thriller", "war", "western", "sport", "reality",
)

KOREAN_LABEL: dict[str, str] = {
    "action": "액션", "adventure": "모험", "animation": "애니메이션", "comedy": "코미디",
    "crime": "범죄", "documentary": "다큐멘터리", "drama": "드라마", "family": "가족",
    "fantasy": "판타지", "history": "역사", "horror": "공포", "music": "음악",
    "mystery": "미스터리", "romance": "로맨스", "scifi": "SF", "thriller": "스릴러",
    "war": "전쟁", "western": "서부", "sport": "스포츠", "reality": "리얼리티",
}

_JUSTWATCH = {
    "act": "action", "ani": "animation", "cmy": "comedy", "crm": "crime",
    "doc": "documentary", "drm": "drama", "fml": "family", "fnt": "fantasy",
    "hst": "history", "hrr": "horror", "msc": "music", "rly": "reality",
    "rma": "romance", "scf": "scifi", "spt": "sport", "trl": "thriller",
    "war": "war", "wsn": "western",
}

_COUPANG = {
    "액션": "action", "무협": "action", "어드벤처": "adventure", "모험": "adventure",
    "애니메이션": "animation", "코미디": "comedy", "범죄": "crime",
    "다큐멘터리": "documentary", "드라마": "drama", "법정": "drama",
    "가족": "family", "키즈": "family", "판타지": "fantasy",
    "시대극": "history", "역사": "history", "공포": "horror", "호러": "horror",
    "음악": "music", "뮤지컬": "music", "미스터리": "mystery", "로맨스": "romance",
    "SF": "scifi", "스릴러": "thriller", "전쟁": "war", "서부": "western",
    "스포츠": "sport",
}

_MOVIELENS = {
    "Action": "action", "Adventure": "adventure", "Animation": "animation",
    "Children": "family", "Comedy": "comedy", "Crime": "crime",
    "Documentary": "documentary", "Drama": "drama", "Fantasy": "fantasy",
    "Film-Noir": "crime", "Horror": "horror", "Musical": "music",
    "Mystery": "mystery", "Romance": "romance", "Sci-Fi": "scifi",
    "Thriller": "thriller", "War": "war", "Western": "western",
}


def _map(labels, table: dict[str, str]) -> list[str]:
    return sorted({table[x] for x in labels if x in table})


def from_justwatch(codes: list[str]) -> list[str]:
    return _map(codes, _JUSTWATCH)


def from_coupang(names: list[str]) -> list[str]:
    return _map(names, _COUPANG)


def from_movielens(pipe_joined: str) -> list[str]:
    return _map(pipe_joined.split("|"), _MOVIELENS)
