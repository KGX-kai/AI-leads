class BusinessError(ValueError):
    def __init__(self, message, code="VALIDATION_ERROR", retryable=False):
        super().__init__(message)
        self.code, self.retryable = code, retryable


def envelope(data=None, error=None, request_id=None):
    return {
        "schema_version": "1.3",
        "ok": error is None,
        "request_id": request_id,
        "data": data if error is None else None,
        "error": None
        if error is None
        else {
            "code": error.code,
            "message": str(error),
            "retryable": error.retryable,
        },
    }
