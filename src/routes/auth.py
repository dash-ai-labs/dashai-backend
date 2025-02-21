import base64
import hashlib
import json
import logging
import secrets
from datetime import datetime, timedelta

import jwt
from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel

from src.celery_tasks import ingest_email
from src.database import EmailAccount, EmailProvider, Token, User, get_db
from src.libs.const import SECRET_KEY
from src.routes.middleware import ALGORITHM, get_user_id
from src.services import FlowService, GoogleProfileService

router = APIRouter()

ACCESS_TOKEN_EXPIRE_DAYS = 30


class GoogleAuthRequest(BaseModel):
    code: str
    redirect_uri: str


logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)


def create_jwt_token(data: dict):
    to_encode = data.copy()
    expire = datetime.utcnow() + timedelta(days=ACCESS_TOKEN_EXPIRE_DAYS)
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt


@router.get("/auth/google/url")
async def google_auth_url():
    # Generate code verifier
    code_verifier = secrets.token_urlsafe(32)
    # Generate code challenge
    code_challenge = (
        base64.urlsafe_b64encode(hashlib.sha256(code_verifier.encode()).digest())
        .decode()
        .rstrip("=")
    )
    flow_service = FlowService(
        state=base64.urlsafe_b64encode(
            json.dumps({"code_verifier": code_verifier}).encode()
        ).decode()
    )
    url, state = flow_service.authorization_url(
        access_type="offline",  # Ensures we get a refresh token
        include_granted_scopes="true",  # Use previously granted scopes
        prompt="consent",  # Prompt the user to ensure consent for refresh token
        code_challenge=code_challenge,
        code_challenge_method="S256",  # Use SHA256 for code challenge
    )
    return {"url": url}


class GoogleCallback(BaseModel):
    code: str
    state: str


@router.post("/auth/google/callback")
async def google_callback(callback: GoogleCallback):
    # Exchange code for tokens
    code, state = callback.code, callback.state
    state = json.loads(base64.urlsafe_b64decode(state).decode("utf-8"))

    code_verifier = state.get("code_verifier")
    user_id = state.get("user_id", None)
    flow = FlowService()
    credentials = flow.credentials(code=code, code_verifier=code_verifier)
    google_profile_service = GoogleProfileService(
        oauth_token=credentials.token, refresh_token=credentials.refresh_token
    )

    user_info = google_profile_service.get_profile()
    with get_db() as db:
        if user_id:
            user = db.query(User).filter(User.id == user_id).first()
        else:
            user = db.query(User).filter(User.google_id == user_info["id"]).first()

        # Create user if not found
        if not user:
            user = User(
                email=user_info["email"],
                google_id=user_info["id"],
                name=user_info.get("name"),
                profile_pic=user_info.get("picture"),
            )
        user.profile_pic = user_info.get("picture")

        email_account = EmailAccount.get_or_create_email_account(
            db, EmailProvider.GMAIL, user, user_info
        )

        # Email account is not synced yet and no token found
        if not email_account.token and not email_account.last_sync:
            oauth_token = Token.get_or_create_token(
                db, email_account.id, credentials.token, credentials.refresh_token
            )
            email_account.token = oauth_token

            user.email_accounts.append(email_account)
            db.add(oauth_token)

        db.add_all([email_account, user])
        db.commit()
        ingest_email.delay(email_account_id=email_account.id)

        user.last_login = datetime.utcnow()

        # Create JWT
        token = create_jwt_token({"sub": str(user.id)})
        response = Response(
            content=json.dumps(
                {
                    "id": str(user.id),
                    "email": user.email,
                    "name": user.name,
                }
            )
        )
        response.set_cookie(
            key="auth_token",
            value=token,
            httponly=True,
            secure=True,
            samesite="strict",
            max_age=60 * 60 * 24 * 30,  # 30 days
            expires=60 * 60 * 24 * 30,
        )
        return response


@router.get("/user/{user_id}/email_accounts")
async def get_email_accounts(request: Request, user_id: str, user=Depends(get_user_id)):
    if user_id == user.get("user_id"):
        with get_db() as db:
            email_accounts: list[EmailAccount] = (
                db.query(User).filter(User.id == user_id).first().email_accounts
            )

            if not user:
                raise HTTPException(status_code=404, detail="User not found")

            return [email_account.to_dict() for email_account in email_accounts]


@router.post("/user/{user_id}/email_accounts/register")
async def register_email_account(
    request: Request, user_id: str, user=Depends(get_user_id)
):
    if user_id == user.get("user_id"):
        with get_db() as db:
            # Generate code verifier
            code_verifier = secrets.token_urlsafe(32)
            # Generate code challenge
            code_challenge = (
                base64.urlsafe_b64encode(
                    hashlib.sha256(code_verifier.encode()).digest()
                )
                .decode()
                .rstrip("=")
            )
            flow_service = FlowService(
                state=base64.urlsafe_b64encode(
                    json.dumps(
                        {"code_verifier": code_verifier, "user_id": user_id}
                    ).encode()
                ).decode()
            )
            url, state = flow_service.authorization_url(
                access_type="offline",  # Ensures we get a refresh token
                include_granted_scopes="true",  # Use previously granted scopes
                prompt="consent",  # Prompt the user to ensure consent for refresh token
                code_challenge=code_challenge,
                code_challenge_method="S256",  # Use SHA256 for code challenge
            )
            return {"url": url}


@router.get("/user/{user_id}/profile")
async def get_user_profile(request: Request, user_id: str, user=Depends(get_user_id)):
    if user_id == user.get("user_id"):
        with get_db() as db:
            user_profile = db.query(User).filter(User.id == user_id).first()

            if not user_profile:
                raise HTTPException(status_code=404, detail="User not found")

            return user_profile.to_dict()

    raise HTTPException(status_code=401, detail="Unauthorized")


@router.post("/auth/logout")
async def logout():
    response = Response()
    response.delete_cookie("auth_token")
    return response
