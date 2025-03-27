# Variant Annotation API

A lightweight API service for uploading, parsing, and annotating genomic variants from VCF files.

## Features

- **Upload VCF Files**: Simple endpoint to upload VCF files for processing
- **Parse Variants**: Convert VCF data into structured JSON format
- **Annotate Variants**: Retrieve additional information about variants from external sources:
  - Ensembl VEP (Variant Effect Predictor)
  - ClinVar database

## Technology Stack

- **FastAPI**: Modern, high-performance web framework for building APIs
- **Pydantic**: Data validation and settings management
- **Uvicorn**: ASGI server for running the application
- **Python 3.8+**: Core programming language

## Project Structure

```
variant-api/
├── main.py              # API logic and endpoints
├── utils.py             # Variant parsing and annotation functions
├── example.vcf          # Sample VCF file for testing
├── requirements.txt     # Python package dependencies
└── README.md            # This file
```

## API Endpoints

### 1. Upload VCF File
`POST /upload`

Upload a VCF file for processing.

### 2. List Variants
`GET /variants`

Return a list of parsed variants in JSON format.

### 3. Get Variant Details
`GET /variants/{variant_id}`

Retrieve detailed information for a specific variant.

### 4. Annotate Variant
`GET /annotate/{variant_id}`

Retrieve annotations for a specific variant from external databases.

## Installation

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
uvicorn main:app --reload
```

## Usage Examples

### Example 1: Upload a VCF file

```bash
curl -X POST "http://localhost:8000/upload" -H "accept: application/json" -H "Content-Type: multipart/form-data" -F "file=@path/to/your/file.vcf"
```

### Example 2: List all variants

```bash
curl -X GET "http://localhost:8000/variants" -H "accept: application/json"
```

### Example 3: Get details for a specific variant

```bash
curl -X GET "http://localhost:8000/variants/variant_id" -H "accept: application/json"
```

### Example 4: Get annotations for a specific variant

```bash
curl -X GET "http://localhost:8000/annotate/variant_id" -H "accept: application/json"
```

## Development

To contribute to this project:

1. Fork the repository
2. Create a new branch for your feature
3. Add tests for your changes
4. Submit a pull request

## License

MIT
