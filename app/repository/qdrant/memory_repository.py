import uuid
from datetime import datetime

from qdrant_client import models

from ...controller.config import logging
from .config import SESSION_SUMMARY_COLLECTION, client, gerar_embedding

logger = logging.getLogger(__name__)


class MemoryRepository:
    @staticmethod
    def _ponto_id(session_id: str) -> str:
        return str(uuid.uuid5(uuid.NAMESPACE_OID, session_id))

    @staticmethod
    def salvar_resumo(
        session_id: str,
        account_id: int,
        resumo: str,
        created_at: datetime,
    ) -> bool:
        """
        Grava o resumo de uma sessão encerrada na collection de memória.
        """

        try:
            logger.info(f"Salvando resumo da sessão {session_id}")

            client.upsert(
                collection_name=SESSION_SUMMARY_COLLECTION,
                points=[
                    models.PointStruct(
                        id=MemoryRepository._ponto_id(session_id),
                        vector=gerar_embedding(resumo),
                        payload={
                            "user_id": str(account_id),
                            "session_id": session_id,
                            "resumo": resumo,
                            "created_at": created_at.isoformat(),
                        },
                    )
                ],
            )

            logger.info(f"Resumo da sessão {session_id} salvo com sucesso")

            return True

        except Exception:
            logger.exception(f"Erro ao salvar resumo da sessão {session_id}")
            return False

    @staticmethod
    def buscar_resumos(
        account_id: int,
        busca: str,
        limite: int = 5,
    ) -> list[dict]:
        """
        Busca os resumos de conversas anteriores mais próximos semanticamente
        da consulta, restritos ao usuário informado.
        """

        try:
            logger.info(f"Buscando resumos anteriores da conta {account_id}")

            resultados = client.query_points(
                collection_name=SESSION_SUMMARY_COLLECTION,
                query=gerar_embedding(busca),
                query_filter=models.Filter(
                    must=[
                        models.FieldCondition(
                            key="user_id",
                            match=models.MatchValue(value=str(account_id)),
                        )
                    ]
                ),
                limit=limite,
            )

            resumos = [
                {
                    "session_id": ponto.payload.get("session_id", ""),
                    "created_at": ponto.payload.get("created_at", ""),
                    "resumo": ponto.payload.get("resumo", ""),
                }
                for ponto in resultados.points
                if ponto.payload and ponto.payload.get("resumo")
            ]

            logger.info(f"Conta {account_id} tem {len(resumos)} resumos relevantes")

            return resumos

        except Exception:
            logger.exception(f"Erro ao buscar resumos da conta {account_id}")
            return []
