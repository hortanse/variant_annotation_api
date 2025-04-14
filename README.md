# Variant Annotation and Interpretation API

A lightweight yet extensible API service for uploading, parsing, and annotating genomic variants from VCF files. Built for both research and clinical-scale workflows.

## Features

- **Upload VCF Files**: Simple endpoint to upload VCF files for processing
- **Annotate Variants**:
  - Use Ensembl VEP CLI (local, offline, batch processing)
  - Use Ensembl VEP REST API (online, lightweight variant-by-variant)
- **Flexible Modes**: Choose between `mode=cli` or `mode=rest`
- **Return rich variant annotations**: gene, transcript consequence, ClinVar significance, gnomAD frequency, and more
- **Built with FastAPI + Docker**: for modern, scalable deployment
- **Easily extendable**: Interpretation rules, caching, and frontend can be added

## Technology Stack

- **FastAPI**: Modern, high-performance web framework for building APIs
- **Pydantic**: Data validation and settings management
- **Uvicorn**: ASGI server for running the application
- **Python 3.8+**: Core programming language
- **Docker**: Containerization for easy deployment

## Project Structure

```
variant_annotation_api/
├── app/
│   ├── __init__.py
│   ├── main.py            # Entry point
│   ├── routes.py          # FastAPI endpoints
│   ├── annotator.py       # Variant annotation logic (formerly utils.py)
│   ├── models.py          # Pydantic models
│   ├── config.py          # API keys, constants
├── data/
│   └── example.vcf        # Sample VCF file for testing
├── tests/
│   ├── test_api.py        # API integration tests
│   └── test_annotator.py  # Unit tests for annotator
├── Dockerfile             # Container configuration
├── .dockerignore         # Files to exclude from Docker build
├── .gitignore            # Git ignore patterns
├── requirements.txt      # Python package dependencies
└── README.md            # This file
```

## API Endpoints

### 1. Upload and Process VCF File
`POST /api/v1/upload`

Upload a VCF file for processing. Supports both single-file and batch processing.

Query Parameters:
- `mode`: `cli` (default) or `rest` - Choose annotation method
- `batch`: `true` or `false` (default) - Enable batch processing

### 2. List Processed Variants
`GET /api/v1/variants`

Return a list of processed variants with basic information.

Query Parameters:
- `limit`: Number of variants to return (default: 100)
- `offset`: Pagination offset (default: 0)
- `chrom`: Filter by chromosome
- `min_quality`: Minimum quality score

### 3. Get Variant Details
`GET /api/v1/variants/{variant_id}`

Retrieve detailed information for a specific variant, including:
- Basic variant information (chromosome, position, alleles)
- Quality metrics
- Filter status
- Raw VCF INFO fields

### 4. Get Variant Annotations
`GET /api/v1/variants/{variant_id}/annotations`

Retrieve comprehensive annotations for a specific variant:
- Gene and transcript information
- Functional consequences
- Population frequencies (gnomAD)
- Clinical significance (ClinVar)
- Additional annotations based on selected mode

Query Parameters:
- `mode`: `cli` (default) or `rest` - Choose annotation method
- `include`: Comma-separated list of annotation sources to include

### 5. Get Annotation Statistics
`GET /api/v1/stats`

Return statistics about processed variants and annotations:
- Total variants processed
- Distribution of variant types
- Annotation success rates
- Processing times

## Installation

### Local Development

```bash
# Clone the repository
git clone https://github.com/hortanse/variant_annotation_api.git
cd variant_annotation_api

# Create a virtual environment
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Start the server
uvicorn app.main:app --reload
```

### Docker Deployment

```bash
# Build the Docker image
docker build -t variant-annotation-api .

# Run the container
docker run -p 8000:8000 variant-annotation-api
```

## Usage Examples

### Example 1: Upload a VCF file with CLI mode

```bash
curl -X POST "http://localhost:8000/api/v1/upload?mode=cli" \
  -H "accept: application/json" \
  -H "Content-Type: multipart/form-data" \
  -F "file=@path/to/your/file.vcf"
```

### Example 2: Get variant annotations with specific sources

```bash
curl -X GET "http://localhost:8000/api/v1/variants/variant_id/annotations?include=vep,clinvar,gnomad" \
  -H "accept: application/json"
```

### Example 3: List variants with filtering

```bash
curl -X GET "http://localhost:8000/api/v1/variants?chrom=1&min_quality=20" \
  -H "accept: application/json"
```

## Development

To contribute to this project:

1. Fork the repository
2. Create a new branch for your feature
3. Add tests for your changes
4. Submit a pull request

## License

MIT
