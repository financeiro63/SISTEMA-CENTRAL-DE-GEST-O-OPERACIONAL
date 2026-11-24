"""Dashboard principal."""
import streamlit as st

import db
import ui


def render():
    st.title("Dashboard")
    c1, _ = st.columns([2, 3])
    with c1:
        unidade_id, unidade_nome = ui.filtro_unidade("dash_unidade")

    filtro_saldo = "" if unidade_id is None else "and s.unidade_dona_id = :u"
    params = {"u": unidade_id}

    # ---- Indicadores que já funcionam na Fase 1 ---------------------
    n_prod = db.query_one("select count(*) as n from produtos where ativo")["n"]
    n_forn = db.query_one("select count(*) as n from fornecedores where ativo")["n"]
    n_unid = db.query_one("select count(*) as n from locais where ativo and tipo = 'unidade'")["n"]

    # Estoque baixo / em falta: soma o saldo da unidade (Central + unidade)
    saldos = db.query(
        f"""select p.nome as produto, l.nome as unidade,
                   sum(s.quantidade) as saldo, p.estoque_minimo as minimo, p.unidade_medida
            from estoque_saldos s
            join produtos p on p.id = s.produto_id and p.ativo
            join locais l on l.id = s.unidade_dona_id
            where p.estoque_minimo > 0 {filtro_saldo}
            group by p.nome, l.nome, p.estoque_minimo, p.unidade_medida""",
        params,
    )
    em_falta = saldos[saldos["saldo"] <= 0]
    baixo = saldos[(saldos["saldo"] > 0) & (saldos["saldo"] <= saldos["minimo"])]

    st.subheader(f"Visão geral — {unidade_nome}")
    a, b, c, d, e = st.columns(5)
    with a:
        ui.card("Unidades ativas", n_unid)
    with b:
        ui.card("Produtos cadastrados", n_prod)
    with c:
        ui.card("Fornecedores", n_forn)
    with d:
        ui.card("Estoque baixo", len(baixo), "no mínimo ou abaixo", "alerta" if len(baixo) else "")
    with e:
        ui.card("Produtos em falta", len(em_falta), "saldo zerado", "alerta" if len(em_falta) else "")

    # ---- Compras do mês (NFs) -----------------------------------------
    filtro_nf = "" if unidade_id is None else "and n.unidade_id = :u"
    meses = db.query(f"""select distinct to_char(data_emissao, 'YYYY-MM') as mes
                         from nfe n where 1=1 {filtro_nf} order by 1 desc""", params)["mes"].tolist()
    st.subheader("Compras (NFs lançadas)")
    if not meses:
        st.info("Nenhuma NF lançada ainda.")
    else:
        rot = {m: f"{['','Jan','Fev','Mar','Abr','Mai','Jun','Jul','Ago','Set','Out','Nov','Dez'][int(m[5:])]}/{m[:4]}"
               for m in meses}
        mes = st.selectbox("Mês de emissão", meses, format_func=rot.get, key="dash_mes")
        nf = db.query(
            f"""select l.nome as unidade, coalesce(nullif(f.nome_fantasia, ''), f.razao_social) as fornecedor,
                       n.tipo, n.valor_total::float as valor, n.conferir
                from nfe n join locais l on l.id = n.unidade_id
                join fornecedores f on f.id = n.fornecedor_id
                where to_char(n.data_emissao, 'YYYY-MM') = :m {filtro_nf}""",
            {**params, "m": mes})
        idx = meses.index(mes)
        anterior = None
        if idx + 1 < len(meses):
            anterior = db.query_one(
                f"""select coalesce(sum(valor_total), 0)::float as v from nfe n
                    where to_char(data_emissao, 'YYYY-MM') = :m {filtro_nf}""",
                {**params, "m": meses[idx + 1]})["v"]
        total = nf["valor"].sum()
        var = ""
        if anterior:
            var = f"{(total / anterior - 1) * 100:+.0f}% vs {rot[meses[idx + 1]]}"
        a, b, c, d = st.columns(4)
        with a:
            ui.card("Compras no mês", len(nf), "NFs lançadas")
        with b:
            ui.card("Valor total comprado", ui.moeda(total), var)
        with c:
            ui.card("Produtos / Serviços",
                    f"{ui.moeda(nf.loc[nf['tipo'] == 'produto', 'valor'].sum())}",
                    f"serviços: {ui.moeda(nf.loc[nf['tipo'] == 'servico', 'valor'].sum())}")
        with d:
            n_c = int(nf["conferir"].sum())
            ui.card("NFs a conferir", n_c, "divergências", "alerta" if n_c else "")
        g1, g2 = st.columns(2)
        with g1:
            st.caption("Gastos por unidade")
            st.bar_chart(nf.groupby("unidade", as_index=False)["valor"].sum()
                           .sort_values("valor", ascending=False),
                         x="unidade", y="valor", color=ui.AZUL, horizontal=True)
        with g2:
            st.caption("Gastos por fornecedor")
            st.bar_chart(nf.groupby("fornecedor", as_index=False)["valor"].sum()
                           .sort_values("valor", ascending=False),
                         x="fornecedor", y="valor", color=ui.AMARELO, horizontal=True)

    # ---- Indicadores das próximas fases (estrutura já reservada) ----
    st.subheader("Próximos módulos")
    futuros = [
        ("Solicitações pendentes", "Fase 2"), ("Solicitações em andamento", "Fase 2"),
        ("Manutenções pendentes", "Fase 3"), ("Consumo de materiais", "Fase 3"),
    ]
    cols = st.columns(4)
    for i, (rotulo, fase) in enumerate(futuros):
        with cols[i % 4]:
            ui.card(rotulo, "—", f"disponível na {fase}", "inativo")

    # ---- Listas de alerta -------------------------------------------
    if len(baixo) or len(em_falta):
        st.subheader("Itens que precisam de atenção")
        t1, t2 = st.tabs([f"Em falta ({len(em_falta)})", f"Estoque baixo ({len(baixo)})"])
        with t1:
            st.dataframe(em_falta, hide_index=True, width="stretch")
        with t2:
            st.dataframe(baixo, hide_index=True, width="stretch")

    # ---- Cadastro por categoria ---------------------------------------
    st.subheader("Cadastros por categoria")
    st.caption("Clique numa barra para abrir os itens comprados daquela categoria.")
    g1, g2 = st.columns(2)
    prod_cat = db.query(
        """select coalesce(c.nome, 'Sem categoria') as categoria, count(*) as produtos
           from produtos p left join categorias c on c.id = p.categoria_id
           where p.ativo group by 1 order by 2 desc"""
    )
    forn_cat = db.query(
        """select c.nome as categoria, count(*) as fornecedores
           from fornecedor_categorias fc
           join categorias c on c.id = fc.categoria_id
           join fornecedores f on f.id = fc.fornecedor_id and f.ativo
           group by 1 order by 2 desc"""
    )
    clique = None
    with g1:
        st.caption("Produtos por categoria")
        if prod_cat.empty:
            st.info("Nenhum produto cadastrado ainda.")
        else:
            clique = _grafico_clicavel(prod_cat, "produtos", ui.AZUL, "ch_prod_cat") or clique
    with g2:
        st.caption("Fornecedores por categoria")
        if forn_cat.empty:
            st.info("Nenhum fornecedor cadastrado ainda.")
        else:
            clique = _grafico_clicavel(forn_cat, "fornecedores", ui.AMARELO, "ch_forn_cat") or clique

    _area_itens_por_categoria(unidade_id, unidade_nome, clique,
                              sorted(set(prod_cat["categoria"]) | set(forn_cat["categoria"])))


