"""
    sincro_bitrix.py
    Serviço de sincronização incremental: Bitrix CRM → PostgreSQL
    Executa a cada 15 minutos via cron ou manualmente.
"""

import os
import time
import logging
import requests
import psycopg2
import psycopg2.extras
from datetime import datetime, timedelta, timezone
from dotenv import load_dotenv

load_dotenv()

# ── Logging ────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler("sync_log.txt", encoding="utf-8"),
        logging.StreamHandler(),
    ],
)
log = logging.getLogger(__name__)

# ── Configuração (via .env) ─────────────────────────────────────
BITRIX_URL    = os.getenv("BITRIX_URL")       # ex: https://dominio.bitrix24.com
BITRIX_TOKEN  = os.getenv("BITRIX_TOKEN")     # webhook token
PG_HOST       = os.getenv("PG_HOST", "localhost")
PG_PORT       = os.getenv("PG_PORT", "5432")
PG_DB         = os.getenv("PG_DB")
PG_USER       = os.getenv("PG_USER")
PG_PASSWORD   = os.getenv("PG_PASSWORD")
BATCH_SIZE    = int(os.getenv("BATCH_SIZE", "50"))
LOOKBACK_MINS = int(os.getenv("LOOKBACK_MINS", "20"))   # janela de segurança

