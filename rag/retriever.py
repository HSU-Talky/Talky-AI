import json
from rag.database import get_db, get_embedding_model

def retrieve_scenario(query_text: str):
    """
    사용자의 입력(query_text)을 받아 가장 유사한 시나리오 1개를 검색하여 반환합니다.
    """
    if not query_text.strip():
        return None

    collection = get_db()
    model = get_embedding_model()

    # 1. 검색어 임베딩
    query_embedding = model.encode(query_text, convert_to_numpy=True).tolist()

    # 2. ChromaDB에 쿼리
    results = collection.query(
        query_embeddings=[query_embedding],
        n_results=1
    )
    
    # 3. 결과 파싱 및 반환
    if results and results['ids'][0]:
        scenario_id = results['ids'][0][0]
        # document에 저장된 content json 문자열을 다시 파싱
        retrieved_content = json.loads(results['documents'][0][0]) 
        print(f"✅ RAG 성공: '{scenario_id}' 시나리오를 검색했습니다.")
        return retrieved_content
    else:
        print("🟡 RAG: 유사한 시나리오를 찾지 못했습니다.")
        return None