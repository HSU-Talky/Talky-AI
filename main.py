import json                                    # 표준 라이브러리: 문자열 ↔ JSON 변환에 사용
from fastapi import FastAPI, HTTPException     # FastAPI 앱 생성, 에러 응답용 예외
from pydantic import BaseModel, Field          # 요청/응답 스키마 정의
from typing import List, Optional              # 타입 힌트: 리스트, Optional
import httpx                                   # 비동기 HTTP 클라이언트 (LLM API 호출용)
from stt import transcribe_audio               # STT 처리 함수 임포트
from rag.retriever import retrieve_scenario
from rag.database import get_db, get_embedding_model  # 이 줄 추가
from difflib import SequenceMatcher

from fastapi import UploadFile, File, Form, HTTPException           # 파일 업로드 처리용

from config import settings                    # 환경설정/비밀키를 담은 settings 객체 임포트

def ensure_diversity(sentences: List[str], similarity_threshold: float = 0.7) -> List[str]:
    """
    문장 리스트에서 유사한 문장들을 제거하여 다양성을 보장합니다.
    """
    if len(sentences) <= 1:
        return sentences
    
    diverse_sentences = [sentences[0]]  # 첫 번째 문장은 항상 포함
    
    for sentence in sentences[1:]:
        is_diverse = True
        for existing in diverse_sentences:
            # 문장 유사도 계산
            similarity = SequenceMatcher(None, sentence, existing).ratio()
            if similarity > similarity_threshold:
                is_diverse = False
                break
        
        if is_diverse:
            diverse_sentences.append(sentence)
    
    return diverse_sentences

def retrieve_scenarios_by_categories(keywords: List[str], context: str):
    """
    여러 카테고리를 고려하여 시나리오를 검색합니다.
    각 카테고리별로 검색하여 모든 카테고리를 반영합니다.
    거리 1.0 이상의 쓰레기 결과는 제거합니다.
    """
    if not keywords:
        return None
    
    all_scenarios = []
    seen_ids = set()
    
    # 각 키워드별로 검색
    for keyword in keywords:
        search_query = f"{keyword} {context}".strip()
        scenarios = retrieve_scenario(search_query, n_results=2)  # 각 카테고리당 2개
        
        if scenarios:
            for scenario in scenarios:
                # 거리 1.0 이상은 무시, 나머지는 모두 추가
                distance = scenario.get('distance', 0)
                if distance < 1.0:  # 거리 1.0 미만만 허용
                    if scenario['id'] not in seen_ids:
                        all_scenarios.append(scenario)
                        seen_ids.add(scenario['id'])
                        print(f"✅ 선택된 시나리오: {scenario['id']} (거리: {distance:.3f})")
                else:
                    print(f"❌ 제외된 시나리오: {scenario['id']} (거리: {distance:.3f}) - 너무 다름")
    
    # 상위 3개 선택 (거리 기준으로 정렬)
    all_scenarios.sort(key=lambda x: x.get('distance', 0))
    print(f"🔍 최종 선택된 시나리오: {len(all_scenarios)}개")
    return all_scenarios[:3]

# FastAPI 앱 및 모델 정의
app = FastAPI(
    title="Talky-AI Service",
    description="백엔드로부터 전달받은 컨텍스트를 기반으로 문장을 생성하는 AI 서비스",
    version="2025.09.14",  # AI가 해야할 일 수정(프롬프트)
)

