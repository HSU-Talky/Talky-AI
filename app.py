import streamlit as st
import httpx

# --- 세션 상태 초기화 ---
if 'conversation_history' not in st.session_state: st.session_state.conversation_history = []
if 'current_recommendations' not in st.session_state: st.session_state.current_recommendations = []
if 'previous_sentence' not in st.session_state: st.session_state.previous_sentence = None
if 'current_category' not in st.session_state: st.session_state.current_category = ""
if 'favorites' not in st.session_state: st.session_state.favorites = []

# --- API 호출 함수들 ---
def call_backend_api(lat, lon, keywords, qr_data, previous_sentence, opponent_dialogue, manual_category):
    backend_url = "http://127.0.0.1:8000/recommendations"
    params = {"keywords": keywords or "", "qr_data": qr_data or "", "previous_sentence": previous_sentence or "", "opponent_dialogue": opponent_dialogue or "", "manual_category": manual_category or ""}
    if lat is not None and lon is not None: params["lat"], params["lon"] = lat, lon
    try:
        with st.spinner("AI가 문장을 생성하고 있습니다..."):
            response = httpx.get(backend_url, params=params, timeout=60)
            response.raise_for_status()
            return response.json()
    except Exception as e:
        st.error(f"오류가 발생했습니다: {e}")
        return None

def log_category_selection(category):
    """선택된 카테고리를 백엔드에 알려 카운트를 올립니다."""
    try:
        httpx.post("http://127.0.0.1:8000/log/category-selection", json={"category": category})
    except Exception as e:
        print(f"카테고리 선택 로깅 실패: {e}")

def get_favorites_from_backend():
    """백엔드에서 즐겨찾기 목록을 가져옵니다."""
    try:
        response = httpx.get("http://127.0.0.1:8000/favorites")
        response.raise_for_status()
        st.session_state.favorites = response.json()
    except Exception as e:
        st.error(f"즐겨찾기 목록을 불러오는 데 실패했습니다: {e}")

def add_favorite_to_backend(sentence):
    """문장을 즐겨찾기에 추가합니다."""
    try:
        response = httpx.post("http://127.0.0.1:8000/favorites", json={"sentence": sentence})
        response.raise_for_status()
        st.toast(f'"{sentence}" 문장을 즐겨찾기에 추가했습니다! ✅')
        get_favorites_from_backend() # 목록 새로고침
    except Exception as e:
        st.error(f"즐겨찾기 추가에 실패했습니다: {e}")

def reset_conversation():
    st.session_state.conversation_history = []
    st.session_state.current_recommendations = []
    st.session_state.previous_sentence = None
    st.session_state.current_category = ""

# --- 1. 메인 화면 구성 ---
st.title("🤖 대화형 AAC 앱")

# --- 2. 메인 탭 구성 ---
main_tab, favorites_tab = st.tabs(["💬 대화하기", "⭐ 즐겨찾기 목록"])

with main_tab:
    # --- 대화 기록 표시 ---
    if st.session_state.conversation_history:
        st.subheader("대화 기록")
        for item in st.session_state.conversation_history:
            if item['speaker'] == '나': st.info(f"**나:** {item['message']}")
            else: st.success(f"**상대방:** {item['message']}")
        st.markdown("---")

    # --- 상태에 따른 UI 분기 처리 ---
    if st.session_state.previous_sentence: # Case 1: 대화 이어가기
        st.header("다음 대화 이어가기")
        st.write(f"**내가 한 말:** \"{st.session_state.previous_sentence}\"")
        opponent_dialogue = st.text_area("상대방이 한 말을 입력하세요 (선택 사항):", key="opponent_dialogue")
        next_keywords = st.text_input("다음에 할 말의 키워드를 입력하세요:", key="next_keywords")
        if st.button("다음 문장 추천받기", use_container_width=True):
            st.session_state.conversation_history.append({"speaker": "나", "message": st.session_state.previous_sentence})
            if opponent_dialogue: st.session_state.conversation_history.append({"speaker": "상대방", "message": opponent_dialogue})
            data = call_backend_api(None, None, next_keywords, None, st.session_state.previous_sentence, opponent_dialogue, st.session_state.current_category)
            if data:
                st.session_state.previous_sentence = None
                st.session_state.current_recommendations = data['recommended_sentences']
                st.rerun()
        if st.button("대화 끝내기", type="secondary"):
            reset_conversation()
            st.rerun()

    elif st.session_state.current_recommendations: # Case 2: 추천 문장 표시
        st.subheader(f"✅ 현재 장소: **{st.session_state.current_category}**")
        st.success("아래 문장으로 대화를 시작하거나 이어가보세요!")
        for sentence in st.session_state.current_recommendations:
            col1, col2 = st.columns([0.85, 0.15])
            with col1:
                if st.button(sentence['text'], use_container_width=True, key=f"sent_{sentence['id']}"):
                    st.session_state.previous_sentence = sentence['text']
                    st.session_state.current_recommendations = []
                    st.rerun()
            with col2:
                if st.button("⭐", key=f"fav_{sentence['id']}", help="즐겨찾기에 추가"):
                    add_favorite_to_backend(sentence['text'])
        st.markdown("---")
        if st.button("새로운 대화 시작하기", key="reset_from_recs"):
            reset_conversation()
            st.rerun()

    else: # Case 3: 새로운 대화 시작
        st.header("1. 어디에 계신가요?")
        tab_manual, tab_auto = st.tabs(["📍 장소 직접 선택", "🤖 자동 인식 (QR/GPS)"])
        with tab_manual:
            locations = ["병원", "식당", "카페", "편의점", "지하철역", "도서관", "기타"]
            cols = st.columns(4)
            selected_location = None
            for i, location in enumerate(locations):
                if cols[i % 4].button(location, key=f"loc_{location}", use_container_width=True):
                    selected_location = "일상 대화" if location == "기타" else location
            keywords_manual = st.text_input("대화 키워드 (선택 사항)", key="keywords_manual")
            if selected_location:
                log_category_selection(selected_location) # 카테고리 선택 횟수 기록
                data = call_backend_api(None, None, keywords_manual, None, None, None, selected_location)
                if data:
                    st.session_state.current_recommendations = data['recommended_sentences']
                    st.session_state.current_category = data['category']
                    st.rerun()
        # (자동 인식 탭 로직은 생략 - 이전과 동일)
        with tab_auto:
            st.subheader("QR 코드로 인식")
            qr_input = st.text_input("QR 데이터", key="qr_data")
            if st.button("QR로 추천받기", key="button_qr"):
                # ... QR 로직
                pass

with favorites_tab:
    st.header("⭐ 즐겨찾기 목록")
    if st.button("새로고침"):
        get_favorites_from_backend()
    
    if not st.session_state.favorites:
        get_favorites_from_backend() # 처음 탭에 들어왔을 때 목록 로드

    if st.session_state.favorites:
        for fav in st.session_state.favorites:
            st.info(fav['sentence'])
    else:
        st.write("아직 즐겨찾기한 문장이 없습니다.")
