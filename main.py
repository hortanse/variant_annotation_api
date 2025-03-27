from fastapi import FastAPI, File, UploadFile, HTTPException, BackgroundTasks, Query
from fastapi.responses import JSONResponse
from typing import List, Dict, Any, Optional
import uvicorn
import os
import asyncio

from utils import (
    Variant, 
    VariantAnnotation, 
    parse_vcf_file, 
    save_uploaded_vcf, 
    annotate_variant_ensembl, 
    annotate_variant_clinvar,
    get_all_variants,
    get_variant_by_id,
    clear_variants
)

app = FastAPI(
    title="Variant Annotation API",
    description="A lightweight API service for uploading, parsing, and annotating genomic variants from VCF files",
    version="0.1.0",
)

# Status variable to track VCF processing
processing_status = {"is_processing": False, "message": ""}

@app.get("/")
async def root():
    """Root endpoint with API information."""
    return {
        "message": "Welcome to the Variant Annotation API",
        "endpoints": {
            "upload": "/upload - Upload a VCF file",
            "variants": "/variants - List all variants",
            "variant_details": "/variants/{variant_id} - Get details for a specific variant",
            "annotate": "/annotate/{variant_id} - Annotate a specific variant",
            "status": "/status - Check VCF processing status"
        }
    }

@app.get("/status")
async def get_status():
    """Get the current status of VCF processing."""
    return processing_status

async def process_vcf_file(file_path: str):
    """Background task to process the VCF file."""
    global processing_status
    processing_status = {"is_processing": True, "message": "Processing VCF file..."}
    
    try:
        # Clear previous variants
        clear_variants()
        
        # Parse the VCF file
        variants = parse_vcf_file(file_path)
        variant_count = len(variants)
        
        processing_status = {
            "is_processing": False, 
            "message": f"Successfully processed VCF file with {variant_count} variants."
        }
    except Exception as e:
        processing_status = {
            "is_processing": False, 
            "message": f"Error processing VCF file: {str(e)}"
        }

@app.post("/upload")
async def upload_vcf(background_tasks: BackgroundTasks, file: UploadFile = File(...)):
    """Upload a VCF file for processing."""
    if not file.filename.endswith('.vcf'):
        raise HTTPException(status_code=400, detail="Only VCF files are accepted")
    
    # Read the file content
    file_content = await file.read()
    
    # Save the uploaded file
    file_path = save_uploaded_vcf(file_content)
    
    # Process the file in the background
    background_tasks.add_task(process_vcf_file, file_path)
    
    return {
        "message": "VCF file uploaded successfully. Processing started...",
        "filename": file.filename,
        "status_endpoint": "/status"
    }

@app.get("/variants", response_model=List[Variant])
async def list_variants(
    limit: int = Query(100, description="Maximum number of variants to return"),
    offset: int = Query(0, description="Number of variants to skip")
):
    """
    Get a list of all variants.
    
    Parameters:
    - limit: Maximum number of variants to return
    - offset: Number of variants to skip
    """
    variants = get_all_variants()
    
    # Apply pagination
    paginated_variants = variants[offset:offset + limit]
    
    if not variants:
        return []
    
    return paginated_variants

@app.get("/variants/{variant_id}", response_model=Variant)
async def get_variant(variant_id: str):
    """
    Get details for a specific variant.
    
    Parameters:
    - variant_id: ID of the variant (rs ID or chrom_pos_ref_alt format)
    """
    variant = get_variant_by_id(variant_id)
    
    if not variant:
        raise HTTPException(status_code=404, detail=f"Variant with ID {variant_id} not found")
    
    return variant

@app.get("/annotate/{variant_id}")
async def annotate_variant(
    variant_id: str,
    source: str = Query("both", description="Annotation source: 'ensembl', 'clinvar', or 'both'")
):
    """
    Annotate a specific variant.
    
    Parameters:
    - variant_id: ID of the variant to annotate
    - source: Annotation source ('ensembl', 'clinvar', or 'both')
    """
    variant = get_variant_by_id(variant_id)
    
    if not variant:
        raise HTTPException(status_code=404, detail=f"Variant with ID {variant_id} not found")
    
    annotations = []
    
    if source.lower() in ["ensembl", "both"]:
        ensembl_annotation = await annotate_variant_ensembl(variant)
        annotations.append(ensembl_annotation)
    
    if source.lower() in ["clinvar", "both"]:
        clinvar_annotation = await annotate_variant_clinvar(variant)
        annotations.append(clinvar_annotation)
    
    return {
        "variant_id": variant_id,
        "annotations": annotations
    }

if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True) 