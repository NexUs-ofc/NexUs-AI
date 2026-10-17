from app.controller.chat import _casa_do_token


def test_token_real_ignora_a_casa_informada_no_pedido():
    # Pedir a casa 1 com o token da casa 3 nao pode dar acesso a casa 1.
    assert _casa_do_token({"user_id": 3}, 1) == 3


def test_token_real_sem_casa_no_pedido_usa_o_token():
    assert _casa_do_token({"user_id": 3}, None) == 3


def test_token_de_desenvolvimento_usa_a_casa_informada():
    assert _casa_do_token({"user_id": 0}, 1) == 1


def test_token_de_desenvolvimento_sem_casa_e_recusado():
    import pytest
    from fastapi import HTTPException

    # Antes caia no default 1 em silencio.
    with pytest.raises(HTTPException) as erro:
        _casa_do_token({"user_id": 0}, None)

    assert erro.value.status_code == 422
