import streamlit as st
import httpx
from datetime import datetime

# --- 세션 상태(Session State) 초기화 ---
if 'conversation_history' not in st.session_state: st.session_state.conversation_history = []
if 'current_recommendations' not in st.session_state: st.session_state.current_recommendations = []
if 'previous_sentence' not in st.session_state: st.session_state.previous_sentence = None
if 'current_category' not in st.session_state: st.session_state.current_category = ""
if 'favorites' not in st.session_state: st.session_state.favorites = []

# --- API 호출 함수들 ---
def call_recommendation_api(lat, lon, keywords, qr_data, previous_sentence, opponent_dialogue, manual_category):
    backend_url = "http://127.0.0.1:8000/recommendations"
    params = {"keywords": keywords or "", "qr_data": qr_data or "", "previous_sentence": previous_sentence or "", "opponent_dialogue": opponent_dialogue or "", "manual_category": manual_category or ""}
    if lat is not None and lon is not None: params["lat"], params["lon"] = lat, lon
    try:
        with st.spinner("AI가 상황에 맞는 문장을 생각하고 있습니다..."):
            response = httpx.get(backend_url, params=params, timeout=60)
            response.raise_for_status()
            return response.json()
    except Exception as e:
        st.error(f"오류가 발생했습니다: {e}")
        return None

def log_speech_to_backend(sentence, location):
    try:
        httpx.post("http://127.0.0.1:8000/speech-logs", json={"sentence": sentence, "location": location})
    except Exception as e: print(f"로그 저장 실패: {e}")

def get_favorites_from_backend():
    try:
        response = httpx.get("http://127.0.0.1:8000/favorites")
        response.raise_for_status()
        st.session_state.favorites = response.json()
    except Exception as e: st.error(f"즐겨찾기 목록을 불러오는 데 실패했습니다: {e}")

def add_favorite_to_backend(sentence):
    try:
        httpx.post("http://127.0.0.1:8000/favorites", json={"sentence": sentence})
        st.toast(f'"{sentence}" 문장을 즐겨찾기에 추가했습니다! ✅')
        get_favorites_from_backend()
    except Exception as e: st.error(f"즐겨찾기 추가에 실패했습니다: {e}")

def reset_conversation():
    for key in st.session_state.keys():
        if key != 'favorites': # 즐겨찾기 목록은 유지
            del st.session_state[key]

# --- 1. 메인 화면 구성 ---
st.set_page_config(layout="wide")
st.title("🤖 대화형 AAC 앱")
st.caption(f"현재 시간: {datetime.now().strftime('%Y년 %m월 %d일 %p %I:%M')}")

# --- 2. 메인 탭 구성 ---
main_tab, favorites_tab = st.tabs(["💬 대화하기", "⭐ 즐겨찾기 목록"])

