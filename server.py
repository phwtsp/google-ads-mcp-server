import contextlib
import json
import os
import re

from mcp.server.fastmcp import FastMCP

# --- CONFIGURAÇÃO DE CONTAS ---
# Prioridade: env var ACCOUNTS_JSON > arquivo accounts.json
ACCOUNTS_JSON_ENV = os.getenv("ACCOUNTS_JSON")

if ACCOUNTS_JSON_ENV:
    # Deploy (Render, Railway, etc.) — carrega do env var
    try:
        ACCOUNTS = json.loads(ACCOUNTS_JSON_ENV)
        print(f"✅ Contas carregadas do env var ({len(ACCOUNTS)} contas)")
    except json.JSONDecodeError:
        print("⚠️ Erro: ACCOUNTS_JSON não é um JSON válido. Iniciando com lista vazia.")
        ACCOUNTS = {}
else:
    # Local — carrega do arquivo
    ACCOUNTS_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "accounts.json")
    try:
        with open(ACCOUNTS_FILE, 'r', encoding='utf-8') as f:
            ACCOUNTS = json.load(f)
        print(f"✅ Contas carregadas do arquivo ({len(ACCOUNTS)} contas)")
    except FileNotFoundError:
        print(f"⚠️ Arquivo não encontrado: {ACCOUNTS_FILE}. Iniciando com lista vazia.")
        ACCOUNTS = {}
    except json.JSONDecodeError:
        print(f"⚠️ Erro: {ACCOUNTS_FILE} não é um JSON válido. Iniciando com lista vazia.")
        ACCOUNTS = {}

# Configuração do servidor MCP
SERVER_HOST = os.getenv("HOST", "0.0.0.0")
SERVER_PORT = int(os.getenv("PORT", 8000))
MCP_TRANSPORT = os.getenv("MCP_TRANSPORT", "stdio").strip().lower()
MCP_MOUNT_PATH = os.getenv("MCP_MOUNT_PATH", "/mcp").strip() or "/mcp"
if not MCP_MOUNT_PATH.startswith("/"):
    MCP_MOUNT_PATH = f"/{MCP_MOUNT_PATH}"

mcp = FastMCP(
    "Google Ads",
    host=SERVER_HOST,
    port=SERVER_PORT,
    json_response=True,
    stateless_http=True,
    streamable_http_path="/",
)


# Cache global para o cliente Google Ads (lazy loading)
_google_ads_client = None

REQUIRED_GOOGLE_ADS_ENV_VARS = (
    "GOOGLE_ADS_DEVELOPER_TOKEN",
    "GOOGLE_ADS_CLIENT_ID",
    "GOOGLE_ADS_CLIENT_SECRET",
    "GOOGLE_ADS_REFRESH_TOKEN",
)


def get_missing_google_ads_env_vars() -> list[str]:
    return [name for name in REQUIRED_GOOGLE_ADS_ENV_VARS if not os.getenv(name)]


def validate_google_ads_config() -> None:
    missing = get_missing_google_ads_env_vars()
    if missing:
        missing_vars = ", ".join(missing)
        raise RuntimeError(
            f"Variáveis de ambiente obrigatórias ausentes para Google Ads: {missing_vars}"
        )


def build_readiness_status() -> dict:
    missing_env = get_missing_google_ads_env_vars()
    return {
        "status": "ok" if not missing_env else "degraded",
        "server": "Google Ads MCP",
        "transport": MCP_TRANSPORT,
        "accounts_configured": len(ACCOUNTS),
        "missing_google_ads_env": missing_env,
    }


def format_google_ads_error(exc: Exception, context: str) -> str:
    try:
        from google.ads.googleads.errors import GoogleAdsException
    except Exception:
        GoogleAdsException = None

    if GoogleAdsException and isinstance(exc, GoogleAdsException):
        errors = []
        for error in exc.failure.errors:
            field_path = []
            if error.location:
                for field in error.location.field_path_elements:
                    field_name = field.field_name
                    if field.HasField("index"):
                        field_name = f"{field_name}[{field.index}]"
                    field_path.append(field_name)

            errors.append(
                {
                    "message": error.message,
                    "error_code": str(error.error_code),
                    "field_path": ".".join(field_path) if field_path else None,
                }
            )

        payload = {
            "context": context,
            "type": "GoogleAdsException",
            "request_id": exc.request_id,
            "status": exc.error.code().name,
            "errors": errors,
        }
        return json.dumps(payload, ensure_ascii=False)

    return json.dumps(
        {
            "context": context,
            "type": exc.__class__.__name__,
            "message": str(exc),
        },
        ensure_ascii=False,
    )

