import os
import subprocess
import tempfile
from typing import Dict, List, Any, Optional, Union
import vcf
import httpx
import json
import logging
from pathlib import Path
from pydantic import BaseModel, Field
from .config import settings
from .models import Variant, VariantCreate, AnnotationResponse
logger = logging.getLogger(__name__)
# Define Pydantic models for data validation
"""
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
"""
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

class VariantAnnotator:
    """Class for handling variant annotation using both VEP CLI and REST API."""
    
    def __init__(self):
        self.vep_cache_dir = Path("data/vep_cache")
        self.vep_cache_dir.mkdir(parents=True, exist_ok=True)
        self.vep_script = os.getenv("VEP_SCRIPT", "vep")
        self.vep_data_dir = os.getenv("VEP_DATA_DIR", "data/vep_data")
    
    @staticmethod
    def parse_vcf_line(line: str) -> Optional[Dict[str, Any]]:
        """
        Parse a single line from a VCF file.
        
        Args:
            line: A line from a VCF file
            
        Returns:
            Dictionary containing variant information or None if not a variant line
        """
        if line.startswith('#'):
            return None
            
        fields = line.strip().split('\t')
        if len(fields) < 8:
            return None
            
        chrom, pos, id_, ref, alt, qual, filter_, info = fields[:8]
        
        # Handle multiple ALT alleles
        alt_alleles = alt.split(',')
        
        # Create a variant for each ALT allele
        variant_data = {
            'chrom': chrom,
            'pos': int(pos),
            'ref': ref,
            'alt': alt_alleles[0],  # For now, just take the first ALT allele
            'qual': float(qual) if qual != '.' else None,
            'filter': filter_,
            'info': {}
        }
        
        # Parse INFO field
        for item in info.split(';'):
            if '=' in item:
                key, value = item.split('=', 1)
                try:
                    # Try to convert to appropriate type
                    if value.isdigit():
                        value = int(value)
                    elif value.replace('.', '', 1).isdigit():
                        value = float(value)
                    elif value.lower() in ('true', 'false'):
                        value = value.lower() == 'true'
                except ValueError:
                    pass
                variant_data['info'][key] = value
        
        return variant_data
    
    async def annotate_variant(self, variant: VariantCreate, mode: str = "rest") -> Dict[str, Any]:
        """
        Annotate a single variant using the specified mode.
        
        Args:
            variant: The variant to annotate
            mode: Annotation mode ('cli' or 'rest')
            
        Returns:
            Dictionary containing annotations
        """
        if mode == "cli":
            return await self._annotate_with_vep_cli(variant)
        else:
            return await self._annotate_with_vep_rest(variant)
    
    async def _annotate_with_vep_cli(self, variant: VariantCreate) -> Dict[str, Any]:
        """
        Annotate a variant using VEP CLI.
        
        Args:
            variant: The variant to annotate
            
        Returns:
            Dictionary containing VEP annotations
        """
        # Create a temporary VCF file for the variant
        with tempfile.NamedTemporaryFile(mode='w', suffix='.vcf', delete=False) as temp_vcf:
            temp_vcf.write("##fileformat=VCFv4.2\n")
            temp_vcf.write("#CHROM\tPOS\tID\tREF\tALT\tQUAL\tFILTER\tINFO\n")
            temp_vcf.write(f"{variant.chrom}\t{variant.pos}\t.\t{variant.ref}\t{variant.alt}\t.\t.\t.\n")
            temp_vcf_path = temp_vcf.name
        
        try:
            # Run VEP CLI
            cmd = [
                self.vep_script,
                "--input_file", temp_vcf_path,
                "--output_file", "STDOUT",
                "--format", "vcf",
                "--cache",
                "--dir_cache", self.vep_data_dir,
                "--offline",
                "--json",
                "--no_stats"
            ]
            
            result = subprocess.run(cmd, capture_output=True, text=True)
            
            if result.returncode != 0:
                logger.error(f"VEP CLI error: {result.stderr}")
                return {"error": "VEP CLI execution failed"}
            
            # Parse VEP output
            annotations = self._parse_vep_output(result.stdout)
            return annotations
            
        except Exception as e:
            logger.error(f"Error running VEP CLI: {str(e)}")
            return {"error": str(e)}
        finally:
            # Clean up temporary file
            os.unlink(temp_vcf_path)
    
    async def _annotate_with_vep_rest(self, variant: VariantCreate) -> Dict[str, Any]:
        """
        Annotate a variant using VEP REST API.
        
        Args:
            variant: The variant to annotate
            
        Returns:
            Dictionary containing VEP annotations
        """
        try:
            async with httpx.AsyncClient() as client:
                # Construct the VEP REST API URL
                url = f"{settings.ENSEMBL_VEP_URL}/vep/human/region/{variant.chrom}:{variant.pos}-{variant.pos}/{variant.alt}"
                
                # Add API key if available
                headers = {}
                if settings.ENSEMBL_API_KEY:
                    headers["Authorization"] = f"Bearer {settings.ENSEMBL_API_KEY}"
                
                response = await client.get(url, headers=headers)
                
                if response.status_code != 200:
                    logger.error(f"VEP REST API error: {response.text}")
                    return {"error": f"VEP REST API error: {response.status_code}"}
                
                data = response.json()
                return self._parse_vep_rest_response(data)
                
        except Exception as e:
            logger.error(f"Error calling VEP REST API: {str(e)}")
            return {"error": str(e)}
    async def annotate_batch_with_vep_cli(self, variants: List[VariantCreate]) -> Dict[str, Dict[str, Any]]:
        """
        Annotate a batch of variants using VEP CLI.
        
        Args:
            variants: List of VariantCreate objects to annotate
            
        Return:
            A dictionary of variant_id -> VEP annotations
        """
        variant_id_map = {}
        # 1. Create temporary input VCF file
        with tempfile.NamedTemporaryFile(mode="w", suffix=".vcf", delete=False) as batch_input_vcf:
            batch_input_vcf.write("##fileformat=VCFv4.2\n")
            batch_input_vcf.write("#CHROM\tPOS\tID\tREF\tALT\tQUAL\tFILTER\tINFO\n")

            for variant in variants:
                variant_id = f"{variant.chrom}_{variant.pos}_{variant.ref}_{variant.alt}"
                variant_id_map[variant_id] = variant
                batch_input_vcf.write(
                    f"{variant.chrom}\t{variant.pos}\t.\t{variant.ref}\t{variant.alt}\t.\t.\t.\n"
                )

            input_vcf_path = batch_input_vcf.name

        # 2. Create temporary output file
        with tempfile.NamedTemporaryFile(mode="w", suffix=".vcf", delete=False) as batch_output_vcf:
            output_vcf_path = batch_output_vcf.name

        # 3. Build VEP command
        cmd = [
            self.vep_script,
            "--input_file", input_vcf_path,
            "--output_file", output_vcf_path,
            "--format", "vcf",
            "--cache",
            "--offline",
            "--dir_cache", str(settings.VEP_DATA_DIR),
            "--species", settings.VEP_SPECIES,
            "--assembly", settings.VEP_ASSEMBLY,
            "--vcf",
            "--no_stats"
        ]

        # 4. Run VEP
        result = subprocess.run(cmd, capture_output=True, text=True)

        if result.returncode != 0:
            logging.error(f"VEP batch CLI failed:\n{result.stderr}")
            raise RuntimeError("VEP batch CLI execution failed")

        # 5. Parse VEP output and extract annotations
        annotations_by_id = {}
        vcf_reader = vcf.Reader(filename=output_vcf_path)

        for record in vcf_reader:
            variant_id = f"{record.CHROM}_{record.POS}_{record.REF}_{record.ALT[0]}"
            annotations_by_id[variant_id] = dict(record.INFO)

        # 6. Cleanup
        os.unlink(input_vcf_path)
        os.unlink(output_vcf_path)

        return annotations_by_id


    def _parse_vep_output(self, output: str) -> Dict[str, Any]:
        """
        Parse VEP CLI output.
        
        Args:
            output: VEP CLI output string
            
        Returns:
            Dictionary containing parsed annotations
        """
        try:
            # VEP JSON output is one JSON object per line
            for line in output.split('\n'):
                if line.strip():
                    return self._parse_vep_rest_response(line)
            return {}
        except Exception as e:
            logger.error(f"Error parsing VEP output: {str(e)}")
            return {"error": "Failed to parse VEP output"}
    
    def _parse_vep_rest_response(self, data: Union[str, Dict]) -> Dict[str, Any]:
        """
        Parse VEP REST API response.
        
        Args:
            data: VEP REST API response data
            
        Returns:
            Dictionary containing parsed annotations
        """
        try:
            if isinstance(data, str):
                import json
                data = json.loads(data)
            
            if not data:
                return {}
            
            # Extract relevant annotations
            annotations = {
                "consequence": [],
                "impact": None,
                "gene": None,
                "transcript": None,
                "protein_change": None,
                "gnomad_af": None
            }
            
            for item in data:
                if "transcript_consequences" in item:
                    for consequence in item["transcript_consequences"]:
                        annotations["consequence"].append(consequence.get("consequence_terms", []))
                        if not annotations["impact"]:
                            annotations["impact"] = consequence.get("impact")
                        if not annotations["gene"]:
                            annotations["gene"] = consequence.get("gene_symbol")
                        if not annotations["transcript"]:
                            annotations["transcript"] = consequence.get("transcript_id")
                        if not annotations["protein_change"]:
                            annotations["protein_change"] = consequence.get("hgvsp")
                
                if "colocated_variants" in item:
                    for variant in item["colocated_variants"]:
                        if "gnomad" in variant:
                            annotations["gnomad_af"] = variant["gnomad"].get("af")
            
            return annotations
            
        except Exception as e:
            logger.error(f"Error parsing VEP response: {str(e)}")
            return {"error": "Failed to parse VEP response"}
    
    @staticmethod
    async def get_ensembl_vep_annotation(variant: Variant) -> Dict[str, Any]:
        """
        Get Ensembl VEP annotation for a variant.
        
        Args:
            variant: The variant to annotate
            
        Returns:
            Dictionary containing VEP annotations
        """
        annotator = VariantAnnotator()
        return await annotator._annotate_with_vep_rest(VariantCreate(**variant.dict()))
    
    @staticmethod
    async def get_clinvar_annotation(variant: Variant) -> Dict[str, Any]:
        """
        Get ClinVar annotation for a variant.
        
        Args:
            variant: The variant to annotate
            
        Returns:
            Dictionary containing ClinVar annotations
        """
        try:
            async with httpx.AsyncClient() as client:
                # Construct the ClinVar API URL
                url = f"{settings.CLINVAR_API_URL}/variation/{variant.chrom}:{variant.pos}-{variant.pos}:{variant.ref}:{variant.alt}"
                
                # Add API key if available
                headers = {}
                if settings.CLINVAR_API_KEY:
                    headers["Authorization"] = f"Bearer {settings.CLINVAR_API_KEY}"
                
                response = await client.get(url, headers=headers)
                
                if response.status_code != 200:
                    logger.error(f"ClinVar API error: {response.text}")
                    return {"error": f"ClinVar API error: {response.status_code}"}
                
                data = response.json()
                return {
                    "clinical_significance": data.get("clinical_significance"),
                    "review_status": data.get("review_status"),
                    "conditions": data.get("conditions", []),
                    "variation_id": data.get("variation_id")
                }
                
        except Exception as e:
            logger.error(f"Error calling ClinVar API: {str(e)}")
            return {"error": str(e)}

def get_all_variants() -> List[Variant]:
    """Return all parsed variants."""
    return list(VARIANTS.values())

def get_variant_by_id(variant_id: str) -> Optional[Variant]:
    """Return a specific variant by ID."""
    return VARIANTS.get(variant_id)

def clear_variants() -> None:
    """Clear all stored variants."""
    VARIANTS.clear() 