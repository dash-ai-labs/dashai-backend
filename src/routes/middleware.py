import jwt
from fastapi import HTTPException, Request
from jose import JWTError

from src.libs.const import SECRET_KEY

ALGORITHM = "HS256"


def get_user_id(request: Request):
    token = request.cookies.get("auth_token")
    if not token:
        raise HTTPException(status_code=401, detail="Not authenticated")

    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        user_id = payload.get("sub")
        if not user_id:
            raise HTTPException(status_code=401, detail="Invalid token")
        return {"user_id": user_id}  # Return user data (expand as needed)
    except JWTError:
        raise HTTPException(status_code=401, detail="Invalid token")
