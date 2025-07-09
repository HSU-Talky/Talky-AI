import json
import asyncio
import pymysql
from fastapi import FastAPI, HTTPException, Query, Depends, Body
from pydantic import BaseModel
from typing import List, Optional
import httpx

from config import settings

# --- 1. FastAPI 앱 및 모델 정의 ---
app = FastAPI(
    title="AAC 대화형 문장 추천 API",
    description="사용자의 상황과 대화의 흐름에 맞는 문장을 AI를 통해 생성하고 추천합니다.",
    version="7.0.0" # 즐겨찾기 편집 기능 추가
)

class Sentence(BaseModel): id: int; text: str
class RecommendationResponse(BaseModel): category: str; recommended_sentences: List[Sentence]
class FavoriteRequest(BaseModel): sentence: str
class FavoriteResponse(BaseModel): id: int; user_id: int; sentence: str; display_order: int
class CategoryLogRequest(BaseModel): category: str
class SpeechLogRequest(BaseModel): sentence: str; location: str
class FavoriteOrderRequest(BaseModel):
    ordered_ids: List[int] # 순서가 정렬된 즐겨찾기 ID 목록


# --- 2. DB 연결 의존성 ---
def get_db():
    try:
        conn = pymysql.connect(
            host=settings.DB_HOST, user=settings.DB_USER, password=settings.DB_PASSWORD,
            database=settings.DB_NAME, charset='utf8mb4', cursorclass=pymysql.cursors.DictCursor
        )
        yield conn
    finally:
        if conn: conn.close()


# --- 3. 핵심 로직 함수들 ---
def get_category_from_qr(db: pymysql.connections.Connection, qr_data: str) -> Optional[str]:
    with db.cursor() as cursor:
        sql = "SELECT c.name FROM Location_Triggers lt JOIN Categories c ON lt.category_id = c.id WHERE lt.trigger_type = 'QR' AND lt.trigger_value = %s"
        cursor.execute(sql, (qr_data,))
        result = cursor.fetchone()
        return result['name'] if result else None
async def get_location_category(lat: float, lon: float) -> Optional[str]:
    category_map = {"HP8": "병원", "FD6": "식당", "CS2": "편의점", "SW8": "지하철역", "CE7": "카페", "SC4": "학교", "CT1": "문화시설"}
    api_url = "https://dapi.kakao.com/v2/local/search/category.json"
    headers = {"Authorization": f"KakaoAK {settings.KAKAO_API_KEY}"}
    async def search_task(code: str, client: httpx.AsyncClient):
        params = {"category_group_code": code, "x": lon, "y": lat, "radius": 200, "size": 1, "sort": "distance"}
        try:
            response = await client.get(api_url, headers=headers, params=params)
            response.raise_for_status()
            result = response.json()
            if result.get("documents"):
                doc = result["documents"][0]
                return {"category": category_map[code], "distance": int(doc.get("distance", 999))}
        except Exception: return None
    async with httpx.AsyncClient() as client:
        tasks = [search_task(code, client) for code in category_map.keys()]
        results = await asyncio.gather(*tasks)
    found_places = [place for place in results if place]
    if not found_places: return None
    closest_place = min(found_places, key=lambda x: x['distance'])
    return closest_place['category']
