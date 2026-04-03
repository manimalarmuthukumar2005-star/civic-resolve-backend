import re
import os
import joblib
import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import Pipeline

# ── Training data ────────────────────────────────────────────────────────────
TRAINING_DATA = [
    # Roads/Public Works
    ("pothole on the road dangerous driving", "Roads/Public Works"),
    ("road is broken needs repair urgently", "Roads/Public Works"),
    ("footpath pavement damaged cracked", "Roads/Public Works"),
    ("bridge construction problem road", "Roads/Public Works"),
    ("speed breaker missing road accident", "Roads/Public Works"),
    ("road divider broken damaged highway", "Roads/Public Works"),
    ("traffic signal not working road", "Roads/Public Works"),
    ("road signs missing dangerous", "Roads/Public Works"),
    ("construction debris blocking road", "Roads/Public Works"),
    ("road marking faded unclear lane", "Roads/Public Works"),
    # Sanitation
    ("garbage not collected overflowing bin", "Sanitation"),
    ("waste dumped illegally trash pile", "Sanitation"),
    ("stray animals near garbage area", "Sanitation"),
    ("public toilet unclean unhygienic", "Sanitation"),
    ("littering park trash not cleaned", "Sanitation"),
    ("dustbin bin full overflow smell", "Sanitation"),
    ("dead animal carcass on road", "Sanitation"),
    ("open defecation public nuisance", "Sanitation"),
    ("commercial waste dumping illegal", "Sanitation"),
    ("cleaning sweeping not done area", "Sanitation"),
    # Drainage/Water
    ("drain blocked flooding water stagnant", "Drainage/Water"),
    ("water pipe leaking burst road", "Drainage/Water"),
    ("sewage overflow manhole open", "Drainage/Water"),
    ("waterlogging rain no drainage", "Drainage/Water"),
    ("contaminated water supply dirty", "Drainage/Water"),
    ("no water supply tap dry", "Drainage/Water"),
    ("gutter choked water overflow", "Drainage/Water"),
    ("sewer line blocked smell", "Drainage/Water"),
    ("storm drain clogged flood", "Drainage/Water"),
    ("water meter not working", "Drainage/Water"),
    # Electrical
    ("streetlight not working dark area", "Electrical"),
    ("electric pole wire hanging dangerous", "Electrical"),
    ("power outage no electricity supply", "Electrical"),
    ("transformer sparking fire hazard", "Electrical"),
    ("street lamp broken vandalized", "Electrical"),
    ("electric short circuit sparks", "Electrical"),
    ("public area lights off night", "Electrical"),
    ("overhead wire sagging low voltage", "Electrical"),
    ("meter box open exposed wires", "Electrical"),
    ("generator failure backup power", "Electrical"),
]

TEXTS = [t for t, _ in TRAINING_DATA]
LABELS = [l for _, l in TRAINING_DATA]

MODEL_PATH = os.path.join(os.path.dirname(__file__), "classifier_model.pkl")

def train_classifier():
    pipeline = Pipeline([
        ('tfidf', TfidfVectorizer(ngram_range=(1, 2), max_features=5000)),
        ('clf', LogisticRegression(max_iter=1000, C=1.0))
    ])
    pipeline.fit(TEXTS, LABELS)
    joblib.dump(pipeline, MODEL_PATH)
    return pipeline

def load_or_train():
    if os.path.exists(MODEL_PATH):
        return joblib.load(MODEL_PATH)
    return train_classifier()

_classifier = None

def get_classifier():
    global _classifier
    if _classifier is None:
        _classifier = load_or_train()
    return _classifier

DEPARTMENT_MAP = {
    "Roads/Public Works": "Roads & Public Works Department",
    "Sanitation": "Sanitation & Waste Management Department",
    "Drainage/Water": "Drainage & Water Supply Department",
    "Electrical": "Electrical & Street Lighting Department",
}

DEPARTMENT_EMAILS = {
    "Roads/Public Works": "roads@civic.gov",
    "Sanitation": "sanitation@civic.gov",
    "Drainage/Water": "drainage@civic.gov",
    "Electrical": "electrical@civic.gov",
}

def categorize_complaint(text):
    clf = get_classifier()
    probs = clf.predict_proba([text])[0]
    classes = clf.classes_
    idx = np.argmax(probs)
    category = classes[idx]
    confidence = float(probs[idx])
    department = DEPARTMENT_MAP.get(category, "General Administration")
    dept_email = DEPARTMENT_EMAILS.get(category, "admin@civic.gov")
    return {
        "category": category,
        "department": department,
        "department_email": dept_email,
        "confidence": round(confidence, 3),
    }

# ── Priority prediction ───────────────────────────────────────────────────────
EMERGENCY_KEYWORDS = [
    "dangerous", "emergency", "fire", "accident", "electrocution",
    "collapse", "flood", "explosion", "sparking", "hazard", "urgent",
    "severe", "critical", "life threatening", "immediately", "burst",
]
HIGH_KEYWORDS = [
    "broken", "blocked", "leak", "overflow", "stagnant", "dark",
    "not working", "damaged", "contaminated", "open manhole", "pothole",
    "overflowing", "short circuit", "hanging wire",
]
MEDIUM_KEYWORDS = [
    "dirty", "unclean", "smell", "faded", "missing", "no supply",
    "garbage", "waste", "dustbin", "litter", "crack", "worn",
]

def predict_priority(text):
    text_lower = text.lower()
    if any(kw in text_lower for kw in EMERGENCY_KEYWORDS):
        return "Emergency"
    if any(kw in text_lower for kw in HIGH_KEYWORDS):
        return "High"
    if any(kw in text_lower for kw in MEDIUM_KEYWORDS):
        return "Medium"
    return "Low"

# ── Image-description validation ─────────────────────────────────────────────
CATEGORY_VISUAL_KEYWORDS = {
    "Roads/Public Works": ["road", "pothole", "asphalt", "pavement", "crack", "street", "construction", "bridge", "highway"],
    "Sanitation": ["garbage", "trash", "waste", "bin", "litter", "dump", "dirty", "plastic", "rubbish"],
    "Drainage/Water": ["water", "drain", "flood", "pipe", "puddle", "manhole", "sewer", "wet", "leak"],
    "Electrical": ["wire", "light", "pole", "electric", "dark", "lamp", "cable", "transformer"],
}

def validate_image_description(description, category, image_filename=None):
    """Basic validation: checks if description keywords match expected category keywords."""
    if not description:
        return False, "Description is required."
    
    desc_lower = description.lower()
    
    # Check word count
    if len(desc_lower.split()) < 5:
        return False, "Description too short. Please provide more detail."
    
    # If no category yet, skip image-category check
    if not category:
        return True, "Valid"
    
    visual_kws = CATEGORY_VISUAL_KEYWORDS.get(category, [])
    combined_text = desc_lower
    if image_filename:
        combined_text += " " + image_filename.lower().replace("_", " ").replace("-", " ")
    
    matches = [kw for kw in visual_kws if kw in combined_text]
    
    # Require at least 1 visual keyword match
    if not matches and visual_kws:
        return False, (
            f"Your image or description doesn't seem to match the detected category '{category}'. "
            f"Please upload an image relevant to: {', '.join(visual_kws[:5])}."
        )
    
    return True, "Valid"