def _grafico_clicavel(df, campo: str, cor: str, key: str):
    """Barras horizontais clicáveis. Devolve a categoria clicada (ou None)."""
    import altair as alt
    sel = alt.selection_point(fields=["categoria"], name="sel")
    ch = (alt.Chart(df)
          .mark_bar(color=cor, cursor="pointer")
          .encode(y=alt.Y("categoria:N", sort="-x", title=None),
                  x=alt.X(f"{campo}:Q", title=campo),
                  opacity=alt.condition(sel, alt.value(1.0), alt.value(0.45)),
                  tooltip=["categoria", campo])
          .add_params(sel)
          .properties(height=max(160, 34 * len(df))))
    ev = st.altair_chart(ch, on_select="rerun", key=key)
    try:
        selecao = ev.selection.get("sel") if hasattr(ev.selection, "get") else ev["selection"]["sel"]
    except Exception:
        return None
    if isinstance(selecao, list) and selecao:
        return selecao[0].get("categoria")
    if isinstance(selecao, dict):
        v = selecao.get("categoria")
        return v[0] if isinstance(v, list) and v else v
    return None


def _area_itens_por_categoria(unidade_id, unidade_nome, clique, categorias):
    """Área abaixo dos gráficos: itens comprados, valores e fornecedores da categoria."""
    st.subheader("Itens comprados por categoria")
    # o clique na barra preenche a categoria escolhida
    if clique and clique != st.session_state.get("_dash_ultimo_clique"):
        st.session_state["dash_cat_sel"] = clique
        st.session_state["_dash_ultimo_clique"] = clique

    filtro = "" if unidade_id is None else "and n.unidade_id = :u"
    df = db.query(
        f"""select coalesce(c.nome, 'Sem categoria') as categoria,
                   coalesce(p.nome, i.descricao) as produto, p.codigo,
                   coalesce(nullif(f.nome_fantasia, ''), f.razao_social) as fornecedor,
                   l.nome as unidade, n.numero as nf, n.data_emissao,
                   to_char(n.data_emissao, 'YYYY-MM') as mes, i.unidade_nf,
                   i.quantidade::float as quantidade, i.valor_total::float as valor
            from nfe_itens i
            join nfe n on n.id = i.nfe_id
            join locais l on l.id = n.unidade_id
            join fornecedores f on f.id = n.fornecedor_id
            left join produtos p on p.id = i.produto_id
            left join categorias c on c.id = p.categoria_id
            where 1=1 {filtro}""",
        {"u": unidade_id})
    if df.empty:
        st.info("Nenhum item de NF carregado ainda.")
        return

    nomes_mes = ["", "Jan", "Fev", "Mar", "Abr", "Mai", "Jun", "Jul", "Ago", "Set", "Out", "Nov", "Dez"]
    rot = lambda m: f"{nomes_mes[int(m[5:])]}/{m[:4]}"
    f1, f2 = st.columns([2, 3])
    with f1:
        opcoes = ["Todas as categorias"] + [c for c in categorias if c in set(df["categoria"])]
        if st.session_state.get("dash_cat_sel") not in opcoes:
            st.session_state["dash_cat_sel"] = "Todas as categorias"
        cat = st.selectbox("Categoria", opcoes, key="dash_cat_sel")
    with f2:
        meses = sorted(df["mes"].unique(), reverse=True)
        sel_m = st.multiselect("Período (mês de emissão)", meses, format_func=rot,
                               key="dash_cat_meses", placeholder="Todos os meses")
    vis = df if not sel_m else df[df["mes"].isin(sel_m)]
    if cat != "Todas as categorias":
        vis = vis[vis["categoria"] == cat]
    if vis.empty:
        st.info("Nenhum item comprado nesse filtro.")
        return

    periodo = ", ".join(rot(m) for m in sorted(sel_m)) if sel_m else "todos os meses"
    st.caption(f"{cat} · {unidade_nome} · {periodo}")
    a, b, c = st.columns(3)
    with a:
        ui.card("Valor dos itens", ui.moeda(vis["valor"].sum()))
    with b:
        ui.card("Produtos diferentes", vis["produto"].nunique())
    with c:
        ui.card("Fornecedores", vis["fornecedor"].nunique())

    if cat == "Todas as categorias":
        st.caption("Valor comprado por categoria e fornecedor — escolha uma categoria (ou clique "
                   "numa barra acima) para abrir os itens.")
        piv = vis.pivot_table(index="categoria", columns="fornecedor", values="valor",
                              aggfunc="sum", fill_value=0)
        piv["Total"] = piv.sum(axis=1)
        st.dataframe(piv.sort_values("Total", ascending=False).map(ui.moeda), width="stretch")
        return

    # uma "pasta" por fornecedor, com os itens comprados dentro
    por_forn = vis.groupby("fornecedor")["valor"].sum().sort_values(ascending=False)
    for forn, total_f in por_forn.items():
        itf = vis[vis["fornecedor"] == forn].sort_values("data_emissao")
        res = (itf.groupby(["produto", "unidade_nf"], as_index=False)
                  .agg(quantidade=("quantidade", "sum"), valor=("valor", "sum"),
                       nfs=("nf", "nunique"),
                       unidades=("unidade", lambda x: ", ".join(sorted(set(x)))),
                       ultima=("data_emissao", "max")))
        res["preco_medio"] = res["valor"] / res["quantidade"]
        ult = itf.groupby("produto").tail(1).set_index("produto")
        res["ultimo_preco"] = res["produto"].map(ult["valor"] / ult["quantidade"])
        res = res.sort_values("valor", ascending=False)
        with st.expander(f"📁 {forn} — {ui.moeda(total_f)} · {len(res)} produto(s)"):
            st.dataframe(
                res[["produto", "unidade_nf", "quantidade", "valor", "preco_medio", "ultimo_preco",
                     "nfs", "unidades", "ultima"]],
                hide_index=True, width="stretch",
                column_config={
                    "produto": "Produto", "unidade_nf": "Un.",
                    "quantidade": st.column_config.NumberColumn("Qtd", format="%.2f"),
                    "valor": st.column_config.NumberColumn("Valor", format="R$ %.2f"),
                    "preco_medio": st.column_config.NumberColumn("Preço médio", format="R$ %.2f"),
                    "ultimo_preco": st.column_config.NumberColumn("Último preço", format="R$ %.2f"),
                    "nfs": "NFs", "unidades": "Unidades que compraram",
                    "ultima": st.column_config.DateColumn("Última compra", format="DD/MM/YYYY"),
                })
