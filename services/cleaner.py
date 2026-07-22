"""
评论数据清理模块
负责去重、字段规范化、数据验证
"""
import re
from datetime import datetime


class ReviewCleaner:
    def clean_reviews(self, reviews, progress_callback=None):
        """清理评论数据"""
        if not reviews:
            return []

        total = len(reviews)
        if progress_callback:
            progress_callback(0.0, f"开始清理 {total} 条评论")

        # 1. 字段规范化
        reviews = self._normalize_fields(reviews)
        if progress_callback:
            progress_callback(0.3, "字段规范化完成")

        # 2. 去重
        reviews = self._deduplicate(reviews)
        if progress_callback:
            progress_callback(0.6, f"去重完成，剩余 {len(reviews)} 条")

        # 3. 数据验证
        reviews = self._validate(reviews)
        if progress_callback:
            progress_callback(0.8, f"验证完成，有效数据 {len(reviews)} 条")

        # 4. 排序（按日期倒序）
        reviews = self._sort(reviews)
        if progress_callback:
            progress_callback(1.0, "清理完成")

        return reviews

    def _normalize_fields(self, reviews):
        """字段规范化"""
        normalized = []
        for r in reviews:
            review = {
                "review_id": str(r.get("review_id", "")).strip(),
                "title": self._clean_text(r.get("title", "")),
                "content": self._clean_text(r.get("content", "")),
                "rating": self._normalize_rating(r.get("rating", 0)),
                "author": str(r.get("author", "")).strip(),
                "version": str(r.get("version", "")).strip(),
                "date": self._normalize_date(r.get("date", "")),
                "app_id": str(r.get("app_id", "")).strip(),
            }
            normalized.append(review)
        return normalized

    def _clean_text(self, text):
        """清理文本：去除HTML标签、多余空白"""
        if not text:
            return ""
        # 去除 HTML 标签
        text = re.sub(r'<[^>]+>', '', str(text))
        # 去除多余空白但保留换行
        text = re.sub(r'[ \t]+', ' ', text)
        # 去除首尾空白
        text = text.strip()
        return text

    def _normalize_rating(self, rating):
        """规范化评分为 1-5 的整数"""
        try:
            r = int(rating)
            return max(1, min(5, r))
        except (ValueError, TypeError):
            return 0

    def _normalize_date(self, date_str):
        """规范化日期为 ISO 8601 格式"""
        if not date_str:
            return ""
        try:
            # 尝试解析 ISO 格式
            dt = datetime.fromisoformat(date_str.replace('Z', '+00:00'))
            return dt.strftime("%Y-%m-%dT%H:%M:%S")
        except (ValueError, AttributeError):
            return date_str

    def _deduplicate(self, reviews):
        """基于 review_id 去重"""
        seen = set()
        unique = []
        for r in reviews:
            rid = r["review_id"]
            if rid and rid not in seen:
                seen.add(rid)
                unique.append(r)
        return unique

    def _validate(self, reviews):
        """验证数据完整性"""
        valid = []
        for r in reviews:
            # 必须有 review_id
            if not r["review_id"]:
                continue
            # 必须有内容（title 或 content 至少有一个）
            if not r["content"] and not r["title"]:
                continue
            # 评分必须有效
            if r["rating"] < 1 or r["rating"] > 5:
                continue
            valid.append(r)
        return valid

    def _sort(self, reviews):
        """按日期倒序排列"""
        return sorted(reviews, key=lambda x: x.get("date", ""), reverse=True)

    def get_statistics(self, reviews):
        """生成清理后的数据统计"""
        if not reviews:
            return {}
        ratings = [r["rating"] for r in reviews]
        return {
            "total": len(reviews),
            "avg_rating": round(sum(ratings) / len(ratings), 2) if ratings else 0,
            "rating_distribution": {
                str(i): ratings.count(i) for i in range(1, 6)
            },
            "versions": list(set(r["version"] for r in reviews if r["version"])),
            "date_range": {
                "earliest": reviews[-1]["date"] if reviews else "",
                "latest": reviews[0]["date"] if reviews else "",
            },
            "has_author": sum(1 for r in reviews if r["author"]),
            "empty_title": sum(1 for r in reviews if not r["title"]),
        }
