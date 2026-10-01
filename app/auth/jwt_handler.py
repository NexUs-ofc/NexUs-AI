"""
Validação do JWT emitido pelo microsserviço de autenticação.

Este serviço é resource server: ele só verifica tokens, nunca emite. Quem emite
é o Auth, com HS256 sobre o segredo compartilhado.

O formato validado aqui é o que o JwtTokenService do Auth produz:

    iss          : nexus-auth
    sub          : id do perfil, como string
    exp / iat    : validade
    jti          : id do token
    profile_type : HOUSEHOLD | COMPANY | ...
    email        : e-mail do perfil

A verificação é a mesma da API Core (NimbusJwtDecoder com a SecretKey mais
JwtValidators.createDefaultWithIssuer): assinatura, expiração e emissor.
"""

import jwt

from ..config import JWT_ALGORITHM, JWT_ISSUER, JWT_SECRET_BYTES


class TokenInvalido(Exception):
    """Token ausente, malformado, expirado, de outro emissor ou mal assinado."""


def decodificar_token(token: str) -> dict:
    """
    Devolve as claims do token ou levanta TokenInvalido.

    O "sub" é exigido na própria decodificação: sem ele não há como saber de
    quem é a requisição, e um token assim não serve para nada aqui.
    """
    try:
        return jwt.decode(
            token,
            JWT_SECRET_BYTES,
            algorithms=[JWT_ALGORITHM],
            issuer=JWT_ISSUER,
            options={"require": ["exp", "sub"]},
        )
    except jwt.ExpiredSignatureError as erro:
        raise TokenInvalido("Token expirado") from erro
    except jwt.InvalidIssuerError as erro:
        raise TokenInvalido("Token emitido por outra origem") from erro
    except jwt.InvalidSignatureError as erro:
        raise TokenInvalido("Assinatura inválida") from erro
    except jwt.InvalidTokenError as erro:
        raise TokenInvalido("Token inválido") from erro
