import base64
import hashlib
import json
import logging
import secrets
from datetime import datetime, timedelta

import jwt
import stripe
from fastapi import APIRouter, Body, Depends, HTTPException, Request, Response
from pydantic import BaseModel
from sqlalchemy import String, cast

from src.celery_tasks import delete_user, ingest_email
from src.database import EmailAccount, EmailProvider, Token, User, get_db
from src.database.notification import Notification
from src.database.waitlist import OffWaitlist
from src.libs.const import (
    DISCORD_USER_ALERTS_CHANNEL,
    SECRET_KEY,
    STAGE,
    STRIPE_SECRET_KEY,
)
from src.libs.discord_service import send_discord_message
from src.libs.types import STAGE_TYPE
from src.routes.middleware import ALGORITHM, get_user_id
from src.services import FlowService, GoogleProfileService, OutlookService

router = APIRouter()

stripe.api_key = STRIPE_SECRET_KEY

ACCESS_TOKEN_EXPIRE_DAYS = 30


class Callback(BaseModel):
    code: str
    state: str


logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)


def create_jwt_token(data: dict):
    to_encode = data.copy()
    expire = datetime.utcnow() + timedelta(days=ACCESS_TOKEN_EXPIRE_DAYS)
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt


@router.get("/auth/outlook/url")
async def outlook_auth_url():
    outlook_service = OutlookService()
    # Generate code verifier
    code_verifier = secrets.token_urlsafe(32)
    # Generate code challenge
    code_challenge = (
        base64.urlsafe_b64encode(hashlib.sha256(code_verifier.encode()).digest())
        .decode()
        .rstrip("=")
    )
    state = base64.urlsafe_b64encode(json.dumps({"code_verifier": code_verifier}).encode()).decode()
    return {"url": outlook_service.authorize_url(state=state, code_challenge=code_challenge)}


def _create_subscription(user: User):
    customer = stripe.Customer.create(email=user.email, name=user.name)
    pricing_id = (
        "price_1RIJqcH77fbQTfphHxKGuWL1"
        if STAGE == STAGE_TYPE.PRODUCTION
        else "price_1RIbQXH77fbQTfphp3iQCvox"
    )
    subscription = stripe.Subscription.create(
        customer=customer.id,
        items=[{"price": pricing_id}],
        trial_period_days=14,
    )
    return_url = (
        "https://app.getdash.ai" if STAGE == STAGE_TYPE.PRODUCTION else "http://localhost:5173"
    )
    checkout_session = stripe.checkout.Session.create(
        mode="setup",  # <-- Important: we're just collecting payment method
        customer=customer.id,  # Your Stripe customer ID
        setup_intent_data={
            "metadata": {"subscription_id": subscription.id}  # Your created subscription ID
        },
        currency="usd",
        success_url=return_url,
    )

    notification = Notification(
        user=user,
        title="Welcome to Dash AI! Your 14 day trial has started.",
        message="You have access to all features for the next 14 days. To continue using Dash AI, please upgrade to a paid plan.",
        link=checkout_session.url,
    )
    return notification


@router.delete("/user/{user_id}")
async def delete_user_route(user_id: str, user=Depends(get_user_id)):
    if user_id == user.get("user_id"):
        with get_db() as db:
            user = db.query(User).filter(User.id == user_id).first()
            delete_user.delay(user_id)
        return {"message": "User deleted"}
    raise HTTPException(status_code=401, detail="Unauthorized")


@router.put("/user/{user_id}")
async def update_user(user_id: str, data: dict = Body(...), user=Depends(get_user_id)):
    if user_id == user.get("user_id"):
        show_tutorial = data.get("show_tutorial")
        if show_tutorial is not None:
            with get_db() as db:
                user = db.query(User).filter(User.id == user_id).first()
                user.show_tutorial = show_tutorial
                db.commit()
        return {"message": "User updated"}
    raise HTTPException(status_code=401, detail="Unauthorized")


@router.post("/user/{user_id}/referral")
async def send_referral(user_id: str, email: str, user=Depends(get_user_id)):
    if user_id == user.get("user_id"):
        with get_db() as db:
            user = db.query(User).filter(User.id == user_id).first()
            referral = db.query(User).filter(User.email == email).first()
            if referral:
                user.referrals.append({"email": email, "accepted": True})
            else:
                user.referrals.append({"email": email, "accepted": False})
            db.commit()
        return {"message": "Referral added"}


