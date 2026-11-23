"""Cadastro de fornecedores."""
import streamlit as st
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

import auth
import db
import ui


def _carregar():
    return db.query(
        """select f.*, coalesce(string_agg(c.nome, ', ' order by c.nome), '') as categorias
           from fornecedores f
           left join fornecedor_categorias fc on fc.fornecedor_id = f.id
           left join categorias c on c.id = fc.categoria_id
           group by f.id
           order by coalesce(nullif(f.nome_fantasia, ''), f.razao_social)"""
    )


def _formulario(k: str, atual=None):
    g = (lambda campo: str(ui.valor(atual, campo, "")))
    cats = db.categorias()

    c1, c2 = st.columns(2)
    with c1:
        razao = st.text_input("Razão social *", value=g("razao_social"), key=f"{k}_razao")
        cnpj = st.text_input("CNPJ", value=ui.formatar_cnpj(g("cnpj")), key=f"{k}_cnpj",
                             placeholder="00.000.000/0000-00")
        telefone = st.text_input("Telefone", value=g("telefone"), key=f"{k}_tel")
        email = st.text_input("E-mail", value=g("email"), key=f"{k}_email")
    with c2:
        fantasia = st.text_input("Nome fantasia", value=g("nome_fantasia"), key=f"{k}_fant")
        tipo = st.text_input("Tipo de fornecimento (ex.: atacado, serviço, loja online)",
                             value=g("tipo_fornecimento"), key=f"{k}_tipo")
        whats = st.text_input("WhatsApp", value=g("whatsapp"), key=f"{k}_whats")
        endereco = st.text_input("Endereço", value=g("endereco"), key=f"{k}_end")

    atuais = [c for c in g("categorias").split(", ") if c] if atual is not None else []
    categorias_sel = st.multiselect("Categorias fornecidas", cats["nome"].tolist(),
                                    default=[c for c in atuais if c in cats["nome"].tolist()],
                                    key=f"{k}_cats")
    produtos = st.text_area("Produtos fornecidos", value=g("produtos_fornecidos"), key=f"{k}_prods")
    obs = st.text_area("Observações", value=g("observacoes"), key=f"{k}_obs")

    erros = []
    if not razao.strip():
        erros.append("Informe a razão social.")
    cnpj_num = ui.somente_numeros(cnpj)
    if cnpj_num and not ui.cnpj_valido(cnpj_num):
        erros.append("CNPJ inválido. Confira os números.")
    if email.strip() and "@" not in email:
        erros.append("E-mail inválido.")

    dados = {
        "razao": razao.strip(), "fant": ui.vazio_para_none(fantasia),
        "cnpj": cnpj_num or None, "tel": ui.vazio_para_none(telefone),
        "whats": ui.vazio_para_none(whats), "email": ui.vazio_para_none(email),
        "end": ui.vazio_para_none(endereco), "tipo": ui.vazio_para_none(tipo),
        "prods": ui.vazio_para_none(produtos), "obs": ui.vazio_para_none(obs),
    }
    ids_cat = cats.loc[cats["nome"].isin(categorias_sel), "id"].astype(int).tolist()
    return dados, ids_cat, erros


SQL_INSERIR = """insert into fornecedores (razao_social, nome_fantasia, cnpj, telefone,
                   whatsapp, email, endereco, tipo_fornecimento, produtos_fornecidos, observacoes)
               values (:razao, :fant, :cnpj, :tel, :whats, :email, :end, :tipo, :prods, :obs)
               returning id"""

SQL_ATUALIZAR = """update fornecedores set razao_social = :razao, nome_fantasia = :fant,
                   cnpj = :cnpj, telefone = :tel, whatsapp = :whats, email = :email,
                   endereco = :end, tipo_fornecimento = :tipo, produtos_fornecidos = :prods,
                   observacoes = :obs, ativo = :ativo
               where id = :id"""


def _gravar(dados: dict, ids_cat: list[int], forn_id: int | None = None) -> int:
    """Grava fornecedor + categorias na mesma transação."""
    with db.transacao() as conn:
        if forn_id is None:
            forn_id = conn.execute(text(SQL_INSERIR), dados).scalar_one()
        else:
            conn.execute(text(SQL_ATUALIZAR), {**dados, "id": forn_id})
        conn.execute(text("delete from fornecedor_categorias where fornecedor_id = :f"),
                     {"f": forn_id})
        for c in ids_cat:
            conn.execute(text("insert into fornecedor_categorias (fornecedor_id, categoria_id) "
                              "values (:f, :c)"), {"f": forn_id, "c": c})
    return forn_id


