"""
Test per app.parsers.image_parser — ImageParser con mock di pytesseract.
Non richiede Tesseract installato: tutta la logica OCR è mockata.
PIL/Pillow è usato per creare immagini reali in memoria.
Coverage target: ≥80%
"""

from pathlib import Path
from unittest.mock import MagicMock, patch

from PIL import Image

# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────


def _make_png_file(tmp_path, name="test.png", size=(20, 20), color=(255, 0, 0)) -> Path:
    """Crea un file PNG reale in tmp_path."""
    img = Image.new("RGB", size, color=color)
    path = tmp_path / name
    img.save(str(path), format="PNG")
    return path


def _make_jpg_file(tmp_path, name="test.jpg", size=(20, 20), color=(0, 255, 0)) -> Path:
    """Crea un file JPEG reale in tmp_path."""
    img = Image.new("RGB", size, color=color)
    path = tmp_path / name
    img.save(str(path), format="JPEG")
    return path


def _make_ocr_data(words, confs, line_nums=None, block_nums=None):
    """Costruisce un dizionario OCR nel formato restituito da pytesseract.image_to_data."""
    n = len(words)
    if line_nums is None:
        line_nums = [1] * n
    if block_nums is None:
        block_nums = [1] * n
    return {
        "text": words,
        "conf": confs,
        "line_num": line_nums,
        "block_num": block_nums,
        "left": [10] * n,
        "top": [20] * n,
        "width": [50] * n,
        "height": [15] * n,
    }


def _mock_pytesseract(ocr_data):
    """Crea un mock di pytesseract che restituisce ocr_data."""
    mock_pt = MagicMock()
    mock_pt.Output.DICT = "dict"
    mock_pt.image_to_data.return_value = ocr_data
    return mock_pt


# ─────────────────────────────────────────────────────────────────────────────
# Test parse() — percorso principale
# ─────────────────────────────────────────────────────────────────────────────