# ── Mapeamento: campo Bitrix → coluna PostgreSQL ────────────────
FIELD_MAP = {
    # standard
    "ID":                           "id",
    "TITLE":                        "titulo",
    "TYPE_ID":                      "tipo_id",
    "CATEGORY_ID":                  "pipeline_id",
    "STAGE_ID":                     "fase_id",
    "STAGE_SEMANTIC_ID":            "fase_grupo",
    "IS_NEW":                       "is_novo",
    "IS_RECURRING":                 "is_recorrente",
    "IS_RETURN_CUSTOMER":           "is_cliente_retorno",
    "IS_REPEATED_APPROACH":         "is_consulta_repetida",
    "PROBABILITY":                  "probabilidade",
    "CURRENCY_ID":                  "moeda",
    "OPPORTUNITY":                  "total",
    "TAX_VALUE":                    "taxa_imposto",
    "COMPANY_ID":                   "empresa_id",
    "CONTACT_ID":                   "contacto_id",
    "BEGINDATE":                    "data_inicio",
    "CLOSEDATE":                    "data_fecho",
    "OPENED":                       "aberto",
    "CLOSED":                       "fechado",
    "COMMENTS":                     "observacao",
    "ASSIGNED_BY_ID":               "responsavel_id",
    "CREATED_BY_ID":                "criado_por_id",
    "MODIFY_BY_ID":                 "modificado_por_id",
    "DATE_CREATE":                  "data_criacao",
    "DATE_MODIFY":                  "data_modificacao",
    "SOURCE_ID":                    "fonte_id",
    "SOURCE_DESCRIPTION":           "fonte_descricao",
    "LEAD_ID":                      "lead_id",
    "UTM_SOURCE":                   "utm_source",
    "UTM_MEDIUM":                   "utm_medium",
    "UTM_CAMPAIGN":                 "utm_campaign",
    "UTM_CONTENT":                  "utm_content",
    "UTM_TERM":                     "utm_term",
    "LAST_ACTIVITY_TIME":           "ultima_atividade",
    "ADDITIONAL_INFO":              "informacoes_adicionais",
    # campos personalizados
    "UF_CRM_1737552038739":         "contacto_nome",
    "UF_CRM_1741214526":            "nif",
    "UF_CRM_1739878822":            "cartao_cidadao",
    "UF_CRM_1741717566":            "doc_ident",
    "UF_CRM_1744735248":            "data_nascimento",
    "UF_CRM_1741214498":            "email",
    "UF_CRM_1741002186":            "telefone_ass_digital",
    "UF_CRM_1741002202":            "email_ass_digital",
    "UF_CRM_1741717528":            "contacto_fixo",
    "UF_CRM_1741000307":            "pessoa_contacto",
    "UF_CRM_1763654744":            "idade",
    "UF_CRM_1741213750":            "titular_conta",
    "UF_CRM_1737650488":            "morada_cliente",
    "UF_CRM_1739880599":            "morada_correspondencia",
    "UF_CRM_1739880641":            "codigo_postal_corresp",
    "UF_CRM_1744736254":            "localidade_corresp",
    "UF_CRM_1739880657":            "morada_fornecimento",
    "UF_CRM_1739880676":            "codigo_postal_fornec",
    "UF_CRM_1741717623":            "localidade_fornecimento",
    "UF_CRM_1742924826":            "distrito",
    "UF_CRM_1742924935":            "concelho",
    "UF_CRM_1737650510":            "cpe",
    "UF_CRM_1737650524":            "cui",
    "UF_CRM_1737716546":            "potencia",
    "UF_CRM_1741213992":            "tensao",
    "UF_CRM_1739880940":            "produto",
    "UF_CRM_1739880995":            "tarifa",
    "UF_CRM_1739881066":            "opcao_horaria",
    "UF_CRM_1739881216":            "escalao",
    "UF_CRM_1748259427":            "n_contadores",
    "UF_CRM_1744736278":            "tipo_predio",
    "UF_CRM_1770725289111":         "operadora",
    "UF_CRM_1744036243":            "operadores",
    "UF_CRM_1739881146":            "antigo_comercializador_luz",
    "UF_CRM_1739881817":            "antigo_comercializador_gas",
    "UF_CRM_1739881123":            "alteracao_titular_luz",
    "UF_CRM_1739881257":            "alteracao_titular_gas",
    "UF_CRM_1741213643":            "entrada_direta_luz",
    "UF_CRM_1741213665":            "entrada_direta_gas",
    "UF_CRM_1739881867":            "inspecao_gas_protocolo",
    "UF_CRM_1739881904":            "forma_pagamento",
    "UF_CRM_1739882650":            "iban",
    "UF_CRM_1749058677":            "validacao_iban",
    "UF_CRM_1739882682":            "envio_fatura",
    "UF_CRM_1739882785":            "servicos",
    "UF_CRM_1761907225772":         "data_fidelizacao",
    "UF_CRM_1772644227589":         "periodo_fidelizacao",
    "UF_CRM_1772643741085":         "fidelizacao_operadoras",
    "UF_CRM_1747400445":            "data_ativacao_gas",
    "UF_CRM_1740572323":            "comercial",
    "UF_CRM_1739878786":            "origem",
    "UF_CRM_1749208232":            "origem_lead",
    "UF_CRM_1741213862":            "campanha",
    "UF_CRM_1741712281":            "segmento",
    "UF_CRM_1741197259":            "estrutura",
    "UF_CRM_1741277830":            "estrutura_multicanal",
    "UF_CRM_1750089434":            "mes_comercial",
    "UF_CRM_1741195024":            "estado_chamada",
    "UF_CRM_1741000374":            "crc",
    "UF_CRM_1737650328":            "tipo_pendente",
    "UF_CRM_1737718668":            "motivo_ko",
    "UF_CRM_1737720051":            "motivo_anulado",
    "UF_CRM_1741717582":            "status_final",
    "UF_CRM_1741717598":            "data_status",
    "UF_CRM_1755688174":            "estado",
    "UF_CRM_1755688236":            "estado_purgatorio",
    "UF_CRM_1751889388":            "id_negocio_ext",
    "UF_CRM_1739882836":            "observacoes",
    "UF_CRM_1742904430":            "valor_fatura",
    "UF_CRM_1742909729":            "preco_energia_ponta",
    "UF_CRM_1742909755":            "preco_energia_cheia",
    "UF_CRM_1742909778":            "preco_energia_vazio",
    "UF_CRM_1742909797":            "preco_energia_super_vazio",
    "UF_CRM_1743170960":            "preco_energia_fora_vazio",
    "UF_CRM_1743177490":            "preco_energia_simples",
    "UF_CRM_1742397077":            "preco_potencia_com_redes",
    "UF_CRM_1742397090":            "preco_potencia_sem_redes",
    "UF_CRM_1742909849":            "consumo_anual_luz_kwh",
    "UF_CRM_1742909890":            "consumo_periodo_contrato",
    "UF_CRM_1742908535":            "margem_luz",
    "UF_CRM_1742908548":            "maturidade_luz",
    "UF_CRM_1743170734":            "proposta_luz",
    "UF_CRM_1770993271837":         "margem",
    "UF_CRM_1772115343334":         "margem_audax",
    "UF_CRM_1772115359282":         "margem_edp",
    "UF_CRM_1772115368376":         "margem_axpo",
    "UF_CRM_1772116871603":         "margem_iberdrola",
    "UF_CRM_1772116883278":         "margem_galp",
    "UF_CRM_1772117228627":         "margem_portulogos",
    "UF_CRM_1772117236683":         "margem_nabalia",
    "UF_CRM_1744298699":            "margem_gas",
    "UF_CRM_1744298711":            "maturidade_gas",
    "UF_CRM_1744298727":            "consumo_anual_gas",
    "UF_CRM_1749725040":            "valor_fatura_gas",
    "UF_CRM_1749725108":            "preco_kwh_gas",
    "UF_CRM_1747400525":            "proposta_gas",
    "UF_CRM_1760615296":            "consumo_periodo_gas",
    "UF_CRM_1760528709":            "pontos_luz",
    "UF_CRM_1760528722":            "pontos_gas",
    "UF_CRM_1739882825":            "servicos_endesa",
    "UF_CRM_1744734586":            "tipo_venda_endesa",
    "UF_CRM_1744813586":            "campanha_endesa",
    "UF_CRM_1744736309":            "residencia_endesa",
    "UF_CRM_1749836517":            "tipo_cliente_endesa",
    "UF_CRM_1749484808":            "desconto_endesa",
    "UF_CRM_1749488557":            "termo_fixo_endesa",
    "UF_CRM_1749488609":            "preco_energia_endesa",
    "UF_CRM_1748519472":            "cs_endesa",
    "UF_CRM_1748519493":            "opp_endesa",
    "UF_CRM_1748519512":            "data_registo_endesa",
    "UF_CRM_1748522958":            "codigo_canal_endesa",
    "UF_CRM_1748524622":            "feedback_auditoria_endesa",
    "UF_CRM_1748524677":            "auditado_por_endesa",
    "UF_CRM_1748524696":            "data_auditoria_endesa",
    "UF_CRM_1760612923":            "data_chamada_ok_endesa",
    "UF_CRM_1750163842":            "data_estado_endesa",
    "UF_CRM_1750784608":            "data_contratacao_endesa",
    "UF_CRM_1750851010":            "nome_agente_endesa",
    "UF_CRM_1750851053":            "chefe_equipa_endesa",
    "UF_CRM_1750853486":            "coordenacao_endesa",
    "UF_CRM_1754663910":            "codigo_agente_endesa",
    "UF_CRM_1765982580":            "id_crm_endesa",
    "UF_CRM_1745432486":            "observacoes_endesa",
    "UF_CRM_1749836644":            "cm_mkt_endesa",
    "UF_CRM_1750164079":            "vivenda_endesa",
    "UF_CRM_1738860400394":         "divida_endesa",
    "UF_CRM_1744734800":            "copia_doc_ident_endesa",
    "UF_CRM_1744734739":            "opcao_sms_endesa",
    "UF_CRM_1752764143":            "tipo_venda_repsol",
    "UF_CRM_1741214026":            "servicos_repsol",
    "UF_CRM_1756461144":            "id_repsol",
    "UF_CRM_1758130442":            "data_ativacao_cpe_repsol",
    "UF_CRM_1758130460":            "data_baixa_cpe_repsol",
    "UF_CRM_1758294817":            "data_ativacao_cui_repsol",
    "UF_CRM_1758294851":            "data_baixa_cui_repsol",
    "UF_CRM_1769513898":            "campanha_galp",
    "UF_CRM_1769513930":            "servicos_adicionais_galp",
    "UF_CRM_1768579815":            "n_cartao_continente",
    "UF_CRM_1769080096":            "n_cliente_nos",
    "UF_CRM_1742905145":            "segmento_multioperador",
    "UF_CRM_1742905224":            "potencia_multioperador",
    "UF_CRM_1742905342":            "n_paineis_multioperador",
    "UF_CRM_1742905392":            "valor_obra",
    "UF_CRM_1742905684":            "nivel_tensao_multioperador",
    "UF_CRM_1742905753":            "combinacao",
    "UF_CRM_1743096894":            "opcao_tarifaria_multiopera",
    "UF_CRM_1743170682":            "data_ativacao_multioperador",
    "UF_CRM_1752574797":            "data_entrega_multioperador",
    "UF_CRM_1762359813":            "n_contrato_multioperador",
    "UF_CRM_1762360077":            "n_adesao_multioperador",
    "UF_CRM_1763137816":            "inicio_fornecimento_multi",
    "UF_CRM_1760633980":            "data_pedido_proposta_multi",
    "UF_CRM_1760634235":            "tipo_contrato_multi",
    "UF_CRM_1760698050":            "producao_anual_mwh",
    "UF_CRM_1760698095":            "potencia_fotovoltaica_kwp",
    "UF_CRM_1761040794":            "id_broker",
    "UF_CRM_1771422262":            "tarifa_yes",
    "UF_CRM_1771422297":            "data_alta_yes",
    "UF_CRM_1771422347":            "data_estado_yes",
    "UF_CRM_1771422391":            "data_ativacao_yes",
    "UF_CRM_1771422506":            "data_assinatura_yes",
    "UF_CRM_1771422578":            "fatura_eletronica_yes",
    "UF_CRM_1773934475275":         "periodo_fidel_audax",
    "UF_CRM_1773934484554":         "periodo_fidel_axpo",
    "UF_CRM_1773934498227":         "periodo_fidel_iberdrola",
    "UF_CRM_1773934509645":         "periodo_fidel_galp",
    "UF_CRM_1773934519595":         "periodo_fidel_portulogos",
    "UF_CRM_1773934533391":         "periodo_fidel_nabalia",
    "UF_CRM_1773934553913":         "periodo_fidel_edp",
    "UF_CRM_1752833132":            "negocio_copiado",
    "UF_CRM_1759249757":            "cb_descontado",
    "UF_CRM_1742567768":            "possibilidade_paineis",
    "UF_CRM_1741001527":            "tarifario",
    "UF_CRM_1737564496860":         "tipo_servico",
    "UF_CRM_1737552170508":         "mensagem",
}