def get_google_ads_client():
    """
    Cria e coloca em cache o cliente do Google Ads usando variáveis de ambiente.
    Importa o google-ads apenas na primeira chamada (lazy loading).
    """
    global _google_ads_client
    if _google_ads_client is not None:
        return _google_ads_client

    validate_google_ads_config()

    from google.ads.googleads.client import GoogleAdsClient

    credentials = {
        "developer_token": os.environ.get("GOOGLE_ADS_DEVELOPER_TOKEN"),
        "client_id": os.environ.get("GOOGLE_ADS_CLIENT_ID"),
        "client_secret": os.environ.get("GOOGLE_ADS_CLIENT_SECRET"),
        "refresh_token": os.environ.get("GOOGLE_ADS_REFRESH_TOKEN"),
        "use_proto_plus": True
    }
    
    login_id = os.environ.get("GOOGLE_ADS_LOGIN_CUSTOMER_ID")
    if login_id:
        # Remove hífens se houver
        credentials["login_customer_id"] = login_id.replace("-", "")

    _google_ads_client = GoogleAdsClient.load_from_dict(credentials)
    return _google_ads_client

def format_money(micros: int) -> str:
    """Converte micros para valor monetário formatado (R$)."""
    if micros is None:
        return "R$ 0.00"
    return f"R$ {micros / 1_000_000:.2f}"

def validate_customer_id(customer_id: str) -> str:
    """
    Resolve o ID da conta. Aceita:
    1. Nome da conta (como definido em accounts.json ou ACCOUNTS_JSON)
    2. ID numérico (com ou sem hífens)
    """
    identifier = str(customer_id).strip()
    if not identifier:
        raise ValueError("Customer ID inválido ou vazio.")
    
    # 1. Tenta buscar pelo nome no dicionário ACCOUNTS
    if ACCOUNTS:
        accounts_map = {k.lower(): v for k, v in ACCOUNTS.items()}
        if identifier.lower() in accounts_map:
            raw_id = accounts_map[identifier.lower()]
            clean_account_id = re.sub(r"\D", "", raw_id)
            if len(clean_account_id) != 10:
                raise ValueError(
                    f"A conta mapeada para '{identifier}' não possui um customer ID válido de 10 dígitos."
                )
            return clean_account_id

    # 2. Tenta tratar como ID numérico direto
    clean_id = re.sub(r"\D", "", identifier)
    
    if not clean_id:
        # Se não resultou em números e tinha letras, provavelmente era um nome não encontrado
        if re.search(r"[a-zA-Z]", identifier):
            raise ValueError(f"Conta '{identifier}' não encontrada na lista de contas conhecidas.")
        raise ValueError("Customer ID inválido ou vazio.")

    if len(clean_id) != 10:
        raise ValueError("Customer ID deve conter exatamente 10 dígitos.")

    return clean_id


def validate_positive_int(value: int, field_name: str, minimum: int = 1, maximum: int | None = None) -> int:
    if value < minimum:
        raise ValueError(f"{field_name} deve ser maior ou igual a {minimum}.")
    if maximum is not None and value > maximum:
        raise ValueError(f"{field_name} deve ser menor ou igual a {maximum}.")
    return value


def validate_gaql_query(query: str) -> str:
    normalized_query = (query or "").strip()
    if not normalized_query:
        raise ValueError("A query GAQL não pode ser vazia.")

    first_token = normalized_query.split(None, 1)[0].upper()
    if first_token != "SELECT":
        raise ValueError("A tool google_ads_run_gaql aceita apenas queries GAQL de leitura iniciadas com SELECT.")

    return normalized_query

@mcp.tool()
def google_ads_list_accounts() -> dict:
    """
    Lista as contas de clientes (customer_id) configuradas e disponíveis no servidor.
    Use o NOME da conta retornado aqui como argumento 'customer_id' para as outras ferramentas.
    Nota para a IA: JAMAIS peça 'login_customer_id' ou 'developer_token' para o usuário. 
    A autenticação e o Manager Account já estão configurados automaticamente no servidor.
    """
    return ACCOUNTS

