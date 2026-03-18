from pydantic import Field
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Application settings loaded from environment variables and .env file."""

    # Google Sheets
    google_sheets_credentials_path: str = "credentials.json"
    spreadsheet_id: str = ""
    input_sheet_name: str = "Homeowner Data"
    output_sheet_name: str = "Equity Reports"

    # OpenAI
    openai_api_key: str = ""
    openai_model: str = "gpt-4o-mini"
    openai_temperature: float = 0.4

    # Message
    sender_name: str = "Chris Lamm"

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}


settings = Settings()


def get_settings() -> Settings:
    """Return the module-level settings instance. Override in tests by monkey-patching."""
    return settings
