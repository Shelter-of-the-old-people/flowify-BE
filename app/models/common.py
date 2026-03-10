from pydantic import BaseModel


class CommonDTO(BaseModel):
    """공통 DTO - 이기종 데이터 규격 통합 (Adapter 패턴)"""

    source_service: str
    data_type: str
    content: dict
    metadata: dict | None = None
