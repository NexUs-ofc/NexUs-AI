"""Entrypoint para a Discloud (GitHub Integration).

A Discloud executa `python MAIN` por padrão. O serviço FastAPI mora em
`app/app.py` e só expõe o objeto `app`, sem bloco `__main__`, então um
`python app/app.py` subiria e sairia sem servir nada.

Este shim não altera nada do código existente: só inicia o mesmo objeto
que o Dockerfile já usa (`uvicorn app.app:app`), na porta/host que a
Discloud exige para `TYPE=site` (proxy -> 0.0.0.0:8080).

O `rapidocr-onnxruntime` arrasta o `opencv-python` (variante com GUI),
que precisa de libGL — e a imagem da Discloud não tem. O Dockerfile
contorna isso trocando pelo `headless`; como nem o `APT` nem o `BUILD`
da Discloud surtiram efeito no container, a mesma troca é replicada
aqui, em Python puro: se o `import cv2` falhar, o pip desinstala o GUI
e reinstala o headless ANTES de o uvicorn importar a aplicação. Se o
cv2 importar de primeira (BUILD funcionou, por exemplo), não gasta
nada: volta direto.
"""

import subprocess
import sys


def _trocar_opencv_se_necessario() -> None:
    try:
        import cv2  # noqa: F401

        return
    except ImportError:
        pass

    subprocess.run(
        [sys.executable, "-m", "pip", "uninstall", "-y", "opencv-python"],
        check=False,
    )
    subprocess.run(
        [
            sys.executable,
            "-m",
            "pip",
            "install",
            "--no-cache-dir",
            "--force-reinstall",
            "--no-deps",
            "opencv-python-headless",
        ],
        check=False,
    )


if __name__ == "__main__":
    _trocar_opencv_se_necessario()
    import uvicorn

    uvicorn.run("app.app:app", host="0.0.0.0", port=8080)
