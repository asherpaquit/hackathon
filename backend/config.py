from pydantic_settings import BaseSettings
from pathlib import Path

BASE_DIR = Path(__file__).parent.parent


class Settings(BaseSettings):
    # Model selection (set in .env):
    #   OLLAMA_MODEL=qwen2.5:3b    → best for 4GB VRAM GPUs (GTX 1050 Ti, GTX 1650)
    #   OLLAMA_MODEL=llama3.2:3b   → fallback for 8GB RAM no-GPU builds
    #   OLLAMA_MODEL=mistral:7b    → best accuracy, needs 8GB VRAM or 16GB RAM
    ollama_model: str = "mistral:7b"
    ollama_host: str = "http://localhost:11434"

    # LOW_MEMORY_MODE=true → reduces workers, context window, and input size
    # Use this on machines with 8GB RAM (e.g. Ryzen 3 3200G + GTX 1050 Ti)
    low_memory_mode: bool = False

    upload_dir: Path = BASE_DIR / "backend" / "uploads"
    output_dir: Path = BASE_DIR / "outputs"
    max_upload_size_mb: int = 50

    model_config = {"env_file": BASE_DIR / ".env", "env_file_encoding": "utf-8"}


settings = Settings()
settings.upload_dir.mkdir(parents=True, exist_ok=True)
settings.output_dir.mkdir(parents=True, exist_ok=True)
