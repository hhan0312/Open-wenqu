from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    deepseek_api_key: str = ""
    deepseek_base_url: str = "https://api.deepseek.com"
    deepseek_model: str = "deepseek-v4-flash"
    open_wenqu_database_url: str = "sqlite:///./data/open_wenqu.db"
    prompt_version: str = "1"
    repo_root: Path = Path(__file__).resolve().parents[2]

    @property
    def skills_root(self) -> Path:
        return self.repo_root / "skills"


def get_settings() -> Settings:
    return Settings()
