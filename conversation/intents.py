"""Intent classification: which agent should own this turn.

Rule-based and deterministic on purpose: intent routing is a
load-bearing decision (it picks the model, the prompt and the grounding
strategy), and a keyword classifier is auditable, free and fast. The
``IntentClassifierPort`` seam is where an LLM- or embedding-based
classifier plugs in when the intent taxonomy outgrows keywords.
"""

from __future__ import annotations

import re
from enum import Enum, unique
from typing import Protocol

from core.logging import get_logger

logger = get_logger("conversation.intents")


@unique
class Intent(str, Enum):
    SUPPORT = "SUPPORT"      # something is broken / how do I ...
    SALES = "SALES"          # pricing, offers, buying modules
    ANALYTICS = "ANALYTICS"  # business performance questions
    TECHNICAL = "TECHNICAL"  # integration/API/hardware depth
    GENERAL = "GENERAL"      # greetings, everything else


class IntentClassifierPort(Protocol):
    def classify(self, text: str) -> Intent: ...


#: Keyword groups per intent, checked in priority order (first match wins).
_RULES: tuple[tuple[Intent, tuple[str, ...]], ...] = (
    (
        Intent.SUPPORT,
        (
            "не работает", "ошибка", "сломал", "проблема", "помог", "как настроить",
            "как включить", "не приходят", "пропада", "broken", "error", "issue",
            "not working", "doesn't work", "how do i", "how to", "help", "troubleshoot",
            "почему не", "not appearing", "not showing", "what should i check", "fix",
        ),
    ),
    (
        Intent.SALES,
        (
            "цена", "стоимость", "сколько стоит", "тариф", "купить", "подключить",
            "скидк", "оффер", "предложение", "price", "cost", "pricing", "buy",
            "subscribe", "offer", "discount", "quote",
        ),
    ),
    (
        Intent.ANALYTICS,
        (
            "выручка", "аналитик", "метрик", "retention", "продажи", "показатели",
            "roi", "окупаемость", "analyz", "analyse", "revenue", "metrics",
            "performance", "отчет", "отчёт", "report", "средний чек",
            "average ticket", "ltv", "заказов в месяц", "orders per month",
            "моего ресторана", "my restaurant",
        ),
    ),
    (
        Intent.TECHNICAL,
        (
            "api", "интеграц", "webhook", "sdk", "железо", "оборудование",
            "hardware", "network", "сеть", "integration", "database", "sql",
        ),
    ),
)


class RuleBasedIntentClassifier:
    """First-match keyword classifier over a normalised utterance."""

    def classify(self, text: str) -> Intent:
        normalized = re.sub(r"\s+", " ", text.lower())
        for intent, keywords in _RULES:
            if any(keyword in normalized for keyword in keywords):
                logger.debug("Intent %s for %r", intent.value, text[:60])
                return intent
        return Intent.GENERAL