@router.post("/auth/outlook/callback")
async def outlook_callback(callback: Callback):
    code = callback.code
    state = callback.state
    if state:
        state = json.loads(base64.urlsafe_b64decode(state).decode("utf-8"))
        user_id = state.get("user_id", None)
        code_verifier = state.get("code_verifier", None)
    else:
        user_id = None
        code_verifier = None
    outlook_service = OutlookService()
    token_data = outlook_service.exchange_code(code, code_verifier)
    user_info = await outlook_service.get_user_info(token=token_data["access_token"])
    print(user_info)
    with get_db() as db:
        if user_id:
            user = db.query(User).filter(User.id == user_id).first()
        else:
            user = db.query(User).filter(User.email == user_info["mail"]).first()

        if not user:
            # Check if this user's email exists in any other user's referrals
            waitlist = True
            try:
                referred = (
                    db.query(User)
                    .filter(User.referrals.is_not(None))
                    .filter(cast(User.referrals["email"], String) == user_info["email"])
                    .first()
                )
            except Exception as e:
                print(e)
                referred = None

            try:
                off_waitlist = (
                    db.query(OffWaitlist).filter(OffWaitlist.email == user_info["email"]).first()
                )
            except Exception as e:
                print(e)
                off_waitlist = None

            waitlist = off_waitlist is None and referred is None
            user = User(
                email=user_info["mail"],
                name=user_info.get("displayName"),
                outlook_id=user_info["id"],
                waitlisted=waitlist,
            )
            notification = _create_subscription(user)
            db.add(notification)
            send_discord_message(f"User {user.email} has signed up", DISCORD_USER_ALERTS_CHANNEL)
        email_account = EmailAccount.get_or_create_email_account(
            db, EmailProvider.OUTLOOK, user, user_info["mail"]
        )
        expires_at = datetime.utcnow() + timedelta(seconds=token_data["expires_in"])
        # Email account is not synced yet and no token found
        if not email_account.token and not email_account.last_sync:
            oauth_token = Token.get_or_create_token(
                db,
                email_account.id,
                token_data["access_token"],
                token_data["refresh_token"],
                expires_at,
            )
            email_account.token = oauth_token

            user.email_accounts.append(email_account)

            db.add(oauth_token)
        else:
            token = email_account.token
            token.token = token_data["access_token"]
            token.refresh_token = token_data["refresh_token"]
            token.expires_at = expires_at
            db.add(token)

        db.add_all([user, email_account])
        db.commit()

        ingest_email.delay(email_account_id=email_account.id)

        user.last_login = datetime.utcnow()
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


@router.post("/auth/google/callback")
async def google_callback(callback: Callback):
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
    print(user_info)
    with get_db() as db:
        if user_id:
            user = db.query(User).filter(User.id == user_id).first()
        else:
            user = db.query(User).filter(User.google_id == user_info["id"]).first()

        # Create user if not found
        if not user:
            # Check if this user's email exists in any other user's referrals
            waitlist = True
            try:
                referred = (
                    db.query(User)
                    .filter(User.referrals.is_not(None))
                    .filter(cast(User.referrals["email"], String) == user_info["email"])
                    .first()
                )
            except Exception as e:
                print(e)
                referred = None

            try:
                off_waitlist = (
                    db.query(OffWaitlist).filter(OffWaitlist.email == user_info["email"]).first()
                )
            except Exception as e:
                print(e)
                off_waitlist = None

            waitlist = off_waitlist is None and referred is None
            # If found, we can use this information later for referral tracking
            # or to automatically connect users who were referred
            user = User(
                email=user_info["email"],
                google_id=user_info["id"],
                name=user_info.get("name"),
                profile_pic=user_info.get("picture"),
                waitlisted=waitlist,
            )
            notification = _create_subscription(user)
            db.add(notification)
            send_discord_message(f"User {user.email} has signed up", DISCORD_USER_ALERTS_CHANNEL)
        user.profile_pic = user_info.get("picture")

        email_account = EmailAccount.get_or_create_email_account(
            db, EmailProvider.GMAIL, user, user_info["email"]
        )
        # Email account is not synced yet and no token found
        if not email_account.token and not email_account.last_sync:

            oauth_token = Token.get_or_create_token(
                db,
                email_account.id,
                credentials.token,
                credentials.refresh_token,
                credentials.expiry,
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


@router.post("/user/{user_id}/email_accounts/register_google")
async def register_google_account(request: Request, user_id: str, user=Depends(get_user_id)):
    if user_id == user.get("user_id"):
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
                json.dumps({"code_verifier": code_verifier, "user_id": user_id}).encode()
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


@router.post("/user/{user_id}/email_accounts/register_outlook")
async def register_outlook_account(request: Request, user_id: str, user=Depends(get_user_id)):
    if user_id == user.get("user_id"):
        outlook_service = OutlookService()
        # Generate code verifier
        code_verifier = secrets.token_urlsafe(32)
        # Generate code challenge
        code_challenge = (
            base64.urlsafe_b64encode(hashlib.sha256(code_verifier.encode()).digest())
            .decode()
            .rstrip("=")
        )
        state = base64.urlsafe_b64encode(
            json.dumps({"code_verifier": code_verifier, "user_id": user_id}).encode()
        ).decode()

        return {"url": outlook_service.authorize_url(state=state, code_challenge=code_challenge)}


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
