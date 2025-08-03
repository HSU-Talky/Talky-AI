# config.py (AI 마이크로서비스 버전)
from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    """
<<<<<<< HEAD
    .env 파일에서 AI 및 외부 서비스 API 키를 읽어옵니다.
=======
    .env 파일에서 AI, 외부 서비스 API 키를 읽어옵니다.
>>>>>>> e06161f501013ba0ef2554f54b04e5b20277d626
    """
    GOOGLE_API_KEY: str
    KAKAO_API_KEY: str

    model_config = SettingsConfigDict(env_file=".env", extra='ignore')
    
# 설정 객체를 생성합니다.
# 이제 다른 파일에서 이 객체를 import하여 설정값을 사용할 수 있습니다.
settings = Settings()
