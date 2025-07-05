import json
import asyncio
from fastapi import FastAPI, HTTPException, Query, Depends
from pydantic import BaseModel
from typing import List, Optional
import httpx
import pymysql

from config import settings

# --- 1. FastAPI 앱 및 모델 정의 ---
app = FastAPI(
    title="AAC 문장 추천",
    description="사용자의 위치와 상황에 맞는 문장을 AI를 통해 생성하고 추천합니다.",
    version="1.2.0"
)

class Sentence(BaseModel):
    id: int
    text: str
class RecommendationResponse(BaseModel):
    category: str
    recommended_sentences: List[Sentence]


# --- 2. DB 연결 의존성 추가 ---
def get_db():
    """DB 커넥션을 생성하고, API 처리가 끝나면 자동으로 닫는 의존성 함수"""
    conn = None
    try:
        conn = pymysql.connect(
            host=settings.DB_HOST, user=settings.DB_USER, password=settings.DB_PASSWORD,
            database=settings.DB_NAME, charset='utf8mb4', cursorclass=pymysql.cursors.DictCursor
        )
        yield conn
    except pymysql.Error as e:
        print(f"데이터베이스 연결 오류: {e}")
        raise HTTPException(status_code=500, detail="데이터베이스 연결에 실패했습니다.")
    finally:
        if conn:
            conn.close()

# --- 3. 외부 서비스 및 DB 호출 로직 ---

def get_sentences_from_db(db: pymysql.connections.Connection, category: str) -> List[dict]:
    """DB에서 특정 카테고리에 맞는 문장들을 모두 가져옵니다."""
    print(f"DB에서 '{category}' 카테고리의 문장들을 조회합니다...")
    with db.cursor() as cursor:
        # 3개의 테이블을 JOIN하여 카테고리 이름으로 문장을 찾는 SQL
        sql = """
            SELECT s.id, s.text 
            FROM Sentences s
            JOIN Sentence_Category_Map scm ON s.id = scm.sentence_id
            JOIN Categories c ON scm.category_id = c.id
            WHERE c.name = %s
        """
        cursor.execute(sql, (category,))
        sentences = cursor.fetchall()
        return sentences
    
def get_category_from_qr(db: pymysql.connections.Connection, qr_data: str) -> Optional[str]:
    """DB의 Location_Triggers 테이블에서 QR 데이터에 해당하는 카테고리를 찾습니다."""
    print(f"DB에서 QR 데이터 '{qr_data}'에 해당하는 장소를 조회합니다...")
    with db.cursor() as cursor:
        sql = """
            SELECT c.name 
            FROM Location_Triggers lt
            JOIN Categories c ON lt.category_id = c.id
            WHERE lt.trigger_type = 'QR' AND lt.trigger_value = %s
        """
        cursor.execute(sql, (qr_data,))
        result = cursor.fetchone()
        if result:
            category_name = result['name']
            print(f"QR 코드를 통해 '{category_name}'(으)로 장소를 확정했습니다.")
            return category_name
    return None

# (get_location_category, generate_ai_sentences 함수는 이전과 동일)
async def get_location_category(lat: float, lon: float) -> Optional[str]:
    """카카오맵 API로 좌표 기반 장소 카테고리를 가져옵니다."""
    # ... 이전과 동일한 코드 ...
    print(f"카카오맵 API로 좌표 ({lat}, {lon})의 주변 장소를 검색합니다...")
    category_map = {"HP8": "병원", "FD6": "식당", "CS2": "편의점", "SW8": "지하철역"}
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
        except httpx.RequestError as e:
            print(f"카테고리 {code} 검색 중 오류: {e}")
        return None
    async with httpx.AsyncClient() as client:
        tasks = [search_task(code, client) for code in category_map.keys()]
        results = await asyncio.gather(*tasks)
    found_places = [place for place in results if place]
    if not found_places:
        return None
    closest_place = min(found_places, key=lambda x: x['distance'])
    print(f"가장 가까운 장소는 '{closest_place['category']}'입니다 (거리: {closest_place['distance']}m).")
    return closest_place['category']