# Campos que são Y/N no Bitrix → boolean no PostgreSQL
BOOL_FIELDS = {"IS_NEW", "IS_RECURRING", "IS_RETURN_CUSTOMER",
               "IS_REPEATED_APPROACH", "OPENED", "CLOSED"}


def bitrix_request(method: str, params: dict) -> dict:
    """Chama a API REST do Bitrix com retry automático."""
    url = f"{BITRIX_URL}/rest/{BITRIX_TOKEN}/{method}.json"
    for attempt in range(3):
        try:
            r = requests.post(url, json=params, timeout=30)
            r.raise_for_status()
            return r.json()
        except requests.RequestException as e:
            log.warning(f"Tentativa {attempt+1}/3 falhou: {e}")
            time.sleep(2 ** attempt)
    raise RuntimeError(f"API Bitrix indisponível: {method}")


def fetch_deals(since: datetime | None = None) -> list[dict]:
    """Obtém negócios do Bitrix. Se 'since' for passado, filtra por data."""
    all_deals = []
    start = 0
    filter_param = {}
    if since:
        filter_param[">DATE_MODIFY"] = since.strftime("%Y-%m-%dT%H:%M:%S")

    while True:
        data = bitrix_request("crm.deal.list", {
            "filter": filter_param,
            "select": list(FIELD_MAP.keys()),
            "start": start,
        })
        result = data.get("result", [])
        all_deals.extend(result)
        log.info(f"  Obtidos {len(all_deals)} negócios (start={start})...")

        if data.get("next"):
            start = data["next"]
            time.sleep(0.3)   # respeitar rate limit Bitrix
        else:
            break

    return all_deals


