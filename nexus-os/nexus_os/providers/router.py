"""Smart provider routing — selects the best available provider per task.

Combines:
- Static catalog data (awesome-free-llm-apiss)
- Live availability (free-llm-api-resources pattern)
- Runtime rate limit tracking
- Quality / speed / context ranking

The router is the "killer feature" of the unified platform: automatic
selection of the best free LLM provider for each call.
"""

from __future__ import annotations

import os
import logging
from dataclasses import dataclass
from enum import Enum
from typing import Optional

from .catalog import ProviderCatalog, Provider, Model
from .rate_limiter import RateLimiter

logger = logging.getLogger(__name__)


class RoutePreference(str, Enum):
    SPEED = "speed"
    QUALITY = "quality"
    COST = "cost"       # cheapest/free-first
    BALANCED = "balanced"


@dataclass(frozen=True)
class RouteResult:
    """The router's decision for a single call."""
    provider: Provider
    model: Model
    score: float
    reason: str


class ProviderRouter:
    """Selects the best provider+model for a given request.

    Usage:
        router = ProviderRouter()
        result = router.select(min_context=32_000, prefer="quality")
        if result:
            print(f"Use {result.provider.name}/{result.model.id}")
    """

    def __init__(
        self,
        catalog: Optional[ProviderCatalog] = None,
        rate_limiter: Optional[RateLimiter] = None,
    ) -> None:
        self.catalog = catalog or ProviderCatalog()
        self.rate_limiter = rate_limiter or RateLimiter()

        # Register all known providers with the rate limiter
        for p in self.catalog.all_providers():
            self.rate_limiter.register(p.name, p.requests_per_minute, p.tokens_per_minute)

    def select(
        self,
        min_context: int = 8192,
        prefer: str | RoutePreference = RoutePreference.BALANCED,
        task_type: str = "",
        fallback_chain: bool = True,
        exclude: Optional[set[str]] = None,
    ) -> Optional[RouteResult]:
        """Select the best available provider and model.

        Args:
            min_context: Minimum context window required.
            prefer: Routing preference (speed/quality/cost/balanced).
            task_type: Optional task hint (e.g., "code_generation").
            fallback_chain: If True, try multiple candidates.
            exclude: Provider names to skip.

        Returns:
            RouteResult or None if no provider is available.
        """
        if isinstance(prefer, str):
            prefer = RoutePreference(prefer)
        exclude = exclude or set()

        candidates: list[tuple[float, Provider, Model, str]] = []

        for provider in self.catalog.enabled_providers():
            if provider.name in exclude:
                continue

            # Check if provider has a usable API key
            if provider.requires_key and not os.environ.get(provider.api_key_env):
                continue

            for model in provider.models:
                if model.context_window < min_context:
                    continue

                # Check rate limits
                if not self.rate_limiter.can_proceed(provider.name):
                    continue

                score, reason = self._score(provider, model, prefer, task_type)
                candidates.append((score, provider, model, reason))

        if not candidates:
            logger.warning("No available provider for min_context=%d, prefer=%s", min_context, prefer)
            return None

        # Sort by score descending
        candidates.sort(key=lambda c: c[0], reverse=True)
        best_score, best_provider, best_model, best_reason = candidates[0]

        return RouteResult(
            provider=best_provider,
            model=best_model,
            score=best_score,
            reason=best_reason,
        )

    def _score(
        self,
        provider: Provider,
        model: Model,
        prefer: RoutePreference,
        task_type: str,
    ) -> tuple[float, str]:
        """Score a provider/model pair. Higher is better."""
        quality = model.quality_score
        speed = min(model.speed_toks_per_sec / 2600.0 * 100, 100)  # normalized to Cerebras
        context = min(model.context_window / 1_000_000 * 100, 100)

        # Tier bonus: free > freemium > paid
        tier_bonus = {"free": 10, "freemium": 5, "paid": 0}.get(provider.tier, 0)

        if prefer == RoutePreference.QUALITY:
            score = quality * 0.6 + speed * 0.1 + context * 0.1 + tier_bonus * 0.2
            reason = f"quality={quality:.0f}, speed={speed:.0f}"
        elif prefer == RoutePreference.SPEED:
            score = speed * 0.6 + quality * 0.15 + context * 0.05 + tier_bonus * 0.2
            reason = f"speed={model.speed_toks_per_sec:.0f} tok/s, quality={quality:.0f}"
        elif prefer == RoutePreference.COST:
            score = tier_bonus * 0.5 + quality * 0.2 + speed * 0.15 + context * 0.15
            reason = f"tier={provider.tier}, quality={quality:.0f}"
        else:  # BALANCED
            score = quality * 0.35 + speed * 0.25 + context * 0.15 + tier_bonus * 0.25
            reason = f"balanced: q={quality:.0f} s={speed:.0f} ctx={model.context_window}"

        # Task-type bonuses
        if task_type == "code_generation" and "code" in model.id.lower():
            score += 8
        if task_type == "reasoning" and model.quality_score >= 85:
            score += 5

        return round(score, 2), reason

    def list_available(self, min_context: int = 0) -> list[RouteResult]:
        """List all currently available provider/model pairs."""
        results = []
        for provider in self.catalog.enabled_providers():
            if provider.requires_key and not os.environ.get(provider.api_key_env):
                continue
            for model in provider.models:
                if model.context_window < min_context:
                    continue
                results.append(RouteResult(
                    provider=provider, model=model,
                    score=model.quality_score,
                    reason=f"{provider.name}/{model.id}",
                ))
        results.sort(key=lambda r: r.score, reverse=True)
        return results