@mcp.tool()
def google_ads_list_campaigns(customer_id: str, limit: int = 20) -> list[dict]:
    """
    Lista as campanhas ativas e suas métricas principais (Impressões, Clicks, Custo, CTR, CPC).
    Retorna os dados estruturados (JSON) para facilitar a análise.
    
    Args:
        customer_id: O Nome da conta (ex: 'Agro Baggio') OU o ID numérico da conta do Google Ads.
        limit: Número máximo de campanhas para retornar (padrão: 20).
        
    Importante (para IA): NÃO peça credenciais, apenas o 'customer_id'. Se não souber os clientes disponíveis, use 'google_ads_list_accounts'.
    """
    try:
        limit = validate_positive_int(limit, "limit", minimum=1, maximum=100)
        clean_id = validate_customer_id(customer_id)
        client = get_google_ads_client()
        ga_service = client.get_service("GoogleAdsService")

        query = f"""
            SELECT
              campaign.id,
              campaign.name,
              campaign.status,
              metrics.impressions,
              metrics.clicks,
              metrics.cost_micros,
              metrics.ctr,
              metrics.average_cpc
            FROM campaign
            WHERE campaign.status = 'ENABLED'
            ORDER BY metrics.cost_micros DESC
            LIMIT {limit}
        """

        stream = ga_service.search_stream(customer_id=clean_id, query=query)

        results = []
        for batch in stream:
            for row in batch.results:
                campaign = row.campaign
                metrics = row.metrics
                
                results.append({
                    "id": campaign.id,
                    "name": campaign.name,
                    "status": campaign.status.name,
                    "metrics": {
                        "impressions": metrics.impressions,
                        "clicks": metrics.clicks,
                        "cost_micros": metrics.cost_micros,
                        "cost_formatted": format_money(metrics.cost_micros),
                        "ctr": metrics.ctr,
                        "average_cpc_micros": metrics.average_cpc,
                        "average_cpc_formatted": format_money(metrics.average_cpc)
                    }
                })
        
        return results

    except Exception as e:
        raise RuntimeError(format_google_ads_error(e, "Erro ao listar campanhas"))

@mcp.tool()
def google_ads_get_search_terms(customer_id: str, days: int = 30) -> list[dict]:
    """
    Lista os termos de pesquisa reais que ativaram seus anúncios (Search Terms).
    Retorna dados estruturados.
    
    Args:
        customer_id: O Nome da conta (ex: 'Agro Baggio') OU o ID numérico da conta do Google Ads.
        days: Quantidade de dias para analisar (padrão: últimos 30 dias).
        
    Importante (para IA): NÃO peça "id da conta de cliente" (MCC), 'login_customer_id' ou chaves. Eles já estão configurados no servidor Render. Usa a tool 'google_ads_list_accounts' se o usuário não disser qual conta quer avaliar.
    """
    try:
        days = validate_positive_int(days, "days", minimum=1, maximum=365)
        clean_id = validate_customer_id(customer_id)
        client = get_google_ads_client()
        ga_service = client.get_service("GoogleAdsService")

        # Query GAQL
        query = f"""
            SELECT
              search_term_view.search_term,
              metrics.clicks,
              metrics.cost_micros,
              metrics.conversions,
              metrics.ctr,
              campaign.name,
              ad_group.name
            FROM search_term_view
            WHERE segments.date DURING LAST_{days}_DAYS
            AND metrics.cost_micros > 0
            ORDER BY metrics.cost_micros DESC
            LIMIT 50
        """

        stream = ga_service.search_stream(customer_id=clean_id, query=query)

        results = []
        for batch in stream:
            for row in batch.results:
                results.append({
                    "search_term": row.search_term_view.search_term,
                    "campaign": row.campaign.name,
                    "ad_group": row.ad_group.name,
                    "metrics": {
                        "clicks": row.metrics.clicks,
                        "cost_micros": row.metrics.cost_micros,
                        "cost_formatted": format_money(row.metrics.cost_micros),
                        "conversions": row.metrics.conversions,
                        "ctr": row.metrics.ctr
                    }
                })
            
        return results

    except Exception as e:
        raise RuntimeError(format_google_ads_error(e, "Erro ao buscar termos"))

