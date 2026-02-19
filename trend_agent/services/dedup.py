"""
内容去重服务 - 基于 simhash 的近似去重
"""

import hashlib
import re
from typing import Set


def _tokenize(text: str) -> list[str]:
    """简单中英文分词"""
    text = re.sub(r"[^\w\u4e00-\u9fff]", " ", text or "")
    tokens = []
    for word in text.split():
        if len(word) >= 2:
            tokens.append(word.lower())
    return tokens


def simhash(text: str, hash_bits: int = 64) -> int:
    """计算文本的 simhash 值"""
    tokens = _tokenize(text)
    if not tokens:
        return 0

    v = [0] * hash_bits
    for token in tokens:
        h = int(hashlib.md5(token.encode("utf-8")).hexdigest(), 16)
        for i in range(hash_bits):
            if h & (1 << i):
                v[i] += 1
            else:
                v[i] -= 1

    fingerprint = 0
    for i in range(hash_bits):
        if v[i] > 0:
            fingerprint |= (1 << i)
    return fingerprint


def hamming_distance(hash1: int, hash2: int) -> int:
    """计算两个 hash 的汉明距离"""
    return bin(hash1 ^ hash2).count("1")


def content_hash(text: str) -> str:
    """生成内容 hash（用于精确去重）"""
    normalized = re.sub(r"\s+", "", text or "").lower()
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()[:16]


class DedupService:
    """内容去重服务"""

    def __init__(self, threshold: int = 5):
        self._threshold = threshold  # hamming distance threshold
        self._hashes: Set[int] = set()
        self._content_hashes: Set[str] = set()

    def is_duplicate(self, text: str) -> bool:
        """检查内容是否与已有内容重复"""
        # 精确去重
        c_hash = content_hash(text)
        if c_hash in self._content_hashes:
            return True

        # 近似去重
        s_hash = simhash(text)
        for existing in self._hashes:
            if hamming_distance(s_hash, existing) <= self._threshold:
                return True

        return False

    def add(self, text: str):
        """添加内容到去重集合"""
        self._content_hashes.add(content_hash(text))
        self._hashes.add(simhash(text))

    def check_and_add(self, text: str) -> bool:
        """检查并添加，返回是否重复"""
        if self.is_duplicate(text):
            return True
        self.add(text)
        return False

    def clear(self):
        self._hashes.clear()
        self._content_hashes.clear()
