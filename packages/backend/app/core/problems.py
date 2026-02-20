from fastapi.responses import JSONResponse


def problem_response(status: int, title: str, detail: str, type_: str = "about:blank") -> JSONResponse:
    return JSONResponse(
        status_code=status,
        media_type="application/problem+json",
        content={
            "type": type_,
            "title": title,
            "status": status,
            "detail": detail,
        },
    )
