from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import Pipeline
import numpy as np
import re

# Training data
TRAINING_DATA = [
    # Roads/Public Works
    ("pothole on road large crack", "Roads/Public Works"),
    ("road damaged broken surface", "Roads/Public Works"),
    ("footpath broken pavement cracked", "Roads/Public Works"),
    ("road repair needed highway", "Roads/Public Works"),
    ("bridge damage crack", "Roads/Public Works"),
    ("construction debris blocking road", "Roads/Public Works"),
    ("speed breaker damaged", "Roads/Public Works"),
    ("road divider broken", "Roads/Public Works"),
    ("pavement footpath needs repair", "Roads/Public Works"),
    ("road marking faded", "Roads/Public Works"),
    # Sanitation
    ("garbage not collected waste overflowing", "Sanitation"),
    ("trash bin overflow litter", "Sanitation"),
    ("waste dump illegal dumping", "Sanitation"),
    ("sanitation worker not coming", "Sanitation"),
    ("garbage heap smell", "Sanitation"),
    ("open defecation area", "Sanitation"),
    ("dead animal carcass removal", "Sanitation"),
    ("public toilet not cleaned", "Sanitation"),
    ("dustbin full garbage spilling", "Sanitation"),
    ("sweeping not done", "Sanitation"),
    # Drainage/Water
    ("drain blocked flooding water logged", "Drainage/Water"),
    ("water pipe leakage burst", "Drainage/Water"),
    ("drainage overflow sewage smell", "Drainage/Water"),
    ("water supply cut shortage", "Drainage/Water"),
    ("manhole open uncovered sewer", "Drainage/Water"),
    ("flood water stagnant", "Drainage/Water"),
    ("tap water no supply", "Drainage/Water"),
    ("sewer line choked blocked", "Drainage/Water"),
    ("water contaminated dirty supply", "Drainage/Water"),
    ("pipeline damage leak underground", "Drainage/Water"),
    # Electrical
    ("streetlight not working dark", "Electrical"),
    ("electric pole fallen wire", "Electrical"),
    ("power outage blackout", "Electrical"),
    ("transformer fault sparking", "Electrical"),
    ("electric shock hazard exposed wire", "Electrical"),
    ("street lamp broken bulb", "Electrical"),
    ("electricity supply irregular", "Electrical"),
    ("high tension wire hanging low", "Electrical"),
    ("meter tampering theft electricity", "Electrical"),
    ("electric box open dangerous", "Electrical"),
]

PRIORITY_KEYWORDS = {
    'Emergency': ['emergency', 'urgent', 'accident', 'danger', 'hazard', 'shock', 'exposed wire',
                  'open manhole', 'sparking', 'fire', 'flood', 'collapse', 'injury', 'gas leak'],
    'High': ['severe', 'major', 'serious', 'critical', 'days', 'week', 'long time', 'blocking',
             'overflow', 'burst', 'fallen pole', 'completely broken'],
    'Medium': ['moderate', 'broken', 'damaged', 'leaking', 'not working', 'missing', 'cracked'],
    'Low': ['minor', 'small', 'little', 'slightly', 'notice', 'faded', 'cosmetic'],
}

class IssueClassifier:
    def __init__(self):
        self.pipeline = Pipeline([
            ('tfidf', TfidfVectorizer(ngram_range=(1, 2), max_features=500)),
            ('clf', LogisticRegression(max_iter=1000, C=5.0)),
        ])
        self._train()

    def _train(self):
        texts = [d[0] for d in TRAINING_DATA]
        labels = [d[1] for d in TRAINING_DATA]
        self.pipeline.fit(texts, labels)

    def predict_category(self, text):
        pred = self.pipeline.predict([text])[0]
        proba = self.pipeline.predict_proba([text])[0]
        confidence = float(max(proba))
        return pred, confidence

    def predict_priority(self, text):
        text_lower = text.lower()
        for priority in ['Emergency', 'High', 'Medium', 'Low']:
            for kw in PRIORITY_KEYWORDS[priority]:
                if kw in text_lower:
                    return priority
        return 'Medium'

    def validate_image_description(self, description, image_filename):
        if not image_filename:
            return False, "No image uploaded"
        ext = image_filename.rsplit('.', 1)[-1].lower() if '.' in image_filename else ''
        if ext not in ['png', 'jpg', 'jpeg', 'gif', 'webp']:
            return False, "Invalid image format"
        if len(description.strip()) < 20:
            return False, "Description too short. Please provide at least 20 characters."
        # Basic relevance: description must have at least 3 meaningful words
        words = re.findall(r'\b[a-zA-Z]{3,}\b', description.lower())
        if len(words) < 3:
            return False, "Description must contain meaningful words describing the issue."
        return True, "Valid"

classifier = IssueClassifier()
