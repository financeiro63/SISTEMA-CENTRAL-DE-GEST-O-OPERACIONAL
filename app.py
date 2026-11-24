"""SISTEMA CENTRAL DE GESTÃO OPERACIONAL — MANTA
Arquivo principal: login, menu e navegação.
"""
import streamlit as st

st.set_page_config(page_title="Gestão Operacional · Manta", page_icon="🏊", layout="wide")

import auth  # noqa: E402
import db  # noqa: E402
import ui  # noqa: E402
from telas import backup, conta, dashboard, fornecedores, itens, notas, produtos, unidades, usuarios  # noqa: E402

ui.aplicar_estilo()

# ---- Conexão com o banco ---------------------------------------------
try:
    existe_usuario = db.query_one("select 1 as ok from usuarios limit 1") is not None
except Exception as erro:
    db.get_engine.clear()  # descarta a conexão antiga: o próximo F5 já lê os Secrets novos
    st.error("Não foi possível conectar ao banco de dados. Confira os Secrets do app "
             "(seção [database]) e se o schema.sql foi executado no Supabase.")
    with st.expander("Detalhe técnico"):
        st.code(type(erro).__name__ + ": " + str(erro)[:500])
    st.stop()

# ---- Login -------------------------------------------------------------
if not existe_usuario:
    auth.tela_primeiro_acesso()
    st.stop()

usuario = auth.usuario_atual()
if usuario is None:
    auth.tela_login()
    st.stop()

# Revalida a cada acesso: usuário desativado ou com perfil alterado perde o acesso na hora
reg = db.query_one(
    """select u.perfil, u.local_id, u.ativo, u.trocar_senha, l.nome as local_nome
       from usuarios u left join locais l on l.id = u.local_id where u.id = :id""",
    {"id": usuario["id"]},
)
if reg is None or not reg["ativo"]:
    auth.sair()
usuario.update({k: reg[k] for k in ("perfil", "local_id", "trocar_senha", "local_nome")})

if usuario.get("trocar_senha"):
    st.title("Defina sua senha")
    auth.tela_trocar_senha(obrigatoria=True)
    st.stop()

# ---- Menu conforme o perfil -----------------------------------------
P = st.Page
paginas = {
    "Principal": [P(dashboard.render, title="Dashboard", icon="📊", default=True)],
    "Compras": [P(notas.render, title="Notas Fiscais", icon="🧾", url_path="notas"),
                P(itens.render, title="Itens comprados", icon="🛒", url_path="itens")],
    "Cadastros": [
        P(unidades.render, title="Unidades", icon="🏢", url_path="unidades"),
        P(produtos.render, title="Produtos", icon="📦", url_path="produtos"),
        P(fornecedores.render, title="Fornecedores", icon="🚚", url_path="fornecedores"),
    ],
}
if usuario["perfil"] == "gerente":
    paginas["Cadastros"] = [paginas["Cadastros"][1]]  # gerente só consulta produtos

admin = [P(conta.render, title="Minha conta", icon="👤", url_path="conta")]
if usuario["perfil"] == "gestor":
    admin = [
        P(usuarios.render, title="Usuários", icon="🔐", url_path="usuarios"),
        P(backup.render, title="Backup", icon="💾", url_path="backup"),
    ] + admin
paginas["Administração"] = admin

with st.sidebar:
    st.markdown(f"**{usuario['nome']}**  \n{auth.PERFIS[usuario['perfil']]}"
                + (f" · {usuario['local_nome']}" if usuario.get("local_nome") else ""))
    if st.button("Sair", width="stretch"):
        auth.sair()

st.navigation(paginas).run()
