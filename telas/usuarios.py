"""Gestão de usuários (somente Gestor)."""
import secrets
import string

import streamlit as st
from sqlalchemy.exc import IntegrityError

import auth
import db
import ui


def _senha_temporaria() -> str:
    alfabeto = string.ascii_letters + string.digits
    while True:
        s = "".join(secrets.choice(alfabeto) for _ in range(10))
        if any(c.isdigit() for c in s) and any(c.isalpha() for c in s):
            return s


def render():
    if not auth.tem_perfil("gestor"):
        ui.sem_permissao()
    st.title("Usuários")

    df = db.query(
        """select u.id, u.nome, u.login, u.perfil, l.nome as unidade, u.ativo, u.trocar_senha
           from usuarios u left join locais l on l.id = u.local_id order by u.nome"""
    )
    st.dataframe(
        df.assign(perfil=df["perfil"].map(auth.PERFIS),
                  ativo=df["ativo"].map({True: "Ativo", False: "Inativo"}),
                  trocar_senha=df["trocar_senha"].map({True: "Pendente", False: "OK"}))
          .drop(columns=["id"]),
        hide_index=True, width="stretch",
        column_config={"nome": "Nome", "login": "Login", "perfil": "Perfil",
                       "unidade": "Unidade", "ativo": "Situação", "trocar_senha": "Troca de senha"},
    )
    st.caption("Gestor: acesso total · Compras: cadastros e operação de todas as unidades · "
               "Gerente: vê e solicita só para a própria unidade.")

    unidades = db.locais(incluir_central=False)
    perfis_lista = list(auth.PERFIS.keys())
    aba_novo, aba_editar = st.tabs(["Novo usuário", "Editar / redefinir senha"])

    with aba_novo:
        nome = st.text_input("Nome completo", key="unovo_nome")
        login = st.text_input("Login (sem espaços, ex.: ana.712)", key="unovo_login")
        perfil = st.selectbox("Perfil", perfis_lista, format_func=auth.PERFIS.get, key="unovo_perfil")
        unidade = None
        if perfil == "gerente":
            unidade = st.selectbox("Unidade do gerente", unidades["nome"].tolist(), key="unovo_un")
        if st.button("Criar usuário", type="primary", key="unovo_salvar"):
            lg = login.strip().lower()
            if not nome.strip() or not lg or " " in lg:
                st.error("Preencha nome e um login sem espaços.")
            else:
                senha = _senha_temporaria()
                local_id = (int(unidades.loc[unidades["nome"] == unidade, "id"].iloc[0])
                            if unidade else None)
                try:
                    r = db.execute(
                        """insert into usuarios (nome, login, senha_hash, perfil, local_id)
                           values (:n, :l, :h, :p, :u) returning id""",
                        {"n": nome.strip(), "l": lg, "h": auth.gerar_hash(senha),
                         "p": perfil, "u": local_id})
                    db.registrar("cadastro de usuário", "usuarios", r["id"], lg)
                    st.success("Usuário criado. Envie os dados abaixo **diretamente para a pessoa** "
                               "(eles não serão mostrados de novo). No 1º acesso ela troca a senha.")
                    st.code(f"Login: {lg}\nSenha temporária: {senha}", language=None)
                except IntegrityError:
                    st.error("Esse login já existe.")

    with aba_editar:
        if df.empty:
            return
        rotulos = (df["nome"] + " (" + df["login"] + ")").tolist()
        escolha = st.selectbox("Usuário", rotulos, key="uedit_sel")
        atual = df.iloc[rotulos.index(escolha)]
        k = f"usr_{int(atual['id'])}"
        eu = auth.usuario_atual()["id"] == int(atual["id"])

        perfil = st.selectbox("Perfil", perfis_lista, index=perfis_lista.index(atual["perfil"]),
                              format_func=auth.PERFIS.get, key=f"{k}_perfil", disabled=eu)
        unidade = None
        if perfil == "gerente":
            nomes = unidades["nome"].tolist()
            unidade = st.selectbox("Unidade do gerente", nomes,
                                   index=nomes.index(ui.valor(atual, "unidade")) if ui.valor(atual, "unidade") in nomes else 0,
                                   key=f"{k}_un")
        ativo = st.checkbox("Ativo", value=bool(atual["ativo"]), key=f"{k}_ativo", disabled=eu)
        if eu:
            st.caption("Você não pode alterar o próprio perfil nem se desativar.")

        c1, c2 = st.columns(2)
        with c1:
            if st.button("Salvar alterações", type="primary", key=f"{k}_salvar"):
                local_id = (int(unidades.loc[unidades["nome"] == unidade, "id"].iloc[0])
                            if unidade else None)
                db.execute("update usuarios set perfil = :p, local_id = :u, ativo = :a where id = :id",
                           {"p": perfil, "u": local_id, "a": ativo, "id": int(atual["id"])})
                db.registrar("edição de usuário", "usuarios", int(atual["id"]), atual["login"])
                st.success("Usuário atualizado.")
                st.rerun()
        with c2:
            if st.button("Redefinir senha", key=f"{k}_reset"):
                senha = _senha_temporaria()
                db.execute("update usuarios set senha_hash = :h, trocar_senha = true where id = :id",
                           {"h": auth.gerar_hash(senha), "id": int(atual["id"])})
                db.registrar("redefinição de senha", "usuarios", int(atual["id"]), atual["login"])
                st.success("Nova senha temporária (envie diretamente para a pessoa):")
                st.code(f"Login: {atual['login']}\nSenha temporária: {senha}", language=None)
