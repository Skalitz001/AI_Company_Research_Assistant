from backend.app.schemas import ResearchReport
from backend.app.services.pdf import render_pdf, safe_filename


def test_pdf_contains_required_sections_and_safe_filename():
    report = ResearchReport.model_validate(
        {
            "company": {
                "name": "Acme / Labs",
                "website": "https://acme.example",
                "phone": None,
                "address": None,
                "country": "United States",
                "industry": "Software",
            },
            "summary": "A company summary.",
            "products_services": ["Workflow software"],
            "pain_points": ["A plausible hypothesis"],
            "competitors": [
                {
                    "name": "Rival",
                    "website": "https://rival.example",
                    "fit": "Same category",
                }
            ],
            "sources": [
                {"title": "Home", "url": "https://acme.example", "source_type": "website"}
            ],
            "warnings": ["Search enrichment was unavailable."],
            "model_id": "openrouter/example-model",
        }
    )
    data = render_pdf(report)
    assert data.startswith(b"%PDF-")
    assert len(data) > 1000
    assert safe_filename(report.company.name) == "acme-labs-research-report.pdf"
