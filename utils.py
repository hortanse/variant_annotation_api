import os
import tempfile
from typing import Dict, List, Any, Optional
import vcf
import httpx
import json
from pydantic import BaseModel, Field

# Define Pydantic models for data validation
class Variant(BaseModel):
    id: str  # rs ID or constructed ID if not available
    chrom: str
    pos: int
    ref: str
    alt: str
    qual: Optional[float] = None
    filter: str
    info: Dict[str, Any] = Field(default_factory=dict)
    genotype: Optional[str] = None
    
class VariantAnnotation(BaseModel):
    variant_id: str
    source: str
    annotations: Dict[str, Any] = Field(default_factory=dict)

# Global variable to store parsed variants
VARIANTS: Dict[str, Variant] = {}

def parse_vcf_file(file_path: str) -> List[Variant]:
    """Parse a VCF file and return a list of variants."""
    variants = []
    vcf_reader = vcf.Reader(open(file_path, 'r'))
    
    for record in vcf_reader:
        # Generate a variant ID if rs ID is not available
        variant_id = record.ID if record.ID else f"{record.CHROM}_{record.POS}_{record.REF}_{record.ALT[0]}"
        
        # Extract genotype if available
        genotype = None
        if record.samples:
            genotype = record.samples[0].gt_type  # 0=HOM_REF, 1=HET, 2=HOM_ALT, None=unavailable
            genotype = {0: "0/0", 1: "0/1", 2: "1/1"}.get(genotype, None)
        
        # Create a Variant object
        variant = Variant(
            id=variant_id,
            chrom=record.CHROM,
            pos=record.POS,
            ref=record.REF,
            alt=str(record.ALT[0]),  # Taking the first ALT allele for simplicity
            qual=record.QUAL,
            filter=record.FILTER or "PASS",
            info={k: v for k, v in record.INFO.items()},
            genotype=genotype
        )
        
        # Store in global dictionary and add to result list
        VARIANTS[variant_id] = variant
        variants.append(variant)
    
    return variants

def save_uploaded_vcf(file_content: bytes) -> str:
    """Save uploaded VCF content to a temporary file and return the file path."""
    temp_dir = tempfile.gettempdir()
    file_path = os.path.join(temp_dir, "uploaded_vcf.vcf")
    
    with open(file_path, 'wb') as f:
        f.write(file_content)
    
    return file_path

async def annotate_variant_ensembl(variant: Variant) -> VariantAnnotation:
    """
    Annotate a variant using the Ensembl VEP REST API.
    """
    base_url = "https://rest.ensembl.org"
    endpoint = "/vep/human/hgvs"
    
    # Create HGVS notation: e.g., 1:g.14653A>G
    hgvs = f"{variant.chrom.replace('chr', '')}:g.{variant.pos}{variant.ref}>{variant.alt}"
    
    async with httpx.AsyncClient() as client:
        response = await client.get(
            f"{base_url}{endpoint}/{hgvs}",
            headers={"Content-Type": "application/json"},
            timeout=30.0
        )
        
        if response.status_code == 200:
            data = response.json()
            return VariantAnnotation(
                variant_id=variant.id,
                source="Ensembl VEP",
                annotations=data[0] if data else {}
            )
        else:
            # Return empty annotation if API call fails
            return VariantAnnotation(
                variant_id=variant.id,
                source="Ensembl VEP",
                annotations={"error": f"Failed to retrieve annotation: {response.status_code}"}
            )

async def annotate_variant_clinvar(variant: Variant) -> VariantAnnotation:
    """
    Annotate a variant using ClinVar via the NCBI E-utilities API.
    """
    # If variant has an rs ID, use it for the query
    if variant.id.startswith("rs"):
        query = variant.id
    else:
        # Otherwise construct a query using genomic coordinates
        query = f"{variant.chrom}[CHR] AND {variant.pos}[BASE_POSITION] AND {variant.ref}>{variant.alt}[ALLELE]"
    
    base_url = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils"
    
    async with httpx.AsyncClient() as client:
        # First, search for the variant in ClinVar
        search_response = await client.get(
            f"{base_url}/esearch.fcgi",
            params={
                "db": "clinvar",
                "term": query,
                "retmode": "json"
            },
            timeout=30.0
        )
        
        if search_response.status_code != 200 or not search_response.json().get("esearchresult", {}).get("idlist"):
            return VariantAnnotation(
                variant_id=variant.id,
                source="ClinVar",
                annotations={"error": "Variant not found in ClinVar"}
            )
        
        variant_id = search_response.json()["esearchresult"]["idlist"][0]
        
        # Then, fetch the summary for that variant
        summary_response = await client.get(
            f"{base_url}/esummary.fcgi",
            params={
                "db": "clinvar",
                "id": variant_id,
                "retmode": "json"
            },
            timeout=30.0
        )
        
        if summary_response.status_code == 200:
            data = summary_response.json()
            return VariantAnnotation(
                variant_id=variant.id,
                source="ClinVar",
                annotations=data.get("result", {}).get(variant_id, {})
            )
        else:
            return VariantAnnotation(
                variant_id=variant.id,
                source="ClinVar",
                annotations={"error": f"Failed to retrieve annotation: {summary_response.status_code}"}
            )

def get_all_variants() -> List[Variant]:
    """Return all parsed variants."""
    return list(VARIANTS.values())

def get_variant_by_id(variant_id: str) -> Optional[Variant]:
    """Return a specific variant by ID."""
    return VARIANTS.get(variant_id)

def clear_variants() -> None:
    """Clear all stored variants."""
    VARIANTS.clear() 