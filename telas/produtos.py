"""Catálogo único de produtos."""
import streamlit as st
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

import auth
import db
import ui


def _carregar():
    return db.query(
        """select p.id, p.codigo, p.nome, p.categoria_id, c.nome as categoria,
                  p.unidade_medida, p.unidade_compra, p.fator_conversao,
                  p.estoque_minimo, p.estoque_maximo, p.localizacao,
                  p.fornecedor_principal_id,
                  coalesce(nullif(f.nome_fantasia, ''), f.razao_social) as fornecedor_principal,
                  p.ultimo_preco, p.data_ultima_compra, p.observacao, p.ativo
           from produtos p
           left join categorias c on c.id = p.categoria_id
           left join fornecedores f on f.id = p.fornecedor_principal_id
           order by p.nome"""
    )


def _formulario(k: str, atual=None):
    """Campos do produto. 'k' isola o estado de cada formulário."""
    cats = db.categorias()
    forns = db.fornecedores_lista()
    g = (lambda campo, padrao=None: ui.valor(atual, campo, padrao))

    nome = st.text_input("Nome do produto *", value=g("nome", ""), key=f"{k}_nome")
    c1, c2 = st.columns(2)
    with c1:
        lista_cat = cats["nome"].tolist()
        idx = lista_cat.index(g("categoria")) if g("categoria") in lista_cat else None
        categoria = st.selectbox("Categoria *", lista_cat, index=idx,
                                 placeholder="Selecione", key=f"{k}_cat")
    with c2:
        lista_f = ["(nenhum)"] + forns["nome"].tolist()
        fp = g("fornecedor_principal")
        fornecedor = st.selectbox("Fornecedor principal", lista_f,
                                  index=lista_f.index(fp) if fp in lista_f else 0, key=f"{k}_forn")

    st.markdown("**Unidade de medida e conversão**")
    c3, c4, c5 = st.columns(3)
    um = ui.UNIDADES_MEDIDA
    with c3:
        v = g("unidade_medida", "un")
        un_med = st.selectbox("Controlado/retirado em", um,
                              index=um.index(v) if v in um else 0, key=f"{k}_um")
    with c4:
        v = g("unidade_compra", "un")
        un_comp = st.selectbox("Chega na NFe em", um,
                               index=um.index(v) if v in um else 0, key=f"{k}_uc")
    with c5:
        fator = st.number_input("Fator de conversão", min_value=0.001,
                                help="Quantas unidades de controle cabem em 1 unidade da NFe. "
                                     "Ex.: chega em cx e é retirado em pct, 1 cx = 10 pct → 10.",
                                value=float(g("fator_conversao", 1) or 1), step=1.0,
                                format="%.3f", key=f"{k}_fator",
                                disabled=(un_comp == un_med))
        if un_comp == un_med:
            fator = 1.0
        else:
            st.caption(f"1 {un_comp} = {fator:g} {un_med}")

    c6, c7, c8 = st.columns(3)
    with c6:
        minimo = st.number_input("Estoque mínimo (unid. de controle)", min_value=0.0,
                                 value=float(g("estoque_minimo", 0) or 0), key=f"{k}_min")
    with c7:
        maximo = st.number_input("Estoque máximo (unid. de controle)", min_value=0.0,
                                 value=float(g("estoque_maximo", 0) or 0), key=f"{k}_max")
    with c8:
        local = st.text_input("Localização (ex.: prateleira A2)",
                              value=g("localizacao", "") or "", key=f"{k}_loc")
    obs = st.text_area("Observação", value=g("observacao", "") or "", key=f"{k}_obs")

    erros = []
    if not nome.strip():
        erros.append("Informe o nome do produto.")
    if not categoria:
        erros.append("Selecione a categoria.")
    if maximo and minimo > maximo:
        erros.append("O estoque mínimo não pode ser maior que o máximo.")

    dados = {
        "nome": nome.strip(),
        "cat": int(cats.loc[cats["nome"] == categoria, "id"].iloc[0]) if categoria else None,
        "um": un_med, "uc": un_comp, "fator": fator,
        "min": minimo, "max": maximo, "loc": ui.vazio_para_none(local),
        "forn": (int(forns.loc[forns["nome"] == fornecedor, "id"].iloc[0])
                 if fornecedor != "(nenhum)" else None),
        "obs": ui.vazio_para_none(obs),
    }
    return dados, erros


