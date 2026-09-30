from pydantic import BaseModel, Field


class NotaFiscalRequest(BaseModel):
    # Aceita base64 puro ou data URL ("data:image/png;base64,...").
    # Limite de ~10 MB de imagem (base64 infla ~33%).
    imagem_base64: str = Field(..., min_length=100, max_length=14_000_000)
