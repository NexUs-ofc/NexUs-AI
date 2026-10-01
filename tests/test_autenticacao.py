"""
Autenticação do ms-ia.

A estratégia é a mesma da API Core: o token do mobile é validado aqui pela
assinatura, sem consultar sessão, Redis ou o microsserviço de autenticação.

Os tokens destes testes são montados com as mesmas claims que o
JwtTokenService do Auth emite.
"""

from datetime import datetime, timedelta, timezone
from uuid import uuid4

import jwt
import pytest
from fastapi import HTTPException
from fastapi.security import HTTPAuthorizationCredentials

from app.auth.api_key_validator import validate_api_key
from app.auth.dependencies import get_current_user
from app.auth.jwt_handler import TokenInvalido, decodificar_token
from app.config import (
    JWT_ALGORITHM,
    JWT_ISSUER,
    JWT_SECRET_BYTES,
    VALID_API_KEYS,
    VALID_TOKENS,
)


def montar_token(**sobrescritas) -> str:
    agora = datetime.now(timezone.utc)

    claims = {
        "iss": JWT_ISSUER,
        "sub": "7",
        "iat": agora,
        "exp": agora + timedelta(minutes=15),
        "jti": str(uuid4()),
        "profile_type": "HOUSEHOLD",
        "email": "teste@ceris.app",
    }
    claims.update(sobrescritas)

    return jwt.encode(claims, JWT_SECRET_BYTES, algorithm=JWT_ALGORITHM)


def credenciais(token: str) -> HTTPAuthorizationCredentials:
    return HTTPAuthorizationCredentials(scheme="Bearer", credentials=token)


# --------------------------------------------------------------- jwt_handler


def test_token_valido_devolve_claims():
    claims = decodificar_token(montar_token())

    assert claims["sub"] == "7"
    assert claims["iss"] == JWT_ISSUER
    assert claims["profile_type"] == "HOUSEHOLD"


def test_assinatura_de_outro_segredo_e_recusada():
    token = jwt.encode(
        {
            "iss": JWT_ISSUER,
            "sub": "7",
            "exp": datetime.now(timezone.utc) + timedelta(minutes=15),
        },
        b"x" * 32,
        algorithm=JWT_ALGORITHM,
    )

    with pytest.raises(TokenInvalido):
        decodificar_token(token)


def test_token_expirado_e_recusado():
    vencido = datetime.now(timezone.utc) - timedelta(minutes=1)

    with pytest.raises(TokenInvalido, match="expirado"):
        decodificar_token(montar_token(exp=vencido))


def test_outro_emissor_e_recusado():
    with pytest.raises(TokenInvalido, match="origem"):
        decodificar_token(montar_token(iss="outro-emissor"))


def test_token_sem_sub_e_recusado():
    agora = datetime.now(timezone.utc)
    token = jwt.encode(
        {"iss": JWT_ISSUER, "exp": agora + timedelta(minutes=15)},
        JWT_SECRET_BYTES,
        algorithm=JWT_ALGORITHM,
    )

    with pytest.raises(TokenInvalido):
        decodificar_token(token)


def test_token_sem_exp_e_recusado():
    token = jwt.encode(
        {"iss": JWT_ISSUER, "sub": "7"},
        JWT_SECRET_BYTES,
        algorithm=JWT_ALGORITHM,
    )

    with pytest.raises(TokenInvalido):
        decodificar_token(token)


def test_lixo_nao_derruba_o_validador():
    """Entrada que nem é JWT tem que virar TokenInvalido, não exceção crua."""
    with pytest.raises(TokenInvalido):
        decodificar_token("nao-e-um-jwt")


# -------------------------------------------------------------- dependencies


def test_dependencia_aceita_token_assinado():
    usuario = get_current_user(
        credentials=credenciais(montar_token()),
        api_key="qualquer",
    )

    assert usuario["user_id"] == 7
    assert usuario["teste"] is False
    assert usuario["claims"]["email"] == "teste@ceris.app"


def test_dependencia_recusa_sem_token():
    with pytest.raises(HTTPException) as erro:
        get_current_user(credentials=None, api_key="qualquer")

    assert erro.value.status_code == 401


def test_dependencia_recusa_assinatura_invalida():
    adulterado = montar_token()[:-4] + "aaaa"

    with pytest.raises(HTTPException) as erro:
        get_current_user(credentials=credenciais(adulterado), api_key="qualquer")

    assert erro.value.status_code == 401
    assert erro.value.headers["WWW-Authenticate"] == "Bearer"


@pytest.mark.skipif(not VALID_TOKENS, reason="VALID_TOKENS vazio")
def test_token_de_teste_do_env_passa():
    token = next(iter(VALID_TOKENS))

    usuario = get_current_user(credentials=credenciais(token), api_key="qualquer")

    assert usuario["teste"] is True


# ------------------------------------------------------------------- api key


def test_api_key_do_env_e_carregada():
    """
    Regressão: a config lia VALID_API_KEYS e o .env definia API_KEY. O conjunto
    ficava vazio e toda requisição tomava 401 "Invalid API key".
    """
    assert VALID_API_KEYS, "nenhuma API key carregada do ambiente"


def test_api_key_valida_passa():
    chave = next(iter(VALID_API_KEYS))

    assert validate_api_key(chave) == chave


def test_api_key_errada_e_recusada():
    with pytest.raises(HTTPException) as erro:
        validate_api_key("chave-que-nao-existe")

    assert erro.value.status_code == 401


def test_api_key_ausente_e_recusada():
    with pytest.raises(HTTPException) as erro:
        validate_api_key(None)

    assert erro.value.status_code == 401


# --------------------------------------------------------------------- redis


def test_redis_saiu_do_projeto():
    """O pacote de auth não pode mais depender de Redis."""
    with pytest.raises(ImportError):
        import app.auth.redis_client  # noqa: F401

    with pytest.raises(ImportError):
        import app.auth.session_validator  # noqa: F401