@app.on_event("startup")
async def startup_event():
    get_db()
    get_embedding_model()  # 이제 정상 작동
    print("RAG 데이터베이스와 임베딩 모델이 준비되었습니다.")

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
    [RAG] 적용 , 모든 컨텍스트를 한 번에 처리하여, 즐겨찾기를 우선적으로 고려한 최종 추천 문장을 생성합니다.
    """
    # 프롬프트에 전달할 정보들을 안전하게 문자열로 변환
    keywords_str = ", ".join(request.keywords) if request.keywords else "없음"
    context_str = request.context if request.context else "없음"
    stt_message_str = request.sttMessage if request.sttMessage else "없음"
    conversation_str = "\n".join([f"- {line}" for line in request.conversation]) if request.conversation else "(대화 시작 전)"
    favorites_str = "\n".join([f"- {fav}" for fav in request.favorites]) if request.favorites else "없음"

    # RAG 검색: 여러 카테고리를 고려하여 시나리오 검색
    retrieved_scenarios = retrieve_scenarios_by_categories(request.keywords, context_str)
    
    scenario_guide = "없음. 아래 '참고 정보'만을 바탕으로 생성하세요."
    example_dialogue_str = "없음" # 변수 초기화
    if retrieved_scenarios:
        # 여러 시나리오 정보를 종합
        scenario_info = []
        all_dialogues = []
        
        for scenario in retrieved_scenarios:
            content = scenario['content']
            goal = content.get('goal', 'N/A')
            flow = "\n".join(content.get('typical_flow', []))
            scenario_info.append(f"• {goal}\n  흐름: {flow}")
            
            if content.get("example_dialogue"):
                dialogue_lines = [f"- {d['speaker']}: {d['line']}" for d in content["example_dialogue"]]
                all_dialogues.extend(dialogue_lines)
        
        scenario_guide = f"""다양한 시나리오 참고:
        {chr(10).join(scenario_info)}"""
        
        if all_dialogues:
            example_dialogue_str = "\n".join(all_dialogues)

    print(f"AI 문장 생성 요청 수신: keywords='{keywords_str}', context='{context_str}'")
    print(f"RAG 검색 결과: {'시나리오 발견' if retrieved_scenarios else '시나리오 없음'}")
    if retrieved_scenarios:
        print(f"🔍 검색된 시나리오 수: {len(retrieved_scenarios)}개")
        for i, scenario in enumerate(retrieved_scenarios):
            print(f"  {i+1}. {scenario['id']} (거리: {scenario.get('distance', 'N/A')})")

    # AI에게 보낼 지시서(프롬프트)
    prompt = f"""
        - 역할 
        당신은 상대방 질문의 '유형'을 먼저 분석하고, 그 유형에 가장 적합한 답변을 생성하는 지능형 대화 문장 생성 AI입니다.

        - 해야할 일
        상대방의 마지막 질문(`sttMessage`)과 사용자가 입력한 상황('context')을 분석하여, 사용자가 다음에 할 법한 말의 '선택지' 4개를 생성하는 것입니다. 
        절대 사용자가 입력한 상황(context)에 직접 대답하는 챗봇처럼 행동하는 것이 아닙니다.
        
        - 따라야 할 생각의 흐름
        1.  **[1단계: 질문 유형 분석]**
            - 상대방의 질문을 읽는다: "{stt_message_str}"
            - 이 질문이 "네/아니오"로 답해야 하는 질문인가? 아니면 "언제, 어디서, 무엇을" 같은 구체적인 정보를 묻는 질문인가? 스스로 판단한다.

        2.  **[2단계: 답변 생성 전략 수립]**
            - **만약 "네/아니오" 질문이라면:** "네, ..." 또는 "아니요, ..." 형식으로 시작하는 답변을 구상한다.
            - **만약 "정보 요구" 질문이라면:** **"네/아니요" 없이** "어제부터요.", "머리가 아파서요." 와 같이 질문의 핵심에 대한 정보로 바로 시작하는 답변을 구상한다.

        3.  **[3단계: 최종 문장 생성 - 다양성 강조]**
            - 먼저, `사용자의 평소 말투 (즐겨찾기)` 목록을 확인한다. 만약 현재 질문에 대한 완벽한 답변이 즐겨찾기에 있다면, 그 문장을 최종 추천 목록에 최우선으로 포함시킨다.
            - 나머지 비어있는 자리(총 4개 중)는 위 2단계 전략과 `참고 정보`를 활용하여 **서로 다른 관점과 표현 방식**으로 문장을 생성한다.
            - **중요: 4개 문장은 모두 다른 의미와 뉘앙스를 가져야 합니다.**
            - **예시:**
              * 질문: "언제부터 아프셨어요?"
              * 좋은 예: ["어제부터요.", "3일 전부터 아팠어요.", "갑자기 아프기 시작했어요.", "오늘 아침부터요."]
              * 나쁜 예: ["어제부터요.", "어제부터 아팠어요.", "어제부터 시작됐어요.", "어제부터 계속 아파요."]
            - **모든 문장은 존댓말로 생성하세요.**


        ### 시나리오 가이드 ###
        {scenario_guide}
        ### 예시 대화 ###
        {example_dialogue_str}


       ### 참고 정보 ###
        - **사용자의 현재 상황:** {context_str}
        - **대화 주제 키워드:** {keywords_str}
        - **사용자의 평소 말투:** {favorites_str}

        ### 출력 형식 ###
        - 답변은 반드시 "generated_sentences" 라는 단 하나의 키를 가진 JSON 객체여야 합니다.
        - 값은 최종적으로 추천할 문장 4개가 담긴 문자열 배열입니다.
        - **각 문장은 서로 다른 의미와 표현을 가져야 합니다.**
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
            generated_sentences = json.loads(text_content).get("generated_sentences", [])
            
            # 다양성 보장 로직 적용
            diverse_sentences = ensure_diversity(generated_sentences)
            print(f"다양성 보장: {len(generated_sentences)}개 → {len(diverse_sentences)}개")
            
            return diverse_sentences
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
        print(f"🔍 파일 업로드 감지: {file.filename}, 크기: {file.size}")
        final_stt = await transcribe_audio(file)
        print(f" STT 결과: {final_stt}")

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
    
    # 카테고리 결정: 키워드 조합 사용
    category = ", ".join(meta.keywords) if meta.keywords else "일상"
    
    return RecommendationResponse(
        category=category,
        sttMessage=final_stt,
        recommended_sentences=final_sentences
    )