def transform(deal: dict) -> dict:
    """Converte um registo Bitrix para o formato da tabela negocios."""
    row = {}
    for bitrix_key, pg_col in FIELD_MAP.items():
        val = deal.get(bitrix_key)

        # booleans
        if bitrix_key in BOOL_FIELDS:
            val = val == "Y" if val is not None else None

        # strings vazias → NULL
        if val == "":
            val = None

        row[pg_col] = val

    row["importado_em"] = datetime.now(timezone.utc)
    return row


def upsert_deals(conn, rows: list[dict]) -> int:
    """Insere ou actualiza registos na tabela negocios (ON CONFLICT DO UPDATE)."""
    if not rows:
        return 0

    cols = list(rows[0].keys())
    placeholders = ", ".join([f"%({c})s" for c in cols])
    updates = ", ".join([
        f"{c} = EXCLUDED.{c}"
        for c in cols if c not in ("id", "importado_em")
    ])

    sql = f"""
        INSERT INTO negocios ({", ".join(cols)})
        VALUES ({placeholders})
        ON CONFLICT (id) DO UPDATE SET
            {updates},
            atualizado_em = NOW()
    """

    with conn.cursor() as cur:
        psycopg2.extras.execute_batch(cur, sql, rows, page_size=BATCH_SIZE)
    conn.commit()
    return len(rows)


