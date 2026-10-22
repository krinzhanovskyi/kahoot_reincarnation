from api.client import get_json
from api.config import QUIZ_URL

def get_quiz_answers(uuid):
    data = get_json(f"{QUIZ_URL}{uuid}")
    questions_data = []

    for q in data.get("questions", []):
        question_text = q.get("question", "Unknown Question")
        correct_answers = [
            c.get("answer", "Unknown Answer")
            for c in q.get("choices", [])
            if c.get("correct") is True
        ]
        questions_data.append({"question": question_text, "answers": correct_answers})

    return questions_data
