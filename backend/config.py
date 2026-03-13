from pydantic_settings import BaseSettings
from pathlib import Path

BASE_DIR = Path(__file__).parent.parent


class Settings(BaseSettings):
    # Local Ollama LLM settings — no API key required
    # Speed tips (set in .env or environment):
    #   OLLAMA_MODEL=llama3.2:3b         → ~3x faster than mistral:7b, great accuracy
    #   OLLAMA_MODEL=qwen2.5:7b          → best structured JSON accuracy at 7B
    #   OLLAMA_NUM_PARALLEL=4            → allow Ollama to run 4 concurrent requests
    #                                      (set this env var before starting Ollama)
    ollama_model: str = "mistral:7b"
    ollama_host: str = "http://localhost:11434"

    upload_dir: Path = BASE_DIR / "backend" / "uploads"
    output_dir: Path = BASE_DIR / "outputs"
    template_path: Path = BASE_DIR / "templates" / "ATL0347N25 Template.xlsm"
    max_upload_size_mb: int = 50

    model_config = {"env_file": BASE_DIR / ".env", "env_file_encoding": "utf-8"}


settings = Settings()
settings.upload_dir.mkdir(parents=True, exist_ok=True)
settings.output_dir.mkdir(parents=True, exist_ok=True)
