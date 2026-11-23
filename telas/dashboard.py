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

    # ---- Indicadores das próximas fases (estrutura já reservada) ----
    st.subheader("Operação do mês")
    futuros = [
        ("Compras realizadas no mês", "Fase 2"), ("Valor total comprado", "Fase 2"),
        ("Solicitações pendentes", "Fase 2"), ("NFe aguardando lançamento", "Fase 2"),
        ("Solicitações em andamento", "Fase 2"), ("Manutenções pendentes", "Fase 3"),
        ("Consumo de materiais", "Fase 3"), ("Gastos por fornecedor", "Fase 4"),
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
    with g1:
        st.caption("Produtos por categoria")
        if prod_cat.empty:
            st.info("Nenhum produto cadastrado ainda.")
        else:
            st.bar_chart(prod_cat, x="categoria", y="produtos", color=ui.AZUL, horizontal=True)
    with g2:
        st.caption("Fornecedores por categoria")
        if forn_cat.empty:
            st.info("Nenhum fornecedor cadastrado ainda.")
        else:
            st.bar_chart(forn_cat, x="categoria", y="fornecedores", color=ui.AMARELO, horizontal=True)
