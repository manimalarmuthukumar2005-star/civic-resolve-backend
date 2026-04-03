import re

POSITIVE_WORDS = ['good', 'great', 'excellent', 'satisfied', 'happy', 'resolved', 'fast',
                  'quick', 'awesome', 'perfect', 'thanks', 'thank', 'helpful', 'nice', 'well']
NEGATIVE_WORDS = ['bad', 'poor', 'terrible', 'horrible', 'dissatisfied', 'slow', 'not', 'never',
                  'again', 'worst', 'useless', 'pathetic', 'delayed', 'ignored', 'unresolved',
                  'still', 'pending', 'disappointed', 'unacceptable', 'broken']

def analyze_sentiment(text, rating=None):
    text_lower = text.lower() if text else ''
    words = re.findall(r'\b\w+\b', text_lower)
    pos = sum(1 for w in words if w in POSITIVE_WORDS)
    neg = sum(1 for w in words if w in NEGATIVE_WORDS)
    
    text_sentiment = 'Neutral'
    if pos > neg:
        text_sentiment = 'Positive'
    elif neg > pos:
        text_sentiment = 'Negative'
    
    # Combine with rating
    if rating is not None:
        if rating >= 4:
            return 'Positive'
        elif rating <= 2:
            return 'Negative'
        else:
            return text_sentiment
    return text_sentiment

def should_reopen(rating, comment):
    sentiment = analyze_sentiment(comment, rating)
    return rating is not None and (rating < 3 or sentiment == 'Negative')
