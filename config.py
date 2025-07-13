from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    """
    .env 파일에서 AI, 외부 서비스 API 키를 읽어옵니다.
    """
    GOOGLE_API_KEY: str
    KAKAO_API_KEY: str

    model_config = SettingsConfigDict(env_file=".env", extra='ignore')
    
# 설정 객체를 생성합니다.
# 이제 다른 파일에서 이 객체를 import하여 설정값을 사용할 수 있습니다.
settings = Settings()
