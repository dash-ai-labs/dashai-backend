import httpx
from fastapi import APIRouter, Response

router = APIRouter()


@router.get("/proxy-stylesheet/")
async def proxy_stylesheet(url: str):
    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(url, timeout=10)
            response.raise_for_status()
            content_type = response.headers.get("Content-Type", "text/css")
            return Response(content=response.text, media_type=content_type)
    except httpx.RequestError:
        return Response("Failed to fetch stylesheet", status_code=500)
