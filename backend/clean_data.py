import json
import re

# โหลด dataset
with open("Project/drug_backup.json", "r", encoding="utf-8") as f:
    raw_data = json.load(f)

cleaned_data = []

# ── Fields ที่ไม่ต้องการใน full_data ──
EXCLUDED_FIELDS = {"URL", "url", "แหล่งอ้างอิง", "website"}


def extract_strength(text):
    match = re.search(r'(\d+)\s*(mg|g|mcg|ml|%)?', text, re.IGNORECASE)
    if match:
        return f"{match.group(1)} mg"
    return None


def clean_text(text):
    """
    ลบ symbol ที่ทำให้ search พัง
    """
    text = text.lower()
    text = re.sub(r'[\[\]\(\)\-_/]', ' ', text)
    text = re.sub(r'\s+', ' ', text)
    return text.strip()


def generate_alias(generic, brand):
    """
    สร้าง alias อัตโนมัติ
    """
    alias_words = []

    generic_clean = clean_text(generic)
    brand_clean = clean_text(brand)

    alias_words.append(generic_clean)
    alias_words.append(brand_clean)

    # เพิ่มคำตัด
    alias_words += generic_clean.split()
    alias_words += brand_clean.split()

    return " ".join(set(alias_words))


for idx, item in enumerate(raw_data):

    generic_name = item.get("ชื่อสามัญ", "").strip()
    brand_raw = item.get("ชื่อการค้า", "").strip()
    form = item.get("รูปแบบยา", "").strip()

    strength = extract_strength(brand_raw)

    brand_name = re.sub(r'\d+\s*(mg|มก)?', '', brand_raw)

    # ⭐ สร้าง alias อัตโนมัติ
    alias = generate_alias(generic_name, brand_name)

    search_words = [
        generic_name,
        brand_name,
        alias,
        form,
        strength if strength else ""
    ]

    search_text = " ".join(search_words).lower()

    # ── ตัด URL และ field ที่ไม่ต้องการออกจาก full_data ──
    full_data = {k: v for k, v in item.items() if k not in EXCLUDED_FIELDS}

    new_record = {
        "id": idx + 1,
        "generic_name": generic_name,
        "brand_name": brand_name,
        "strength": strength,
        "form": form,
        "search_text": search_text,
        "full_data": full_data
    }

    cleaned_data.append(new_record)


with open("cleaned_medicine.json", "w", encoding="utf-8") as f:
    json.dump(cleaned_data, f, ensure_ascii=False, indent=2)

print(f"✅ cleaned_medicine.json created — {len(cleaned_data)} records")