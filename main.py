"""Entrypoint para a Discloud (GitHub Integration).

A Discloud executa `python MAIN` por padrão. O serviço FastAPI mora em
`app/app.py` e só expõe o objeto `app`, sem bloco `__main__`, então um
`python app/app.py` subiria e sairia sem servir nada.

Este shim não altera nada do código existente: só inicia o mesmo objeto
que o Dockerfile já usa (`uvicorn app.app:app`), na porta/host que a
Discloud exige para `TYPE=site` (proxy -> 0.0.0.0:8080).

O `rapidocr-onnxruntime` arrasta o `opencv-python` (variante com GUI),
que precisa de libGL — e a imagem da Discloud não tem. No runtime o app
roda como usuário sem permissão de escrita no site-packages global, e o
"user site" que o pip cria como fallback não entra no sys.path (ele é
montado no boot, antes de a pasta existir). Por isso a troca para o
`headless` é feita num diretório próprio dentro do HOME, inserido na
frente do sys.path: primeiro tenta importar o cv2 (se já resolve, não
gasta nada); se falhar, instala o headless nesse diretório e importa
de novo, antes de o uvicorn carregar a aplicação.
"""

import importlib
import shutil
import subprocess
import sys
from pathlib import Path

_PYPILIBS = Path(__file__).resolve().parent / ".pylibs"


def _garantir_cv2_headless() -> None:
    if str(_PYPILIBS) not in sys.path:
        sys.path.insert(0, str(_PYPILIBS))

    try:
        import cv2  # noqa: F401

        return
    except ImportError:
        pass

    if _PYPILIBS.exists():
        shutil.rmtree(_PYPILIBS)

    subprocess.run(
        [
            sys.executable,
            "-m",
            "pip",
            "install",
            "--no-cache-dir",
            "--target",
            str(_PYPILIBS),
            "opencv-python-headless",
        ],
        check=False,
    )
    importlib.invalidate_caches()


if __name__ == "__main__":
    _garantir_cv2_headless()
    import uvicorn

    uvicorn.run("app.app:app", host="0.0.0.0", port=8080)
