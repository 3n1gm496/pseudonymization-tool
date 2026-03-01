"""
Parser per immagini .jpg/.png.
Esegue OCR locale con Tesseract, estrae testo e bounding box,
e rimuove i metadati EXIF.
"""
import logging
from pathlib import Path
from typing import List, Optional

from app.parsers.base import BaseParser, ParseResult, TextChunk
from app.core.config import OCR_LANGUAGES
from app.core.exceptions import ImageParsingError

logger = logging.getLogger(__name__)


class ImageParser(BaseParser):
    """Parser per immagini JPG e PNG con OCR locale."""

    @property
    def supported_extensions(self) -> List[str]:
        return [".jpg", ".jpeg", ".png"]

    def parse(self, file_path: Path) -> ParseResult:
        result = ParseResult(file_path=file_path, is_image=True)
        result.image_path = file_path

        try:
            import pytesseract
            from PIL import Image

            # Apri l'immagine e rimuovi i metadati EXIF creando una copia pulita
            original_image = Image.open(str(file_path))

            # Crea una copia senza metadati EXIF
            clean_image = self._strip_exif(original_image)

            # Salva l'immagine pulita (senza EXIF) nella stessa directory temporanea
            clean_path = file_path.parent / f"clean_{file_path.name}"
            clean_image.save(str(clean_path))
            result.image_path = clean_path

            # Esegui OCR con bounding box per parola
            try:
                ocr_data = pytesseract.image_to_data(
                    clean_image,
                    lang=OCR_LANGUAGES,
                    output_type=pytesseract.Output.DICT
                )
            except Exception as ocr_err:
                result.success = False
                result.error_message = (
                    f"Errore durante l'esecuzione dell'OCR: {ocr_err}. "
                    f"Verificare che Tesseract sia installato correttamente."
                )
                return result

            # Estrai le parole con confidenza sufficiente
            n_boxes = len(ocr_data["text"])
            low_confidence_words = 0
            total_words = 0

            # Raggruppa le parole per linea per creare chunk di testo significativi
            lines: dict = {}
            for i in range(n_boxes):
                word = ocr_data["text"][i].strip()
                if not word:
                    continue

                conf = int(ocr_data["conf"][i])
                if conf < 0:  # Tesseract usa -1 per elementi non-testo
                    continue

                total_words += 1
                line_num = ocr_data["line_num"][i]
                block_num = ocr_data["block_num"][i]
                line_key = (block_num, line_num)

                if line_key not in lines:
                    lines[line_key] = {
                        "words": [],
                        "bboxes": [],
                        "confs": [],
                        "line_num": ocr_data["line_num"][i],
                    }

                x, y, w, h = (
                    ocr_data["left"][i],
                    ocr_data["top"][i],
                    ocr_data["width"][i],
                    ocr_data["height"][i],
                )
                lines[line_key]["words"].append(word)
                lines[line_key]["bboxes"].append([x, y, w, h])
                lines[line_key]["confs"].append(conf)

                if conf < 60:
                    low_confidence_words += 1

            # Crea TextChunk per ogni linea OCR
            for line_key, line_data in sorted(lines.items()):
                line_text = " ".join(line_data["words"])
                avg_conf = sum(line_data["confs"]) / len(line_data["confs"]) if line_data["confs"] else 0

                # Calcola il bounding box che racchiude tutta la linea
                if line_data["bboxes"]:
                    all_x = [b[0] for b in line_data["bboxes"]]
                    all_y = [b[1] for b in line_data["bboxes"]]
                    all_x2 = [b[0] + b[2] for b in line_data["bboxes"]]
                    all_y2 = [b[1] + b[3] for b in line_data["bboxes"]]
                    bbox = [min(all_x), min(all_y), max(all_x2) - min(all_x), max(all_y2) - min(all_y)]
                else:
                    bbox = None

                result.chunks.append(
                    TextChunk(
                        text=line_text,
                        source_ref=f"blocco {line_key[0]}, linea {line_key[1]}",
                        line_number=line_data["line_num"],
                        bbox=bbox,
                    )
                )

            # Warning se OCR di bassa qualità
            if total_words == 0:
                result.warnings.append(
                    "L'OCR non ha rilevato testo nell'immagine. "
                    "L'immagine potrebbe essere vuota, di bassa qualità o contenere solo grafica. "
                    "ATTENZIONE: il file è marcato come parzialmente processato."
                )
            elif total_words > 0 and low_confidence_words / total_words > 0.3:
                result.warnings.append(
                    f"OCR di bassa qualità: {low_confidence_words}/{total_words} parole hanno confidenza < 60%. "
                    f"Potrebbero esserci dati sensibili non rilevati. "
                    f"ATTENZIONE: il file è marcato come parzialmente processato."
                )

        except ImportError as e:
            result.success = False
            result.error_message = f"Libreria mancante per il processing delle immagini: {e}"
            logger.error("Missing image processing library: %s", e)
        except ImageParsingError as e:
            result.success = False
            result.error_message = str(e)
            logger.warning("Image parsing error: %s", e)
        except Exception as e:
            result.success = False
            result.error_message = f"Errore durante il parsing dell'immagine: {e}"
            logger.error("Unexpected error in image parser: %s", e)

        return result

    @staticmethod
    def _strip_exif(image) -> object:
        """
        Crea una copia dell'immagine senza metadati EXIF.
        Questo viene fatto ricreando l'immagine da zero dai dati pixel.
        """
        from PIL import Image
        import io

        # Metodo robusto: salva in buffer senza metadati e ricarica
        buffer = io.BytesIO()
        # Converti in RGB se necessario (es. RGBA non supportato da JPEG)
        if image.mode in ("RGBA", "P"):
            clean = image.convert("RGB")
        else:
            clean = image.copy()

        # Salva senza info EXIF
        clean.save(buffer, format="PNG")
        buffer.seek(0)
        return Image.open(buffer).copy()
