"""
Unified heat scoring for cross-platform ranking.
"""

from collections import defaultdict
from datetime import datetime, timezone
import math
from typing import Any, Dict, List, Optional

from trend_agent.config.settings import settings
from trend_agent.models.message import TrendItem


def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


def _parse_time(value: str) -> datetime:
    if not value:
        return _now_utc()
    text = value.strip()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        dt = datetime.fromisoformat(text)
    except ValueError:
        return _now_utc()
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


class HeatScoreService:
    """
    Default formula:
      score = 0.45 * platform_percentile + 0.25 * velocity + 0.20 * freshness + 0.10 * cross_platform
    Weights and decay are configurable via settings.heat_score.
    """

    def score_batch(self, items: List[TrendItem]) -> List[TrendItem]:
        if not items:
            return items

        platform_values: Dict[str, List[float]] = defaultdict(list)
        content_platforms: Dict[str, set[str]] = defaultdict(set)
        velocity_values: List[float] = []
        now = _now_utc()

        for item in items:
            platform_values[item.source_platform].append(float(item.engagement_score or 0.0))
            if item.content_hash:
                content_platforms[item.content_hash].add(item.source_platform)

            published = _parse_time(item.published_at or item.scraped_at)
            age_hours = max((now - published).total_seconds() / 3600.0, 1.0 / 60.0)
            velocity_values.append(float(item.engagement_score or 0.0) / age_hours)

        velocity_max = max(velocity_values) if velocity_values else 1.0
        if velocity_max <= 0:
            velocity_max = 1.0

        for index, item in enumerate(items):
            engagement = float(item.engagement_score or 0.0)
            p_values = sorted(platform_values[item.source_platform])
            percentile = _percentile_rank(p_values, engagement)

            published = _parse_time(item.published_at or item.scraped_at)
            age_hours = max((now - published).total_seconds() / 3600.0, 0.0)

            velocity = min(velocity_values[index] / velocity_max, 1.0)
            freshness = self._freshness_score(age_hours)
            cross_platform = 0.0
            if item.content_hash:
                cross_platform = min((len(content_platforms[item.content_hash]) - 1) / 2.0, 1.0)

            w = self._normalized_component_weights()
            score = (
                w["platform_percentile"] * percentile
                + w["velocity"] * velocity
                + w["freshness"] * freshness
                + w["cross_platform"] * cross_platform
            )
            platform_boost = settings.heat_score.platform_weights.get(item.source_platform.lower(), 1.0)
            github_components = self._github_components(item, now)
            github_boost = github_components.get("github_boost", 1.0)
            score *= max(0.0, platform_boost) * max(0.0, github_boost)
            item.normalized_heat_score = round(max(0.0, min(score, 1.0)), 6)
            item.heat_breakdown = {
                "platform_percentile": round(percentile, 6),
                "velocity": round(velocity, 6),
                "freshness": round(freshness, 6),
                "cross_platform": round(cross_platform, 6),
                "platform_weight": round(float(platform_boost), 6),
                "github_boost": round(float(github_boost), 6),
                "github_star_velocity": round(float(github_components.get("star_velocity", 0.0)), 6),
                "github_contributor_activity": round(float(github_components.get("contributor_activity", 0.0)), 6),
                "github_release_adoption": round(float(github_components.get("release_adoption", 0.0)), 6),
                "github_composite": round(float(github_components.get("github_composite", 0.0)), 6),
            }

        return items

    def sort_items(self, items: List[TrendItem], strategy: str = "hybrid") -> List[TrendItem]:
        strategy = (strategy or "hybrid").lower()
        if strategy == "engagement":
            return sorted(
                items,
                key=lambda i: (float(i.engagement_score or 0.0), i.source_platform, i.source_id),
                reverse=True,
            )
        if strategy == "recency":
            return sorted(
                items,
                key=lambda i: (_parse_time(i.published_at or i.scraped_at), i.source_platform, i.source_id),
                reverse=True,
            )
        return sorted(
            items,
            key=lambda i: (float(i.normalized_heat_score or 0.0), i.source_platform, i.source_id),
            reverse=True,
        )

    @staticmethod
    def _normalized_component_weights() -> Dict[str, float]:
        values = {
            "platform_percentile": max(0.0, float(settings.heat_score.weight_platform_percentile)),
            "velocity": max(0.0, float(settings.heat_score.weight_velocity)),
            "freshness": max(0.0, float(settings.heat_score.weight_freshness)),
            "cross_platform": max(0.0, float(settings.heat_score.weight_cross_platform)),
        }
        total = sum(values.values())
        if total <= 0:
            return {
                "platform_percentile": 0.45,
                "velocity": 0.25,
                "freshness": 0.20,
                "cross_platform": 0.10,
            }
        return {k: v / total for k, v in values.items()}

    @staticmethod
    def _freshness_score(age_hours: float) -> float:
        age = max(0.0, float(age_hours))
        max_age = max(1.0, float(settings.heat_score.freshness_max_age_hours))
        if age >= max_age:
            return 0.0
        half_life = max(0.1, float(settings.heat_score.freshness_half_life_hours))
        decay = math.exp(-math.log(2) * age / half_life)
        return max(0.0, min(decay, 1.0))

    @staticmethod
    def _as_float(value: Any, default: float = 0.0) -> float:
        try:
            return float(value)
        except (TypeError, ValueError):
            return default

    @staticmethod
    def _norm_log(value: float, cap: float) -> float:
        v = max(0.0, float(value))
        c = max(1.0, float(cap))
        if v <= 0:
            return 0.0
        return max(0.0, min(math.log1p(v) / math.log1p(c), 1.0))

    @staticmethod
    def _github_feature_weights() -> Dict[str, float]:
        hs = settings.heat_score
        values = {
            "star_velocity": max(0.0, HeatScoreService._as_float(hs.github_weight_star_velocity)),
            "contributor_activity": max(0.0, HeatScoreService._as_float(hs.github_weight_contributor_activity)),
            "release_adoption": max(0.0, HeatScoreService._as_float(hs.github_weight_release_adoption)),
        }
        total = sum(values.values())
        if total <= 0:
            return {"star_velocity": 0.45, "contributor_activity": 0.35, "release_adoption": 0.20}
        return {k: v / total for k, v in values.items()}

    def _github_components(self, item: TrendItem, now: datetime) -> Dict[str, float]:
        if item.source_platform.lower() != "github":
            return {
                "star_velocity": 0.0,
                "contributor_activity": 0.0,
                "release_adoption": 0.0,
                "github_composite": 0.0,
                "github_boost": 1.0,
            }

        metrics = item.platform_metrics or {}
        hs = settings.heat_score

        # Prefer scraper-provided velocity; fallback to stars / repo age.
        star_velocity_raw = self._as_float(metrics.get("star_velocity_per_day"))
        if star_velocity_raw <= 0:
            stars = self._as_float(metrics.get("stars"))
            repo_created_dt: Optional[datetime] = _parse_time(str(metrics.get("repo_created_at", ""))) if metrics.get("repo_created_at") else None
            if not repo_created_dt:
                repo_created_dt = _parse_time(item.published_at or item.scraped_at)
            repo_age_days = max((now - repo_created_dt).total_seconds() / 86400.0, 1.0 / 24.0)
            star_velocity_raw = stars / repo_age_days
        star_velocity = self._norm_log(star_velocity_raw, hs.github_star_velocity_norm_cap)

        forks = self._as_float(metrics.get("forks"))
        open_issues = self._as_float(metrics.get("open_issues"))
        comments = self._as_float(metrics.get("comments"))
        upvotes = self._as_float(metrics.get("upvote_count"))
        contributor_activity_raw = forks + open_issues * 0.7 + comments * 1.5 + upvotes * 1.2
        contributor_activity = self._norm_log(
            contributor_activity_raw, hs.github_contributor_activity_norm_cap,
        )

        downloads = self._as_float(metrics.get("download_count"))
        assets = self._as_float(metrics.get("assets_count"))
        reactions = self._as_float(metrics.get("reaction_count"))
        advisory_cvss = self._as_float(metrics.get("cvss_score"))
        release_adoption_raw = downloads + assets * 20.0 + reactions * 3.0 + advisory_cvss * 50.0
        release_adoption = self._norm_log(
            release_adoption_raw, hs.github_release_adoption_norm_cap,
        )

        weights = self._github_feature_weights()
        github_composite = (
            weights["star_velocity"] * star_velocity
            + weights["contributor_activity"] * contributor_activity
            + weights["release_adoption"] * release_adoption
        )

        base = self._as_float(hs.github_boost_base, 0.75)
        boost_range = self._as_float(hs.github_boost_range, 0.50)
        github_boost = max(0.0, base + boost_range * github_composite)
        return {
            "star_velocity": star_velocity,
            "contributor_activity": contributor_activity,
            "release_adoption": release_adoption,
            "github_composite": github_composite,
            "github_boost": github_boost,
        }


def _percentile_rank(sorted_values: List[float], value: float) -> float:
    if not sorted_values:
        return 0.0
    if len(sorted_values) == 1:
        return 1.0
    count = 0
    for v in sorted_values:
        if v <= value:
            count += 1
    return (count - 1) / (len(sorted_values) - 1)
