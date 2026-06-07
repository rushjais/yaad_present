from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    supabase_url: str = ""
    supabase_service_key: str = ""

    # Moss — on-device SDK (pip install moss)
    # Accepts MOSS_PROJECT_ID (canonical) or MOSS_ID (legacy alias teammates may use)
    moss_project_id: str = Field("", alias="MOSS_PROJECT_ID")
    moss_project_key: str = Field("", alias="MOSS_PROJECT_KEY")
    moss_index: str = "yaad_amma"

    # Groq — LLM gateway (primary)
    groq_api_key: str = ""

    # TrueFoundry — LLM gateway (alternative; needs base_url + model [CONFIRM])
    truefoundry_api_key: str = ""
    truefoundry_base_url: str = ""   # e.g. https://<workspace>.truefoundry.com/api/llm/v1
    truefoundry_model: str = ""

    # MiniMax — TTS (global endpoint: api.minimaxi.chat)
    minimax_api_key: str = ""
    minimax_group_id: str = ""
    minimax_base_url: str = "https://api.minimaxi.chat"  # confirmed working endpoint

    # OpenAI — vision fallback (optional)
    openai_api_key: str = ""

    # Unsiloed — document ingestion (medical PDFs)
    unsiloed_api_key: str = ""
    unsiloed_base_url: str = "https://platformbackend.unsiloed.ai"

    confidence_threshold: float = 0.45  # τ — below this → safe refusal

    # retrieval scoring weights
    alpha: float = 0.5   # semantic
    beta: float = 0.25   # recency
    gamma: float = 0.15  # salience
    delta: float = 0.10  # graph proximity
    recency_lambda: float = 0.01  # decay rate (per hour)

    @field_validator(
        "supabase_url", "supabase_service_key",
        "groq_api_key", "truefoundry_api_key", "truefoundry_base_url",
        "minimax_api_key", "minimax_group_id",
        "openai_api_key",
        "unsiloed_api_key", "unsiloed_base_url",
        mode="before",
    )
    @classmethod
    def strip_whitespace(cls, v: str) -> str:
        return v.strip().rstrip("/") if isinstance(v, str) else v

    @field_validator("moss_project_id", "moss_project_key", mode="before")
    @classmethod
    def strip_moss(cls, v: str) -> str:
        return v.strip() if isinstance(v, str) else v

    def __init__(self, **data):
        import os
        # Support legacy env var names MOSS_ID / MOSS_API_KEY
        if not data.get("MOSS_PROJECT_ID") and os.environ.get("MOSS_ID"):
            data["MOSS_PROJECT_ID"] = os.environ["MOSS_ID"]
        if not data.get("MOSS_PROJECT_KEY") and os.environ.get("MOSS_API_KEY"):
            data["MOSS_PROJECT_KEY"] = os.environ["MOSS_API_KEY"]
        super().__init__(**data)


settings = Settings()
