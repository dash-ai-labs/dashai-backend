import stripe

from fastapi.responses import JSONResponse
from fastapi import APIRouter, Depends, Request

from src.routes.middleware import get_user_id
from src.database.db import get_db
from src.database.user import MembershipStatus, User
from src.libs.const import STRIPE_PRICE_ID, STRIPE_REDIRECT_URI, STRIPE_SECRET_KEY

router = APIRouter()


@router.post("/webhooks")
async def stripe_webhook(request: Request):
    stripe.api_key = STRIPE_SECRET_KEY
    body = await request.json()

    event_type = body.get("type")
    data_object = body.get("data", {}).get("object", {})

    indicates_payment_method_added = False
    customer_id = data_object.get("customer")
    user_email = None
    user_id_from_ref = data_object.get("client_reference_id")

    if event_type == "checkout.session.completed":
        # Treat both setup and subscription completion as adding a payment method
        if data_object.get("mode") in ("setup", "subscription"):
            indicates_payment_method_added = True
            customer_id = data_object.get("customer")
            # Stripe includes customer_details on the Session
            user_email = (
                data_object.get("customer_details", {}).get("email")
                if isinstance(data_object, dict)
                else None
            )

    # If we still don't have an email, try fetching the customer from Stripe
    if not user_email and customer_id:
        try:
            customer = stripe.Customer.retrieve(customer_id)
            user_email = customer.get("email")
        except Exception:
            pass

    if indicates_payment_method_added:
        with get_db() as db:
            user = None
            if user_id_from_ref:
                user = db.query(User).filter(User.id == user_id_from_ref).first()
            if not user and user_email:
                user = db.query(User).filter(User.email == user_email).first()
            if user and user.waitlisted:
                user.waitlisted = False
                user.membership_status = MembershipStatus.TRIAL.value
                db.add(user)
                db.commit()

    return {"received": True}


@router.post("/create_checkout_session")
async def create_checkout_session(user=Depends(get_user_id)):
    try:
        stripe.api_key = STRIPE_SECRET_KEY
        session = stripe.checkout.Session.create(
            mode="subscription",
            payment_method_types=["card"],
            line_items=[{"price": STRIPE_PRICE_ID, "quantity": 1}],
            subscription_data={"trial_period_days": 7},
            success_url=f"{STRIPE_REDIRECT_URI}/inbox?session_id={{CHECKOUT_SESSION_ID}}",
            cancel_url=f"{STRIPE_REDIRECT_URI}/waitlist",
            client_reference_id=user.get("user_id"),  # Google user ID
        )
        return {"id": session.id}
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=400)
