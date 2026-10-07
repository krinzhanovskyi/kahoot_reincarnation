import requests
from api.config import SEARCH_URL, HEADERS

def search_quizzes(query, limit=5):
    params = {"query": query, "cursor": 0, "limit": limit}
    try:
        response = requests.get(SEARCH_URL, params=params, headers=HEADERS)
        response.raise_for_status()
        data = response.json()
        
        results = []
        for item in data.get("entities", []):
            quiz_data = item.get("kahoot", item.get("card", item))
            uuid = quiz_data.get("uuid")
            title = quiz_data.get("title", "Untitled")
            
            if uuid:
                results.append({"title": title, "uuid": uuid})
                
        return results
    except Exception:
        return []