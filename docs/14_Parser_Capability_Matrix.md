# Parser Capability Matrix

**Version:** 1.0  
**Date:** 2026-03-01  
**Purpose:** Explicit documentation of parser capabilities and known limitations for MVP baseline.

---

## Overview

This document provides a comprehensive matrix of what each parser **can** and **cannot** process. This serves as:
1. **User-facing documentation** of expected behavior
2. **Test specification** for limitation coverage
3. **Product roadmap** input for future enhancements

---

## Capability Matrix

| Parser | Supported Formats | **Capabilities** | **Limitations (MVP)** | **Warnings Generated** |
|--------|------------------|------------------|----------------------|------------------------|
| **TextParser** | `.txt`, `.md`, `.csv` | - Full text extraction<br>- UTF-8 encoding<br>- Line-by-line processing | None (baseline) | - Encoding errors (non-UTF-8)<br>- Empty files |
| **DocxParser** | `.docx` | - Paragraphs (body)<br>- Tables (all cells)<br>- Headers & footers<br>- Multiple sections | ❌ **Comments**<br>❌ **Footnotes/endnotes**<br>❌ **Text boxes**<br>❌ **Embedded objects**<br>❌ **Macros/VBA**<br>❌ **Track changes** | `"LIMITE MVP: Commenti, note a piè di pagina, caselle di testo e macro non vengono processati."` |
| **XlsxParser** | `.xlsx` | - Text cells (strings)<br>- Multiple sheets<br>- Cell references | ⚠️ **Formulas** (ignored by design)<br>❌ **Charts**<br>❌ **Pivot tables**<br>❌ **Cell comments**<br>❌ **Conditional formatting** | `"Trovate N celle con formule: NON sono state modificate (come da policy MVP)."`<br>`"Processate N celle testuali su M celle totali analizzate."` |
| **PdfParser** | `.pdf` | - Textual PDFs<br>- Multi-page extraction<br>- Per-page processing | ❌ **Scanned/image-based PDFs** (no OCR on PDF)<br>❌ **Encrypted/password-protected PDFs**<br>❌ **Embedded images**<br>❌ **Form fields** | `"Il PDF non contiene testo estraibile. Potrebbe essere un PDF basato su immagini (scansione)."`<br>`"Solo N/M pagine contengono testo estraibile."` |
| **ImageParser** | `.jpg`, `.png` | - Tesseract OCR (ita, eng)<br>- Bounding boxes<br>- EXIF stripping | ⚠️ **Low OCR confidence** (< 60)<br>❌ **Handwriting**<br>❌ **Complex layouts**<br>❌ **Rotated text** | `"OCR confidence bassa per N parole."`<br>`"Tesseract non configurato: impossibile estrarre testo dall'immagine."` |

---

## Transformation Limitations

| Transformer | **Capabilities** | **Known Limitations** | **Output Warnings** |
|------------|------------------|----------------------|---------------------|
| **DocxTransformer** | - In-place text replacement in paragraphs<br>- Table cell replacement<br>- Header/footer replacement | ❌ Same as DocxParser limitations<br>❌ **Formatting may shift** (runs merged) | `"LIMITE MVP: Commenti, note a piè di pagina e caselle di testo non sono stati processati."` |
| **XlsxTransformer** | - Text cell replacement<br>- Formula preservation | ⚠️ **Formulas untouched** (by design) | `"Celle con formule preservate."` |
| **PdfTransformer** | - Per-page text extraction<br>- PDF rebuild (fpdf2/reportlab) | ❌ **Layout NOT preserved**<br>❌ **Images lost**<br>❌ **Hyperlinks lost**<br>❌ **Fonts may differ** | `"PDF rebuild (fpdf2/reportlab) ok. Layout differente."`<br>`"Attenzione: Il PDF risultante ha un layout semplificato. Formattazione e immagini originali perse."` |
| **ImageTransformer** | - Visual redaction (black boxes)<br>- Bbox-based masking | ⚠️ **Requires OCR bbox** (no bbox = no redaction)<br>❌ **Low-conf words may not be detected** | `"Redazione visuale applicata su N finding."` |
| **TextTransformer** | - Full text replacement<br>- Preserves line structure | None (baseline) | None |

---

## Test Coverage Requirements

Each limitation **must** have at least one test that:
1. ✅ **Verifies the limitation is correctly detected**
2. ✅ **Ensures appropriate warnings are generated**
3. ✅ **Confirms no crash/silent failure occurs**

