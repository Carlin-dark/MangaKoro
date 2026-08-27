from __future__ import annotations

import time
from typing import Any
import requests

BASE_URL = "https://api.mangadex.org"

class MangaDexError(RuntimeError):
    pass

class MangaDexClient:
    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({"User-Agent": "MangaKoro/1.5 (desktop reader)"})

    def _get(self, path: str, params: dict[str, Any] | list[tuple[str, Any]] | None = None) -> dict[str, Any]:
        for attempt in range(3):
            try:
                response = self.session.get(BASE_URL + path, params=params, timeout=20)
                if response.status_code == 429:
                    if attempt == 2:
                        raise MangaDexError(self._error_message(response))
                    time.sleep(int(response.headers.get("Retry-After", "2")))
                    continue
                if response.status_code >= 400:
                    raise MangaDexError(self._error_message(response))
                response.raise_for_status()
                return response.json()
            except MangaDexError:
                raise
            except requests.RequestException as exc:
                if attempt == 2:
                    raise MangaDexError("Não foi possível conectar ao MangaDex.") from exc
                time.sleep(1.5 * (attempt + 1))
        raise MangaDexError("A API não respondeu.")

    @staticmethod
    def _error_message(response: requests.Response) -> str:
        try:
            errors = response.json().get("errors", [])
            details = []
            for error in errors:
                detail = error.get("detail") or error.get("title")
                if detail and detail not in details:
                    details.append(detail)
            if details:
                return f"MangaDex HTTP {response.status_code}: " + " | ".join(details)
        except (ValueError, TypeError, AttributeError):
            pass
        return f"MangaDex HTTP {response.status_code}: {response.text or 'erro desconhecido'}"

    def _attributes(self, item: dict[str, Any]) -> dict[str, Any]:
        attrs = item.get("attributes", {})
        title = next(iter(attrs.get("title", {}).values()), "Sem título")
        description = attrs.get("description", {})
        description = next(iter(description.values()), "Sem sinopse disponível.")
        tags = [next(iter(t.get("attributes", {}).get("name", {}).values()), "") for t in attrs.get("tags", [])]
        
        # Pega o nome do autor
        author = "Desconhecido"
        for relation in item.get("relationships", []):
            if relation.get("type") == "author":
                author = relation.get("attributes", {}).get("name", author)

        return {
            "id": item.get("id", ""),
            "title": title,
            "description": description,
            "status": attrs.get("status", "unknown"),
            "year": attrs.get("year", "N/A"),
            "content_rating": attrs.get("contentRating", "safe"),
            "tags": [t for t in tags if t],
            "author": author,
            "alt_titles": [v for t in attrs.get("altTitles", []) for v in t.values()],
        }

    def _cover(self, item: dict[str, Any]) -> str:
        for relation in item.get("relationships", []):
            if relation.get("type") == "cover_art":
                filename = relation.get("attributes", {}).get("fileName")
                if filename:
                    return f"https://uploads.mangadex.org/covers/{item['id']}/{filename}"
        return ""

    def search(self, title: str = "", offset: int = 0, **filters: Any) -> list[dict[str, Any]]:
        limit = filters.get("limit", self.db.setting("search_limit", 24)) if hasattr(self, 'db') else filters.get("limit", 24)
        params: list[tuple[str, Any]] = [
            ("limit", limit),
            ("offset", offset),
            ("includes[]", "cover_art"),
            ("includes[]", "author"),
        ]
        
        if title.strip():
            params.append(("title", title.strip()))

        order = filters.get("order")
        if order:
            params.append((f"order[{order}]", "desc"))
        else:
            if not title.strip() and not filters.get("included_tags"):
                params.append(("order[followedCount]", "desc")) # Padrão para "Em Alta" se não tiver busca
            else:
                params.append(("order[relevance]", "desc"))

        filter_mappings = [
            ("content_ratings", "contentRating[]"),
            ("status", "status[]"),
            ("languages", "availableTranslatedLanguage[]"),
            ("included_tags", "includedTags[]"),
            ("excluded_tags", "excludedTags[]"),
        ]

        for key, param_name in filter_mappings:
            values = filters.get(key)
            if values:
                if isinstance(values, list):
                    for v in values:
                        params.append((param_name, v))
                else:
                    params.append((param_name, values))

        data = self._get("/manga", params).get("data", [])
        result = []
        for item in data:
            manga = self._attributes(item)
            manga["cover"] = self._cover(item)
            result.append(manga)
        return result

    def manga(self, manga_id: str) -> dict[str, Any]:
        item = self._get(f"/manga/{manga_id}", [("includes[]", "cover_art"), ("includes[]", "author")]).get("data", {})
        result = self._attributes(item)
        result["cover"] = self._cover(item)
        return result

    def chapters(self, manga_id: str, languages: list[str] | None = None) -> list[dict[str, Any]]:
        params: list[tuple[str, Any]] = [
            ("manga", manga_id),
            ("limit", 100),
            ("order[chapter]", "desc"),
            ("includes[]", "scanlation_group"),
        ]
        
        if languages and "all" not in languages and "todos" not in languages:
            for language in languages:
                params.append(("translatedLanguage[]", language))
            
        for content_rating in ["safe", "suggestive", "erotica", "pornographic"]:
            params.append(("contentRating[]", content_rating))

        data = self._get("/chapter", params).get("data", [])
        chapters = []
        for item in data:
            attrs = item.get("attributes", {})
            group_name = "Scan desconhecida"
            for rel in item.get("relationships", []):
                if rel.get("type") == "scanlation_group":
                    group_name = rel.get("attributes", {}).get("name", group_name)

            chapters.append({
                "id": item.get("id", ""),
                "chapter": attrs.get("chapter") or "0",
                "volume": attrs.get("volume") or "",
                "title": attrs.get("title") or "Sem título",
                "language": attrs.get("translatedLanguage", "desconhecido"),
                "group": group_name,
            })
        return chapters

    def pages(self, chapter_id: str, data_saver: bool = False) -> list[str]:
        data = self._get(f"/at-home/server/{chapter_id}")
        base = data.get("baseUrl", "")
        chapter = data.get("chapter", {})
        hash_value = chapter.get("hash", "")
        quality = "data-saver" if data_saver and chapter.get("dataSaver") else "data"
        return [f"{base}/{quality}/{hash_value}/{page}" for page in chapter.get(quality, [])]