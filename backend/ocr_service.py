import os
import pytesseract
from PIL import Image
import io
from pdf2image import convert_from_bytes
import traceback

# Configure Tesseract path for Windows
pytesseract.pytesseract.tesseract_cmd = r'C:\Program Files\Tesseract-OCR\tesseract.exe'

class OCRService:
    @staticmethod
    def extract_text(file_bytes: bytes, mime_type: str) -> str:
        """
        Extract text from images or PDFs using Tesseract OCR.
        For PDFs, it converts pages to images first.
        """
        try:
            print(f"[OCR] Starting extraction for {mime_type}...")
            text = ""
            
            if mime_type == 'application/pdf':
                try:
                    # Method 1: pdf2image (Requires Poppler)
                    images = convert_from_bytes(file_bytes)
                    print(f"[OCR] PDF converted via pdf2image ({len(images)} pages)")
                except Exception as p2i_err:
                    print(f"[OCR] pdf2image failed (likely missing Poppler): {p2i_err}")
                    print(f"[OCR] Attempting fallback via PyMuPDF...")
                    import fitz
                    from PIL import Image
                    doc = fitz.open(stream=file_bytes, filetype="pdf")
                    images = []
                    for page in doc:
                        pix = page.get_pixmap()
                        img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
                        images.append(img)
                    print(f"[OCR] PDF converted via PyMuPDF ({len(images)} pages)")
                
                for i, image in enumerate(images):
                    page_text = pytesseract.image_to_string(image)
                    text += f"\n--- Page {i+1} ---\n{page_text}"
            else:
                # Assume image (JPG/PNG)
                image = Image.open(io.BytesIO(file_bytes))
                text = pytesseract.image_to_string(image)
            
            cleaned_text = OCRService._clean_text(text)
            print(f"[OCR] Extraction complete. Length: {len(cleaned_text)}")
            return cleaned_text
        except Exception as e:
            print(f"[OCR] Error: {e}")
            traceback.print_exc()
            return ""

    @staticmethod
    def _clean_text(text: str) -> str:
        """Basic cleanup of OCR output."""
        if not text: return ""
        # Remove excessive whitespace
        lines = [line.strip() for line in text.split('\n') if line.strip()]
        return '\n'.join(lines)

ocr_service = OCRService()
