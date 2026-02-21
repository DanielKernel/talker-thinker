"""
Keywords Manager for Talker-Thinker

Provides centralized keyword management with:
- Dynamic loading from JSON files
- Hot word learning mechanism
- Priority-based matching
- Usage statistics tracking
"""

import json
import os
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional, Set
from dataclasses import dataclass, field

from monitoring.logging import get_logger

logger = get_logger("keywords_manager")


@dataclass
class KeywordEntry:
    """Represents a keyword entry"""
    keywords: List[str]
    priority: int = 1
    usage_count: int = 0
    description: str = ""
    synonyms: List[str] = field(default_factory=list)


@dataclass
class TopicEntry:
    """Represents a topic entry"""
    keywords: List[str]
    synonyms: List[str] = field(default_factory=list)


class KeywordsManager:
    """
    Centralized keyword management system

    Features:
    - Load keywords from JSON files
    - Dynamic hot word learning
    - Priority-based matching
    - Usage statistics tracking
    """

    # Default paths for keyword files
    BASE_KEYWORDS_FILE = "data/keywords/base_keywords.json"
    USER_KEYWORDS_FILE = "data/keywords/user_keywords.json"
    HOT_KEYWORDS_FILE = "data/keywords/hot_keywords.json"
    TOPICS_FILE = "data/keywords/topics.json"

    # Hot word learning thresholds
    HOT_WORD_THRESHOLD = 10  # Times a word must be used to become "hot"
    HOT_WORD_DECAY_DAYS = 7  # Days after which usage counts decay

    def __init__(self, base_dir: str = None):
        """
        Initialize the keywords manager

        Args:
            base_dir: Base directory for keyword files (defaults to project root)
        """
        if base_dir is None:
            # Find project root (parent of data/keywords)
            self.base_dir = Path(__file__).parent.parent
        else:
            self.base_dir = Path(base_dir)

        # Keyword storage
        self._intents: Dict[str, KeywordEntry] = {}
        self._emotions: Dict[str, KeywordEntry] = {}
        self._topics: Dict[str, TopicEntry] = {}
        self._filters: Dict[str, List[str]] = {}
        self._hot_keywords: Dict[str, int] = {}
        self._user_keywords: Dict[str, Any] = {}

        # Usage tracking for hot word learning
        self._usage_tracker: Dict[str, int] = {}
        self._last_decay_time: float = time.time()

        # Load keyword libraries
        self._load_all_keywords()

    def _get_file_path(self, relative_path: str) -> Path:
        """Get absolute path for a keyword file"""
        return self.base_dir / relative_path

    def _load_json_file(self, file_path: Path, default: dict = None) -> dict:
        """Load a JSON file, returning default if not found"""
        if file_path.exists():
            try:
                with open(file_path, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except (json.JSONDecodeError, IOError) as e:
                logger.warning(f"Failed to load {file_path}: {e}")
        return default or {}

    def _save_json_file(self, file_path: Path, data: dict) -> bool:
        """Save data to a JSON file"""
        try:
            file_path.parent.mkdir(parents=True, exist_ok=True)
            with open(file_path, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            return True
        except IOError as e:
            logger.error(f"Failed to save {file_path}: {e}")
            return False

    def _load_all_keywords(self):
        """Load all keyword libraries"""
        # Load base keywords
        base_path = self._get_file_path(self.BASE_KEYWORDS_FILE)
        base_data = self._load_json_file(base_path, {})
        self._parse_base_keywords(base_data)

        # Load user keywords
        user_path = self._get_file_path(self.USER_KEYWORDS_FILE)
        self._user_keywords = self._load_json_file(user_path, {})
        self._merge_user_keywords()

        # Load hot keywords
        hot_path = self._get_file_path(self.HOT_KEYWORDS_FILE)
        hot_data = self._load_json_file(hot_path, {})
        self._hot_keywords = hot_data.get('hot_keywords', {})

        # Load additional topics
        topics_path = self._get_file_path(self.TOPICS_FILE)
        topics_data = self._load_json_file(topics_path, {})
        self._merge_topics(topics_data)

        logger.info(f"Loaded keywords: {len(self._intents)} intents, "
                   f"{len(self._emotions)} emotions, {len(self._topics)} topics, "
                   f"{len(self._hot_keywords)} hot words")

    def _parse_base_keywords(self, data: dict):
        """Parse base keywords data"""
        # Parse intents
        for intent_name, intent_data in data.get('intents', {}).items():
            self._intents[intent_name] = KeywordEntry(
                keywords=intent_data.get('keywords', []),
                priority=intent_data.get('priority', 1),
                usage_count=intent_data.get('usage_count', 0),
                description=intent_data.get('description', ''),
                synonyms=intent_data.get('english', [])
            )

        # Parse emotions
        for emotion_name, emotion_data in data.get('emotions', {}).items():
            self._emotions[emotion_name] = KeywordEntry(
                keywords=emotion_data.get('keywords', []),
                priority=emotion_data.get('threshold', 1),
                description=emotion_data.get('description', '')
            )

        # Parse topics
        for topic_name, topic_data in data.get('topics', {}).items():
            self._topics[topic_name] = TopicEntry(
                keywords=topic_data.get('keywords', []),
                synonyms=topic_data.get('synonyms', [])
            )

        # Parse filters
        self._filters = data.get('filters', {})

    def _merge_user_keywords(self):
        """Merge user-defined keywords"""
        # Merge custom intents
        for intent_name, intent_data in self._user_keywords.get('custom_intents', {}).items():
            if intent_name in self._intents:
                # Merge with existing
                existing = self._intents[intent_name]
                for kw in intent_data.get('keywords', []):
                    if kw not in existing.keywords:
                        existing.keywords.append(kw)
            else:
                # Add new
                self._intents[intent_name] = KeywordEntry(
                    keywords=intent_data.get('keywords', []),
                    priority=intent_data.get('priority', 1)
                )

        # Merge custom topics
        for topic_name, topic_data in self._user_keywords.get('custom_topics', {}).items():
            if topic_name in self._topics:
                existing = self._topics[topic_name]
                for kw in topic_data.get('keywords', []):
                    if kw not in existing.keywords:
                        existing.keywords.append(kw)
            else:
                self._topics[topic_name] = TopicEntry(
                    keywords=topic_data.get('keywords', []),
                    synonyms=topic_data.get('synonyms', [])
                )

    def _merge_topics(self, topics_data: dict):
        """Merge additional topics from topics.json"""
        for topic_name, topic_data in topics_data.get('topics', {}).items():
            if topic_name not in self._topics:
                self._topics[topic_name] = TopicEntry(
                    keywords=topic_data.get('keywords', []),
                    synonyms=topic_data.get('synonyms', [])
                )

    # === Intent Classification ===

    def get_intent_keywords(self, intent_type: str) -> List[str]:
        """Get keywords for a specific intent type"""
        if intent_type in self._intents:
            entry = self._intents[intent_type]
            return entry.keywords + entry.synonyms
        return []

    def match_intent(self, text: str) -> Optional[str]:
        """
        Match text against intent keywords

        Args:
            text: Input text to match

        Returns:
            Matched intent type or None
        """
        text_lower = text.lower().strip()

        # Sort intents by priority (lower number = higher priority)
        sorted_intents = sorted(
            self._intents.items(),
            key=lambda x: x[1].priority
        )

        for intent_name, entry in sorted_intents:
            all_keywords = entry.keywords + entry.synonyms
            if any(kw in text_lower for kw in all_keywords):
                # Track usage for hot word learning
                self._track_usage(intent_name, all_keywords)
                return intent_name

        return None

    def has_intent_keyword(self, text: str, intent_type: str) -> bool:
        """Check if text contains keywords for a specific intent"""
        keywords = self.get_intent_keywords(intent_type)
        text_lower = text.lower().strip()
        return any(kw in text_lower for kw in keywords)

    # === Emotion Detection ===

    def get_emotion_keywords(self, emotion_type: str) -> List[str]:
        """Get keywords for a specific emotion type"""
        if emotion_type in self._emotions:
            return self._emotions[emotion_type].keywords
        return []

    def detect_emotion(self, text: str) -> str:
        """
        Detect emotion from text

        Args:
            text: Input text

        Returns:
            Emotion label ('complaint', 'negative', 'positive', or 'neutral')
        """
        text_lower = text.lower().strip()

        # Check complaint
        complaint_kws = self.get_emotion_keywords('complaint')
        if any(kw in text_lower for kw in complaint_kws):
            return 'complaint'

        # Check negative
        negative_kws = self.get_emotion_keywords('negative')
        if any(kw in text_lower for kw in negative_kws):
            return 'negative'

        # Check positive
        positive_kws = self.get_emotion_keywords('positive')
        if any(kw in text_lower for kw in positive_kws):
            return 'positive'

        return 'neutral'

    # === Topic Extraction ===

    def get_topic_keywords(self, topic: str) -> List[str]:
        """Get all keywords (including synonyms) for a topic"""
        if topic in self._topics:
            entry = self._topics[topic]
            return entry.keywords + entry.synonyms
        return []

    def extract_topic(self, text: str) -> Optional[str]:
        """
        Extract topic from text

        Args:
            text: Input text

        Returns:
            Matched topic name or None
        """
        text_lower = text.lower().strip()

        for topic_name, entry in self._topics.items():
            all_keywords = entry.keywords + entry.synonyms
            if any(kw in text_lower for kw in all_keywords):
                return topic_name

        return None

    def get_all_topics(self) -> List[str]:
        """Get list of all defined topics"""
        return list(self._topics.keys())

    # === Filter Phrases ===

    def get_filter_phrases(self, filter_type: str) -> List[str]:
        """Get filter phrases by type"""
        return self._filters.get(filter_type, [])

    # === Hot Word Learning ===

    def _track_usage(self, category: str, keywords: List[str]):
        """Track keyword usage for hot word learning"""
        # Check if decay is needed
        self._maybe_decay_usage()

        # Track each matched keyword
        for kw in keywords:
            kw_lower = kw.lower()
            self._usage_tracker[kw_lower] = self._usage_tracker.get(kw_lower, 0) + 1

            # Check if should become hot word
            if self._usage_tracker[kw_lower] >= self.HOT_WORD_THRESHOLD:
                self._add_hot_keyword(kw_lower, self._usage_tracker[kw_lower])

    def _maybe_decay_usage(self):
        """Decay usage counts periodically"""
        now = time.time()
        decay_interval = self.HOT_WORD_DECAY_DAYS * 24 * 60 * 60

        if now - self._last_decay_time > decay_interval:
            self._decay_usage()
            self._last_decay_time = now

    def _decay_usage(self):
        """Decay all usage counts by 50%"""
        for kw in list(self._usage_tracker.keys()):
            self._usage_tracker[kw] = max(0, self._usage_tracker[kw] // 2)
            if self._usage_tracker[kw] == 0:
                del self._usage_tracker[kw]

        # Also decay hot keyword counts
        for kw in list(self._hot_keywords.keys()):
            self._hot_keywords[kw] = max(0, self._hot_keywords[kw] // 2)
            if self._hot_keywords[kw] == 0:
                del self._hot_keywords[kw]

    def _add_hot_keyword(self, keyword: str, count: int):
        """Add or update a hot keyword"""
        if keyword not in self._hot_keywords or self._hot_keywords[keyword] < count:
            self._hot_keywords[keyword] = count
            self._save_hot_keywords()
            logger.debug(f"Added hot keyword: {keyword} (count: {count})")

    def _save_hot_keywords(self):
        """Save hot keywords to file"""
        hot_path = self._get_file_path(self.HOT_KEYWORDS_FILE)
        data = {
            "version": "1.0.0",
            "updated_at": datetime.now().isoformat(),
            "description": "热词库 - 基于用户使用习惯自动学习的高频词汇",
            "hot_keywords": self._hot_keywords,
            "learning_stats": {
                "total_learned": len(self._hot_keywords),
                "last_updated": datetime.now().isoformat()
            }
        }
        self._save_json_file(hot_path, data)

    def get_hot_keywords(self) -> Dict[str, int]:
        """Get all hot keywords with their counts"""
        return self._hot_keywords.copy()

    def is_hot_keyword(self, keyword: str) -> bool:
        """Check if a keyword is in the hot word library"""
        return keyword.lower() in self._hot_keywords

    def get_hot_keyword_priority(self, keyword: str) -> int:
        """
        Get priority boost for hot keywords

        Returns:
            Priority boost (higher count = higher boost)
        """
        kw_lower = keyword.lower()
        if kw_lower in self._hot_keywords:
            count = self._hot_keywords[kw_lower]
            # Boost based on usage count
            if count >= 100:
                return 10
            elif count >= 50:
                return 5
            elif count >= 20:
                return 3
            else:
                return 1
        return 0

    # === User Custom Keywords ===

    def add_custom_keyword(self, category: str, name: str, keywords: List[str],
                          priority: int = 1) -> bool:
        """
        Add a custom keyword entry

        Args:
            category: Category ('intent', 'topic', 'emotion')
            name: Name of the keyword entry
            keywords: List of keywords
            priority: Priority level

        Returns:
            True if successful
        """
        if category == 'intent':
            self._intents[name] = KeywordEntry(
                keywords=keywords,
                priority=priority
            )
        elif category == 'topic':
            self._topics[name] = TopicEntry(
                keywords=keywords
            )
        elif category == 'emotion':
            self._emotions[name] = KeywordEntry(
                keywords=keywords,
                priority=priority
            )
        else:
            logger.warning(f"Unknown category: {category}")
            return False

        # Save to user keywords file
        self._save_user_keywords()
        return True

    def _save_user_keywords(self):
        """Save user-defined keywords to file"""
        user_path = self._get_file_path(self.USER_KEYWORDS_FILE)
        data = {
            "version": "1.0.0",
            "updated_at": datetime.now().isoformat(),
            "description": "用户自定义关键词库",
            "custom_intents": {
                name: {"keywords": entry.keywords, "priority": entry.priority}
                for name, entry in self._intents.items()
            },
            "custom_topics": {
                name: {"keywords": entry.keywords, "synonyms": entry.synonyms}
                for name, entry in self._topics.items()
            },
            "custom_emotions": {
                name: {"keywords": entry.keywords}
                for name, entry in self._emotions.items()
            }
        }
        self._save_json_file(user_path, data)

    # === Utility Methods ===

    def reload_keywords(self):
        """Reload all keyword libraries from files"""
        self._load_all_keywords()
        logger.info("Reloaded all keyword libraries")

    def get_stats(self) -> Dict[str, Any]:
        """Get keyword library statistics"""
        return {
            "intents": len(self._intents),
            "emotions": len(self._emotions),
            "topics": len(self._topics),
            "hot_keywords": len(self._hot_keywords),
            "filters": len(self._filters),
        }

    def search_keywords(self, query: str) -> Dict[str, List[str]]:
        """
        Search for keywords matching a query

        Args:
            query: Search query

        Returns:
            Dictionary of category -> matching keywords
        """
        query_lower = query.lower().strip()
        results = {
            "intents": [],
            "topics": [],
            "emotions": [],
            "hot": []
        }

        # Search intents
        for name, entry in self._intents.items():
            if query_lower in name.lower():
                results["intents"].append(name)
            for kw in entry.keywords + entry.synonyms:
                if query_lower in kw.lower():
                    results["intents"].append(f"{name}: {kw}")

        # Search topics
        for name, entry in self._topics.items():
            if query_lower in name.lower():
                results["topics"].append(name)
            for kw in entry.keywords + entry.synonyms:
                if query_lower in kw.lower():
                    results["topics"].append(f"{name}: {kw}")

        # Search emotions
        for name, entry in self._emotions.items():
            if query_lower in name.lower():
                results["emotions"].append(name)
            for kw in entry.keywords:
                if query_lower in kw.lower():
                    results["emotions"].append(f"{name}: {kw}")

        # Search hot keywords
        for kw in self._hot_keywords:
            if query_lower in kw.lower():
                results["hot"].append(kw)

        return results


# Global instance (singleton pattern)
_keywords_manager: Optional[KeywordsManager] = None


def get_keywords_manager() -> KeywordsManager:
    """Get the global KeywordsManager instance"""
    global _keywords_manager
    if _keywords_manager is None:
        _keywords_manager = KeywordsManager()
    return _keywords_manager
