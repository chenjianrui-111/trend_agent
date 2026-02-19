"""
Regression tests for heat score and strategy sorting stability.
"""

from trend_agent.models.message import TrendItem
from trend_agent.config.settings import settings
from trend_agent.services.heat_score import HeatScoreService


def _item(
    platform: str,
    source_id: str,
    engagement: float,
    published_at: str,
    content_hash: str,
) -> TrendItem:
    return TrendItem(
        source_platform=platform,
        source_id=source_id,
        engagement_score=engagement,
        published_at=published_at,
        scraped_at=published_at,
        content_hash=content_hash,
        title=f"{platform}-{source_id}",
        description="desc",
    )


def test_heat_score_stable_sort_order():
    service = HeatScoreService()
    items = [
        _item("twitter", "t1", 1200, "2026-02-19T02:00:00+00:00", "h1"),
        _item("youtube", "y1", 2500, "2026-02-19T01:00:00+00:00", "h2"),
        _item("weibo", "w1", 2200, "2026-02-19T01:30:00+00:00", "h3"),
        _item("twitter", "t2", 1200, "2026-02-19T02:00:00+00:00", "h1"),
    ]

    first = service.sort_items(service.score_batch(items), strategy="hybrid")
    second = service.sort_items(service.score_batch(items), strategy="hybrid")

    first_ids = [(i.source_platform, i.source_id) for i in first]
    second_ids = [(i.source_platform, i.source_id) for i in second]
    assert first_ids == second_ids
    assert all(0.0 <= i.normalized_heat_score <= 1.0 for i in first)


def test_heat_score_strategy_sorting():
    service = HeatScoreService()
    items = [
        _item("twitter", "a", 100, "2026-02-18T00:00:00+00:00", "c1"),
        _item("twitter", "b", 500, "2026-02-19T00:00:00+00:00", "c2"),
        _item("twitter", "c", 300, "2026-02-17T00:00:00+00:00", "c3"),
    ]

    scored = service.score_batch(items)
    by_engagement = service.sort_items(scored, strategy="engagement")
    by_recency = service.sort_items(scored, strategy="recency")

    assert by_engagement[0].source_id == "b"
    assert by_recency[0].source_id == "b"


def test_heat_score_respects_platform_weight_overrides():
    hs = settings.heat_score
    original = (
        hs.weight_platform_percentile,
        hs.weight_velocity,
        hs.weight_freshness,
        hs.weight_cross_platform,
        dict(hs.platform_weights),
    )
    try:
        hs.weight_platform_percentile = 0.45
        hs.weight_velocity = 0.25
        hs.weight_freshness = 0.20
        hs.weight_cross_platform = 0.10
        hs.platform_weights = {"twitter": 1.4, "youtube": 0.6}

        service = HeatScoreService()
        items = [
            _item("twitter", "tw", 1000, "2026-02-19T00:00:00+00:00", "h_tw"),
            _item("youtube", "yt", 1000, "2026-02-19T00:00:00+00:00", "h_yt"),
        ]
        ranked = service.sort_items(service.score_batch(items), strategy="hybrid")
        assert ranked[0].source_platform == "twitter"
    finally:
        hs.weight_platform_percentile = original[0]
        hs.weight_velocity = original[1]
        hs.weight_freshness = original[2]
        hs.weight_cross_platform = original[3]
        hs.platform_weights = original[4]


def test_heat_score_freshness_decay_parameter_affects_ranking():
    hs = settings.heat_score
    original = (
        hs.weight_platform_percentile,
        hs.weight_velocity,
        hs.weight_freshness,
        hs.weight_cross_platform,
        hs.freshness_half_life_hours,
        hs.freshness_max_age_hours,
    )
    try:
        hs.weight_platform_percentile = 0.0
        hs.weight_velocity = 0.0
        hs.weight_freshness = 1.0
        hs.weight_cross_platform = 0.0
        hs.freshness_half_life_hours = 1.0
        hs.freshness_max_age_hours = 240.0

        service = HeatScoreService()
        items = [
            _item("twitter", "fresh", 100, "2026-02-19T00:00:00+00:00", "h_f"),
            _item("twitter", "old", 100, "2026-02-15T00:00:00+00:00", "h_o"),
        ]
        ranked = service.sort_items(service.score_batch(items), strategy="hybrid")
        assert ranked[0].source_id == "fresh"
        assert ranked[0].normalized_heat_score >= ranked[1].normalized_heat_score
    finally:
        hs.weight_platform_percentile = original[0]
        hs.weight_velocity = original[1]
        hs.weight_freshness = original[2]
        hs.weight_cross_platform = original[3]
        hs.freshness_half_life_hours = original[4]
        hs.freshness_max_age_hours = original[5]


