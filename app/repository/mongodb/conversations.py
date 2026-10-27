from datetime import UTC, datetime, timedelta

from bson import ObjectId
from pymongo import MongoClient
from pymongo.errors import PyMongoError

from ...config import MONGODB_URI
from ...controller.config import logging

logger = logging.getLogger(__name__)

# Quanto tempo depois da ultima mensagem uma sessao sem session_id ainda e
# continuada (ver sessao_recente).
JANELA_SESSAO = timedelta(hours=2)

class ConversationsRepository:
    client = MongoClient(MONGODB_URI)
    db = client.get_database("db_ceris")
    conversations_collection = db.get_collection("conversations")

    @staticmethod
    def create_session(account_id: int) -> str:
        try:
            result = ConversationsRepository.conversations_collection.insert_one({
                "account_id": account_id,
                "historico": [],
                "created_at": datetime.now(UTC),
                "updated_at": datetime.now(UTC),
            })

            logger.info(f"Sessão criada: {result.inserted_id}")

            return str(result.inserted_id)

        except PyMongoError:
            logger.exception("Erro ao criar sessão")
            return None

    @staticmethod
    def sessao_recente(account_id: int) -> str | None:
        """
        Ultima sessao aberta da conta, com mensagem dentro da JANELA_SESSAO.

        O app (e o Swagger, que manda "string") nem sempre devolve o
        session_id. Sem isto cada mensagem abria uma sessao nova e o chat
        esquecia a anterior: "salva essa receita" nao achava receita nenhuma.
        """

        try:
            doc = ConversationsRepository.conversations_collection.find_one(
                {
                    "account_id": account_id,
                    "ended_at": None,
                    "updated_at": {"$gte": datetime.now(UTC) - JANELA_SESSAO},
                },
                {"_id": 1},
                sort=[("updated_at", -1)],
            )
        except PyMongoError:
            logger.exception(f"Erro ao buscar sessao recente da conta {account_id}")
            return None

        if doc is None:
            return None

        logger.info(f"Continuando a sessao {doc['_id']} da conta {account_id}")

        return str(doc["_id"])

    @staticmethod
    def pertence_conta(session_id: str, account_id: int) -> bool:
        """Autoriza a sessao sem carregar seu historico."""
        if not ObjectId.is_valid(session_id):
            return False
        try:
            return ConversationsRepository.conversations_collection.find_one(
                {"_id": ObjectId(session_id), "account_id": account_id},
                {"_id": 1},
            ) is not None
        except PyMongoError:
            logger.exception("Erro ao verificar propriedade da sessao")
            return False

    @staticmethod
    def get_historico(session_id: str, account_id: int) -> list[dict]:
        if not ObjectId.is_valid(session_id):
            return []

        try:
            logger.info(f"Buscando histórico da sessão {session_id}")

            doc = ConversationsRepository.conversations_collection.find_one(
                {"_id": ObjectId(session_id), "account_id": account_id}
            )

            if doc is None:
                logger.info(f"Sessão {session_id} não encontrada")
                return []

            historico = doc.get("historico", [])

            logger.info(f"Histórico da sessão {session_id} carregado, {len(historico)} mensagens")

            return historico

        except PyMongoError:
            logger.exception("Erro ao buscar histórico")
            return []

    @staticmethod
    def sessao_ativa(session_id: str, account_id: int) -> bool:
        # Id que nao e ObjectId (ex.: o "string" de exemplo do Swagger) nao e
        # sessao nenhuma: o chat abre uma nova em vez de devolver 500.
        if not ObjectId.is_valid(session_id):
            logger.info(f"session_id invalido ({session_id!r}), abrindo sessao nova")
            return False

        try:
            logger.info(f"Verificando se a sessão {session_id} está ativa")

            doc = ConversationsRepository.conversations_collection.find_one(
                {"_id": ObjectId(session_id), "account_id": account_id}
            )

            ativa = doc is not None and doc.get("ended_at") is None

            logger.info(f"Sessão {session_id} ativa={ativa}")

            return ativa

        except PyMongoError:
            logger.exception(f"Erro ao verificar sessão {session_id}")
            return False

    @staticmethod
    def sessao_encerrada(session_id: str, account_id: int) -> bool:
        if not ObjectId.is_valid(session_id):
            return False
        try:
            doc = ConversationsRepository.conversations_collection.find_one(
                {"_id": ObjectId(session_id), "account_id": account_id},
                {"ended_at": 1},
            )
            return doc is not None and doc.get("ended_at") is not None
        except PyMongoError:
            logger.exception("Erro ao consultar estado de encerramento da sessão")
            return False

    @staticmethod
    def end_session(session_id: str, account_id: int) -> bool:
        if not ObjectId.is_valid(session_id):
            return False

        try:
            logger.info(f"Finalizando sessão {session_id}")

            result = ConversationsRepository.conversations_collection.update_one(
                {"_id": ObjectId(session_id), "account_id": account_id},
                {
                    "$set": {
                        "ended_at": datetime.now(UTC),
                        "status": "closed",
                    }
                }
            )

            logger.info(f"Sessão {session_id} finalizada, matched_count={result.matched_count}")

            return result.matched_count > 0

        except PyMongoError:
            logger.exception(f"Erro ao finalizar sessão {session_id}")
            return False

    @staticmethod
    def append_messages(session_id: str, user_msg: str, assistant_msg: str,
                        *, account_id: int, receita: dict | None = None, assunto: dict | None = None,
                        trace_id: str | None = None):
        if not ObjectId.is_valid(session_id):
            return
        try:
            logger.info(f"Salvando mensagens da sessão {session_id}")
            assistant = {"role": "assistant", "content": assistant_msg}
            if receita:
                assistant["receita"] = receita
            if assunto:
                assistant["assunto"] = assunto

            result = ConversationsRepository.conversations_collection.update_one(
                {"_id": ObjectId(session_id), "account_id": account_id},
                {
                    "$push": {
                        "historico": {
                            "$each": [
                                {"role": "user", "content": user_msg},
                                assistant,
                            ]
                        }
                    },
                    "$set": {"updated_at": datetime.now(UTC),
                              **({"last_trace_id": trace_id} if trace_id else {})}
                }
            )

            logger.info(f"Mensagens da sessão {session_id} salvas, matched_count={result.matched_count}")

        except PyMongoError:
            logger.exception("Erro ao salvar mensagens")

    @staticmethod
    def submit_section_feedback(session_id: str, account_id: int, rating: int, comment: str | None):
        if not ObjectId.is_valid(session_id):
            return "missing", None
        try:
            query = {"_id": ObjectId(session_id), "account_id": account_id,
                     "ended_at": {"$ne": None}, "section_feedback": {"$exists": False}}
            doc = ConversationsRepository.conversations_collection.find_one(
                {"_id": ObjectId(session_id), "account_id": account_id},
                {"ended_at": 1, "last_trace_id": 1, "section_feedback": 1},
            )
            if doc is None:
                return "missing", None
            if doc.get("ended_at") is None:
                return "open", None
            if doc.get("section_feedback") is not None:
                return "duplicate", None
            result = ConversationsRepository.conversations_collection.update_one(
                query, {"$set": {"section_feedback": {
                    "rating": rating, "comment": comment, "status": "pending",
                    "created_at": datetime.now(UTC),
                }}},
            )
            return ("claimed", doc.get("last_trace_id")) if result.matched_count else ("duplicate", None)
        except PyMongoError:
            logger.exception("Erro ao persistir avaliação da sessão")
            return "unavailable", None
