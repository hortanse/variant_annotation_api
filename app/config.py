from typing import Optional
from pydantic import BaseSettings, Field, validator
from pathlib import Path
import os

class Settings(BaseSettings):
    """Application settings."""
    
    # API Settings
    API_V1_STR: str = "/api/v1"
    PROJECT_NAME: str = "Variant Annotation and Interpretation API"
    VERSION: str = "1.0.0"
    DEBUG: bool = False
    
    # External API Settings
    ENSEMBL_VEP_URL: str = "https://rest.ensembl.org"
    CLINVAR_API_URL: str = "https://api.ncbi.nlm.nih.gov/variation/v0"
    ENSEMBL_API_KEY: Optional[str] = None
    CLINVAR_API_KEY: Optional[str] = None
    
    # File Upload Settings
    MAX_UPLOAD_SIZE: int = 10 * 1024 * 1024  # 10MB
    ALLOWED_EXTENSIONS: set = {".vcf", ".vcf.gz"}
    UPLOAD_DIR: Path = Path("data/uploads")
    PROCESSED_DIR: Path = Path("data/processed")
    
    # VEP Settings
    VEP_SCRIPT: str = "vep"
    VEP_DATA_DIR: Path = Path("data/vep_data")
    VEP_CACHE_DIR: Path = Path("data/vep_cache")
    VEP_SPECIES: str = "homo_sapiens"
    VEP_ASSEMBLY: str = "GRCh38"
    
    # Batch Processing Settings
    BATCH_SIZE: int = 1000
    MAX_CONCURRENT_JOBS: int = 4
    
    # Logging Settings
    LOG_LEVEL: str = "INFO"
    LOG_FORMAT: str = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    LOG_FILE: Optional[Path] = None
    
    class Config:
        env_file = ".env"
        case_sensitive = True
    
    @validator("UPLOAD_DIR", "PROCESSED_DIR", "VEP_DATA_DIR", "VEP_CACHE_DIR", pre=True)
    def create_directories(cls, v: Path) -> Path:
        """Create directories if they don't exist."""
        v = Path(v)
        v.mkdir(parents=True, exist_ok=True)
        return v
    
    @validator("LOG_FILE", pre=True)
    def setup_log_file(cls, v: Optional[Path]) -> Optional[Path]:
        """Setup log file if specified."""
        if v:
            v = Path(v)
            v.parent.mkdir(parents=True, exist_ok=True)
        return v
    
    @validator("VEP_SCRIPT", pre=True)
    def validate_vep_script(cls, v: str) -> str:
        """Validate VEP script path."""
        if not os.path.isfile(v) and not os.access(v, os.X_OK):
            raise ValueError(f"VEP script not found or not executable: {v}")
        return v
    
    @validator("ALLOWED_EXTENSIONS", pre=True)
    def validate_extensions(cls, v: set) -> set:
        """Validate file extensions."""
        if not all(ext.startswith('.') for ext in v):
            raise ValueError("All extensions must start with '.'")
        return v

# Create global settings instance
settings = Settings()

# Configure logging
import logging
logging.basicConfig(
    level=getattr(logging, settings.LOG_LEVEL),
    format=settings.LOG_FORMAT,
    filename=settings.LOG_FILE,
)
