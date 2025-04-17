import pytest
import os
from pathlib import Path
from unittest.mock import patch, MagicMock
import json
from typing import Dict, Any

from app.annotator import VariantAnnotator
from app.models import VariantCreate, Variant
from app.config import settings

# Test data
TEST_VCF_LINE = "1\t12345\t.\tA\tG\t100\tPASS\tAC=1;AF=0.5"
TEST_VCF_LINE_WITH_INFO = "1\t12345\t.\tA\tG\t100\tPASS\tAC=1;AF=0.5;DP=100;MQ=60"
TEST_VCF_HEADER = "##fileformat=VCFv4.2\n#CHROM\tPOS\tID\tREF\tALT\tQUAL\tFILTER\tINFO"

# Mock VEP REST API response
MOCK_VEP_RESPONSE = [
    {
    "id": "1_12345_A_G",
    "most_severe_consequence": "missense_variant",
    "transcript_consequences": [
        {
            "gene_symbol": "TEST_GENE",
            "transcript_id": "ENST000001",
            "consequence_terms": ["missense_variant"],
            "impact": "MODERATE",
            "hgvsp": "p.Arg123Gly"
        }
    ],
    "colocated_variants": [
        {
            "gnomad": {
                "af": 0.001
            }
        }
    ]
}
]

# Mock ClinVar response
MOCK_CLINVAR_RESPONSE = {
    "clinical_significance": "Pathogenic",
    "review_status": "reviewed by expert panel",
    "conditions": ["Test Disease"],
    "variation_id": "12345"
}

@pytest.fixture
def annotator():
    """Create a VariantAnnotator instance for testing."""
    return VariantAnnotator()

@pytest.fixture
def test_variant():
    """Create a test variant."""
    return VariantCreate(
        chrom="1",
        pos=12345,
        ref="A",
        alt="G",
        qual=100.0,
        filter="PASS",
        info={"AC": 1, "AF": 0.5}
    )

def test_parse_vcf_line(annotator):
    """Test parsing a VCF line."""
    variant_data = annotator.parse_vcf_line(TEST_VCF_LINE)
    assert variant_data is not None
    assert variant_data["chrom"] == "1"
    assert variant_data["pos"] == 12345
    assert variant_data["ref"] == "A"
    assert variant_data["alt"] == "G"
    assert variant_data["qual"] == 100.0
    assert variant_data["filter"] == "PASS"
    assert variant_data["info"] == {"AC": 1, "AF": 0.5}

def test_parse_vcf_line_with_info(annotator):
    """Test parsing a VCF line with additional INFO fields."""
    variant_data = annotator.parse_vcf_line(TEST_VCF_LINE_WITH_INFO)
    assert variant_data is not None
    assert variant_data["info"] == {
        "AC": 1,
        "AF": 0.5,
        "DP": 100,
        "MQ": 60
    }

def test_parse_vcf_line_header(annotator):
    """Test parsing a VCF header line."""
    variant_data = annotator.parse_vcf_line(TEST_VCF_HEADER)
    assert variant_data is None

@pytest.mark.asyncio
async def test_annotate_variant_rest(annotator, test_variant):
    """Test variant annotation using REST API."""
    with patch("httpx.AsyncClient.get") as mock_get:
        # Mock VEP response
        mock_get.return_value = MagicMock(
            status_code=200,
            json=lambda: MOCK_VEP_RESPONSE
        )
        
        annotations = await annotator._annotate_with_vep_rest(test_variant)
        assert annotations is not None
        assert "consequence" in annotations
        assert "gene" in annotations
        assert "transcript" in annotations
        assert "protein_change" in annotations
        assert "gnomad_af" in annotations

@pytest.mark.asyncio
async def test_annotate_variant_cli(annotator, test_variant):
    """Test variant annotation using VEP CLI."""
    with patch("subprocess.run") as mock_run:
        # Mock VEP CLI output
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout=json.dumps(MOCK_VEP_RESPONSE)
        )
        
        annotations = await annotator._annotate_with_vep_cli(test_variant)
        assert annotations is not None
        assert "consequence" in annotations
        assert "gene" in annotations
        assert "transcript" in annotations
        assert "protein_change" in annotations
        assert "gnomad_af" in annotations

@pytest.mark.asyncio
async def test_annotate_batch_with_vep_cli(annotator):
    """Test batch annotation using VEP CLI."""
    variants = [
        VariantCreate(
            chrom="1",
            pos=12345,
            ref="A",
            alt="G",
            qual=100.0,
            filter="PASS",
            info={}
        ),
        VariantCreate(
            chrom="1",
            pos=12346,
            ref="C",
            alt="T",
            qual=100.0,
            filter="PASS",
            info={}
        )
    ]
    
    with patch("subprocess.run") as mock_run:
        # Mock VEP CLI output
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout=""
        )
        
        # Mock VCF reader
        with patch("vcf.Reader") as mock_reader:
            mock_record = MagicMock()
            mock_record.CHROM = "1"
            mock_record.POS = 12345
            mock_record.REF = "A"
            mock_record.ALT = ["G"]
            mock_record.INFO = {"consequence": "missense_variant"}
            mock_reader.return_value = [mock_record]
            
            annotations = await annotator.annotate_batch_with_vep_cli(variants)
            assert annotations is not None
            assert len(annotations) == 1
            assert "1_12345_A_G" in annotations

@pytest.mark.asyncio
async def test_get_clinvar_annotation(annotator):
    """Test ClinVar annotation retrieval."""
    variant = Variant(
        id="1_12345_A_G",
        chrom="1",
        pos=12345,
        ref="A",
        alt="G",
        qual=100.0,
        filter="PASS",
        info={}
    )
    
    with patch("httpx.AsyncClient.get") as mock_get:
        # Mock ClinVar response
        mock_get.return_value = MagicMock(
            status_code=200,
            json=lambda: MOCK_CLINVAR_RESPONSE
        )
        
        annotations = await annotator.get_clinvar_annotation(variant)
        assert annotations is not None
        assert "clinical_significance" in annotations
        assert "review_status" in annotations
        assert "conditions" in annotations
        assert "variation_id" in annotations

def test_parse_vep_rest_response(annotator):
    """Test parsing VEP REST API response."""
    annotations = annotator._parse_vep_rest_response(MOCK_VEP_RESPONSE)
    assert annotations is not None
    assert "consequence" in annotations
    assert "gene" in annotations
    assert "transcript" in annotations
    assert "protein_change" in annotations
    assert "gnomad_af" in annotations

def test_parse_vep_output(annotator):
    """Test parsing VEP CLI output."""
    vep_output = json.dumps(MOCK_VEP_RESPONSE)
    annotations = annotator._parse_vep_output(vep_output)
    assert annotations is not None
    assert "consequence" in annotations
    assert "gene" in annotations
    assert "transcript" in annotations
    assert "protein_change" in annotations
    assert "gnomad_af" in annotations