class TestImageParserParse:
    """Test per ImageParser.parse() con pytesseract mockato."""

    def test_parse_success_with_text(self, tmp_path):
        """parse() con OCR che trova testo restituisce chunks con le parole."""
        from app.parsers.image_parser import ImageParser

        img_path = _make_png_file(tmp_path)
        ocr_data = _make_ocr_data(
            words=["Mario", "Rossi", "email@test.com"],
            confs=[90, 85, 92],
        )
        mock_pt = _mock_pytesseract(ocr_data)

        with patch.dict("sys.modules", {"pytesseract": mock_pt}):
            parser = ImageParser()
            result = parser.parse(img_path)

        assert result.success is True
        assert len(result.chunks) == 1  # Tutte sulla stessa linea
        assert "Mario" in result.chunks[0].text
        # image_path punta al file clean (prefisso clean_) salvato dal parser
        assert result.image_path is not None
        assert result.file_path == img_path

    def test_parse_success_multiple_lines(self, tmp_path):
        """parse() con OCR su più linee crea un chunk per ogni linea."""
        from app.parsers.image_parser import ImageParser

        img_path = _make_png_file(tmp_path, name="multi.png")
        ocr_data = _make_ocr_data(
            words=["Nome:", "Mario", "Email:", "test@example.com"],
            confs=[90, 88, 85, 92],
            line_nums=[1, 1, 2, 2],
            block_nums=[1, 1, 1, 1],
        )
        mock_pt = _mock_pytesseract(ocr_data)

        with patch.dict("sys.modules", {"pytesseract": mock_pt}):
            parser = ImageParser()
            result = parser.parse(img_path)

        assert result.success is True
        assert len(result.chunks) == 2
        assert "Nome:" in result.chunks[0].text
        assert "Email:" in result.chunks[1].text

    def test_parse_no_text_detected(self, tmp_path):
        """parse() con OCR che non trova testo aggiunge warning."""
        from app.parsers.image_parser import ImageParser

        img_path = _make_png_file(tmp_path, name="empty.png")
        # Solo parole vuote o spazi
        ocr_data = _make_ocr_data(words=["", "  ", ""], confs=[0, 0, 0])
        mock_pt = _mock_pytesseract(ocr_data)

        with patch.dict("sys.modules", {"pytesseract": mock_pt}):
            parser = ImageParser()
            result = parser.parse(img_path)

        assert result.success is True
        assert len(result.chunks) == 0
        assert len(result.warnings) == 1
        assert "non ha rilevato testo" in result.warnings[0]

    def test_parse_low_confidence_warning(self, tmp_path):
        """parse() con OCR di bassa qualità aggiunge warning di confidenza."""
        from app.parsers.image_parser import ImageParser

        img_path = _make_png_file(tmp_path, name="blurry.png")
        # 3/4 parole con confidenza < 60 (75% > soglia 30%)
        ocr_data = _make_ocr_data(
            words=["word1", "word2", "word3", "word4"],
            confs=[30, 25, 40, 90],
        )
        mock_pt = _mock_pytesseract(ocr_data)

        with patch.dict("sys.modules", {"pytesseract": mock_pt}):
            parser = ImageParser()
            result = parser.parse(img_path)

        assert result.success is True
        assert len(result.warnings) == 1
        assert "bassa qualità" in result.warnings[0]

    def test_parse_skips_negative_confidence(self, tmp_path):
        """parse() salta le parole con confidenza -1 (elementi non-testo di Tesseract)."""
        from app.parsers.image_parser import ImageParser

        img_path = _make_png_file(tmp_path, name="neg_conf.png")
        ocr_data = _make_ocr_data(
            words=["Mario", "ignored_neg", "Rossi"],
            confs=[90, -1, 85],
        )
        mock_pt = _mock_pytesseract(ocr_data)

        with patch.dict("sys.modules", {"pytesseract": mock_pt}):
            parser = ImageParser()
            result = parser.parse(img_path)

        assert result.success is True
        full_text = " ".join(c.text for c in result.chunks)
        assert "ignored_neg" not in full_text

    def test_parse_ocr_error_adds_warning(self, tmp_path):
        """parse() con errore OCR aggiunge warning e restituisce result parziale."""
        from app.parsers.image_parser import ImageParser

        img_path = _make_png_file(tmp_path, name="ocr_err.png")

        mock_pt = MagicMock()
        mock_pt.Output.DICT = "dict"
        mock_pt.image_to_data.side_effect = Exception("Tesseract not found")

        with patch.dict("sys.modules", {"pytesseract": mock_pt}):
            parser = ImageParser()
            result = parser.parse(img_path)

        # L'errore OCR viene catturato: o warning o success=False
        assert len(result.warnings) >= 1 or result.success is False

    def test_parse_import_error(self, tmp_path):
        """parse() con ImportError (pytesseract non installato) restituisce result con errore."""
        from app.parsers.image_parser import ImageParser

        img_path = _make_png_file(tmp_path, name="no_pytess.png")

        # Rimuove pytesseract dai moduli per simulare ImportError
        with patch.dict("sys.modules", {"pytesseract": None}):
            parser = ImageParser()
            result = parser.parse(img_path)

        assert result.success is False
        assert result.error_message is not None

    def test_parse_generic_exception(self, tmp_path):
        """parse() con eccezione generica durante PIL.Image.open restituisce result con errore."""
        from app.parsers.image_parser import ImageParser

        img_path = _make_png_file(tmp_path, name="generic_err.png")

        mock_pt = MagicMock()
        mock_pt.Output.DICT = "dict"

        with (
            patch.dict("sys.modules", {"pytesseract": mock_pt}),
            patch("PIL.Image.open", side_effect=RuntimeError("Unexpected PIL error")),
        ):
            parser = ImageParser()
            result = parser.parse(img_path)

        assert result.success is False
        assert result.error_message is not None

    def test_parse_jpeg_file(self, tmp_path):
        """parse() funziona anche con file .jpg."""
        from app.parsers.image_parser import ImageParser

        img_path = _make_jpg_file(tmp_path)
        ocr_data = _make_ocr_data(words=["Test"], confs=[95])
        mock_pt = _mock_pytesseract(ocr_data)

        with patch.dict("sys.modules", {"pytesseract": mock_pt}):
            parser = ImageParser()
            result = parser.parse(img_path)

        assert result.success is True
        assert result.image_path is not None
        assert result.file_path == img_path

    def test_parse_chunks_have_bbox(self, tmp_path):
        """parse() popola il campo bbox nei chunks."""
        from app.parsers.image_parser import ImageParser

        img_path = _make_png_file(tmp_path, name="bbox.png")
        ocr_data = _make_ocr_data(words=["Hello"], confs=[90])
        mock_pt = _mock_pytesseract(ocr_data)

        with patch.dict("sys.modules", {"pytesseract": mock_pt}):
            parser = ImageParser()
            result = parser.parse(img_path)

        assert result.success is True
        assert len(result.chunks) == 1
        assert result.chunks[0].bbox is not None


# ─────────────────────────────────────────────────────────────────────────────
# Test _strip_exif()
# ─────────────────────────────────────────────────────────────────────────────


class TestStripExif:
    """Test per ImageParser._strip_exif() con immagini PIL reali."""

    def test_strip_exif_rgb_image(self):
        """_strip_exif() su immagine RGB restituisce immagine senza metadati."""
        from app.parsers.image_parser import ImageParser

        img = Image.new("RGB", (10, 10), color=(255, 0, 0))
        result = ImageParser._strip_exif(img)

        assert result is not None
        assert result.mode in ("RGB", "RGBA", "L", "P")

    def test_strip_exif_rgba_image(self):
        """_strip_exif() su immagine RGBA converte in RGB prima di salvare."""
        from app.parsers.image_parser import ImageParser

        img = Image.new("RGBA", (10, 10), color=(255, 0, 0, 128))
        result = ImageParser._strip_exif(img)

        assert result is not None

    def test_strip_exif_palette_image(self):
        """_strip_exif() su immagine P (palette) converte in RGB."""
        from app.parsers.image_parser import ImageParser

        img = Image.new("P", (10, 10))
        result = ImageParser._strip_exif(img)

        assert result is not None


# ─────────────────────────────────────────────────────────────────────────────
# Test supported_extensions
# ─────────────────────────────────────────────────────────────────────────────


class TestSupportedExtensions:
    """Test per ImageParser.supported_extensions."""

    def test_supported_extensions(self):
        """ImageParser supporta .jpg, .jpeg, .png."""
        from app.parsers.image_parser import ImageParser

        parser = ImageParser()
        exts = parser.supported_extensions
        assert ".jpg" in exts
        assert ".jpeg" in exts
        assert ".png" in exts
