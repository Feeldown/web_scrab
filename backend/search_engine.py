import json
import re
import os
from collections import defaultdict
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity
from rapidfuzz import fuzz


# ==============================
# Load dataset
# ==============================

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
json_path = os.path.join(BASE_DIR, "cleaned_medicine.json")

with open(json_path, "r", encoding="utf-8") as f:
    cleaned_data = json.load(f)


# ==============================
# SYNONYMS (ไทย / พิมพ์ง่าย)
# ==============================

SYNONYMS = {
    "พารา": "paracetamol",
    "พาราเซตามอล": "paracetamol",
    "ยาแก้ปวด": "paracetamol",
    "ยาแก้ไข้": "paracetamol",
    "amox": "amoxicillin",
    "ยาแก้อักเสบ": "amoxicillin"
}


def apply_synonyms(text):
    for k, v in SYNONYMS.items():
        if k in text:
            text = text.replace(k, v)
    return text


# ==============================
# OCR normalization
# ==============================

def normalize_ocr(text):
    text = text.lower()

    replacements = {
        "0": "o",
        "1": "l",
        "5": "s",
        "|": "l"
    }

    for k, v in replacements.items():
        text = text.replace(k, v)

    text = re.sub(r'[^a-z0-9ก-๙\s]', ' ', text)
    text = re.sub(r'\s+', ' ', text)

    return text.strip()


# ==============================
# TF-IDF model
# ==============================

vectorizer = TfidfVectorizer(
    analyzer="char_wb",
    ngram_range=(3, 5)
)

corpus = [item["search_text"] for item in cleaned_data]
tfidf_matrix = vectorizer.fit_transform(corpus)


# ==============================
# Strength index
# ==============================

strength_index = defaultdict(list)

for i, item in enumerate(cleaned_data):
    if item["strength"]:
        strength_key = item["strength"].lower()
        strength_index[strength_key].append(i)


# ==============================
# Extract strength
# ==============================

def extract_strength(text):
    match = re.search(
        r'(\d+(?:\.\d+)?)\s?(mg|mcg|g|ml|iu|%)',
        text,
        re.IGNORECASE
    )

    if match:
        value = match.group(1)
        unit = match.group(2).lower()

        if '.' in value and value.endswith('0'):
            value = value.rstrip('0').rstrip('.')

        return f"{value} {unit}"

    return None


# ==============================
# Auto correct (Fuzzy)
# ==============================

def auto_correct(query):
    best_match = query
    best_score = 0

    for item in cleaned_data:
        text = item["search_text"]
        score = fuzz.ratio(query, text)

        if score > best_score:
            best_score = score
            best_match = text

    if best_score > 70:
        return best_match

    return query


# ==============================
# Highlight (for UI)
# ==============================

def highlight(text, query):
    for word in query.split():
        if len(word) > 2:
            text = text.replace(word, f"<mark>{word}</mark>")
    return text


# ==============================
# Dynamic threshold
# ==============================

def get_threshold(is_ocr: bool) -> float:
    return 0.45 if is_ocr else 0.60


# ==============================
# Main Search Function
# ==============================

def search_medicine(query: str, is_ocr: bool = False):

    original_query = query

    # Normalize + Synonym + AutoCorrect
    query = normalize_ocr(query)
    query = apply_synonyms(query)
    query = auto_correct(query)

    strength = extract_strength(query)

    # -------------------------
    # Phase 1 : Strength filter
    # -------------------------

    if strength and strength in strength_index:
        candidate_indexes = strength_index[strength]
        matrix_subset = tfidf_matrix[candidate_indexes]
        filter_applied = True
    else:
        candidate_indexes = list(range(len(cleaned_data)))
        matrix_subset = tfidf_matrix
        filter_applied = False

    # -------------------------
    # Phase 2 : TF-IDF
    # -------------------------

    query_vec = vectorizer.transform([query])
    tfidf_scores = cosine_similarity(query_vec, matrix_subset)[0]

    top_k = min(50, len(tfidf_scores))
    top_indices = tfidf_scores.argsort()[-top_k:][::-1]

    candidate_list = [
        (candidate_indexes[i], float(tfidf_scores[i]))
        for i in top_indices
    ]

    # -------------------------
    # Phase 3 : Fuzzy re-rank
    # -------------------------

    scored_results = []

    for idx, tfidf_score in candidate_list:
        item = cleaned_data[idx]
        text = item["search_text"]

        fuzzy_score1 = fuzz.token_set_ratio(query, text) / 100
        fuzzy_score2 = fuzz.partial_ratio(query, text) / 100
        fuzzy_score = max(fuzzy_score1, fuzzy_score2)

        final_score = 0.4 * tfidf_score + 0.6 * fuzzy_score

        scored_results.append({
            "data": item,
            "score": round(final_score, 4),
            "tfidf_score": round(tfidf_score, 4),
            "fuzzy_score": round(fuzzy_score, 4),
            "highlight": highlight(text, query)
        })

    scored_results.sort(key=lambda x: x["score"], reverse=True)

    top_results = scored_results[:5]

    threshold = get_threshold(is_ocr)

    # -------------------------
    # Not found
    # -------------------------

    if not top_results:
        return {
            "status": "not_found",
            "message": "ไม่พบข้อมูลยา"
        }

    # -------------------------
    # Fallback mode 🔥
    # -------------------------

    if top_results[0]["score"] < threshold:
        return {
            "query": original_query,
            "corrected_query": query,
            "status": "fallback",
            "message": "ไม่มั่นใจ แต่ลองดูผลลัพธ์ใกล้เคียง",
            "results": top_results[:3],
            "best_score": top_results[0]["score"]
        }

    # -------------------------
    # Success
    # -------------------------

    return {
        "query": original_query,
        "corrected_query": query,
        "status": "success",
        "filter_by_strength": filter_applied,
        "is_ocr": is_ocr,
        "threshold_used": threshold,
        "results": top_results
    }