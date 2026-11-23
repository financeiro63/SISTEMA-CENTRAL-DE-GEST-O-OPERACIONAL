-- =====================================================================
-- SISTEMA CENTRAL DE GESTÃO OPERACIONAL — MANTA
-- Banco de dados — FASE 1 (preparado para as fases seguintes)
--
-- COMO USAR: no Supabase, abra "SQL Editor" > "New query", cole este
-- arquivo inteiro e clique em "Run". Rode UMA vez só.
-- =====================================================================

-- ---------------------------------------------------------------------
-- LOCAIS: as 5 unidades + a Central (local físico de mercadorias)
-- ---------------------------------------------------------------------
create table if not exists locais (
    id                  serial primary key,
    nome                text not null unique,
    tipo                text not null check (tipo in ('unidade', 'central')),
    recebe_via_central  boolean not null default false,  -- unidade retira material da Central?
    ativo               boolean not null default true,
    criado_em           timestamptz not null default now()
);

insert into locais (nome, tipo, recebe_via_central) values
    ('Manta 712 Norte',        'unidade', true),
    ('Manta 702 Sul',          'unidade', true),
    ('Manta 610 Sul',          'unidade', true),
    ('Manta 303W / Sudoeste',  'unidade', false),
    ('Manta Vicente Pires',    'unidade', false),
    ('Central',                'central', false)
on conflict (nome) do nothing;

-- ---------------------------------------------------------------------
-- USUÁRIOS E PERFIS
--   gestor  = vê e altera tudo, aprova, gerencia usuários
--   compras = cadastros, compras, NFe, estoque (todas as unidades)
--   gerente = vê só a própria unidade, faz solicitações
-- ---------------------------------------------------------------------
create table if not exists usuarios (
    id            serial primary key,
    nome          text not null,
    login         text not null unique,
    senha_hash    text not null,
    perfil        text not null check (perfil in ('gestor', 'compras', 'gerente')),
    local_id      integer references locais(id),
    trocar_senha  boolean not null default true,   -- força troca no 1º acesso
    ativo         boolean not null default true,
    criado_em     timestamptz not null default now(),
    constraint gerente_tem_unidade check (perfil <> 'gerente' or local_id is not null)
);

-- ---------------------------------------------------------------------
-- CATEGORIAS de materiais / gastos
-- ---------------------------------------------------------------------
create table if not exists categorias (
    id     serial primary key,
    nome   text not null unique,
    ativo  boolean not null default true
);

insert into categorias (nome) values
    ('Limpeza'), ('Escritório / Papelaria'), ('Manutenção'),
    ('Piscina / Químicos'), ('Uniformes'), ('Copa / Cozinha'),
    ('Primeiros socorros'), ('Marketing / Impressos'),
    ('Equipamentos'), ('Higiene'), ('Outros')
on conflict (nome) do nothing;

-- ---------------------------------------------------------------------
-- FORNECEDORES
-- ---------------------------------------------------------------------
create table if not exists fornecedores (
    id                   serial primary key,
    razao_social         text not null,
    nome_fantasia        text,
    cnpj                 text unique,          -- só números (14 dígitos)
    telefone             text,
    whatsapp             text,
    email                text,
    endereco             text,
    tipo_fornecimento    text,
    produtos_fornecidos  text,
    observacoes          text,
    ativo                boolean not null default true,
    criado_em            timestamptz not null default now()
);

create table if not exists fornecedor_categorias (
    fornecedor_id  integer not null references fornecedores(id) on delete cascade,
    categoria_id   integer not null references categorias(id),
    primary key (fornecedor_id, categoria_id)
);

-- ---------------------------------------------------------------------
-- PRODUTOS — catálogo ÚNICO (cada produto cadastrado uma vez só)
--   unidade_medida  = como o item é controlado/retirado (ex.: pct)
--   unidade_compra  = como chega na NFe (ex.: cx)
--   fator_conversao = quantas unidade_medida há em 1 unidade_compra
--                     (ex.: 1 cx = 10 pct  -> fator 10)
-- ---------------------------------------------------------------------
create table if not exists produtos (
    id                       serial primary key,
    codigo                   text unique,
    nome                     text not null,
    categoria_id             integer references categorias(id),
    unidade_medida           text not null default 'un',
    unidade_compra           text not null default 'un',
    fator_conversao          numeric(12,3) not null default 1 check (fator_conversao > 0),
    estoque_minimo           numeric(12,3) not null default 0 check (estoque_minimo >= 0),
    estoque_maximo           numeric(12,3) not null default 0 check (estoque_maximo >= 0),
    localizacao              text,
    fornecedor_principal_id  integer references fornecedores(id),
    ultimo_preco             numeric(14,2),     -- preenchido pela NFe (Fase 2)
    data_ultima_compra       date,              -- preenchido pela NFe (Fase 2)
    observacao               text,
    ativo                    boolean not null default true,
    criado_em                timestamptz not null default now()
);
create unique index if not exists produtos_nome_unico on produtos (lower(nome));

-- ---------------------------------------------------------------------
-- SALDO DE ESTOQUE (preparado para a Fase 2)
--   unidade_dona_id  = unidade a quem o material pertence (dona da NFe)
--   local_fisico_id  = onde o material está (Central ou a própria unidade)
--   Ex.: 10 pct de papel toalha da 712 Norte guardados na Central.
--   Quantidade sempre na unidade_medida do produto.
-- ---------------------------------------------------------------------
create table if not exists estoque_saldos (
    produto_id       integer not null references produtos(id),
    unidade_dona_id  integer not null references locais(id),
    local_fisico_id  integer not null references locais(id),
    quantidade       numeric(14,3) not null default 0,
    atualizado_em    timestamptz not null default now(),
    primary key (produto_id, unidade_dona_id, local_fisico_id)
);

-- ---------------------------------------------------------------------
-- REGISTRO DE AÇÕES (auditoria: quem fez o quê e quando)
-- ---------------------------------------------------------------------
create table if not exists log_acoes (
    id           bigserial primary key,
    usuario_id   integer references usuarios(id),
    acao         text not null,
    tabela       text,
    registro_id  integer,
    detalhe      text,
    quando       timestamptz not null default now()
);

-- ---------------------------------------------------------------------
-- SEGURANÇA: bloqueia o acesso pela API pública do Supabase.
-- O sistema conecta direto no banco (usuário dono das tabelas), então
-- continua funcionando normalmente. Sem políticas = API sem acesso.
-- ---------------------------------------------------------------------
alter table locais                 enable row level security;
alter table usuarios               enable row level security;
alter table categorias             enable row level security;
alter table fornecedores           enable row level security;
alter table fornecedor_categorias  enable row level security;
alter table produtos               enable row level security;
alter table estoque_saldos         enable row level security;
alter table log_acoes              enable row level security;