### Example Test Cases

#### DOCX Limitations
```python
def test_docx_comments_ignored():
    """Verify comments in DOCX are not processed and warning is emitted."""
    # Given: DOCX with comments
    # When: Parsed
    # Then: Warning about comments limitation
    
def test_docx_footnotes_ignored():
    """Verify footnotes are not processed and warning is emitted."""
    # Given: DOCX with footnotes
    # When: Parsed
    # Then: Warning about footnotes limitation
```

#### PDF Limitations
```python
def test_pdf_scanned_detected():
    """Verify scanned PDFs are detected and marked unsafe."""
    # Given: PDF with no extractable text
    # When: Parsed
    # Then: success=False, error_message contains "scansione"
    
def test_pdf_encrypted_rejected():
    """Verify encrypted PDFs are rejected with clear message."""
    # Given: Password-protected PDF
    # When: Parsed
    # Then: success=False, error_message contains "cifrato"
```

#### XLSX Limitations
```python
def test_xlsx_formulas_preserved():
    """Verify cells with formulas are NOT modified."""
    # Given: XLSX with formulas
    # When: Transformed
    # Then: Formulas untouched, warning emitted
```

#### PDF Transform Limitations
```python
def test_pdf_transform_layout_warning():
    """Verify PDF transform emits layout warning."""
    # Given: PDF with complex layout
    # When: Transformed
    # Then: Warning about "layout differente"
```

---

## Capability Evolution Roadmap

### Phase 2 (Post-MVP)
- **DOCX**: Add comment/footnote extraction
- **PDF**: Integrate OCR for scanned PDFs (image extraction + Tesseract)
- **XLSX**: Add chart title extraction

### Phase 3 (Future)
- **DOCX**: Track changes support
- **PDF**: Layout-preserving transformation (PDFMiner + structure preservation)
- **Image**: Handwriting recognition, rotated text handling

---

## Security Implications

### Data Leakage Risk Matrix

| Parser | **Limitation** | **Risk Level** | **Mitigation** |
|--------|---------------|---------------|---------------|
| DocxParser | Comments not processed | 🟡 **Medium** | Warning emitted, user must manually review |
| DocxParser | Footnotes not processed | 🟡 **Medium** | Warning emitted, user must manually review |
| PdfParser | Scanned PDFs not processed | 🔴 **High** | File marked FAILED, export blocked if strict mode |
| PdfParser | Images in PDF not analyzed | 🟠 **Medium-High** | Warning emitted |
| XlsxParser | Formula content not analyzed | 🟢 **Low** | Formulas rarely contain PII (by design) |
| ImageParser | Low-confidence OCR words | 🟡 **Medium** | Bboxes still returned for visual redaction |

### Recommended User Actions

For **High-Risk** limitations:
1. Use **strict mode** to block export
2. Manually review files with warnings
3. Use external OCR for scanned PDFs before upload

---

## Implementation Notes

### Current Warning System

All limitations generate warnings via:
- `ParseResult.warnings` (list of strings)
- `TransformWarnings` (list of strings returned by transformer)
- `Report.warnings_and_limits` (aggregated in final report)

### Future: Structured Limitation Metadata

Consider extending `ParseResult` with:
```python
class ParseResult:
    limitations: List[ParserLimitation]  # Structured limitation metadata

@dataclass
class ParserLimitation:
    category: str  # "unsupported_feature", "quality_degradation", "security_risk"
    feature: str   # "docx_comments", "pdf_layout", "ocr_confidence"
    severity: str  # "low", "medium", "high", "critical"
    message: str
    mitigation: Optional[str]
```

This would enable:
- Programmatic filtering by severity
- User-facing limitation dashboard
- Automated safety label degradation based on limitation severity

---

## Validation Checklist

- [x] All parsers have documented limitations
- [x] All transformers have documented limitations
- [x] Security risk levels assigned
- [ ] Test coverage for each limitation (P2-1 in progress)
- [ ] User-facing documentation updated (README)
- [ ] Report template includes limitation summary

---

## References

- [02_Technical_Architecture.md](02_Technical_Architecture.md) - Parser design rationale
- [08_Risks_and_Mitigations.md](08_Risks_and_Mitigations.md) - Risk assessment
- [13_Super_Critical_Analysis.md](13_Super_Critical_Analysis.md) - P2 technical debt
- Test suite: `backend/tests/test_parser_limitations.py` (to be created)
