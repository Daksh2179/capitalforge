"""LogoCache: filesystem-backed storage for fetched logo bytes, plus
negative caching for tickers confirmed to have no logo. Swappable
storage backend — LogoService depends only on this interface's shape,
never on filesystem details directly.
"""

from pathlib import Path


class LogoCache:
    def __init__(self, directory: str | Path = "logo_cache") -> None:
        self._directory = Path(directory)
        self._directory.mkdir(parents=True, exist_ok=True)

    def get(self, ticker: str) -> bytes | None:
        path = self._path_for(ticker)
        if not path.exists() or path.stat().st_size == 0:
            return None
        return path.read_bytes()

    def save(self, ticker: str, image_bytes: bytes) -> None:
        self._path_for(ticker).write_bytes(image_bytes)

    def has_negative_cache(self, ticker: str) -> bool:
        return self._negative_path_for(ticker).exists()

    def save_negative_cache(self, ticker: str) -> None:
        self._negative_path_for(ticker).touch()

    def _path_for(self, ticker: str) -> Path:
        return self._directory / f"{ticker.upper()}.png"

    def _negative_path_for(self, ticker: str) -> Path:
        return self._directory / f"{ticker.upper()}.nologo"