async def generate_ai_sentences(category: str, keywords: Optional[str], previous_sentence: Optional[str], opponent_dialogue: Optional[str]) -> List[str]:
    if previous_sentence:
        prompt = f"""당신은 AAC 사용자를 위한 대화 전문가입니다. 당신은 항상 사용자(손님, 환자 등)의 입장에서 말해야 합니다. 다음 대화의 맥락을 파악하고, 사용자의 입장에서 자연스럽게 이어질 다음 문장 5개를 생성해주세요.
        [현재 장소]: {category}, [사용자가 방금 한 말]: "{previous_sentence}", [상대방이 방금 한 말]: "{opponent_dialogue or "(입력 없음)"}", [사용자가 다음에 하고 싶은 말의 키워드]: {keywords or "없음"}
        [출력 형식] "generated_sentences" 키를 가진 JSON 객체로, 값은 문자열 배열이어야 합니다."""
    else:
        prompt = f"""당신은 AAC 앱의 문장 생성 전문가입니다. 당신은 항상 사용자(손님, 환자 등)의 입장에서 대화를 시작하는 문장을 생성해야 합니다. "무엇을 도와드릴까요?"가 아닌, "주문할게요." 와 같은 사용자가 먼저 할 법한 요청이나 질문 5개를 생성해주세요.
        [현재 장소]: {category}, [키워드]: {keywords or "없음"}
        [출력 형식] "generated_sentences" 키를 가진 JSON 객체로, 값은 문자열 배열이어야 합니다."""
    api_url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash-latest:generateContent?key={settings.GOOGLE_API_KEY}"
    payload = {"contents": [{"parts": [{"text": prompt}]}], "generationConfig": {"responseMimeType": "application/json", "temperature": 0.7}}
    try:
        async with httpx.AsyncClient() as client:
            response = await client.post(api_url, json=payload, timeout=30)
            response.raise_for_status()
            ai_response = response.json()
            text_content = ai_response["candidates"][0]["content"]["parts"][0]["text"]
            return json.loads(text_content).get("generated_sentences", [])
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"AI 서비스 처리 중 오류가 발생했습니다: {e}")


# --- 4. API 엔드포인트들 ---

@app.get("/recommendations", response_model=RecommendationResponse)
async def get_recommendations(
    lat: Optional[float] = Query(None), lon: Optional[float] = Query(None),
    qr_data: Optional[str] = Query(None), keywords: Optional[str] = Query(None),
    previous_sentence: Optional[str] = Query(None), opponent_dialogue: Optional[str] = Query(None),
    manual_category: Optional[str] = Query(None), db: pymysql.connections.Connection = Depends(get_db)
):
    category = None
    if manual_category: category = manual_category
    elif qr_data: category = get_category_from_qr(db, qr_data)
    elif lat is not None and lon is not None: category = await get_location_category(lat, lon)
    if not category:
        if previous_sentence: category = "일상 대화"
        else: raise HTTPException(status_code=404, detail="위치 정보를 확인할 수 없습니다.")
    generated_sentences = await generate_ai_sentences(category, keywords, previous_sentence, opponent_dialogue)
    if not generated_sentences: raise HTTPException(status_code=500, detail="AI가 문장을 생성하지 못했습니다.")
    final_sentences = [Sentence(id=i + 1, text=text) for i, text in enumerate(generated_sentences)]
    return RecommendationResponse(category=category, recommended_sentences=final_sentences)

@app.post("/speech-logs", status_code=201)
def create_speech_log(log_request: SpeechLogRequest, db: pymysql.connections.Connection = Depends(get_db)):
    with db.cursor() as cursor:
        sql = "INSERT INTO speech_logs (user_id, sentence, location) VALUES (1, %s, %s)"
        cursor.execute(sql, (log_request.sentence, log_request.location))
    db.commit()
    return {"message": "Speech log created successfully."}

# === 즐겨찾기 API 수정 및 추가 ===

@app.get("/favorites", response_model=List[FavoriteResponse])
def get_favorites(db: pymysql.connections.Connection = Depends(get_db)):
    """(임시 user_id=1) 즐겨찾기 문장을 display_order 순서대로 조회합니다."""
    with db.cursor() as cursor:
        sql = "SELECT id, user_id, sentence, display_order FROM favorites WHERE user_id = 1 ORDER BY display_order ASC"
        cursor.execute(sql)
        return cursor.fetchall()

@app.post("/favorites", response_model=FavoriteResponse, status_code=201)
def add_favorite(favorite_request: FavoriteRequest, db: pymysql.connections.Connection = Depends(get_db)):
    """새로운 문장을 즐겨찾기에 추가합니다. 가장 높은 display_order + 1 로 추가됩니다."""
    with db.cursor() as cursor:
        # 가장 높은 display_order 값을 찾습니다.
        cursor.execute("SELECT MAX(display_order) as max_order FROM favorites WHERE user_id = 1")
        max_order = cursor.fetchone()['max_order'] or 0
        
        sql = "INSERT INTO favorites (user_id, sentence, display_order) VALUES (1, %s, %s)"
        cursor.execute(sql, (favorite_request.sentence, max_order + 1))
        new_id = cursor.lastrowid
    db.commit()
    return FavoriteResponse(id=new_id, user_id=1, sentence=favorite_request.sentence)
