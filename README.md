# sincro_bitrix — Sincronização Bitrix CRM → PostgreSQL

Serviço Python que sincroniza automaticamente os negócios do Bitrix CRM para a base de dados PostgreSQL, permitindo análise e reporting via Power BI.

---

## Arquitectura

```
Bitrix CRM  ──(REST API)──►  sincro_bitrix.py  ──(UPSERT)──►  PostgreSQL  ──►  Power BI
                                    │
                              .env (credenciais)
                              sync_log.txt (logs)
```

---

## Pré-requisitos

- Python 3.11+
- Acesso à API REST do Bitrix24 (webhook com permissão `crm`)
- Base de dados PostgreSQL já criada com o schema `DW_Energia-v1.sql`
- (Recomendado) [Neon](https://neon.com) — PostgreSQL gratuito em Frankfurt, RGPD compliant

---

## Instalação

### 1. Clonar ou copiar os ficheiros

```
sincro_bitrix.py
DW_Energia-v1.sql
.env
README.md
```

### 2. Instalar dependências

```bash
pip install requests psycopg2-binary python-dotenv
```

### 3. Criar o ficheiro `.env`

```bash
cp .env.example .env
```

Editar o `.env` com as tuas credenciais:

```env
# Bitrix CRM
BITRIX_URL=https://dominio.bitrix24.com
BITRIX_TOKEN=xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx

# PostgreSQL (exemplo Neon)
PG_HOST=db.xxxxxxxxxxxx.neon.co
PG_PORT=
PG_DB=postgres
PG_USER=postgres
PG_PASSWORD=a_tua_password

# Sincronização
BATCH_SIZE=50
LOOKBACK_MINS=20
```

> ⚠️ Nunca coloques o `.env` no git. Adiciona-o ao `.gitignore`.

### 4. Criar o schema na base de dados

```bash
psql -U postgres -d postgres -f DW_Energia-v1.sql
```

Ou, no Supabase, vai a **SQL Editor** e cola o conteúdo do ficheiro.

### 5. Primeira sincronização (carga completa)

```bash
python sync_bitrix.py --full
```

---

## Utilização

### Sync incremental (normal)

Busca apenas os negócios modificados desde a última execução, com uma janela de segurança de 20 minutos para não perder registos.

```bash
python sync_bitrix.py
```

### Sync completo

Recarrega todos os negócios do Bitrix. Usar apenas na primeira vez ou para reconstruir a base de dados.

```bash
python sync_bitrix.py --full
```

---

## Agendamento automático

### Linux / macOS (cron)

```bash
crontab -e
```

Adicionar a linha para executar a cada 15 minutos:

```
*/15 * * * * cd /caminho/do/projeto && python sync_bitrix.py >> sync_log.txt 2>&1
```

### Windows (Agendador de Tarefas)

```cmd
schtasks /create /sc minute /mo 15 /tn "SyncBitrix" /tr "python C:\caminho\sync_bitrix.py"
```

---

## Como obter o token do Bitrix

1. No Bitrix24, ir a **Configurações → Integrações → Webhooks de entrada**
2. Clicar em **Adicionar webhook**
3. Seleccionar a permissão **CRM** (apenas leitura)
4. Copiar o URL gerado — tem o formato:
   ```
   https://seudominio.bitrix24.com/rest/1/xxxxxxxxxxxxxxxx/
   ```
5. O `BITRIX_URL` é `https://seudominio.bitrix24.com`
6. O `BITRIX_TOKEN` é o código após `/rest/1/` (ex: `xxxxxxxxxxxxxxxx`)

---

## Campos sincronizados

O serviço sincroniza **~200 campos** do Bitrix, organizados por categoria:

| Categoria | Exemplos |
|---|---|
| Standard Bitrix | ID, título, fase, pipeline, probabilidade, total |
| Cliente | NIF, email, telefone, cartão cidadão, data nascimento |
| Morada | Morada fornecimento, código postal, distrito, concelho |
| Instalação | CPE, CUI, potência, tensão, opção horária, tarifa |
| Contrato | Operadora, IBAN, forma pagamento, data fidelização |
| Comercial | Comercial, campanha, estrutura, origem lead, segmento |
| Preços | Margem luz/gás, consumo anual, preços por período |
| Endesa | Agente, auditoria, campanha, código canal, CS/OPP |
| Repsol | Tipo venda, datas CPE/CUI, documentação |
| Galp | Campanha, serviços adicionais, nº cartão Continente |
| Multioperador | Segmento, potência, nº painéis, proposta, ativação |
| YES | Tarifa, datas alta/ativação/assinatura |

O mapeamento completo está na variável `FIELD_MAP` do script.

---

## Views disponíveis para Power BI

Após a sincronização, estas views estão prontas para ligar directamente ao Power BI:

| View | Descrição |
|---|---|
| `v_ganhos_por_operadora` | Negócios ganhos por mês, operadora, segmento e distrito |
| `v_pipeline_atual` | Negócios em aberto por fase e comercial |
| `v_performance_comercial` | Taxa de conversão e valor ganho por comercial/campanha |
| `v_instalacoes` | CPE/CUI com consumos, margens e tarifas |
| `v_negocios_perdidos` | Análise de motivos KO e anulados |

### Ligar ao Power BI

1. **Obter Dados → Base de dados PostgreSQL**
2. Servidor: `db.xxxxxxxxxxxx.supabase.co` (ou o teu host)
3. Base de dados: `postgres`
4. Modo: **Import** (recomendado) ou DirectQuery
5. Seleccionar as views pretendidas

---

## Estrutura da fase (`fase_grupo`)

O campo `fase_grupo` segue a lógica nativa do Bitrix:

| Valor | Significado |
|---|---|
| `W` | Work — negócio em processo |
| `S` | Success — negócio ganho |
| `F` | Fail — negócio perdido ou anulado |

Este campo é o mais útil para filtrar rapidamente no Power BI.

---

## Logs

O serviço escreve logs em `sync_log.txt` e no terminal:

```
2025-05-04 10:00:01 [INFO] Iniciando sync INCREMENTAL
2025-05-04 10:00:01 [INFO] Sync incremental desde: 2025-05-04T09:40:00
2025-05-04 10:00:03 [INFO]   Obtidos 47 negócios (start=0)...
2025-05-04 10:00:03 [INFO] Total de negócios recebidos: 47
2025-05-04 10:00:04 [INFO] UPSERT concluído: 47 registos
2025-05-04 10:00:04 [INFO] Sync concluído com sucesso.
```

Em caso de erro, o log inclui o traceback completo para diagnóstico.

---

## Troubleshooting

**Erro 401 / token inválido**
Verificar o `BITRIX_TOKEN` no `.env`. O token expira se o webhook for regenerado no Bitrix.

**Erro de ligação ao PostgreSQL**
Confirmar que o `PG_HOST`, `PG_PORT`, `PG_USER` e `PG_PASSWORD` estão correctos. No Supabase, usar a connection string da secção **Settings → Database**.

**Campos a NULL inesperadamente**
Verificar se o campo existe no mapa `FIELD_MAP` do script. Campos novos adicionados ao Bitrix precisam de ser mapeados manualmente.

**Sync muito lento**
Reduzir o `BATCH_SIZE` no `.env` para 25 ou aumentar o intervalo do cron.

---

## Ficheiros do projecto

```
.
├── sync_bitrix.py          # Serviço de sincronização principal
├── DW_Energia-v1.sql # Schema PostgreSQL (tabela + views)
├── .env                    # Credenciais (não versionar)
├── .env.example            # Template de credenciais
├── sync_log.txt            # Log de execuções (gerado automaticamente)
└── README.md               # Esta documentação
```

---

## Licença

Uso interno. Todos os direitos reservados.
# sincronizacao-dados-bitrix
