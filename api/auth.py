"""Auth routes — login and token verification."""

import os
import logging
from datetime import datetime, timedelta, timezone
from fastapi import APIRouter, HTTPException, Depends
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel
import jwt

logger = logging.getLogger(__name__)
router = APIRouter()
security = HTTPBearer()

JWT_SECRET  = os.getenv("JWT_SECRET", "change-me-in-production")
JWT_ALGO    = "HS256"
JWT_EXPIRY_H = 12

# Simple user store — replace with DB lookup in production
USERS = {
    os.getenv("ADMIN_EMAIL", "admin@solvit.co.ke"): os.getenv("ADMIN_PASSWORD", "solvit2024"),
}


class LoginRequest(BaseModel):
    email: str
    password: str


@router.post("/login")
def login(payload: LoginRequest):
    expected_pw = USERS.get(payload.email)
    if not expected_pw or expected_pw != payload.password:
        raise HTTPException(status_code=401, detail="Invalid credentials")

    token = jwt.encode(
        {
            "sub": payload.email,
            "exp": datetime.now(timezone.utc) + timedelta(hours=JWT_EXPIRY_H),
        },
        JWT_SECRET,
        algorithm=JWT_ALGO,
    )
    return {
        "token": token,
        "user": {"name": "AM Lead", "email": payload.email, "role": "am_lead"},
    }


def get_current_user(credentials: HTTPAuthorizationCredentials = Depends(security)):
    try:
        payload = jwt.decode(credentials.credentials, JWT_SECRET, algorithms=[JWT_ALGO])
        return payload["sub"]
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token expired")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Invalid token")
