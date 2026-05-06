"""Static provider catalog — derived from awesome-free-llm-apiss data.json pattern.

Contains structured provider metadata: base URLs, models, rate limits,
context windows, and quality/speed scores used by the router.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional


@dataclass(frozen=True)
class Model:
    id: str
    name: str
    context_window: int
    max_output: int = 4096
    quality_score: float = 70.0       # 0-100, subjective benchmark composite
    speed_toks_per_sec: float = 100.0 # approximate output speed


@dataclass
class Provider:
    name: str
    base_url: str
    api_key_env: str = ""             # env var name that holds the API key
    models: list[Model] = field(default_factory=list)
    requests_per_minute: int = 30
    tokens_per_minute: int = 60_000
    tier: str = "free"                # free | freemium | paid
    requires_key: bool = False
    enabled: bool = True

    def find_model(self, model_id: str) -> Optional[Model]:
        for m in self.models:
            if m.id == model_id:
                return m
        return None


class ProviderCatalog:
    """In-memory provider catalog.

    In production this would load from providers/data/providers.json
    (merged from awesome-free-llm-apiss + free-llm-api-resources).
    Here we seed with representative free-tier providers.
    """

    def __init__(self) -> None:
        self._providers: dict[str, Provider] = {}
        self._seed_defaults()

    def _seed_defaults(self) -> None:
        """Seed with real free-tier provider metadata."""
        providers = [
            Provider(
                name="groq",
                base_url="https://api.groq.com/openai/v1",
                api_key_env="GROQ_API_KEY",
                requests_per_minute=30,
                tokens_per_minute=14400,
                tier="free",
                requires_key=True,
                models=[
                    Model("llama-3.3-70b-versatile", "Llama 3.3 70B", 128_000,
                          quality_score=82, speed_toks_per_sec=500),
                    Model("llama-3.1-8b-instant", "Llama 3.1 8B Instant", 128_000,
                          quality_score=65, speed_toks_per_sec=750),
                    Model("gemma2-9b-it", "Gemma 2 9B", 8192,
                          quality_score=60, speed_toks_per_sec=600),
                ],
            ),
            Provider(
                name="cerebras",
                base_url="https://api.cerebras.ai/v1",
                api_key_env="CEREBRAS_API_KEY",
                requests_per_minute=30,
                tokens_per_minute=60_000,
                tier="free",
                requires_key=True,
                models=[
                    Model("llama3.1-8b", "Llama 3.1 8B", 8192,
                          quality_score=60, speed_toks_per_sec=2600),
                    Model("llama3.1-70b", "Llama 3.1 70B", 8192,
                          quality_score=78, speed_toks_per_sec=1800),
                ],
            ),
            Provider(
                name="openrouter",
                base_url="https://openrouter.ai/api/v1",
                api_key_env="OPENROUTER_API_KEY",
                requests_per_minute=20,
                tokens_per_minute=40_000,
                tier="freemium",
                requires_key=True,
                models=[
                    Model("meta-llama/llama-3.1-8b-instruct:free", "Llama 3.1 8B (free)", 16384,
                          quality_score=58, speed_toks_per_sec=200),
                    Model("mistralai/mistral-7b-instruct:free", "Mistral 7B (free)", 32768,
                          quality_score=62, speed_toks_per_sec=180),
                    Model("google/gemma-2-9b-it:free", "Gemma 2 9B (free)", 8192,
                          quality_score=60, speed_toks_per_sec=150),
                ],
            ),
            Provider(
                name="google",
                base_url="https://generativelanguage.googleapis.com/v1beta",
                api_key_env="GOOGLE_API_KEY",
                requests_per_minute=15,
                tokens_per_minute=32_000,
                tier="free",
                requires_key=True,
                models=[
                    Model("gemini-2.0-flash", "Gemini 2.0 Flash", 1_048_576,
                          quality_score=88, speed_toks_per_sec=400),
                    Model("gemini-1.5-flash", "Gemini 1.5 Flash", 1_048_576,
                          quality_score=80, speed_toks_per_sec=350),
                ],
            ),
            Provider(
                name="huggingface",
                base_url="https://api-inference.huggingface.co/models",
                api_key_env="HF_TOKEN",
                requests_per_minute=10,
                tokens_per_minute=20_000,
                tier="free",
                requires_key=True,
                models=[
                    Model("meta-llama/Meta-Llama-3.1-70B-Instruct", "Llama 3.1 70B HF", 131072,
                          quality_score=80, speed_toks_per_sec=80),
                ],
            ),
            Provider(
                name="github",
                base_url="https://models.inference.ai.azure.com",
                api_key_env="GITHUB_TOKEN",
                requests_per_minute=15,
                tokens_per_minute=40_000,
                tier="free",
                requires_key=True,
                models=[
                    Model("gpt-4o-mini", "GPT-4o Mini", 128_000,
                          quality_score=85, speed_toks_per_sec=300),
                    Model("Meta-Llama-3.1-405B-Instruct", "Llama 3.1 405B", 128_000,
                          quality_score=85, speed_toks_per_sec=60),
                ],
            ),
            Provider(
                name="mistral",
                base_url="https://api.mistral.ai/v1",
                api_key_env="MISTRAL_API_KEY",
                requests_per_minute=30,
                tokens_per_minute=60_000,
                tier="free",
                requires_key=True,
                models=[
                    Model("mistral-small-latest", "Mistral Small", 32768,
                          quality_score=75, speed_toks_per_sec=350),
                    Model("codestral-latest", "Codestral", 32768,
                          quality_score=80, speed_toks_per_sec=300),
                ],
            ),
            Provider(
                name="kilo",
                base_url="https://api.kilo.ai/api/gateway",
                api_key_env="KILO_API_KEY",
                requests_per_minute=30,
                tokens_per_minute=100_000,
                tier="free",
                requires_key=True,
                models=[
                    Model("inclusionai/ling-2.6-1t:free", "Ling 2.6 1T", 262_144,
                          quality_score=99, speed_toks_per_sec=80),
                    Model("stepfun/step-3.5-flash:free", "Step 3.5 Flash", 262_144,
                          quality_score=93, speed_toks_per_sec=74),
                    Model("nvidia/nemotron-3-super-120b-a12b:free", "Nemotron 3 Super 120B", 262_144,
                          quality_score=62, speed_toks_per_sec=60),
                    Model("tencent/hy3-preview:free", "HY3 Preview", 262_144,
                          quality_score=56, speed_toks_per_sec=74),
                    Model("nvidia/nemotron-3-nano-omni-30b-a3b-reasoning:free", "Nemotron 3 Nano 30B", 256_000,
                          quality_score=41, speed_toks_per_sec=45),
                    Model("poolside/laguna-m.1:free", "Laguna M.1", 131_072,
                          quality_score=41, speed_toks_per_sec=45),
                    Model("poolside/laguna-xs.2:free", "Laguna XS.2", 131_072,
                          quality_score=41, speed_toks_per_sec=45),
                    Model("baidu/qianfan-ocr-fast:free", "Qianfan OCR Fast", 65_536,
                          quality_score=11, speed_toks_per_sec=30),
                ],
            ),
        ]
        for p in providers:
            self._providers[p.name] = p

    def get(self, name: str) -> Optional[Provider]:
        return self._providers.get(name)

    def all_providers(self) -> list[Provider]:
        return list(self._providers.values())

    def enabled_providers(self) -> list[Provider]:
        return [p for p in self._providers.values() if p.enabled]

    def all_models(self) -> list[tuple[Provider, Model]]:
        result = []
        for p in self._providers.values():
            for m in p.models:
                result.append((p, m))
        return result

    def register(self, provider: Provider) -> None:
        self._providers[provider.name] = provider

