import json                                   # 표준 라이브러리: 문자열 ↔ JSON 변환에 사용
from fastapi import FastAPI, HTTPException     # FastAPI 앱 생성, 에러 응답용 예외
from pydantic import BaseModel, Field          # 요청/응답 스키마 정의
from typing import List, Optional              # 타입 힌트: 리스트, Optional
import httpx                                   # 비동기 HTTP 클라이언트 (LLM API 호출용)
from stt import transcribe_audio               # STT 처리 함수 임포트

from fastapi import UploadFile, File, Form, HTTPException           # 파일 업로드 처리용

from config import settings                    # 환경설정/비밀키를 담은 settings 객체 임포트

# FastAPI 앱 및 모델 정의
app = FastAPI(
    title="Talky-AI Service",
    description="백엔드로부터 전달받은 컨텍스트를 기반으로 문장을 생성하는 AI 서비스",
    version="2025.09.02",  # AI 프롬프트 우선순위 강화 버전
)

# /recommendations API를 위한 모델들
class RecommendationRequest(BaseModel):        # 요청 바디 스키마 정의
    keywords: List[str] = Field(...,           # 필수 필드: 장소/상황 키워드 목록
        description="장소, 상황 등을 나타내는 키워드 목록",
        example=["병원", "두통"])
    context: Optional[str] = Field(            # 선택 필드: 현재 상황 설명
        None, description="사용자가 직접 입력한 현재 상황 설명",
        example="머리가 아파서 왔어요") # null 허용
    conversation: Optional[List[str]] = Field( # 선택 필드: 최근 대화 기록 (문자열 리스트)
        None, description="최근 대화 기록 (사용자, 상대방 포함)",
        example=["안녕하세요, 어떻게 오셨어요?", "진료받으러 왔습니다."]) # null 허용
    sttMessage: Optional[str] = Field(
        None,
        description="상대방의 마지막 음성인식(STT) 메시지",
        example="아픈지 얼마나 되셨어요?"  # 타입을 str에 맞게 수정
    )
    favorites: Optional[List[str]] = Field(    # 선택 필드: 즐겨찾기 문장 목록
        default_factory=list,                  # 기본값: [] (None이어도 빈 리스트로 처리)
        description="사용자가 즐겨찾기한 문장 목록",
        example=["그렇게 해주세요", "감사합니다"]) # 없어도 빈 리스트로 처리될 수 있게 함

class Sentence(BaseModel):                     # 내부적으로 사용하는 문장 객체 스키마
    id: int                                    # 고유 ID (1부터 부여)
    text: str                                  # 문장 텍스트

class RecommendationResponse(BaseModel):       # 응답 바디 스키마 정의
    category: str                              # 메인 카테고리(첫 번째 키워드 등)
    sttMessage : Optional[str]                 # 마지막 STT 메시지 (Optional)
    recommended_sentences: List[Sentence]      # 추천 문장 리스트

# AI 로직 함수 
async def generate_ai_sentences(request: RecommendationRequest) -> List[str]:
    """
    모든 컨텍스트를 한 번에 처리하여, 즐겨찾기를 우선적으로 고려한 최종 추천 문장을 생성합니다.
    """
    # 프롬프트에 전달할 정보들을 안전하게 문자열로 변환
    keywords_str = ", ".join(request.keywords) if request.keywords else "없음"
    context_str = request.context if request.context else "없음"
    stt_message_str = request.sttMessage if request.sttMessage else "없음"
    conversation_str = "\n".join([f"- {line}" for line in request.conversation]) if request.conversation else "(대화 시작 전)"
    favorites_str = "\n".join([f"- {fav}" for fav in request.favorites]) if request.favorites else "없음"

    print(f"AI 문장 생성 요청 수신: keywords='{keywords_str}', context='{context_str}'")

    # AI에게 보낼 훨씬 더 똑똑하고 상세한 지시서(프롬프트)
    prompt = f"""
        - 역할 
        당신은 상대방 질문의 '유형'을 먼저 분석하고, 그 유형에 가장 적합한 답변을 생성하는 지능형 대화 문장 생성 AI입니다.

        - 해야할 일
        상대방의 마지막 질문(`sttMessage`)을 분석하여, 그에 대한 가장 자연스럽고 직접적인 답변 문장 4개를 생성합니다.
        
        - 따라야 할 생각의 흐름
        1.  **[1단계: 질문 유형 분석]**
            - 상대방의 질문을 읽는다: "{stt_message_str}"
            - 이 질문이 "네/아니오"로 답해야 하는 질문인가? 아니면 "언제, 어디서, 무엇을" 같은 구체적인 정보를 묻는 질문인가? 스스로 판단한다.

        2.  **[2단계: 답변 생성 전략 수립]**
            - **만약 "네/아니오" 질문이라면:** "네, ..." 또는 "아니요, ..." 형식으로 시작하는 답변을 구상한다.
            - **만약 "정보 요구" 질문이라면:** **"네/아니요" 없이** "어제부터요.", "머리가 아파서요." 와 같이 질문의 핵심에 대한 정보로 바로 시작하는 답변을 구상한다.

        3.  **[3단계: 최종 문장 생성]**
            - 먼저, `사용자의 평소 말투 (즐겨찾기)` 목록을 확인한다. 만약 현재 질문에 대한 완벽한 답변이 즐겨찾기에 있다면, 그 문장을 최종 추천 목록에 최우선으로 포함시킨다.
            - 나머지 비어있는 자리(총 4개 중)는 위 2단계 전략과 `참고 정보`를 활용하여 가장 적절하고 다양한 새 문장을 생성하여 채워넣는다.


       ### 참고 정보 ###
        - **사용자의 현재 상황:** {context_str}
        - **대화 주제 키워드:** {keywords_str}
        - **사용자의 평소 말투:** {favorites_str}

        ### 출력 형식 ###
        - 답변은 반드시 "generated_sentences" 라는 단 하나의 키를 가진 JSON 객체여야 합니다.
        - 값은 최종적으로 추천할 문장 4개가 담긴 문자열 배열입니다.
    """

    # Gemini 2.5 Flash 모델
    api_url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash-preview-05-20:generateContent?key={settings.GOOGLE_API_KEY}"
    payload = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {
            "responseMimeType": "application/json",
            "temperature": 0.3 
        }
    }

    try:
        async with httpx.AsyncClient() as client:
            response = await client.post(api_url, json=payload, timeout=30)
            response.raise_for_status()
            ai_response = response.json()
            candidates = ai_response.get("candidates", [])
            if not candidates:
                return []
            text_content = candidates[0].get("content", {}).get("parts", [{}])[0].get("text", "{}")
            return json.loads(text_content).get("generated_sentences", [])
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"AI 서비스 처리 중 오류가 발생했습니다: {e}")

