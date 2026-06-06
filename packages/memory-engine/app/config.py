from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    supabase_url: str = ""
    supabase_service_key: str = ""

    # [CONFIRM] on-device/WASM vs cloud + exact SDK
    moss_api_key: str = ""
    moss_base_url: str = "https://api.getmoss.dev"
    moss_index: str = "yaad_amma"

    openai_api_key: str = ""  # used for embeddings fallback if Moss cloud needs it

    confidence_threshold: float = 0.45  # τ — below this → safe refusal

    # retrieval scoring weights
    alpha: float = 0.5   # semantic
    beta: float = 0.25   # recency
    gamma: float = 0.15  # salience
    delta: float = 0.10  # graph proximity
    recency_lambda: float = 0.01  # decay rate (per hour)


settings = Settings()
