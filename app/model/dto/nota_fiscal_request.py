from pydantic import BaseModel


class NotaFiscalRequest(BaseModel):
    imagem_base64: str