def render():
    st.title("Fornecedores")
    pode_editar = auth.tem_perfil("gestor", "compras")
    df = _carregar()

    # ---- Busca: "quem fornece este tipo de material?" ----------------
    f1, f2, f3 = st.columns([3, 2, 1])
    with f1:
        busca = st.text_input("Buscar por nome, CNPJ ou produto fornecido", key="forn_busca")
    with f2:
        cat = st.selectbox("Fornece a categoria", ["Todas"] + db.categorias()["nome"].tolist(),
                           key="forn_cat")
    with f3:
        inativos = st.checkbox("Mostrar inativos", key="forn_inat")

    vis = df.copy()
    if not inativos:
        vis = vis[vis["ativo"]]
    if busca:
        b = busca.strip().lower()
        texto = (vis["razao_social"].fillna("") + " " + vis["nome_fantasia"].fillna("") + " "
                 + vis["cnpj"].fillna("") + " " + vis["produtos_fornecidos"].fillna("")).str.lower()
        vis = vis[texto.str.contains(b, regex=False)
                  | texto.str.contains(ui.somente_numeros(b) or "§", regex=False)]
    if cat != "Todas":
        vis = vis[vis["categorias"].str.split(", ").apply(lambda l: cat in l)]

    vis = vis.assign(cnpj=vis["cnpj"].apply(ui.formatar_cnpj))
    st.dataframe(
        vis[["nome_fantasia", "razao_social", "cnpj", "categorias", "telefone", "whatsapp",
             "email", "produtos_fornecidos"]],
        hide_index=True, width="stretch",
        column_config={"nome_fantasia": "Nome fantasia", "razao_social": "Razão social",
                       "cnpj": "CNPJ", "categorias": "Categorias", "telefone": "Telefone",
                       "whatsapp": "WhatsApp", "email": "E-mail",
                       "produtos_fornecidos": "Produtos fornecidos"},
    )
    st.caption(f"{len(vis)} fornecedor(es).")

    if not pode_editar:
        return

    aba_novo, aba_editar = st.tabs(["Novo fornecedor", "Editar fornecedor"])

    with aba_novo:
        dados, ids_cat, erros = _formulario("fnovo")
        if st.button("Cadastrar fornecedor", type="primary", key="fnovo_salvar"):
            if erros:
                for e in erros:
                    st.error(e)
            else:
                try:
                    novo_id = _gravar(dados, ids_cat)
                    db.registrar("cadastro de fornecedor", "fornecedores", novo_id, dados["razao"])
                    for chave in [k for k in st.session_state if k.startswith("fnovo_")]:
                        del st.session_state[chave]
                    st.success("Fornecedor cadastrado.")
                    st.rerun()
                except IntegrityError:
                    st.error("Já existe um fornecedor com esse CNPJ.")

    with aba_editar:
        if df.empty:
            st.info("Nenhum fornecedor cadastrado.")
        else:
            rotulos = ("#" + df["id"].astype(str) + " " + df["nome_fantasia"].fillna(df["razao_social"]) + " — "
                       + df["cnpj"].apply(ui.formatar_cnpj).replace("", "sem CNPJ")).tolist()
            escolha = st.selectbox("Fornecedor", rotulos, key="edit_forn")
            atual = df.iloc[rotulos.index(escolha)]
            k = f"forn_{int(atual['id'])}"
            dados, ids_cat, erros = _formulario(k, atual)
            ativo = st.checkbox("Ativo", value=bool(atual["ativo"]), key=f"{k}_ativo")
            confirma = True
            if atual["ativo"] and not ativo:
                confirma = st.checkbox("Confirmo que quero DESATIVAR este fornecedor "
                                       "(o histórico é mantido).", key=f"{k}_conf")
            if st.button("Salvar alterações", type="primary", key=f"{k}_salvar"):
                if erros:
                    for e in erros:
                        st.error(e)
                elif not confirma:
                    st.error("Marque a confirmação para desativar.")
                else:
                    try:
                        _gravar({**dados, "ativo": ativo}, ids_cat, int(atual["id"]))
                        db.registrar("edição de fornecedor", "fornecedores", int(atual["id"]),
                                     dados["razao"])
                        st.success("Fornecedor atualizado.")
                        st.rerun()
                    except IntegrityError:
                        st.error("Já existe outro fornecedor com esse CNPJ.")
