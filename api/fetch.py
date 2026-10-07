import requests
from api.config import QUIZ_URL, HEADERS

def get_quiz_answers(uuid):
    try:
        response = requests.get(f"{QUIZ_URL}{uuid}", headers=HEADERS)
        response.raise_for_status()
        data = response.json()
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
    except Exception:
        return []