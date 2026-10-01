import base64
import binascii
import os
import re

from dotenv import load_dotenv

load_dotenv()
 
MONGODB_URI = os.getenv("MONGODB_URI")
PGSQL_URL = os.getenv("PGSQL_URL")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
GROQ_API_KEY = os.getenv("GROQ_API_KEY")
QDRANT_DATABASE_URL = os.getenv("QDRANT_DATABASE_URL")
QDRANT_API_KEY = os.getenv("QDRANT_API_KEY")
DOC_FILE_PATH = os.getenv("DOC_FILE_PATH")
FAQ_FILE_PATH = os.getenv("FAQ_FILE_PATH")
TRACING_API_KEY = os.getenv("TRACING_API_KEY")

JWT_SECRET_KEY = os.getenv("JWT_SECRET_KEY")

if not JWT_SECRET_KEY:
    raise RuntimeError(
        "JWT_SECRET_KEY não definida. Configure a mesma chave usada pelo "
        "microsserviço de autenticação; sem ela os tokens não podem ser validados."
    )

def _bytes_do_segredo(valor: str) -> bytes:
    """
    Converte o segredo configurado nos bytes da chave HMAC.

    O Auth assina com Base64 decodificado para bytes (JWT_SECRET_BASE64 ->
    SecretKeySpec), e a Core valida igual. O que importa dos dois lados são os
    mesmos bytes, não a representação.

    Aceita as duas formas porque este .env guarda o segredo em hex enquanto o
    Auth guarda em Base64. A ordem do teste não é detalhe: 64 caracteres hex
    também são Base64 válido, e decodificar como Base64 devolveria 48 bytes
    errados sem erro nenhum — assinatura nunca fecharia, sem nada no log.
    """
    if re.fullmatch(r"[0-9a-fA-F]{64}", valor):
        return bytes.fromhex(valor)

    try:
        return base64.b64decode(valor, validate=True)
    except (binascii.Error, ValueError) as erro:
        raise RuntimeError(
            "JWT_SECRET_KEY não é hex de 64 caracteres nem Base64 válido. "
            "Use os mesmos bytes de JWT_SECRET_BASE64 do microsserviço de "
            "autenticação."
        ) from erro


JWT_SECRET_BYTES = _bytes_do_segredo(JWT_SECRET_KEY)

# Mesma checagem que o Auth faz ao montar a SecretKeySpec.
if len(JWT_SECRET_BYTES) < 32:
    raise RuntimeError(
        "JWT_SECRET_KEY deve representar ao menos 32 bytes depois de decodificada."
    )

JWT_ALGORITHM = os.getenv("JWT_ALGORITHM", "HS256")

# O Auth põe isto no claim "iss"; a Core valida com createDefaultWithIssuer.
JWT_ISSUER = os.getenv("JWT_ISSUER", "nexus-auth")

API_KEY_HEADER = os.getenv("API_KEY_HEADER", "X-API-Key")

# Tokens de teste aceitos sem verificação de assinatura. Existe para
# desenvolvimento e para a suíte de testes; em produção fica vazio.
VALID_TOKENS = {
    token.strip() for token in os.getenv("VALID_TOKENS", "").split(",") if token.strip()
}
# Lida de API_KEY, o mesmo nome que o Auth (app.api-key=${API_KEY}) e o mobile
# usam. Antes isto lia VALID_API_KEYS, que nenhum .env definia: o conjunto saía
# vazio e o validador recusava toda chave com "Invalid API key", como se a
# chave estivesse errada.
#
# Aceita lista separada por vírgula para dar rotação sem derrubar o serviço.
VALID_API_KEYS = {
    key.strip() for key in os.getenv("API_KEY", "").split(",") if key.strip()
}

# Sem chave configurada, toda requisição tomaria 401 dizendo que a chave é
# inválida. Melhor não subir do que subir recusando tudo em silêncio.
if not VALID_API_KEYS:
    raise RuntimeError(
        "API_KEY não definida. Sem ela nenhuma requisição é aceita, e o erro "
        "aparece como 'Invalid API key' em vez de falta de configuração."
    )

LANGCHAIN_TRACING_V2 = os.getenv("LANGCHAIN_TRACING_V2", "true")
LANGCHAIN_API_KEY = os.getenv("LANGCHAIN_API_KEY")
LANGCHAIN_PROJECT = os.getenv("LANGCHAIN_PROJECT", "ceris-ms-ia")
LANGSMITH_WORKSPACE_ID = os.getenv("LANGSMITH_WORKSPACE_ID")

os.environ["LANGCHAIN_TRACING_V2"] = LANGCHAIN_TRACING_V2
os.environ["LANGCHAIN_PROJECT"] = LANGCHAIN_PROJECT

if LANGCHAIN_API_KEY:
    os.environ["LANGCHAIN_API_KEY"] = LANGCHAIN_API_KEY

if LANGSMITH_WORKSPACE_ID:
    os.environ["LANGSMITH_WORKSPACE_ID"] = LANGSMITH_WORKSPACE_ID

TAVILY_API_KEY = os.getenv("TAVILY_API_KEY")