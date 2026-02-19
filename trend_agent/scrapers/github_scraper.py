"""
GitHub scraper - repositories + releases + issues + pull requests + discussions + security advisories.
"""

import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

from trend_agent.config.settings import settings
from trend_agent.models.message import TrendItem
from trend_agent.observability import metrics as obs
from trend_agent.scrapers.base import BaseScraper
from trend_agent.services.dedup import content_hash

logger = logging.getLogger(__name__)


class GitHubScraper(BaseScraper):
    """GitHub REST API scraper with incremental cursor + ETag support."""

    name = "github"

    def __init__(self):
        super().__init__()
        self._etag_cache: Dict[str, str] = {}
        self._cursor: Dict[str, str] = {}

    def load_state(self, state: Dict[str, Any]) -> None:
        etags = state.get("etag_cache")
        cursor = state.get("cursor")
        if isinstance(etags, dict):
            self._etag_cache = {str(k): str(v) for k, v in etags.items() if k and v}
        if isinstance(cursor, dict):
            self._cursor = {str(k): str(v) for k, v in cursor.items() if k and v}

    def dump_state(self) -> Dict[str, Any]:
        return {
            "etag_cache": dict(self._etag_cache),
            "cursor": dict(self._cursor),
        }

    def _headers(self, accept: str = "application/vnd.github+json") -> Dict[str, str]:
        headers = {
            "Accept": accept,
            "User-Agent": "trend-agent/0.1",
            "X-GitHub-Api-Version": "2022-11-28",
        }
        if settings.scraper.github_token:
            headers["Authorization"] = f"Bearer {settings.scraper.github_token}"
        return headers

    async def _request_json(
        self,
        session,
        url: str,
        params: Dict[str, Any],
        cache_key: str,
        accept: str = "application/vnd.github+json",
    ) -> Tuple[Optional[Any], int]:
        headers = self._headers(accept=accept)
        etag = self._etag_cache.get(cache_key)
        if etag:
            headers["If-None-Match"] = etag

        try:
            async with session.get(url, headers=headers, params=params) as resp:
                status = int(resp.status)
                obs.record_scrape_request(self.name, "http_call")
                obs.record_scrape_http_status(self.name, status)
                obs.record_scrape_cost(self.name, request_units=1.0)
                if status == 304:
                    return None, status
                if status == 404:
                    return None, status
                if status >= 400:
                    body = await resp.text()
                    logger.warning("GitHub request failed: %s status=%s body=%s", url, status, body[:180])
                    return None, status

                resp_headers = getattr(resp, "headers", {}) or {}
                etag_new = resp_headers.get("ETag") or resp_headers.get("etag")
                if etag_new:
                    self._etag_cache[cache_key] = str(etag_new)
                return await resp.json(), status
        except Exception as e:
            logger.warning("GitHub request error: %s url=%s", e, url)
            return None, 0

    async def scrape(
        self,
        query: Optional[str] = None,
        limit: int = 50,
        capture_mode: str = "hybrid",
        start_time: Optional[str] = None,
        end_time: Optional[str] = None,
        sort_strategy: str = "hybrid",
    ) -> List[TrendItem]:
        session = await self._get_session()
        max_items = max(1, min(limit, 100))
        repo_limit = min(max_items, max(8, max_items // 2))
        side_limit = min(30, max(3, max_items // 3))

        repos = await self._fetch_trending_repos(
            session=session,
            query=query,
            limit=repo_limit,
            capture_mode=capture_mode,
            start_time=start_time,
            end_time=end_time,
            sort_strategy=sort_strategy,
        )

        repo_candidates = repos[:min(len(repos), max(3, side_limit))]
        releases = await self._fetch_latest_releases(
            session=session,
            repos=repo_candidates,
            limit=side_limit,
            start_time=start_time,
            end_time=end_time,
        )
        issues = await self._fetch_search_items(
            session=session,
            query=query,
            limit=side_limit,
            kind="issue",
            capture_mode=capture_mode,
            start_time=start_time,
            end_time=end_time,
            sort_strategy=sort_strategy,
        )
        pull_requests = await self._fetch_search_items(
            session=session,
            query=query,
            limit=side_limit,
            kind="pr",
            capture_mode=capture_mode,
            start_time=start_time,
            end_time=end_time,
            sort_strategy=sort_strategy,
        )
        discussions = await self._fetch_discussions(
            session=session,
            repos=repo_candidates,
            limit=side_limit,
            start_time=start_time,
            end_time=end_time,
        )
        advisories = await self._fetch_security_advisories(
            session=session,
            query=query,
            limit=side_limit,
            start_time=start_time,
            end_time=end_time,
        )

        items = repos + releases + issues + pull_requests + discussions + advisories
        logger.info(
            "GitHub scraped repos=%d releases=%d issues=%d prs=%d discussions=%d advisories=%d",
            len(repos), len(releases), len(issues), len(pull_requests), len(discussions), len(advisories),
        )
        obs.record_scrape_items(self.name, len(items))
        obs.record_scrape_cost(self.name, item_units=float(len(items)))
        return items[: max_items * 3]

    async def _fetch_trending_repos(
        self,
        session,
        query: Optional[str],
        limit: int,
        capture_mode: str,
        start_time: Optional[str],
        end_time: Optional[str],
        sort_strategy: str,
    ) -> List[TrendItem]:
        q = self._build_repo_query(query, capture_mode, start_time, end_time)
        sort = "stars" if capture_mode == "by_hot" or sort_strategy in ("engagement", "hybrid") else "updated"
        params = {
            "q": q,
            "sort": sort,
            "order": "desc",
            "per_page": min(limit, 100),
            "page": 1,
        }
        url = f"{settings.scraper.github_api_base_url.rstrip('/')}/search/repositories"
        data, _ = await self._request_json(
            session=session,
            url=url,
            params=params,
            cache_key=f"repo:{q}:{sort}:{params['per_page']}",
        )
        if not data:
            return []

        start_dt, end_dt, cursor_dt = self._time_filters("github_trending", start_time, end_time)
        now = datetime.now(timezone.utc)
        items: List[TrendItem] = []

        for repo in data.get("items", [])[:limit]:
            full_name = repo.get("full_name", "")
            if not full_name:
                continue
            update_ts = repo.get("pushed_at") or repo.get("updated_at") or repo.get("created_at") or ""
            if not self._within_window(update_ts, start_dt, end_dt, cursor_dt):
                continue

            stars = int(repo.get("stargazers_count", 0) or 0)
            forks = int(repo.get("forks_count", 0) or 0)
            watchers = int(repo.get("watchers_count", 0) or 0)
            open_issues = int(repo.get("open_issues_count", 0) or 0)
            star_velocity = self._calc_star_velocity(stars, repo.get("created_at"), now=now)
            engagement = stars + forks * 2 + watchers + max(0, open_issues // 2)

            owner = repo.get("owner", {}) or {}
            description = repo.get("description", "") or ""
            topics = repo.get("topics", []) or []
            homepage = repo.get("homepage", "") or ""
            html_url = repo.get("html_url", "") or f"https://github.com/{full_name}"
            media = [owner.get("avatar_url", "")] if owner.get("avatar_url") else []

            items.append(
                TrendItem(
                    source_platform="github",
                    source_channel="github_trending",
                    source_type="repository",
                    source_id=full_name,
                    source_url=html_url,
                    title=full_name,
                    description=description[:1000],
                    author=owner.get("login", ""),
                    author_id=str(owner.get("id", "")),
                    language="en",
                    engagement_score=float(engagement),
                    tags=[str(t) for t in topics[:10]],
                    external_urls=[u for u in [homepage, html_url] if u],
                    media_urls=media,
                    published_at=update_ts,
                    platform_metrics={
                        "stars": stars,
                        "forks": forks,
                        "watchers": watchers,
                        "open_issues": open_issues,
                        "language": repo.get("language", ""),
                        "repo_created_at": repo.get("created_at", ""),
                        "repo_updated_at": repo.get("updated_at", ""),
                        "repo_pushed_at": repo.get("pushed_at", ""),
                        "star_velocity_per_day": star_velocity,
                    },
                    scraped_at=datetime.now(timezone.utc).isoformat(),
                    raw_data=repo,
                    content_hash=content_hash(full_name + description),
                )
            )

        self._update_cursor("github_trending", [i.published_at for i in items])
        return items

    async def _fetch_latest_releases(
        self,
        session,
        repos: List[TrendItem],
        limit: int,
        start_time: Optional[str],
        end_time: Optional[str],
    ) -> List[TrendItem]:
        results: List[TrendItem] = []
        start_dt, end_dt, cursor_dt = self._time_filters("github_release", start_time, end_time)

        for repo in repos:
            if len(results) >= limit:
                break
            full_name = repo.source_id
            url = f"{settings.scraper.github_api_base_url.rstrip('/')}/repos/{full_name}/releases"
            data, status = await self._request_json(
                session=session,
                url=url,
                params={"per_page": 1, "page": 1},
                cache_key=f"release:{full_name}",
            )
            if status in (304, 404) or not data:
                continue

            release_list = data if isinstance(data, list) else []
            if not release_list:
                continue
            rel = release_list[0]
            release_time_str = rel.get("published_at") or rel.get("created_at") or ""
            if not self._within_window(release_time_str, start_dt, end_dt, cursor_dt):
                continue

            assets = rel.get("assets", []) or []
            downloads = sum(int(a.get("download_count", 0) or 0) for a in assets)
            reactions = rel.get("reactions", {}) or {}
            reaction_sum = sum(
                int(reactions.get(k, 0) or 0)
                for k in ("+1", "-1", "laugh", "hooray", "confused", "heart", "rocket", "eyes")
            )
            comments = int(rel.get("comments", 0) or 0)
            engagement = downloads + len(assets) * 20 + comments * 5 + reaction_sum * 3
            title = rel.get("name") or rel.get("tag_name") or f"{full_name} release"
            body = rel.get("body", "") or ""
            rel_url = rel.get("html_url", "") or repo.source_url

            results.append(
                TrendItem(
                    source_platform="github",
                    source_channel="github_release",
                    source_type="release",
                    source_id=f"{full_name}#release#{rel.get('id', '')}",
                    source_url=rel_url,
                    title=f"{full_name}: {title}",
                    description=body[:1000],
                    author=(rel.get("author") or {}).get("login", repo.author),
                    author_id=str((rel.get("author") or {}).get("id", "")),
                    language="en",
                    engagement_score=float(engagement),
                    tags=[str(rel.get("tag_name", ""))] if rel.get("tag_name") else [],
                    external_urls=[u for u in [rel.get("tarball_url", ""), rel.get("zipball_url", ""), rel_url] if u],
                    published_at=release_time_str,
                    platform_metrics={
                        "repo_full_name": full_name,
                        "assets_count": len(assets),
                        "download_count": downloads,
                        "comments": comments,
                        "reaction_count": reaction_sum,
                        "tag_name": rel.get("tag_name", ""),
                    },
                    scraped_at=datetime.now(timezone.utc).isoformat(),
                    raw_data={
                        "release": rel,
                        "repo_source_id": full_name,
                    },
                    content_hash=content_hash(full_name + title + body),
                )
            )

        self._update_cursor("github_release", [i.published_at for i in results])
        return results

    async def _fetch_search_items(
        self,
        session,
        query: Optional[str],
        limit: int,
        kind: str,
        capture_mode: str,
        start_time: Optional[str],
        end_time: Optional[str],
        sort_strategy: str,
    ) -> List[TrendItem]:
        channel = "github_issue" if kind == "issue" else "github_pull_request"
        source_type = "issue" if kind == "issue" else "pull_request"
        base_query = self._build_issue_pr_query(query=query, kind=kind, capture_mode=capture_mode)
        sort = "comments" if capture_mode == "by_hot" or sort_strategy in ("engagement", "hybrid") else "updated"
        params = {
            "q": base_query,
            "sort": sort,
            "order": "desc",
            "per_page": min(limit, 100),
            "page": 1,
        }
        url = f"{settings.scraper.github_api_base_url.rstrip('/')}/search/issues"
        data, _ = await self._request_json(
            session=session,
            url=url,
            params=params,
            cache_key=f"{channel}:{base_query}:{sort}:{params['per_page']}",
        )
        if not data:
            return []

        start_dt, end_dt, cursor_dt = self._time_filters(channel, start_time, end_time)
        items: List[TrendItem] = []

        for issue in data.get("items", [])[:limit]:
            update_ts = issue.get("updated_at") or issue.get("created_at") or ""
            if not self._within_window(update_ts, start_dt, end_dt, cursor_dt):
                continue

            repository = self._extract_repo_full_name(issue)
            number = issue.get("number", issue.get("id", ""))
            source_id = f"{repository}#{'issue' if kind == 'issue' else 'pr'}#{number}"
            html_url = issue.get("html_url", "")
            title = issue.get("title", "")
            body = issue.get("body", "") or ""
            comments = int(issue.get("comments", 0) or 0)
            reactions = issue.get("reactions", {}) or {}
            reaction_sum = sum(
                int(reactions.get(k, 0) or 0)
                for k in ("+1", "-1", "laugh", "hooray", "confused", "heart", "rocket", "eyes")
            )
            engagement = comments * 5 + reaction_sum * 2
            labels = issue.get("labels", []) or []
            tags = [
                f"#{str(lbl.get('name', '')).strip()}#"
                for lbl in labels if isinstance(lbl, dict) and lbl.get("name")
            ][:10]
            user = issue.get("user", {}) or {}

            items.append(
                TrendItem(
                    source_platform="github",
                    source_channel=channel,
                    source_type=source_type,
                    source_id=source_id,
                    source_url=html_url,
                    title=title[:200],
                    description=body[:1000],
                    author=user.get("login", ""),
                    author_id=str(user.get("id", "")),
                    language="en",
                    engagement_score=float(engagement),
                    tags=tags,
                    external_urls=[html_url] if html_url else [],
                    published_at=update_ts,
                    platform_metrics={
                        "repo_full_name": repository,
                        "comments": comments,
                        "reaction_count": reaction_sum,
                        "state": issue.get("state", ""),
                    },
                    scraped_at=datetime.now(timezone.utc).isoformat(),
                    raw_data=issue,
                    content_hash=content_hash(source_id + title + body),
                )
            )

        self._update_cursor(channel, [i.published_at for i in items])
        return items

    async def _fetch_discussions(
        self,
        session,
        repos: List[TrendItem],
        limit: int,
        start_time: Optional[str],
        end_time: Optional[str],
    ) -> List[TrendItem]:
        results: List[TrendItem] = []
        if not repos or limit <= 0:
            return results

        start_dt, end_dt, cursor_dt = self._time_filters("github_discussion", start_time, end_time)
        for repo in repos:
            if len(results) >= limit:
                break
            full_name = repo.source_id
            if "/" not in full_name:
                continue

            url = f"{settings.scraper.github_api_base_url.rstrip('/')}/repos/{full_name}/discussions"
            per_page = min(20, max(1, limit - len(results)))
            data, status = await self._request_json(
                session=session,
                url=url,
                params={"per_page": per_page, "page": 1, "sort": "updated", "direction": "desc"},
                cache_key=f"discussion:{full_name}:{per_page}",
            )
            if status in (304, 404) or not data:
                continue

            discussions = data if isinstance(data, list) else data.get("items", [])
            if not isinstance(discussions, list):
                continue

            for discussion in discussions:
                if len(results) >= limit:
                    break
                update_ts = discussion.get("updated_at") or discussion.get("created_at") or ""
                if not self._within_window(update_ts, start_dt, end_dt, cursor_dt):
                    continue

                number = discussion.get("number", discussion.get("id", ""))
                title = discussion.get("title", "")
                body = discussion.get("body", "") or ""
                html_url = discussion.get("html_url", "")
                upvotes = int(discussion.get("upvote_count", 0) or 0)
                comments = int(discussion.get("comments", 0) or 0)
                engagement = upvotes * 4 + comments * 3
                user = discussion.get("user", {}) or {}

                results.append(
                    TrendItem(
                        source_platform="github",
                        source_channel="github_discussion",
                        source_type="discussion",
                        source_id=f"{full_name}#discussion#{number}",
                        source_url=html_url,
                        title=title[:200],
                        description=body[:1000],
                        author=user.get("login", ""),
                        author_id=str(user.get("id", "")),
                        language="en",
                        engagement_score=float(engagement),
                        external_urls=[html_url] if html_url else [],
                        published_at=update_ts,
                        platform_metrics={
                            "repo_full_name": full_name,
                            "upvote_count": upvotes,
                            "comments": comments,
                            "category": (discussion.get("category") or {}).get("name", ""),
                        },
                        scraped_at=datetime.now(timezone.utc).isoformat(),
                        raw_data=discussion,
                        content_hash=content_hash(full_name + str(number) + title),
                    )
                )

        self._update_cursor("github_discussion", [i.published_at for i in results])
        return results

    async def _fetch_security_advisories(
        self,
        session,
        query: Optional[str],
        limit: int,
        start_time: Optional[str],
        end_time: Optional[str],
    ) -> List[TrendItem]:
        if limit <= 0:
            return []

        params = {
            "sort": "updated",
            "direction": "desc",
            "per_page": min(limit, 100),
            "page": 1,
        }
        url = f"{settings.scraper.github_api_base_url.rstrip('/')}/advisories"
        data, _ = await self._request_json(
            session=session,
            url=url,
            params=params,
            cache_key=f"advisory:{params['per_page']}",
        )
        if not data:
            return []

        start_dt, end_dt, cursor_dt = self._time_filters("github_security_advisory", start_time, end_time)
        keyword = (query or "").strip().lower()
        advisories = data if isinstance(data, list) else data.get("items", [])
        if not isinstance(advisories, list):
            return []

        severity_score = {
            "low": 20.0,
            "moderate": 40.0,
            "medium": 40.0,
            "high": 70.0,
            "critical": 100.0,
        }

        results: List[TrendItem] = []
        for adv in advisories[:limit]:
            updated_ts = adv.get("updated_at") or adv.get("published_at") or ""
            if not self._within_window(updated_ts, start_dt, end_dt, cursor_dt):
                continue

            ghsa_id = adv.get("ghsa_id", "") or str(adv.get("id", ""))
            summary = adv.get("summary", "") or ""
            description = adv.get("description", "") or ""
            cves = adv.get("cve_id") or adv.get("cves") or []
            cve_list = [str(cves)] if isinstance(cves, str) else [str(c) for c in (cves or [])]
            if keyword:
                haystack = f"{ghsa_id} {summary} {description} {' '.join(cve_list)}".lower()
                if keyword not in haystack:
                    continue

            severity = str(adv.get("severity", "")).lower()
            cvss_score = float(((adv.get("cvss") or {}).get("score", 0)) or 0.0)
            epss_pct = float(((adv.get("epss") or {}).get("percentage", 0)) or 0.0)
            if epss_pct > 1:
                epss_pct = epss_pct / 100.0
            engagement = (
                severity_score.get(severity, 10.0)
                + cvss_score * 8.0
                + epss_pct * 100.0
                + len(cve_list) * 6.0
            )

            source_url = adv.get("html_url", "") or f"https://github.com/advisories/{ghsa_id}"
            results.append(
                TrendItem(
                    source_platform="github",
                    source_channel="github_security_advisory",
                    source_type="security_advisory",
                    source_id=ghsa_id,
                    source_url=source_url,
                    title=summary[:200] or ghsa_id,
                    description=description[:1000],
                    author="github_advisory_database",
                    language="en",
                    engagement_score=float(engagement),
                    tags=[f"#severity:{severity}#"] if severity else [],
                    external_urls=[source_url],
                    published_at=updated_ts,
                    platform_metrics={
                        "severity": severity,
                        "cvss_score": cvss_score,
                        "epss_percentage": epss_pct,
                        "cve_count": len(cve_list),
                    },
                    scraped_at=datetime.now(timezone.utc).isoformat(),
                    raw_data=adv,
                    content_hash=content_hash(ghsa_id + summary + updated_ts),
                )
            )

        self._update_cursor("github_security_advisory", [i.published_at for i in results])
        return results

    @staticmethod
    def _build_repo_query(
        query: Optional[str],
        capture_mode: str,
        start_time: Optional[str],
        end_time: Optional[str],
    ) -> str:
        terms = []
        if query:
            terms.append(query.strip())
        else:
            terms.append("topic:ai OR topic:machine-learning OR topic:developer-tools")

        if capture_mode in ("by_time", "hybrid"):
            start_ymd = GitHubScraper._to_ymd(start_time)
            end_ymd = GitHubScraper._to_ymd(end_time)
            if start_ymd and end_ymd:
                terms.append(f"pushed:{start_ymd}..{end_ymd}")
            elif start_ymd:
                terms.append(f"pushed:>={start_ymd}")
            elif end_ymd:
                terms.append(f"pushed:<={end_ymd}")
        if capture_mode == "by_hot":
            terms.append("stars:>50")
        return " ".join(t for t in terms if t)

    @staticmethod
    def _build_issue_pr_query(query: Optional[str], kind: str, capture_mode: str) -> str:
        base = query.strip() if query else "ai OR machine learning OR developer tools"
        terms = [base, "archived:false", f"is:{kind}"]
        if capture_mode == "by_hot":
            terms.append("comments:>2")
        return " ".join(t for t in terms if t)

    @staticmethod
    def _extract_repo_full_name(item: Dict[str, Any]) -> str:
        html_url = str(item.get("html_url", "") or "")
        if html_url.startswith("https://github.com/"):
            path = html_url.replace("https://github.com/", "").split("/")
            if len(path) >= 2:
                return f"{path[0]}/{path[1]}"
        repo_api = str(item.get("repository_url", "") or "")
        if "/repos/" in repo_api:
            tail = repo_api.split("/repos/", 1)[1]
            parts = [p for p in tail.split("/") if p]
            if len(parts) >= 2:
                return f"{parts[0]}/{parts[1]}"
        return "unknown/unknown"

    def _time_filters(
        self,
        channel: str,
        start_time: Optional[str],
        end_time: Optional[str],
    ) -> Tuple[Optional[datetime], Optional[datetime], Optional[datetime]]:
        start_dt = self._parse_dt(start_time)
        end_dt = self._parse_dt(end_time)
        cursor_dt = None
        if not start_dt and not end_dt:
            cursor_dt = self._parse_dt(self._cursor.get(channel))
        return start_dt, end_dt, cursor_dt

    def _update_cursor(self, channel: str, time_values: List[str]) -> None:
        max_dt = self._parse_dt(self._cursor.get(channel))
        for value in time_values:
            dt = self._parse_dt(value)
            if not dt:
                continue
            if max_dt is None or dt > max_dt:
                max_dt = dt
        if max_dt:
            self._cursor[channel] = max_dt.isoformat()

    @staticmethod
    def _within_window(
        value: Optional[str],
        start_dt: Optional[datetime],
        end_dt: Optional[datetime],
        cursor_dt: Optional[datetime],
    ) -> bool:
        dt = GitHubScraper._parse_dt(value)
        if dt is None:
            return not (start_dt or end_dt or cursor_dt)
        if start_dt and dt < start_dt:
            return False
        if end_dt and dt > end_dt:
            return False
        if cursor_dt and dt <= cursor_dt:
            return False
        return True

    @staticmethod
    def _calc_star_velocity(stars: int, created_at: Optional[str], now: datetime) -> float:
        created_dt = GitHubScraper._parse_dt(created_at) or now
        age_days = max((now - created_dt).total_seconds() / 86400.0, 1.0 / 24.0)
        return float(stars) / age_days

    @staticmethod
    def _to_ymd(value: Optional[str]) -> str:
        dt = GitHubScraper._parse_dt(value)
        if not dt:
            return ""
        return dt.strftime("%Y-%m-%d")

    @staticmethod
    def _parse_dt(value: Optional[str]) -> Optional[datetime]:
        if not value:
            return None
        text = value.strip()
        if not text:
            return None
        if text.endswith("Z"):
            text = text[:-1] + "+00:00"
        try:
            dt = datetime.fromisoformat(text)
        except ValueError:
            return None
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)

    async def health_check(self) -> Dict:
        try:
            session = await self._get_session()
            data, status = await self._request_json(
                session=session,
                url=f"{settings.scraper.github_api_base_url.rstrip('/')}/rate_limit",
                params={},
                cache_key="health:rate_limit",
            )
            return {
                "status": "healthy" if status and status < 400 else "unhealthy",
                "source": "github",
                "http_status": status,
                "rate_limit_present": bool(data),
            }
        except Exception as e:
            return {"status": "unhealthy", "source": "github", "error": str(e)}
