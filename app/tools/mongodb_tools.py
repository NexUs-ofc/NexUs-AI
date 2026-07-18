from langchain.tools import tool
from dotenv import load_dotenv
import os
from datetime import datetime
from ..repository.entities.mongodb.event import Event
from ..repository.mongodb.events import EventsRepository

events_repository = EventsRepository()

@tool("add_event")
def add_event(
    titulo:str,
    descricao:str,
    data:datetime,
    duracao:int,
    local:str,
    qtd_pessoas:int
) -> Event:
    """
    Insere um evento no banco de dados, campos obrigatórios:
        - titulo: Texto intuitivo sobre o evento;
        - descricao: Texto explicitando informações do evento, deve conter tipo do evento obrigatóriamente;
        - data: Data do evento em Datetime;
        - duracao: Duração do evento em minutos;
        - local: Localização do evento;
        - qtd_pessoas: Total de participantes do evento;
    """

    evento = Event(
        title=titulo,
        description=descricao,
        date=data,
        duration=duracao,
        local=local,
        qtd_people=qtd_pessoas,
    )

    return events_repository.create_event(event=evento)



@tool("get_events")
def get_events(
    inicio: datetime = None,
    fim: datetime = None,
    tipo: str = None,
    qtd_min: int = None,
    titulo_receitas: list[str] = None,
) -> list[Event]:
    """
    Busca eventos no banco de dados com base ou não nos seguintes filtros opcionais fornecidos:
        - inicio: Data mínima de intervalo que evento pode estar;
        - fim: Data máxima de intervalo que evento pode estar;
        - tipo: Tipo de evento que será validado na descrição (ex: Churrasco, festa, jantar, etc...);
        - qtd_min: Quantidade mínima de pessoas que evento deve ter;
        - titulo_receitas: Receitas que o evento deve ter;
    """

    return events_repository.get_events(
        start=inicio,
        end=fim,
        type=tipo,
        qtd_min=qtd_min,
        recipes_titles=titulo_receitas
    )

