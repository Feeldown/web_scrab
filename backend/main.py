import cv2
import logging
import numpy as np
import pytesseract
import tempfile
import os
from contextlib import asynccontextmanager
from fastapi import FastAPI, File, UploadFile, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, ConfigDict, field_validator
from typing import Optional, List, Union


# ==============================
# Logging
# ==============================

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s - %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S"
)
logger = logging.getLogger("drug-api")


# ==============================
# Lifespan (startup / shutdown)
# ==============================

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    try:
        from search_engine import search_medicine, cleaned_data
        logger.info(f"Search engine loaded — {len(cleaned_data)} drugs in dataset")
    except Exception as e:
        logger.critical(f"Failed to load search engine: {e}")
        raise RuntimeError(f"Search engine init failed: {e}")
    yield
    # Shutdown
    logger.info("Server shutting down")


# ==============================
# App
# ==============================

app = FastAPI(
    title="Drug Information Retrieval System",
    version="1.0",
    lifespan=lifespan
)

allowed_origins_raw = os.getenv("ALLOWED_ORIGINS", "*").strip()
allowed_origin_regex = os.getenv("ALLOWED_ORIGIN_REGEX", r"https://.*\.vercel\.app")

if allowed_origins_raw == "*":
    allowed_origins = ["*"]
    allowed_origin_regex = None
else:
    allowed_origins = [o.strip() for o in allowed_origins_raw.split(",") if o.strip()]

app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_origin_regex=allowed_origin_regex,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ==============================
# Request / Response Models
# ==============================

