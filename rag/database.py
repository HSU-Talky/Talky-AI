import json
import chromadb
import google.generativeai as genai
from sentence_transformers import SentenceTransformer

# --- 설정 ---
SCENARIOS_PATH = "./data/scenarios.json"
DB_PATH = "./data/vector_db"
COLLECTION_NAME = "talky_scenarios"
EMBEDDING_MODEL_NAME = "all-MiniLM-L12-v2" # SBERT 모델

# --- 전역 변수 (싱글톤) ---
_db_client = None
_scenario_collection = None
_embedding_model = None

def get_embedding_model():
    """임베딩 모델을 한 번만 로드하여 재사용 (싱글톤)"""
    global _embedding_model
    if _embedding_model is None:
        _embedding_model = SentenceTransformer(EMBEDDING_MODEL_NAME)
    return _embedding_model

def get_db():
    """ChromaDB 클라이언트와 컬렉션을 한 번만 초기화하여 재사용"""
    global _db_client, _scenario_collection
    if _db_client is None:
        _db_client = chromadb.PersistentClient(path=DB_PATH)
        _scenario_collection = _db_client.get_or_create_collection(name=COLLECTION_NAME)
    return _scenario_collection

def build_database(force_rebuild=False):
    """
    scenarios.json 파일을 읽어 ChromaDB에 벡터 데이터베이스를 구축하는 함수.
    최초 1회 또는 데이터 업데이트 시 실행합니다.
    """
    collection = get_db()
    
    # 강제 재구축 옵션
    if force_rebuild:
        print("기존 데이터를 삭제하고 재구축합니다...")
        try:
            collection.delete_collection()
            collection = get_db()
        except:
            print("컬렉션 삭제 실패, 계속 진행합니다...")
    
    # DB에 이미 데이터가 있으면 중복 구축 방지
    if collection.count() > 0 and not force_rebuild:
        print(f"이미 {collection.count()}개의 데이터가 존재합니다. 구축을 건너뜁니다.")
        return

    print("scenarios.json 파일을 읽어 데이터베이스 구축을 시작합니다...")
    
    with open(SCENARIOS_PATH, "r", encoding="utf-8") as f:
        scenarios = json.load(f)

    model = get_embedding_model()
    
    # 데이터 준비
    ids = [s["scenario_id"] for s in scenarios]
    documents = [s["embedding_text"] for s in scenarios]
    metadatas = [{"category": s["category"], "task": s["task"]} for s in scenarios]
    
    # SBERT 모델로 임베딩 생성
    embeddings = model.encode(documents, convert_to_numpy=True).tolist()
    
    # DB에 추가
    collection.add(
        ids=ids,
        embeddings=embeddings,
        documents=[json.dumps(s["content"]) for s in scenarios], # content를 document로 저장
        metadatas=metadatas
    )
    
    print(f"데이터베이스 구축 완료! 총 {collection.count()}개의 시나리오가 추가되었습니다.")

# 이 파일을 직접 실행하면 DB를 구축하도록 설정
if __name__ == '__main__':
    build_database()