def test_heat_score_github_platform_specific_features_affect_ranking():
    hs = settings.heat_score
    original = (
        hs.weight_platform_percentile,
        hs.weight_velocity,
        hs.weight_freshness,
        hs.weight_cross_platform,
        dict(hs.platform_weights),
        hs.github_weight_star_velocity,
        hs.github_weight_contributor_activity,
        hs.github_weight_release_adoption,
        hs.github_boost_base,
        hs.github_boost_range,
    )
    try:
        hs.weight_platform_percentile = 0.45
        hs.weight_velocity = 0.25
        hs.weight_freshness = 0.20
        hs.weight_cross_platform = 0.10
        hs.platform_weights = {}
        hs.github_weight_star_velocity = 0.50
        hs.github_weight_contributor_activity = 0.30
        hs.github_weight_release_adoption = 0.20
        hs.github_boost_base = 0.10
        hs.github_boost_range = 0.80

        service = HeatScoreService()
        hot = _item("github", "repo_hot", 1000, "2026-02-19T00:00:00+00:00", "gh_hot")
        cold = _item("github", "repo_cold", 1000, "2026-02-19T00:00:00+00:00", "gh_cold")
        hot.platform_metrics = {
            "stars": 12000,
            "forks": 900,
            "open_issues": 400,
            "download_count": 45000,
            "assets_count": 12,
            "repo_created_at": "2026-01-01T00:00:00+00:00",
        }
        cold.platform_metrics = {
            "stars": 40,
            "forks": 2,
            "open_issues": 1,
            "download_count": 10,
            "assets_count": 0,
            "repo_created_at": "2026-01-01T00:00:00+00:00",
        }

        ranked = service.sort_items(service.score_batch([cold, hot]), strategy="hybrid")
        assert ranked[0].source_id == "repo_hot"
        assert ranked[0].normalized_heat_score > ranked[1].normalized_heat_score
        assert ranked[0].heat_breakdown["github_composite"] > ranked[1].heat_breakdown["github_composite"]
    finally:
        hs.weight_platform_percentile = original[0]
        hs.weight_velocity = original[1]
        hs.weight_freshness = original[2]
        hs.weight_cross_platform = original[3]
        hs.platform_weights = original[4]
        hs.github_weight_star_velocity = original[5]
        hs.github_weight_contributor_activity = original[6]
        hs.github_weight_release_adoption = original[7]
        hs.github_boost_base = original[8]
        hs.github_boost_range = original[9]


def test_heat_score_github_release_adoption_weight_can_dominate():
    hs = settings.heat_score
    original = (
        hs.weight_platform_percentile,
        hs.weight_velocity,
        hs.weight_freshness,
        hs.weight_cross_platform,
        hs.github_weight_star_velocity,
        hs.github_weight_contributor_activity,
        hs.github_weight_release_adoption,
        hs.github_boost_base,
        hs.github_boost_range,
    )
    try:
        hs.weight_platform_percentile = 0.45
        hs.weight_velocity = 0.25
        hs.weight_freshness = 0.20
        hs.weight_cross_platform = 0.10
        hs.github_weight_star_velocity = 0.0
        hs.github_weight_contributor_activity = 0.0
        hs.github_weight_release_adoption = 1.0
        hs.github_boost_base = 0.10
        hs.github_boost_range = 0.90

        service = HeatScoreService()
        release_heavy = _item("github", "release_heavy", 1000, "2026-02-19T00:00:00+00:00", "gh_rel")
        star_heavy = _item("github", "star_heavy", 1000, "2026-02-19T00:00:00+00:00", "gh_star")
        release_heavy.platform_metrics = {"download_count": 90000, "assets_count": 20}
        star_heavy.platform_metrics = {"stars": 500000, "forks": 10000, "repo_created_at": "2024-01-01T00:00:00+00:00"}

        ranked = service.sort_items(service.score_batch([star_heavy, release_heavy]), strategy="hybrid")
        assert ranked[0].source_id == "release_heavy"
    finally:
        hs.weight_platform_percentile = original[0]
        hs.weight_velocity = original[1]
        hs.weight_freshness = original[2]
        hs.weight_cross_platform = original[3]
        hs.github_weight_star_velocity = original[4]
        hs.github_weight_contributor_activity = original[5]
        hs.github_weight_release_adoption = original[6]
        hs.github_boost_base = original[7]
        hs.github_boost_range = original[8]