class QueryRequest(BaseModel):
    query: str

    @field_validator("query")
    @classmethod
    def validate_query(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("query ต้องไม่ว่างเปล่า")
        if len(v) > 300:
            raise ValueError("query ยาวเกินไป (สูงสุด 300 ตัวอักษร)")
        if v.replace(" ", "").isdigit():
            raise ValueError("query ต้องมีชื่อยา ไม่ใช่ตัวเลขล้วน")
        return v


class SearchResult(BaseModel):
    model_config = ConfigDict(exclude_none=True)
    data: dict
    score: float
    tfidf_score: float
    fuzzy_score: float


class SearchMethodInfo(BaseModel):
    vector_model: str
    ranking: str
    top_results: int


class SearchResponse(BaseModel):
    """success case"""
    query: str
    status: str
    corrected_query: Optional[str] = None
    message: Optional[str] = None
    filter_by_strength: bool
    is_ocr: bool
    threshold_used: float
    search_method: Optional[SearchMethodInfo] = None
    results: List[SearchResult]


class SearchNotFoundResponse(BaseModel):
    """not_found case"""
    query: str
    status: str
    message: str
    threshold_used: float
    best_score: Optional[float] = None
    dataset_size: int


class SearchFallbackResponse(BaseModel):
    """fallback case (e.g. corrected_query suggestions)"""
    query: str
    status: str
    message: str
    corrected_query: Optional[str] = None
    results: List[SearchResult]


class OCRSearchResponse(BaseModel):
    model_config = ConfigDict(exclude_none=True)
    ocr_text: Optional[str] = None
    ocr_confidence: Optional[float] = None
    result: Optional[dict] = None
    error: Optional[str] = None


# ==============================
# Endpoints
# ==============================

@app.get("/")
def read_root():
    return {
        "project": "Drug Information Retrieval System",
        "version": "1.0",
        "status": "Running"
    }


@app.post(
    "/search",
    response_model=Union[SearchResponse, SearchNotFoundResponse, SearchFallbackResponse],
    response_model_exclude_none=True
)
def search(query_request: QueryRequest):
    from search_engine import search_medicine

    logger.info(f"[/search] query='{query_request.query}'")

    try:
        result = search_medicine(query_request.query, is_ocr=False)
        top_score = result.get("results", [{}])[0].get("score") if result.get("results") else "N/A"
        logger.info(f"[/search] status={result['status']} top_score={top_score}")
        return result

    except Exception as e:
        logger.error(f"[/search] error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="เกิดข้อผิดพลาดในการค้นหา")


# ==============================
# OCR Preprocessing
# ==============================

def preprocess_image(img: np.ndarray) -> np.ndarray:
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    gray = cv2.resize(gray, None, fx=2, fy=2, interpolation=cv2.INTER_CUBIC)
    denoised = cv2.fastNlMeansDenoising(gray, h=10)
    binary = cv2.adaptiveThreshold(
        denoised, 255,
        cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
        cv2.THRESH_BINARY,
        blockSize=31, C=10
    )
    return binary


# ==============================
# OCR with confidence filter
# ==============================

def ocr_image(image_path: str) -> tuple[str, float]:
    img = cv2.imread(image_path)

    if img is None:
        raise ValueError("ไม่สามารถอ่านไฟล์ภาพได้ ไฟล์อาจเสียหาย")

    processed = preprocess_image(img)

    data = pytesseract.image_to_data(
        processed,
        lang="tha+eng",
        config="--psm 11",
        output_type=pytesseract.Output.DICT
    )

    words, confidences = [], []
    for i, word in enumerate(data["text"]):
        conf = int(data["conf"][i])
        if conf > 60 and word.strip():
            words.append(word.strip())
            confidences.append(conf)

    text = " ".join(words)
    avg_conf = round(sum(confidences) / len(confidences), 1) if confidences else 0.0

    return text, avg_conf


# ==============================
# OCR Endpoint
# ==============================

ALLOWED_EXTENSIONS = (".png", ".jpg", ".jpeg")
MAX_FILE_SIZE_MB = 10

@app.post("/ocr-search", response_model=OCRSearchResponse, response_model_exclude_none=True)
async def ocr_search(file: UploadFile = File(...)):
    from search_engine import search_medicine

    # ตรวจสอบนามสกุลไฟล์
    if not file.filename.lower().endswith(ALLOWED_EXTENSIONS):
        logger.warning(f"[/ocr-search] invalid file type: {file.filename}")
        return OCRSearchResponse(error="รองรับเฉพาะไฟล์ภาพ .png .jpg .jpeg")

    # อ่านไฟล์และตรวจสอบขนาด
    content = await file.read()
    size_mb = len(content) / (1024 * 1024)

    if size_mb > MAX_FILE_SIZE_MB:
        logger.warning(f"[/ocr-search] file too large: {size_mb:.1f} MB")
        return OCRSearchResponse(error=f"ไฟล์ใหญ่เกินไป (สูงสุด {MAX_FILE_SIZE_MB} MB)")

    logger.info(f"[/ocr-search] file='{file.filename}' size={size_mb:.2f}MB")

    # บันทึกไฟล์ชั่วคราวพร้อม extension เดิม
    with tempfile.NamedTemporaryFile(delete=False, suffix=os.path.splitext(file.filename)[1]) as tmp:
        tmp.write(content)
        temp_path = tmp.name

    try:
        extracted_text, avg_confidence = ocr_image(temp_path)
        logger.info(f"[/ocr-search] OCR text='{extracted_text[:80]}' confidence={avg_confidence}%")

        if not extracted_text.strip():
            return OCRSearchResponse(
                error="ไม่สามารถอ่านข้อความจากภาพได้",
                ocr_confidence=avg_confidence
            )

        result = search_medicine(extracted_text, is_ocr=True)
        logger.info(f"[/ocr-search] search status={result['status']}")

        return OCRSearchResponse(
            ocr_text=extracted_text,
            ocr_confidence=avg_confidence,
            result=result
        )

    except ValueError as e:
        logger.warning(f"[/ocr-search] validation error: {e}")
        return OCRSearchResponse(error=str(e))

    except Exception as e:
        logger.error(f"[/ocr-search] unexpected error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="เกิดข้อผิดพลาดในการประมวลผลภาพ")

    finally:
        if os.path.exists(temp_path):
            os.remove(temp_path)