"""Login, senhas e permissões."""
import hashlib
import hmac
import secrets
import time

import streamlit as st

import db

ITERACOES = 240_000
PERFIS = {"gestor": "Gestor", "compras": "Compras / Administrativo", "gerente": "Gerente de unidade"}


# ---------------------------------------------------------------------
# Senhas (PBKDF2-SHA256 com sal; nunca guardamos a senha em texto)
# ---------------------------------------------------------------------
def gerar_hash(senha: str) -> str:
    sal = secrets.token_hex(16)
    h = hashlib.pbkdf2_hmac("sha256", senha.encode(), bytes.fromhex(sal), ITERACOES).hex()
    return f"pbkdf2${ITERACOES}${sal}${h}"


def conferir_senha(senha: str, armazenado: str) -> bool:
    try:
        _, it, sal, h = armazenado.split("$")
        calc = hashlib.pbkdf2_hmac("sha256", senha.encode(), bytes.fromhex(sal), int(it)).hex()
        return hmac.compare_digest(calc, h)
    except Exception:
        return False


def senha_valida(senha: str) -> str | None:
    """Devolve a mensagem de erro, ou None se a senha for aceitável."""
    if len(senha) < 8:
        return "A senha precisa ter pelo menos 8 caracteres."
    if senha.isdigit() or senha.isalpha():
        return "Use letras e números na senha."
    return None


# ---------------------------------------------------------------------
# Sessão
# ---------------------------------------------------------------------
def usuario_atual() -> dict | None:
    return st.session_state.get("usuario")


def tem_perfil(*perfis: str) -> bool:
    u = usuario_atual()
    return bool(u) and u["perfil"] in perfis


def sair():
    st.session_state.clear()
    st.rerun()


def _carregar_usuario(login: str):
    return db.query_one(
        """select u.id, u.nome, u.login, u.senha_hash, u.perfil, u.local_id,
                  u.trocar_senha, u.ativo, l.nome as local_nome
           from usuarios u left join locais l on l.id = u.local_id
           where lower(u.login) = lower(:login)""",
        {"login": login.strip()},
    )


# ---------------------------------------------------------------------
# Telas
# ---------------------------------------------------------------------
def tela_primeiro_acesso():
    """Aparece só enquanto não existe nenhum usuário: cria o 1º gestor."""
    st.title("Configuração inicial")
    st.info("Nenhum usuário cadastrado ainda. Crie o primeiro **Gestor** do sistema.")
    with st.form("primeiro_gestor"):
        nome = st.text_input("Nome completo")
        login = st.text_input("Login (ex.: gleysson)")
        s1 = st.text_input("Senha", type="password")
        s2 = st.text_input("Repita a senha", type="password")
        ok = st.form_submit_button("Criar gestor", type="primary")
    if ok:
        erro = senha_valida(s1)
        if not nome.strip() or not login.strip():
            st.error("Preencha nome e login.")
        elif s1 != s2:
            st.error("As senhas não conferem.")
        elif erro:
            st.error(erro)
        else:
            # confere de novo para evitar dois cadastros simultâneos
            if db.query_one("select 1 from usuarios limit 1"):
                st.error("Já existe usuário cadastrado. Recarregue a página.")
                return
            db.execute(
                """insert into usuarios (nome, login, senha_hash, perfil, trocar_senha)
                   values (:n, :l, :h, 'gestor', false)""",
                {"n": nome.strip(), "l": login.strip().lower(), "h": gerar_hash(s1)},
            )
            st.success("Gestor criado. Faça o login.")
            time.sleep(1.5)
            st.rerun()


def tela_login():
    col = st.columns([1, 2, 1])[1]
    with col:
        st.markdown("<div class='login-titulo'>MANTA · Gestão Operacional</div>",
                    unsafe_allow_html=True)
        with st.form("login"):
            login = st.text_input("Login")
            senha = st.text_input("Senha", type="password")
            ok = st.form_submit_button("Entrar", type="primary", width="stretch")
        if ok:
            u = _carregar_usuario(login) if login else None
            if u and u["ativo"] and conferir_senha(senha, u["senha_hash"]):
                dados = dict(u)
                dados.pop("senha_hash", None)
                st.session_state["usuario"] = dados
                db.registrar("login", "usuarios", u["id"])
                st.rerun()
            else:
                time.sleep(1.5)  # dificulta tentativa e erro
                st.error("Login ou senha incorretos.")


def tela_trocar_senha(obrigatoria: bool = False):
    u = usuario_atual()
    if obrigatoria:
        st.warning("Primeiro acesso: defina uma nova senha para continuar.")
    with st.form("trocar_senha"):
        atual = st.text_input("Senha atual", type="password")
        s1 = st.text_input("Nova senha", type="password")
        s2 = st.text_input("Repita a nova senha", type="password")
        ok = st.form_submit_button("Salvar nova senha", type="primary")
    if ok:
        reg = _carregar_usuario(u["login"])
        erro = senha_valida(s1)
        if not reg or not conferir_senha(atual, reg["senha_hash"]):
            st.error("Senha atual incorreta.")
        elif s1 != s2:
            st.error("As senhas novas não conferem.")
        elif erro:
            st.error(erro)
        else:
            db.execute(
                "update usuarios set senha_hash = :h, trocar_senha = false where id = :id",
                {"h": gerar_hash(s1), "id": u["id"]},
            )
            db.registrar("troca de senha", "usuarios", u["id"])
            st.session_state["usuario"]["trocar_senha"] = False
            st.success("Senha alterada.")
            time.sleep(1)
            st.rerun()
