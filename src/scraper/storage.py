"""Filesystem storage for raw HTML pages.

Saves and loads gzip-compressed HTML files organized by match ID and
page type under a match-centric directory structure::

    base_dir/
      matches/
        {match_id}/
          overview.html.gz
          map-{mapstatsid}-stats.html.gz
          map-{mapstatsid}-performance.html.gz
          map-{mapstatsid}-economy.html.gz
"""

import gzip
from pathlib import Path


class HtmlStorage:
    """Gzipped HTML save/load/exists filesystem layer.

    Usage::

        storage = HtmlStorage("data/raw")
        path = storage.save(html, match_id=12345, page_type="overview")
        html = storage.load(match_id=12345, page_type="overview")
    """

    # Page type -> filename template
    PAGE_TYPES: dict[str, str] = {
        "overview": "overview.html.gz",
        "map_stats": "map-{mapstatsid}-stats.html.gz",
        "map_performance": "map-{mapstatsid}-performance.html.gz",
        "map_economy": "map-{mapstatsid}-economy.html.gz",
    }

    # Page types that require a mapstatsid parameter
    _REQUIRES_MAPSTATSID = {"map_stats", "map_performance", "map_economy"}

    def __init__(self, base_dir: str | Path) -> None:
        self.base_dir = Path(base_dir)

    def save(
        self,
        html: str,
        match_id: int,
        page_type: str,
        mapstatsid: int | None = None,
    ) -> Path:
        """Save HTML to disk as gzip-compressed file.

        Args:
            html: Raw HTML string to save.
            match_id: HLTV match ID.
            page_type: One of the keys in PAGE_TYPES.
            mapstatsid: Required for map_* page types.

        Returns:
            Path to the written file.

        Raises:
            ValueError: If page_type is invalid or mapstatsid is missing
                when required.
        """
        file_path = self._build_path(match_id, page_type, mapstatsid)
        file_path.parent.mkdir(parents=True, exist_ok=True)
        file_path.write_bytes(gzip.compress(html.encode("utf-8")))
        return file_path

    def load(
        self,
        match_id: int,
        page_type: str,
        mapstatsid: int | None = None,
    ) -> str:
        """Load HTML from a gzip-compressed file on disk.

        Args:
            match_id: HLTV match ID.
            page_type: One of the keys in PAGE_TYPES.
            mapstatsid: Required for map_* page types.

        Returns:
            The decompressed HTML string.

        Raises:
            FileNotFoundError: If the file does not exist.
            ValueError: If page_type is invalid or mapstatsid is missing.
        """
        file_path = self._build_path(match_id, page_type, mapstatsid)
        if not file_path.exists():
            raise FileNotFoundError(
                f"No saved HTML for match {match_id}, "
                f"page_type={page_type!r}, mapstatsid={mapstatsid}: "
                f"{file_path}"
            )
        return gzip.decompress(file_path.read_bytes()).decode("utf-8")

    def exists(
        self,
        match_id: int,
        page_type: str,
        mapstatsid: int | None = None,
    ) -> bool:
        """Check whether a saved HTML file exists on disk."""
        return self._build_path(match_id, page_type, mapstatsid).exists()

    def list_match_files(self, match_id: int) -> list[Path]:
        """Return all .html.gz files saved for a given match.

        Returns an empty list if the match directory does not exist.
        """
        match_dir = self.base_dir / "matches" / str(match_id)
        if not match_dir.exists():
            return []
        return sorted(match_dir.glob("*.html.gz"))

    def _build_path(
        self,
        match_id: int,
        page_type: str,
        mapstatsid: int | None,
    ) -> Path:
        """Build the filesystem path for a given page.

        Raises:
            ValueError: If page_type is not recognized or if a map_*
                page_type is used without providing mapstatsid.
        """
        if page_type not in self.PAGE_TYPES:
            raise ValueError(
                f"Unknown page_type {page_type!r}. "
                f"Valid types: {list(self.PAGE_TYPES.keys())}"
            )
        if page_type in self._REQUIRES_MAPSTATSID and mapstatsid is None:
            raise ValueError(
                f"page_type {page_type!r} requires a mapstatsid parameter."
            )
        template = self.PAGE_TYPES[page_type]
        filename = template.format(mapstatsid=mapstatsid)
        return self.base_dir / "matches" / str(match_id) / filename