async def generate_ai_sentences(category: str, keywords: Optional[str]) -> List[str]:
    """Gemini AI API를 호출하여 문장을 생성합니다."""
    print(f"Gemini AI에게 '{category}' 상황에 맞는 문장 생성을 요청합니다...")
    
    prompt = f"""
        당신은 언어 표현에 어려움이 있는 사용자를 돕는 AAC 앱의 문장 생성 전문가입니다.
        사용자의 현재 상황에 맞춰, 직접 사용할 수 있는 예의 바르고 간결한 문장 5개를 생성해주세요.
        주어진 키워드가 있다면, 반드시 해당 키워드를 활용하여 문장을 만들어주세요.

        [사용자 상황]
        - 현재 장소: {category}
        - 사용자가 입력한 키워드: {keywords if keywords else "없음"}

        [출력 형식]
        당신의 답변은 반드시 "generated_sentences" 라는 단 하나의 키를 가진 JSON 객체여야 합니다.
        이 키의 값은 당신이 생성한 문장 5개가 담긴 문자열 배열(array of strings)입니다.
    """
    
    # API URL과 payload를 Gemini 방식으로 되돌립니다.
    api_url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash-latest:generateContent?key={settings.GOOGLE_API_KEY}"
    payload = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {"responseMimeType": "application/json", "temperature": 0.8}
    }
    
    try:
        async with httpx.AsyncClient() as client:
            response = await client.post(api_url, json=payload, timeout=30)
            response.raise_for_status()
            ai_response = response.json()
            
            # 응답 파싱 로직을 Gemini 방식으로 되돌립니다.
            text_content = ai_response["candidates"][0]["content"]["parts"][0]["text"]
            return json.loads(text_content).get("generated_sentences", [])
            
    except httpx.HTTPStatusError as e:
        print(f"!!! Google AI API가 에러를 반환했습니다: status_code={e.response.status_code}")
        print(f"!!! 응답 내용: {e.response.text}")
        raise HTTPException(status_code=e.response.status_code, detail=f"AI 서비스 오류: {e.response.text}")
    except Exception as e:
        print(f"!!! AI 응답 처리 중 알 수 없는 오류 발생: {e}")
        raise HTTPException(status_code=500, detail=f"AI 응답 처리 중 오류 발생: {e}")


# --- 메인 API 엔드포인트는 수정할 필요 없이 그대로 둡니다 ---
@app.get("/recommendations", response_model=RecommendationResponse, summary="AI 문장 추천 받기")
async def get_recommendations(
    lat: Optional[float] = Query(None, description="현재 위도", example=37.5665),
    lon: Optional[float] = Query(None, description="현재 경도", example=126.9780),
    qr_data: Optional[str] = Query(None, description="스캔된 QR 코드의 데이터", example="hospital-reception-001"),
    keywords: Optional[str] = Query(None, description="문장에 포함하고 싶은 키워드", example="두통약,계산"),
    db: pymysql.connections.Connection = Depends(get_db)
):
    # (이하 로직은 이전과 동일)
    category = None
    if qr_data:
        category = get_category_from_qr(db, qr_data)
    if not category and lat is not None and lon is not None:
        category = await get_location_category(lat, lon)
    if not category:
        raise HTTPException(status_code=404, detail="위치 정보를 확인할 수 없습니다.")

    generated_sentences = await generate_ai_sentences(category, keywords)
    if not generated_sentences:
        raise HTTPException(status_code=500, detail="AI가 문장을 생성하지 못했습니다.")

    final_sentences = [Sentence(id=i + 1, text=text) for i, text in enumerate(generated_sentences)]
    return RecommendationResponse(category=category, recommended_sentences=final_sentences)
