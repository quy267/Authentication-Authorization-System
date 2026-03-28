from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.api.deps import get_current_user, require_role
from app.models.oauth2_client import OAuth2Client
from app.models.user import User
from app.schemas.auth import MessageResponse
from app.schemas.oauth2 import (
    OAuth2ClientCreateRequest,
    OAuth2ClientResponse,
    OAuth2RevokeRequest,
    OAuth2TokenRequest,
    OAuth2TokenResponse,
)
from app.services import oauth2_service

router = APIRouter(prefix="/oauth", tags=["oauth2"])


@router.post(
    "/clients",
    response_model=OAuth2ClientResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_client(
    body: OAuth2ClientCreateRequest,
    current_user: User = Depends(require_role("admin")),
):
    client, raw_secret = await oauth2_service.create_client(
        client_name=body.client_name,
        redirect_uris=body.redirect_uris,
        allowed_scopes=body.allowed_scopes,
        grant_types=body.grant_types,
        token_endpoint_auth_method=body.token_endpoint_auth_method,
    )
    # Return raw secret only on creation (not stored)
    return OAuth2ClientResponse(
        client_id=client.client_id,
        client_secret=raw_secret,
        client_name=client.client_name,
        redirect_uris=client.redirect_uris,
        allowed_scopes=client.allowed_scopes,
        grant_types=client.grant_types,
        token_endpoint_auth_method=client.token_endpoint_auth_method,
    )


@router.get("/clients", response_model=list[OAuth2ClientResponse])
async def list_clients(
    current_user: User = Depends(require_role("admin")),
):
    clients = await OAuth2Client.find_all().to_list()
    return [
        OAuth2ClientResponse(
            client_id=c.client_id,
            client_secret=None,  # Never expose hashed secrets
            client_name=c.client_name,
            redirect_uris=c.redirect_uris,
            allowed_scopes=c.allowed_scopes,
            grant_types=c.grant_types,
            token_endpoint_auth_method=c.token_endpoint_auth_method,
        )
        for c in clients
    ]


@router.get("/authorize")
async def authorize(
    response_type: str = Query(...),
    client_id: str = Query(...),
    redirect_uri: str = Query(...),
    scope: str = Query(""),
    state: str = Query(""),
    code_challenge: str | None = Query(None),
    code_challenge_method: str | None = Query(None),
    current_user: User = Depends(get_current_user),
):
    if response_type != "code":
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Unsupported response_type")

    code = await oauth2_service.authorize(
        client_id=client_id,
        redirect_uri=redirect_uri,
        scope=scope,
        user_id=str(current_user.id),
        code_challenge=code_challenge,
        code_challenge_method=code_challenge_method,
    )
    return {"code": code, "state": state}


@router.post("/token", response_model=OAuth2TokenResponse)
async def token(body: OAuth2TokenRequest):
    if body.grant_type == "authorization_code":
        if not body.code or not body.redirect_uri:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "Missing code or redirect_uri")
        return await oauth2_service.exchange_code(
            code=body.code,
            redirect_uri=body.redirect_uri,
            client_id=body.client_id,
            client_secret=body.client_secret,
            code_verifier=body.code_verifier,
        )
    elif body.grant_type == "client_credentials":
        if not body.client_secret:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "Missing client_secret")
        return await oauth2_service.client_credentials_grant(
            client_id=body.client_id,
            client_secret=body.client_secret,
            scope=body.scope or "",
        )
    elif body.grant_type == "refresh_token":
        if not body.refresh_token:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "Missing refresh_token")
        return await oauth2_service.refresh_oauth2_token(
            refresh_token=body.refresh_token,
            client_id=body.client_id,
        )
    else:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Unsupported grant_type")


@router.post("/revoke", response_model=MessageResponse)
async def revoke(body: OAuth2RevokeRequest):
    await oauth2_service.revoke_token(body.token)
    return {"message": "token revoked"}
