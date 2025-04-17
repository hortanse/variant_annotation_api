from typing import List, Optional
from fastapi import APIRouter, UploadFile, File, HTTPException, Query, BackgroundTasks
from fastapi.responses import JSONResponse
from pathlib import Path
from enum import Enum
import time
import logging

from .models import (
    Variant,
    VariantCreate,
    AnnotationResponse,
    UploadResponse,
    StatsResponse
)
from .annotator import VariantAnnotator
from .config import settings

# Create router with API prefix
router = APIRouter(prefix=settings.API_V1_STR)

# Initialize annotator
annotator = VariantAnnotator()

class AnnotationMode(str, Enum):
    CLI = "cli"
    REST = "rest"
# In-memory storage for variants (replace with database in production)
variants: dict = {}
processing_status: dict = {"is_processing": False, "message": ""}

## Upload & annotate VCF endpoints
@router.post("/upload", response_model=UploadResponse)
async def upload_vcf(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    mode: str = Query("rest", description="Annotation mode: 'cli' or 'rest'"),
    batch: bool = Query(False, description="Enable batch processing")
):
    """
    Upload a VCF file for processing.
    
    Args:
        file: The VCF file to upload
        mode: Annotation mode ('cli' or 'rest')
        batch: Whether to enable batch processing
    """
    # Validate file extension
    file_ext = Path(file.filename).suffix.lower()
    if file_ext not in settings.ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail=f"File type not allowed. Allowed types: {', '.join(settings.ALLOWED_EXTENSIONS)}"
        )
    
    # Create upload directory if it doesn't exist
    settings.UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    
    # Save the uploaded file
    file_path = settings.UPLOAD_DIR / f"{int(time.time())}_{file.filename}"
    try:
        with open(file_path, "wb") as buffer:
            content = await file.read()
            buffer.write(content)
    except Exception as e:
        logging.error(f"Error saving file: {str(e)}")
        raise HTTPException(status_code=500, detail="Error saving uploaded file")
    
    # Process the file in the background
    background_tasks.add_task(process_vcf_file, file_path, mode, batch)
    
    return UploadResponse(
        message="VCF file uploaded successfully. Processing started...",
        variant_count=0,  # Will be updated after processing
        file_name=file.filename
    )

async def process_vcf_file(file_path: Path, mode: str, batch: bool):
    """Background task to process the VCF file."""
    global processing_status, variants
    processing_status = {"is_processing": True, "message": "Processing VCF file..."}
    start_time = time.time()

    try:
        if mode == "cli" and batch:
            # Batch CLI Mode (all variants at once)
            variant_records = []
            with open(file_path, 'r') as f:
                for line in f:
                    variant_data = annotator.parse_vcf_line(line)
                    if variant_data:
                        variant = VariantCreate(**variant_data)
                        variant_records.append(variant)

            # Batch annotate (write to VCF, run CLI, parse output)
            annotations_by_id = await annotator.annotate_batch_with_vep_cli(variant_records)

            for variant in variant_records:
                variant_id = f"{variant.chrom}_{variant.pos}_{variant.ref}_{variant.alt}"
                variants[variant_id] = Variant(
                    **variant.dict(),
                    id=variant_id,
                    annotations=annotations_by_id.get(variant_id, {})
                )

        else:
            # REST Mode (variant-by-variant)
            with open(file_path, 'r') as f:
                for line in f:
                    variant_data = annotator.parse_vcf_line(line)
                    if variant_data:
                        variant = VariantCreate(**variant_data)
                        variant_id = f"{variant.chrom}_{variant.pos}_{variant.ref}_{variant.alt}"

                        annotations = await annotator.annotate_variant(variant, mode)
                        variants[variant_id] = Variant(
                            **variant.dict(),
                            id=variant_id,
                            annotations=annotations
                        )

        processing_time = time.time() - start_time
        processing_status = {
            "is_processing": False,
            "message": f"Successfully processed {len(variants)} variants in {processing_time:.2f} seconds"
        }

    except Exception as e:
        logging.error(f"Error processing VCF file: {str(e)}")
        processing_status = {
            "is_processing": False,
            "message": f"Error processing VCF file: {str(e)}"
        }

## Get all 
@router.get("/variants", response_model=List[Variant])
async def list_variants(
    limit: int = Query(100, description="Number of variants to return"),
    offset: int = Query(0, description="Pagination offset"),
    chrom: Optional[str] = Query(None, description="Filter by chromosome"),
    min_quality: Optional[float] = Query(None, description="Minimum quality score")
):
    """
    List processed variants with optional filtering.
    """
    filtered_variants = list(variants.values())
    
    if chrom:
        filtered_variants = [v for v in filtered_variants if v.chrom == chrom]
    
    if min_quality is not None:
        filtered_variants = [v for v in filtered_variants if v.qual and v.qual >= min_quality]
    
    return filtered_variants[offset:offset + limit]

## Get variant by ID
@router.get("/variants/{variant_id}", response_model=Variant)
async def get_variant(variant_id: str):
    """
    Get detailed information for a specific variant.
    """
    if variant_id not in variants:
        raise HTTPException(status_code=404, detail="Variant not found")
    return variants[variant_id]

## Get variant annotations
@router.get("/variants/{variant_id}/annotations", response_model=AnnotationResponse)
async def get_variant_annotations(
    variant_id: str,
    mode: str = Query("rest", description="Annotation mode: 'cli' or 'rest'"),
    include: str = Query("all", description="Comma-separated list of annotation sources to include")
):
    """
    Get annotations for a specific variant.
    """
    if variant_id not in variants:
        raise HTTPException(status_code=404, detail="Variant not found")
    
    variant = variants[variant_id]
    sources = [s.strip() for s in include.split(',')]
    
    annotations = {}
    if "all" in sources or "vep" in sources:
        annotations["ensembl_vep"] = await annotator.get_ensembl_vep_annotation(variant)
    if "all" in sources or "clinvar" in sources:
        annotations["clinvar"] = await annotator.get_clinvar_annotation(variant)
    
    return AnnotationResponse(
        variant_id=variant_id,
        ensembl_vep=annotations.get("ensembl_vep"),
        clinvar=annotations.get("clinvar")
    )

## Stats endpoint
@router.get("/stats", response_model=StatsResponse)
async def get_stats():
    """
    Get statistics about processed variants and annotations.
    """
    total_variants = len(variants)
    variant_types = {}
    success_rates = {
        "ensembl_vep": 0,
        "clinvar": 0
    }
    
    for variant in variants.values():
        # Count variant types
        var_type = f"{len(variant.ref)}_{len(variant.alt)}"
        variant_types[var_type] = variant_types.get(var_type, 0) + 1
        
        # Calculate success rates
        if variant.annotations.get("ensembl_vep"):
            success_rates["ensembl_vep"] += 1
        if variant.annotations.get("clinvar"):
            success_rates["clinvar"] += 1
    
    if total_variants > 0:
        success_rates = {k: v/total_variants for k, v in success_rates.items()}
    
    return StatsResponse(
        total_variants=total_variants,
        variant_types=variant_types,
        annotation_success_rates=success_rates,
        last_processed=processing_status.get("message", "")
    )
