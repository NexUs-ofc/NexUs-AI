"""Entrypoint para a Discloud (GitHub Integration).

A Discloud executa `python MAIN` por padrão. O serviço FastAPI mora em
`app/app.py` e só expõe o objeto `app`, sem bloco `__main__`, então um
`python app/app.py` subiria e sairia sem servir nada.

Este shim não altera nada do código existente: só inicia o mesmo objeto
que o Dockerfile já usa (`uvicorn app.app:app`), na porta/host que a
Discloud exige para `TYPE=site` (proxy -> 0.0.0.0:8080).
"""

import uvicorn

if __name__ == "__main__":
    uvicorn.run("app.app:app", host="0.0.0.0", port=8080)
