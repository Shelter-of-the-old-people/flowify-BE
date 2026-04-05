from app.common.errors import ErrorCode, FlowifyException


def test_error_code_properties():
    assert ErrorCode.INTERNAL_ERROR.http_status == 500
    assert ErrorCode.INTERNAL_ERROR.message == "내부 서버 오류가 발생했습니다"
    assert ErrorCode.UNAUTHORIZED.http_status == 401
    assert ErrorCode.LLM_API_ERROR.http_status == 502
    assert ErrorCode.LLM_GENERATION_FAILED.http_status == 422
    assert ErrorCode.ROLLBACK_UNAVAILABLE.http_status == 400


def test_flowify_exception_defaults():
    exc = FlowifyException(ErrorCode.NODE_EXECUTION_FAILED)
    assert exc.error_code == ErrorCode.NODE_EXECUTION_FAILED
    assert exc.detail == "노드 실행에 실패했습니다"
    assert exc.context == {}


def test_flowify_exception_custom():
    exc = FlowifyException(
        ErrorCode.EXTERNAL_API_ERROR,
        detail="Google Drive API 실패",
        context={"service": "google_drive", "status_code": 503},
    )
    assert exc.detail == "Google Drive API 실패"
    assert exc.context["service"] == "google_drive"
    assert str(exc) == "Google Drive API 실패"


def test_all_error_codes_have_required_fields():
    for code in ErrorCode:
        assert isinstance(code.http_status, int)
        assert 400 <= code.http_status <= 599
        assert isinstance(code.message, str)
        assert len(code.message) > 0
