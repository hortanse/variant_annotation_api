from typing import Dict, List, Optional, Any
from pydantic import BaseModel, Field, validator, root_validator
from datetime import datetime

class VariantBase(BaseModel):
    """Base model for variant data."""
    chrom: str = Field(..., description="Chromosome name")
    pos: int = Field(..., description="1-based position on the chromosome")
    ref: str = Field(..., description="Reference allele")
    alt: str = Field(..., description="Alternate allele")
    qual: Optional[float] = Field(None, description="Quality score")
    filter: Optional[str] = Field(None, description="Filter status")
    info: Dict[str, Any] = Field(default_factory=dict, description="Additional INFO fields")

    @validator('chrom')
    def validate_chrom(cls, v):
        """Validate chromosome format."""
        # Remove 'chr' prefix if present
        v = v.lower().replace('chr', '')
        # Check if it's a valid chromosome (1-22, X, Y, MT)
        if v not in [str(i) for i in range(1, 23)] + ['x', 'y', 'mt']:
            raise ValueError(f"Invalid chromosome: {v}")
        return v

    @validator('ref', 'alt')
    def validate_alleles(cls, v):
        """Validate allele format."""
        if not all(base in 'ACGTN' for base in v.upper()):
            raise ValueError(f"Invalid allele: {v}")
        return v

class VariantCreate(VariantBase):
    """Model for creating new variants."""
    pass

class Variant(VariantBase):
    """Model for variant with annotations."""
    id: str = Field(..., description="Unique variant identifier")
    annotations: Dict[str, Any] = Field(default_factory=dict, description="Variant annotations")
    created_at: datetime = Field(default_factory=datetime.now, description="Creation timestamp")
    updated_at: datetime = Field(default_factory=datetime.now, description="Last update timestamp")

    @validator('id')
    def validate_id(cls, v, values):
        """Generate ID if not provided."""
        if not v:
            return f"{values['chrom']}_{values['pos']}_{values['ref']}_{values['alt']}"
        return v

class AnnotationResponse(BaseModel):
    """Model for variant annotation response."""
    variant_id: str = Field(..., description="Variant identifier")
    ensembl_vep: Optional[Dict[str, Any]] = Field(None, description="Ensembl VEP annotations")
    clinvar: Optional[Dict[str, Any]] = Field(None, description="ClinVar annotations")
    error: Optional[str] = Field(None, description="Error message if annotation failed")

    class Config:
        schema_extra = {
            "example": {
                "variant_id": "1_123456_A_G",
                "ensembl_vep": {
                    "consequence": ["missense_variant"],
                    "impact": "MODERATE",
                    "gene": "BRCA1",
                    "transcript": "ENST00000357654",
                    "protein_change": "p.Arg123Gly",
                    "gnomad_af": 0.001
                },
                "clinvar": {
                    "clinical_significance": "Pathogenic",
                    "review_status": "reviewed by expert panel",
                    "conditions": ["Breast-ovarian cancer, familial 1"],
                    "variation_id": "12345"
                }
            }
        }

class UploadResponse(BaseModel):
    """Model for file upload response."""
    message: str = Field(..., description="Status message")
    variant_count: int = Field(0, description="Number of variants processed")
    file_name: str = Field(..., description="Name of the uploaded file")
    processing_time: Optional[float] = Field(None, description="Processing time in seconds")

    class Config:
        schema_extra = {
            "example": {
                "message": "VCF file uploaded successfully. Processing started...",
                "variant_count": 0,
                "file_name": "example.vcf",
                "processing_time": 1.23
            }
        }

class StatsResponse(BaseModel):
    """Model for statistics response."""
    total_variants: int = Field(..., description="Total number of processed variants")
    variant_types: Dict[str, int] = Field(..., description="Count of different variant types")
    annotation_success_rates: Dict[str, float] = Field(..., description="Success rates for different annotation sources")
    last_processed: str = Field(..., description="Message about last processing status")

    class Config:
        schema_extra = {
            "example": {
                "total_variants": 1000,
                "variant_types": {
                    "1_1": 800,
                    "1_2": 150,
                    "2_2": 50
                },
                "annotation_success_rates": {
                    "ensembl_vep": 0.95,
                    "clinvar": 0.85
                },
                "last_processed": "Successfully processed 1000 variants"
            }
        }