def render():
    st.title("Produtos")
    pode_editar = auth.tem_perfil("gestor", "compras")
    df = _carregar()

    # ---- Busca e filtros --------------------------------------------
    f1, f2, f3 = st.columns([3, 2, 1])
    with f1:
        busca = st.text_input("Buscar por nome ou código", key="prod_busca")
    with f2:
        cat = st.selectbox("Categoria", ["Todas"] + db.categorias()["nome"].tolist(), key="prod_cat")
    with f3:
        inativos = st.checkbox("Mostrar inativos", key="prod_inat")

    vis = df.copy()
    if not inativos:
        vis = vis[vis["ativo"]]
    if busca:
        b = busca.strip().lower()
        vis = vis[vis["nome"].str.lower().str.contains(b, regex=False)
                  | vis["codigo"].fillna("").str.lower().str.contains(b, regex=False)]
    if cat != "Todas":
        vis = vis[vis["categoria"] == cat]

    st.dataframe(
        vis[["codigo", "nome", "categoria", "unidade_medida", "unidade_compra", "fator_conversao",
             "estoque_minimo", "estoque_maximo", "fornecedor_principal", "ultimo_preco",
             "data_ultima_compra", "localizacao"]],
        hide_index=True, width="stretch",
        column_config={
            "codigo": "Código", "nome": "Produto", "categoria": "Categoria",
            "unidade_medida": "Controle em", "unidade_compra": "Compra em",
            "fator_conversao": st.column_config.NumberColumn("Fator", format="%.3g"),
            "estoque_minimo": "Mínimo", "estoque_maximo": "Máximo",
            "fornecedor_principal": "Fornecedor principal",
            "ultimo_preco": st.column_config.NumberColumn("Último preço", format="R$ %.2f"),
            "data_ultima_compra": st.column_config.DateColumn("Última compra", format="DD/MM/YYYY"),
            "localizacao": "Localização",
        },
    )
    st.caption(f"{len(vis)} produto(s). Último preço e data da última compra serão "
               "preenchidos automaticamente pelas NFe (Fase 2).")

    if not pode_editar:
        return

    aba_novo, aba_editar, aba_cat = st.tabs(["Novo produto", "Editar produto", "Categorias"])

    with aba_novo:
        dados, erros = _formulario("novo")
        if st.button("Cadastrar produto", type="primary", key="novo_salvar"):
            if erros:
                for e in erros:
                    st.error(e)
            else:
                try:
                    with db.transacao() as conn:
                        novo_id = conn.execute(text(
                            """insert into produtos (nome, categoria_id, unidade_medida,
                                   unidade_compra, fator_conversao, estoque_minimo, estoque_maximo,
                                   localizacao, fornecedor_principal_id, observacao)
                               values (:nome, :cat, :um, :uc, :fator, :min, :max, :loc, :forn, :obs)
                               returning id"""), dados).scalar_one()
                        codigo = f"P{novo_id:05d}"
                        conn.execute(text("update produtos set codigo = :c where id = :id"),
                                     {"c": codigo, "id": novo_id})
                    db.registrar("cadastro de produto", "produtos", novo_id, dados["nome"])
                    for chave in [k for k in st.session_state if k.startswith("novo_")]:
                        del st.session_state[chave]
                    st.success(f"Produto cadastrado com o código {codigo}.")
                    st.rerun()
                except IntegrityError:
                    st.error("Já existe um produto com esse nome.")

    with aba_editar:
        if df.empty:
            st.info("Nenhum produto cadastrado.")
        else:
            rotulos = (df["codigo"].fillna("") + " — " + df["nome"]).tolist()
            escolha = st.selectbox("Produto", rotulos, key="edit_prod")
            atual = df.iloc[rotulos.index(escolha)]
            k = f"prod_{int(atual['id'])}"
            dados, erros = _formulario(k, atual)
            ativo = st.checkbox("Ativo", value=bool(atual["ativo"]), key=f"{k}_ativo")
            confirma = True
            if atual["ativo"] and not ativo:
                confirma = st.checkbox("Confirmo que quero DESATIVAR este produto "
                                       "(o histórico é mantido).", key=f"{k}_conf")
            if st.button("Salvar alterações", type="primary", key=f"{k}_salvar"):
                if erros:
                    for e in erros:
                        st.error(e)
                elif not confirma:
                    st.error("Marque a confirmação para desativar.")
                else:
                    try:
                        db.execute(
                            """update produtos set nome = :nome, categoria_id = :cat,
                                   unidade_medida = :um, unidade_compra = :uc,
                                   fator_conversao = :fator, estoque_minimo = :min,
                                   estoque_maximo = :max, localizacao = :loc,
                                   fornecedor_principal_id = :forn, observacao = :obs,
                                   ativo = :ativo
                               where id = :id""",
                            {**dados, "ativo": ativo, "id": int(atual["id"])})
                        db.registrar("edição de produto", "produtos", int(atual["id"]), dados["nome"])
                        st.success("Produto atualizado.")
                        st.rerun()
                    except IntegrityError:
                        st.error("Já existe outro produto com esse nome.")

    with aba_cat:
        cats = db.categorias(somente_ativas=False)
        st.dataframe(cats[["nome", "ativo"]].rename(columns={"nome": "Categoria", "ativo": "Ativa"}),
                     hide_index=True, width="stretch")
        nova = st.text_input("Nova categoria", key="cat_nova")
        if st.button("Adicionar categoria", key="cat_add"):
            if not nova.strip():
                st.error("Informe o nome da categoria.")
            else:
                try:
                    db.execute("insert into categorias (nome) values (:n)", {"n": nova.strip()})
                    db.registrar("cadastro de categoria", "categorias", None, nova.strip())
                    del st.session_state["cat_nova"]
                    st.rerun()
                except IntegrityError:
                    st.error("Essa categoria já existe.")
