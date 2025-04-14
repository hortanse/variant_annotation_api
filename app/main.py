from fastapi import FastAPI, File, UploadFile, HTTPException, Query, BackgroundTasks
from fastapi.responses import JSONResponse
from typing import List, Dict, Any, Optional
from enum import Enum
import uvicorn
import os
import asyncio
from datetime import datetime

from .models import Variant, VariantCreate, AnnotationResponse, UploadResponse
from .annotator import VariantAnnotator
from .config import settings

app = FastAPI(
    title="Variant Annotation and Interpretation API",
    description="A lightweight yet extensible API service for uploading, parsing, and annotating genomic variants from VCF files",
    version="1.0.0",
    docs_url="/api/v1/docs",
    redoc_url="/api/v1/redoc",
    openapi_url="/api/v1/openapi.json"
)

class AnnotationMode(str, Enum):
    CLI = "cli"
    REST = "rest"

# In-memory storage for variants (replace with database in production)
variants: Dict[str, Variant] = {}
processing_status: Dict[str, Any] = {"is_processing": False, "message": ""}

@app.get("/api/v1/")
async def root():
    """Root endpoint with API information."""
    return {
        "message": "Welcome to the Variant Annotation and Interpretation API",
        "version": "1.0.0",
        "endpoints": {
            "upload": "/api/v1/upload - Upload and process VCF files",
            "variants": "/api/v1/variants - List processed variants",
            "variant_details": "/api/v1/variants/{variant_id} - Get variant details",
            "annotations": "/api/v1/variants/{variant_id}/annotations - Get variant annotations",
            "stats": "/api/v1/stats - Get annotation statistics"
        }
    }

@app.post("/api/v1/upload", response_model=UploadResponse)
async def upload_vcf(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    mode: AnnotationMode = Query(AnnotationMode.CLI, description="Annotation method to use"),
    batch: bool = Query(False, description="Enable batch processing")
):
    """
    Upload a VCF file for processing.
    
    Args:
        file: The VCF file to upload
        mode: Annotation method (cli or rest)
        batch: Whether to enable batch processing
    """
    if not file.filename.endswith(('.vcf', '.vcf.gz')):
        raise HTTPException(status_code=400, detail="Only VCF files are accepted")
    
    # Save the uploaded file
    file_path = f"data/uploads/{datetime.now().strftime('%Y%m%d_%H%M%S')}_{file.filename}"
    os.makedirs(os.path.dirname(file_path), exist_ok=True)
    
    with open(file_path, "wb") as buffer:
        content = await file.read()
        buffer.write(content)
    
    # Process the file in the background
    background_tasks.add_task(process_vcf_file, file_path, mode, batch)
    
    return UploadResponse(
        message="VCF file uploaded successfully. Processing started...",
        variant_count=0,  # Will be updated after processing
        file_name=file.filename
    )

async def process_vcf_file(file_path: str, mode: AnnotationMode, batch: bool):
    """Background task to process the VCF file."""
    global processing_status, variants
    processing_status = {"is_processing": True, "message": "Processing VCF file..."}
    
    try:
        annotator = VariantAnnotator()
        variant_count = 0
        
        with open(file_path, 'r') as f:
            for line in f:
                variant_data = annotator.parse_vcf_line(line)
                if variant_data:
                    variant = VariantCreate(**variant_data)
                    variant_id = f"{variant.chrom}_{variant.pos}_{variant.ref}_{variant.alt}"
                    
                    if mode == AnnotationMode.CLI and batch:
                        # Batch process with VEP CLI
                        pass  # Implement VEP CLI batch processing
                    else:
                        # Process with REST API
                        annotations = annotator.annotate_variant(variant)
                        variants[variant_id] = Variant(
                            **variant.dict(),
                            annotations=annotations
                        )
                    
                    variant_count += 1
        
        processing_status = {
            "is_processing": False,
            "message": f"Successfully processed {variant_count} variants"
        }
    except Exception as e:
        processing_status = {
            "is_processing": False,
            "message": f"Error processing VCF file: {str(e)}"
        }

@app.get("/api/v1/variants", response_model=List[Variant])
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

@app.get("/api/v1/variants/{variant_id}", response_model=Variant)
async def get_variant(variant_id: str):
    """
    Get detailed information for a specific variant.
    """
    if variant_id not in variants:
        raise HTTPException(status_code=404, detail="Variant not found")
    return variants[variant_id]

@app.get("/api/v1/variants/{variant_id}/annotations", response_model=AnnotationResponse)
async def get_variant_annotations(
    variant_id: str,
    mode: AnnotationMode = Query(AnnotationMode.CLI, description="Annotation method to use"),
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
        annotations["ensembl_vep"] = await VariantAnnotator.get_ensembl_vep_annotation(variant)
    if "all" in sources or "clinvar" in sources:
        annotations["clinvar"] = await VariantAnnotator.get_clinvar_annotation(variant)
    
    return AnnotationResponse(
        variant_id=variant_id,
        ensembl_vep=annotations.get("ensembl_vep"),
        clinvar=annotations.get("clinvar")
    )

@app.get("/api/v1/stats")
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
    
    return {
        "total_variants": total_variants,
        "variant_types": variant_types,
        "annotation_success_rates": success_rates,
        "last_processed": processing_status.get("message", "")
    }

if __name__ == "__main__":
    uvicorn.run("app.main:app", host="0.0.0.0", port=8000, reload=True) 