# 메타데이터 모델 정의
class Metadata(BaseModel):
    keywords: List[str] = Field(..., description="키워드 목록")
    context: Optional[str] = Field(None, description="현재 상황 설명")
    choose: Optional[str] = Field(None, description="사용자가 선택한 문장")
    favorites: List[str] = Field(default_factory=list, description="즐겨찾기 문장 목록")
    conversation: Optional[List[str]] = Field(None, description="누적 대화 이력")


# 🔧 통합 턴 처리 엔드포인트 추가
@app.post("/recommendations", response_model=RecommendationResponse, summary="통합 처리: STT→이력→추천")
async def dialogue_turn(
    metadata: str = Form(...),                     # JSON 문자열
    file: UploadFile = File(None),                 # mp3 파일 (Optional)
    sttMessage: Optional[str] = Form(None)         # 텍스트 (Optional)
):
    """
    음성/텍스트 입력을 받아 STT → 대화이력 저장 → 추천 생성까지 한 번에 처리
    """
    try:
        # 메타데이터 파싱
        meta = Metadata.model_validate_json(metadata)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"metadata 파싱 실패: {e}")

    # 1) STT 처리: 파일이 있으면 우선 사용, 없으면 sttMessage 사용
    final_stt = sttMessage
    if final_stt is None and file is not None:
        final_stt = await transcribe_audio(file)

    # 2) 대화 이력 관리 (현재는 메타데이터의 conversation 사용)
    conversation_list = meta.conversation or []

    # 3) AI 추천 생성 요청 모델 구성
    req = RecommendationRequest(
        keywords=meta.keywords,
        context=meta.context,
        conversation=conversation_list,
        sttMessage=final_stt,
        favorites=meta.favorites,
    )

    # 4) 기존 추천 로직 재사용
    generated = await generate_ai_sentences(req)
    if not generated:
        raise HTTPException(status_code=500, detail="AI가 문장을 생성하지 못했습니다.")

    final_sentences = [Sentence(id=i+1, text=t) for i, t in enumerate(generated)]
    category = meta.keywords[0] if meta.keywords else "일상"
    
    return RecommendationResponse(
        category=category,
        sttMessage=final_stt,
        recommended_sentences=final_sentences
    )

# # --- 3. API 엔드포인트 ---
# @app.post("/recommendations", response_model=RecommendationResponse, summary="AI 실시간 문장 추천 (컨텍스트 기반)")
# async def get_recommendations(request: RecommendationRequest):
#     """메인 백엔드로부터 전달받은 풍부한 컨텍스트로 AI 추천 문장을 생성합니다."""

#     # 이제 단 하나의 AI 함수만 호출하면 됩니다.
#     generated_sentences = await generate_ai_sentences(request)

#     if not generated_sentences:
#         raise HTTPException(status_code=500, detail="AI가 문장을 생성하지 못했습니다.")

#     final_sentences = [Sentence(id=i + 1, text=text) for i, text in enumerate(generated_sentences)]

#     main_category = request.keywords[0] if request.keywords else "일상"

#     return RecommendationResponse(
#         category=main_category,
#         recommended_sentences=final_sentences
#     )

# @app.post("/stt/transcribe", summary="음성 파일을 텍스트로 변환 (STT)")
# async def stt_transcribe(file: UploadFile = File(...)):
#     """
#     업로드된 음성 파일을 OpenAI Whisper로 텍스트 변환합니다.
#     """
#     try:
#         text = await transcribe_audio(file)
#         return {"transcription": text}
#     except Exception as e:
#         raise HTTPException(status_code=500, detail=f"STT 처리 중 오류: {e}")