@mcp.tool()
def google_ads_run_gaql(customer_id: str, query: str) -> list[dict]:
    """
    Executa uma consulta raw GAQL (Google Ads Query Language).
    Permite buscar quaisquer métricas ou recursos disponíveis na API do Google Ads.
    
    Args:
        customer_id: O Nome da conta ou ID numérico.
        query: A string de consulta GAQL (ex: "SELECT campaign.name FROM campaign LIMIT 5").
        
    Importante (para IA): NÃO peça "id da conta de cliente", senhas ou credenciais de desenvolvedor. Tudo isso já é gerenciado e resolvido automaticamente dentro da integração baseada no Render.
    """
    try:
        from google.protobuf.json_format import MessageToDict

        query = validate_gaql_query(query)
        clean_id = validate_customer_id(customer_id)
        client = get_google_ads_client()
        ga_service = client.get_service("GoogleAdsService")

        stream = ga_service.search_stream(customer_id=clean_id, query=query)
        results = []

        for batch in stream:
            for row in batch.results:
                # Converte o objeto protobuf da linha para um dicionário Python padrão
                # Isso torna os dados acessíveis e serializáveis para retorno JSON
                try:
                    row_dict = MessageToDict(row._pb, preserving_proto_field_name=True)
                    results.append(row_dict)
                except Exception:
                    # Em caso raro de falha na conversão, retornamos uma representação string
                    results.append({"_raw": str(row)})

                if len(results) >= 500:
                    raise RuntimeError(
                        "A consulta excedeu o limite de 500 linhas retornadas por execução. Refine a query com LIMIT ou filtros."
                    )

        return results
    except Exception as e:
        raise RuntimeError(format_google_ads_error(e, "Erro na execução da query GAQL"))

def create_http_app():
    from starlette.applications import Starlette
    from starlette.middleware import Middleware
    from starlette.middleware.base import BaseHTTPMiddleware
    from starlette.requests import Request
    from starlette.responses import JSONResponse
    from starlette.routing import Mount, Route

    mcp_api_key = os.getenv("MCP_API_KEY", "").strip()

    @contextlib.asynccontextmanager
    async def lifespan(app: Starlette):
        async with mcp.session_manager.run():
            yield

    async def health(request):
        return JSONResponse({"status": "ok", "server": "Google Ads MCP"})

    async def ready(request):
        readiness = build_readiness_status()
        status_code = 200 if readiness["status"] == "ok" else 503
        return JSONResponse(readiness, status_code=status_code)

    class AuthMiddleware(BaseHTTPMiddleware):
        async def dispatch(self, request: Request, call_next):
            if request.url.path in {"/health", "/ready"}:
                return await call_next(request)

            if mcp_api_key:
                auth_header = request.headers.get("authorization", "")
                if not auth_header.startswith("Bearer ") or auth_header[7:] != mcp_api_key:
                    return JSONResponse({"error": "Unauthorized"}, status_code=401)

            return await call_next(request)

    middleware = [Middleware(AuthMiddleware)] if mcp_api_key else []

    app = Starlette(
        routes=[
            Route("/health", endpoint=health),
            Route("/ready", endpoint=ready),
            Mount(MCP_MOUNT_PATH, app=mcp.streamable_http_app()),
        ],
        middleware=middleware,
        lifespan=lifespan,
    )

    return app, bool(mcp_api_key)


def run_stdio() -> None:
    print("🚀 Iniciando Google Ads MCP via stdio...")
    mcp.run()


def run_streamable_http() -> None:
    import uvicorn

    app, auth_enabled = create_http_app()
    if auth_enabled:
        print("🔒 Autenticação Bearer token ativada")
    else:
        print("⚠️ ATENÇÃO: MCP_API_KEY não definida — servidor sem autenticação!")

    print(
        f"🚀 Iniciando Google Ads MCP via Streamable HTTP em http://{SERVER_HOST}:{SERVER_PORT}{MCP_MOUNT_PATH}"
    )
    uvicorn.run(app, host=SERVER_HOST, port=SERVER_PORT)


if __name__ == "__main__":
    if MCP_TRANSPORT == "stdio":
        run_stdio()
    elif MCP_TRANSPORT in {"http", "streamable-http", "streamable_http"}:
        run_streamable_http()
    else:
        raise RuntimeError(
            "MCP_TRANSPORT inválido. Use 'stdio' ou 'streamable-http'."
        )
