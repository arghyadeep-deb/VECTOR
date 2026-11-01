"""Title generator — generate session titles from conversation content."""

import re

STOP_WORDS = {"the", "a", "an", "is", "are", "was", "were", "be", "been",
              "being", "have", "has", "had", "do", "does", "did", "will",
              "would", "could", "should", "may", "might", "shall", "can",
              "to", "of", "in", "for", "on", "with", "at", "by", "from",
              "as", "into", "through", "during", "before", "after", "about"}


def generate_title(messages: list[dict], max_words: int = 8) -> str:
    """Generate a title from the first user message."""
    for msg in messages:
        if msg.get("role") == "user":
            text = msg.get("content", "")
            words = re.findall(r'\b[a-zA-Z]{3,}\b', text)
            significant = [w for w in words if w.lower() not in STOP_WORDS]
            title = " ".join(significant[:max_words])
            return title.capitalize() if title else "New conversation"
    return "New conversation"
