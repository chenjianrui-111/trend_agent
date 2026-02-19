"""
Tests for content deduplication service.
"""

from trend_agent.services.dedup import DedupService, simhash, hamming_distance, content_hash


class TestSimhash:
    def test_identical_texts(self):
        h1 = simhash("Hello world test")
        h2 = simhash("Hello world test")
        assert h1 == h2

    def test_similar_texts(self):
        h1 = simhash("OpenAI releases GPT-5 with major improvements")
        h2 = simhash("OpenAI releases GPT-5 with significant improvements")
        dist = hamming_distance(h1, h2)
        assert dist < 10  # Similar texts should have low distance

    def test_different_texts(self):
        h1 = simhash("OpenAI releases GPT-5")
        h2 = simhash("Bitcoin reaches new all-time high in 2026")
        dist = hamming_distance(h1, h2)
        assert dist > 5  # Different texts should have higher distance

    def test_empty_text(self):
        h = simhash("")
        assert h == 0

    def test_content_hash(self):
        h1 = content_hash("Hello World")
        h2 = content_hash("hello world")
        assert h1 == h2  # Normalized

        h3 = content_hash("Hello  World")
        assert h1 == h3  # Whitespace normalized


class TestDedupService:
    def test_no_duplicate(self):
        svc = DedupService()
        assert not svc.is_duplicate("First unique text here")
        svc.add("First unique text here")
        assert not svc.is_duplicate("Completely different text here")

    def test_exact_duplicate(self):
        svc = DedupService()
        svc.add("This is a duplicate text for testing")
        assert svc.is_duplicate("This is a duplicate text for testing")

    def test_check_and_add(self):
        svc = DedupService()
        assert not svc.check_and_add("First text")
        assert svc.check_and_add("First text")  # Now duplicate

    def test_clear(self):
        svc = DedupService()
        svc.add("Some text content")
        assert svc.is_duplicate("Some text content")
        svc.clear()
        assert not svc.is_duplicate("Some text content")