def get_last_sync(conn) -> datetime | None:
    """Lê o timestamp da última sincronização bem-sucedida."""
    with conn.cursor() as cur:
        cur.execute("""
            SELECT MAX(data_modificacao) FROM negocios
            WHERE data_modificacao IS NOT NULL
        """)
        result = cur.fetchone()
        return result[0] if result and result[0] else None


def run_sync(full: bool = False):
    log.info("=" * 55)
    log.info(f"Iniciando {'sync COMPLETO' if full else 'sync INCREMENTAL'}")

    conn = psycopg2.connect(
        host=PG_HOST, port=PG_PORT, dbname=PG_DB,
        user=PG_USER, password=PG_PASSWORD
    )

    try:
        since = None
        if not full:
            last = get_last_sync(conn)
            if last:
                # janela de segurança para evitar perder registos
                since = last - timedelta(minutes=LOOKBACK_MINS)
                log.info(f"Sync incremental desde: {since.isoformat()}")
            else:
                log.info("Sem registos na BD — a fazer sync completo")

        deals = fetch_deals(since=since)
        log.info(f"Total de negócios recebidos: {len(deals)}")

        if deals:
            rows = [transform(d) for d in deals]
            count = upsert_deals(conn, rows)
            log.info(f"UPSERT concluído: {count} registos")
        else:
            log.info("Nenhum negócio novo ou modificado.")

        log.info("Sync concluído com sucesso.")

    except Exception as e:
        log.error(f"Erro durante sync: {e}", exc_info=True)
        raise
    finally:
        conn.close()


if __name__ == "__main__":
    import sys
    full_sync = "--full" in sys.argv
    run_sync(full=full_sync)
