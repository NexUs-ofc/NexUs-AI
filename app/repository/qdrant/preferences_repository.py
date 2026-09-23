import uuid
from datetime import datetime, timezone

from qdrant_client import models

from ...controller.config import logging
from .config import PROFILE_PREFERENCES_COLLECTION, client, gerar_embedding

logger = logging.getLogger(__name__)


class PreferencesRepository:
    @staticmethod
    def _ponto_id(account_id: int, preferencia: str) -> str:
        semente = f"{account_id}:{preferencia.strip().lower()}"

        return str(uuid.uuid5(uuid.NAMESPACE_OID, semente))

    @staticmethod
    def salvar_preferencia(account_id: int, preferencia: str) -> bool:
        """
        Grava uma preferência em texto livre do usuário.

        Reenviar a mesma preferência não duplica o ponto.
        """

        texto = preferencia.strip()

        if not texto:
            return False

        try:
            logger.info(f"Salvando preferência da conta {account_id}")

            client.upsert(
                collection_name=PROFILE_PREFERENCES_COLLECTION,
                points=[
                    models.PointStruct(
                        id=PreferencesRepository._ponto_id(account_id, texto),
                        vector=gerar_embedding(texto),
                        payload={
                            "user_id": str(account_id),
                            "preferencia": texto,
                            "created_at": datetime.now(timezone.utc).isoformat(),
                        },
                    )
                ],
            )

            logger.info(f"Preferência da conta {account_id} salva com sucesso")

            return True

        except Exception:
            logger.exception(f"Erro ao salvar preferência da conta {account_id}")
            return False

    @staticmethod
    def buscar_preferencias(
        account_id: int,
        busca: str,
        limite: int = 5,
    ) -> list[str]:
        """
        Busca as preferências do usuário mais próximas semanticamente
        da consulta informada.
        """

        try:
            logger.info(f"Buscando preferências da conta {account_id}")

            resultados = client.query_points(
                collection_name=PROFILE_PREFERENCES_COLLECTION,
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

            preferencias = [
                ponto.payload["preferencia"]
                for ponto in resultados.points
                if ponto.payload and ponto.payload.get("preferencia")
            ]

            logger.info(
                f"Conta {account_id} tem {len(preferencias)} preferências relevantes"
            )

            return preferencias

        except Exception:
            logger.exception(f"Erro ao buscar preferências da conta {account_id}")
            return []

    @staticmethod
    def remover_preferencias(account_id: int) -> bool:
        """
        Remove todas as preferências cadastradas do usuário.
        """

        try:
            logger.info(f"Removendo preferências da conta {account_id}")

            client.delete(
                collection_name=PROFILE_PREFERENCES_COLLECTION,
                points_selector=models.FilterSelector(
                    filter=models.Filter(
                        must=[
                            models.FieldCondition(
                                key="user_id",
                                match=models.MatchValue(value=str(account_id)),
                            )
                        ]
                    )
                ),
            )

            logger.info(f"Preferências da conta {account_id} removidas")

            return True

        except Exception:
            logger.exception(f"Erro ao remover preferências da conta {account_id}")
            return False

    @staticmethod
    def listar_preferencias(account_id: int, limite: int = 50) -> list[str]:
        """
        Lista todas as preferências cadastradas do usuário, sem busca semântica.
        """

        try:
            pontos, _ = client.scroll(
                collection_name=PROFILE_PREFERENCES_COLLECTION,
                scroll_filter=models.Filter(
                    must=[
                        models.FieldCondition(
                            key="user_id",
                            match=models.MatchValue(value=str(account_id)),
                        )
                    ]
                ),
                limit=limite,
            )

            return [
                ponto.payload["preferencia"]
                for ponto in pontos
                if ponto.payload and ponto.payload.get("preferencia")
            ]

        except Exception:
            logger.exception(f"Erro ao listar preferências da conta {account_id}")
            return []
