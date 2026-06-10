from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # API-Football
    api_football_key: str = ""
    api_football_host: str = "v3.football.api-sports.io"

    # Anthropic
    anthropic_api_key: str = ""
    claude_model: str = "claude-sonnet-4-6"

    # Storage
    db_path: str = "data/worldcup.db"
    snapshot_dir: str = "data/snapshots"
    raw_data_dir: str = "data/raw"

    # Model
    model_version: str = "v1.0-boosted"
    simulation_n_runs: int = 10000

    # Streamlit
    streamlit_port: int = 8501

    # Scraper rate limits
    fbref_rate_limit_secs: float = 2.0
    transfermarkt_rate_limit_secs: float = 3.0


settings = Settings()