with main_tab:
    col1, col2 = st.columns([2, 1])
    
    with col1: # 왼쪽 (대화 진행 영역)
        # Case 1: 새로운 대화 시작
        if not st.session_state.previous_sentence and not st.session_state.current_recommendations:
            st.header("1. 어디에 계신가요?")
            st.info("장소를 선택하거나, QR/GPS로 인식하여 대화를 시작하세요.")
            tab_manual, tab_auto = st.tabs(["📍 장소 직접 선택", "🤖 자동 인식 (QR/GPS)"])
            with tab_manual:
                locations = ["병원", "식당", "카페", "편의점", "지하철역", "도서관", "기타"]
                cols_loc = st.columns(4)
                selected_location = None
                for i, location in enumerate(locations):
                    if cols_loc[i % 4].button(location, key=f"loc_{location}", use_container_width=True):
                        selected_location = "일상 대화" if location == "기타" else location
                keywords_manual = st.text_input("대화 키워드 (선택 사항)", key="keywords_manual")
                if selected_location:
                    data = call_recommendation_api(None, None, keywords_manual, None, None, None, selected_location)
                    if data:
                        st.session_state.current_recommendations = data['recommended_sentences']
                        st.session_state.current_category = data['category']
                        st.rerun()
            with tab_auto:
                qr_input = st.text_input("QR 데이터", key="qr_data")
                if st.button("QR로 추천받기", key="button_qr"):
                    data = call_recommendation_api(None, None, "", qr_input, None, None, None)
                    if data:
                        st.session_state.current_recommendations = data['recommended_sentences']
                        st.session_state.current_category = data['category']
                        st.rerun()
                st.markdown("---")
                lat_input = st.number_input("위도", value=37.5, format="%.4f", key="lat_gps")
                lon_input = st.number_input("경도", value=127.0, format="%.4f", key="lon_gps")
                if st.button("GPS로 추천받기", key="button_gps"):
                    data = call_recommendation_api(lat_input, lon_input, "", None, None, None)
                    if data:
                        st.session_state.current_recommendations = data['recommended_sentences']
                        st.session_state.current_category = data['category']
                        st.rerun()
        
        # Case 2: 추천 문장 표시
        elif st.session_state.current_recommendations:
            st.header(f"✅ 현재 장소: {st.session_state.current_category}")
            st.success("아래 문장으로 대화를 시작하거나 이어가보세요!")
            for sentence in st.session_state.current_recommendations:
                col_sent, col_fav = st.columns([0.85, 0.15])
                if col_sent.button(sentence['text'], use_container_width=True, key=f"sent_{sentence['id']}"):
                    log_speech_to_backend(sentence['text'], st.session_state.current_category)
                    st.session_state.previous_sentence = sentence['text']
                    st.session_state.current_recommendations = []
                    st.rerun()
                if col_fav.button("⭐", key=f"fav_{sentence['id']}", help="즐겨찾기에 추가"):
                    add_favorite_to_backend(sentence['text'])
            
            # === 여기가 수정된 부분입니다! (새로고침 기능) ===
            st.markdown("---")
            with st.expander("다른 문장 추천받기 (새로고침)"):
                refresh_keywords = st.text_input("새로운 키워드를 입력하여 다시 추천받을 수 있습니다:", key="refresh_keywords")
                if st.button("🔄 새로고침", key="refresh_button"):
                    last_sentence = st.session_state.conversation_history[-1]['message'] if st.session_state.conversation_history else None
                    data = call_recommendation_api(None, None, refresh_keywords, None, last_sentence, None, st.session_state.current_category)
                    if data:
                        st.session_state.current_recommendations = data['recommended_sentences']
                        st.rerun()

        # Case 3: 대화 이어가기
        elif st.session_state.previous_sentence:
            st.header("다음 대화 이어가기")
            st.write(f"**내가 방금 한 말:** \"{st.session_state.previous_sentence}\"")
            opponent_dialogue = st.text_area("상대방이 한 말을 입력하세요 (선택 사항):", key="opponent_dialogue")
            next_keywords = st.text_input("다음에 할 말의 키워드를 입력하세요:", key="next_keywords")
            if st.button("다음 문장 추천받기", use_container_width=True):
                st.session_state.conversation_history.append({"speaker": "나", "message": st.session_state.previous_sentence})
                if opponent_dialogue: st.session_state.conversation_history.append({"speaker": "상대방", "message": opponent_dialogue})
                data = call_recommendation_api(None, None, next_keywords, None, st.session_state.previous_sentence, opponent_dialogue, st.session_state.current_category)
                if data:
                    st.session_state.previous_sentence = None
                    st.session_state.current_recommendations = data['recommended_sentences']
                    st.rerun()
            if st.button("대화 끝내기", type="secondary"):
                reset_conversation()
                st.rerun()

    with col2: # 오른쪽 (대화 기록 영역)
        st.subheader("💬 대화 기록")
        if st.button("대화 초기화", use_container_width=True):
            reset_conversation()
            st.rerun()
        st.markdown("---")
        if st.session_state.conversation_history:
            for item in st.session_state.conversation_history:
                if item['speaker'] == '나': st.info(f"**나:** {item['message']}")
                else: st.success(f"**상대방:** {item['message']}")
        else:
            st.write("아직 대화 기록이 없습니다.")

with favorites_tab:
    st.header("⭐ 즐겨찾기 목록")
    if st.button("새로고침", key="fav_refresh"):
        get_favorites_from_backend()
    if not st.session_state.favorites:
        get_favorites_from_backend()
    if st.session_state.favorites:
        for fav in st.session_state.favorites:
            st.info(fav['sentence'])
    else:
        st.write("아직 즐겨찾기한 문장이 없습니다.")
