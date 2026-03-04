"""
Router API per la gestione degli utenti locali.

Tutti gli endpoint richiedono autenticazione e ruolo 'admin'.
"""

import logging

import app.core.auth as _auth_module
from app.core.audit import audit_event
from app.core.auth import destroy_all_sessions, extract_token_from_request, validate_csrf_dependency, validate_session
from app.core.user_manager import (
    VALID_ROLES,
    create_user,
    delete_user,
    get_user,
    list_users,
    update_user_password,
    update_user_role,
)
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field, field_validator

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/users", tags=["users"])


# ─── Schemas ─────────────────────────────────────────────────────────────────


class CreateUserRequest(BaseModel):
    username: str = Field(..., min_length=1, max_length=64)
    password: str = Field(..., min_length=8, max_length=128)
    role: str = Field(default="operator")

    @field_validator("role")
    @classmethod
    def validate_role(cls, v: str) -> str:
        if v not in VALID_ROLES:
            raise ValueError(f"Ruolo non valido: {v}. Validi: {sorted(VALID_ROLES)}")
        return v

    @field_validator("username")
    @classmethod
    def validate_username(cls, v: str) -> str:
        v = v.strip().lower()
        if not v:
            raise ValueError("Il nome utente non può essere vuoto")
        # Permetti solo caratteri alfanumerici, trattini e underscore
        import re

        if not re.match(r"^[a-z0-9_\-\.]+$", v):
            raise ValueError(
                "Il nome utente può contenere solo lettere minuscole, numeri, " "trattini, underscore e punti"
            )
        return v


class UpdateRoleRequest(BaseModel):
    role: str = Field(...)

    @field_validator("role")
    @classmethod
    def validate_role(cls, v: str) -> str:
        if v not in VALID_ROLES:
            raise ValueError(f"Ruolo non valido: {v}. Validi: {sorted(VALID_ROLES)}")
        return v


class UpdatePasswordRequest(BaseModel):
    new_password: str = Field(..., min_length=8, max_length=128)


# ─── Auth dependency ──────────────────────────────────────────────────────────


def _require_admin(request: Request) -> str:
    """
    FastAPI dependency: verifica che la richiesta provenga da un utente admin.
    Ritorna l'username dell'admin autenticato.
    """
    if not _auth_module.AUTH_ENABLED:
        return "admin"

    token = extract_token_from_request(request)
    result = validate_session(token)
    if result is None:
        raise HTTPException(status_code=401, detail="Autenticazione richiesta")

    username, role = result
    if role != "admin":
        raise HTTPException(
            status_code=403,
            detail="Accesso negato: questa operazione richiede il ruolo 'admin'",
        )
    return username


# ─── Endpoints ───────────────────────────────────────────────────────────────


@router.get("")
async def list_users_endpoint(
    request: Request,
    admin_username: str = Depends(_require_admin),
):
    """
    Ritorna la lista di tutti gli utenti (solo admin).
    """
    users = list_users()
    return {"users": users, "total": len(users)}


@router.post("", dependencies=[Depends(validate_csrf_dependency)])
async def create_user_endpoint(
    body: CreateUserRequest,
    request: Request,
    admin_username: str = Depends(_require_admin),
):
    """
    Crea un nuovo utente locale (solo admin).
    """
    try:
        create_user(body.username, body.password, body.role)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    audit_event(
        request,
        "user_created",
        new_user=body.username,
        role=body.role,
        by=admin_username,
    )
    logger.info("users_routes: utente '%s' creato da admin '%s'", body.username, admin_username)

    user = get_user(body.username)
    return {"message": f"Utente '{body.username}' creato con successo", "user": user}


@router.get("/me")
async def get_current_user(request: Request):
    """
    Ritorna le informazioni sull'utente correntemente autenticato.
    Accessibile a tutti gli utenti autenticati (admin e operator).
    """
    if not _auth_module.AUTH_ENABLED:
        return {"username": "admin", "role": "admin"}

    token = extract_token_from_request(request)
    result = validate_session(token)
    if result is None:
        raise HTTPException(status_code=401, detail="Autenticazione richiesta")

    username, role = result
    user = get_user(username)
    if user is None:
        # Utente nella sessione ma non nel DB (es. eliminato mentre loggato)
        raise HTTPException(status_code=401, detail="Utente non trovato")

    return {"username": username, "role": role}


@router.get("/{username}")
async def get_user_endpoint(
    username: str,
    request: Request,
    admin_username: str = Depends(_require_admin),
):
    """
    Recupera i dettagli di un utente specifico (solo admin).
    """
    user = get_user(username)
    if user is None:
        raise HTTPException(status_code=404, detail=f"Utente '{username}' non trovato")
    return user


@router.put("/{username}/role", dependencies=[Depends(validate_csrf_dependency)])
async def update_role_endpoint(
    username: str,
    body: UpdateRoleRequest,
    request: Request,
    admin_username: str = Depends(_require_admin),
):
    """
    Aggiorna il ruolo di un utente (solo admin).
    """
    try:
        update_user_role(username, body.role)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    audit_event(
        request,
        "user_role_updated",
        target_user=username,
        new_role=body.role,
        by=admin_username,
    )
    logger.info(
        "users_routes: ruolo di '%s' aggiornato a '%s' da admin '%s'",
        username,
        body.role,
        admin_username,
    )

    user = get_user(username)
    return {"message": f"Ruolo di '{username}' aggiornato a '{body.role}'", "user": user}


@router.put("/{username}/password", dependencies=[Depends(validate_csrf_dependency)])
async def update_password_endpoint(
    username: str,
    body: UpdatePasswordRequest,
    request: Request,
    admin_username: str = Depends(_require_admin),
):
    """
    Aggiorna la password di un utente (solo admin o l'utente stesso).
    """
    # Verifica che sia l'admin o l'utente stesso
    token = extract_token_from_request(request)
    result = validate_session(token)
    if result is None:
        raise HTTPException(status_code=401, detail="Autenticazione richiesta")

    requester_username, requester_role = result
    if requester_role != "admin" and requester_username != username:
        raise HTTPException(
            status_code=403,
            detail="Accesso negato: puoi modificare solo la tua password",
        )

    try:
        update_user_password(username, body.new_password)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    # Invalida tutte le sessioni dell'utente (sicurezza: cambio password)
    if requester_role == "admin" and requester_username != username:
        # L'admin ha cambiato la password di un altro utente: invalida le sue sessioni
        destroy_all_sessions()
        logger.info(
            "users_routes: sessioni invalidate dopo cambio password di '%s' da admin '%s'",
            username,
            admin_username,
        )

    audit_event(
        request,
        "user_password_changed",
        target_user=username,
        by=requester_username,
    )

    return {"message": f"Password di '{username}' aggiornata con successo"}


@router.delete("/{username}", dependencies=[Depends(validate_csrf_dependency)])
async def delete_user_endpoint(
    username: str,
    request: Request,
    admin_username: str = Depends(_require_admin),
):
    """
    Elimina un utente (solo admin).
    Non è possibile eliminare l'ultimo admin.
    """
    try:
        delete_user(username)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    audit_event(
        request,
        "user_deleted",
        deleted_user=username,
        by=admin_username,
    )
    logger.info("users_routes: utente '%s' eliminato da admin '%s'", username, admin_username)

    return {"message": f"Utente '{username}' eliminato con successo"}
