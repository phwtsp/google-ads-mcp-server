import os
import re
import json
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

# Configura host/port para deploy (Render injeta PORT automaticamente)
SERVER_PORT = int(os.getenv("PORT", 8000))
mcp = FastMCP("Google Ads", host="0.0.0.0", port=SERVER_PORT)


# Cache global para o cliente Google Ads (lazy loading)
_google_ads_client = None

def get_google_ads_client():
    """
    Cria e coloca em cache o cliente do Google Ads usando variáveis de ambiente.
    Importa o google-ads apenas na primeira chamada (lazy loading).
    """
    global _google_ads_client
    if _google_ads_client is not None:
        return _google_ads_client
    
    from google.ads.googleads.client import GoogleAdsClient
    
    credentials = {
        "developer_token": os.environ.get("GOOGLE_ADS_DEVELOPER_TOKEN"),
        "client_id": os.environ.get("GOOGLE_ADS_CLIENT_ID"),
        "client_secret": os.environ.get("GOOGLE_ADS_CLIENT_SECRET"),
        "refresh_token": os.environ.get("GOOGLE_ADS_REFRESH_TOKEN"),
        "use_proto_plus": True
    }
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
    
    # 1. Tenta buscar pelo nome no dicionário ACCOUNTS
    if ACCOUNTS:
        accounts_map = {k.lower(): v for k, v in ACCOUNTS.items()}
        if identifier.lower() in accounts_map:
            raw_id = accounts_map[identifier.lower()]
            return re.sub(r"\D", "", raw_id)

    # 2. Tenta tratar como ID numérico direto
    clean_id = re.sub(r"\D", "", identifier)
    
    if not clean_id:
        # Se não resultou em números e tinha letras, provavelmente era um nome não encontrado
        if re.search(r"[a-zA-Z]", identifier):
            raise ValueError(f"Conta '{identifier}' não encontrada na lista de contas conhecidas.")
        raise ValueError("Customer ID inválido ou vazio.")
        
    return clean_id

@mcp.tool()
def google_ads_list_campaigns(customer_id: str, limit: int = 20) -> list[dict]:
    """
    Lista as campanhas ativas e suas métricas principais (Impressões, Clicks, Custo, CTR, CPC).
    Retorna os dados estruturados (JSON) para facilitar a análise.
    
    Args:
        customer_id: O Nome da conta (ex: 'Agro Baggio') OU o ID numérico da conta do Google Ads.
        limit: Número máximo de campanhas para retornar (padrão: 20).
    """
    try:
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
        raise RuntimeError(f"Erro ao listar campanhas: {str(e)}")

@mcp.tool()
def google_ads_get_search_terms(customer_id: str, days: int = 30) -> list[dict]:
    """
    Lista os termos de pesquisa reais que ativaram seus anúncios (Search Terms).
    Retorna dados estruturados.
    
    Args:
        customer_id: O Nome da conta (ex: 'Agro Baggio') OU o ID numérico da conta do Google Ads.
        days: Quantidade de dias para analisar (padrão: últimos 30 dias).
    """
    try:
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
        raise RuntimeError(f"Erro ao buscar termos: {str(e)}")

@mcp.tool()
def google_ads_run_gaql(customer_id: str, query: str) -> list[dict]:
    """
    Executa uma consulta raw GAQL (Google Ads Query Language).
    Permite buscar quaisquer métricas ou recursos disponíveis na API do Google Ads.
    
    Args:
        customer_id: O Nome da conta ou ID numérico.
        query: A string de consulta GAQL (ex: "SELECT campaign.name FROM campaign LIMIT 5").
    """
    try:
        from google.protobuf.json_format import MessageToDict
        
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
        
        return results
    except Exception as e:
        raise RuntimeError(f"Erro na execução da query GAQL: {str(e)}")

# Inicia o servidor
if __name__ == "__main__":
    # Se PORT está definido (Render/Cloud), usa SSE com auth. Senão, usa stdio (local).
    if os.getenv("PORT"):
        import uvicorn
        from starlette.applications import Starlette
        from starlette.routing import Route, Mount
        from starlette.responses import JSONResponse
        from mcp.server.sse import SseServerTransport

        MCP_API_KEY = os.getenv("MCP_API_KEY", "").strip()
        sse = SseServerTransport("/messages/")

        async def handle_sse(request):
            async with sse.connect_sse(
                request.scope, request.receive, request._send
            ) as (read_stream, write_stream):
                await mcp._mcp_server.run(
                    read_stream, write_stream,
                    mcp._mcp_server.create_initialization_options()
                )

        async def health(request):
            return JSONResponse({"status": "ok", "server": "Google Ads MCP"})

        starlette_app = Starlette(
            routes=[
                Route("/health", endpoint=health),
                Route("/sse", endpoint=handle_sse),
                Mount("/messages/", app=sse.handle_post_message),
            ]
        )

        # Middleware de autenticação Bearer token (ASGI puro — compatível com SSE)
        if MCP_API_KEY:
            inner_app = starlette_app

            async def authenticated_app(scope, receive, send):
                if scope["type"] == "http":
                    # /health liberado sem auth (para health checks do Render)
                    path = scope.get("path", "")
                    if path != "/health":
                        headers = dict(scope.get("headers", []))
                        auth_header = headers.get(b"authorization", b"").decode()
                        if not auth_header.startswith("Bearer ") or auth_header[7:] != MCP_API_KEY:
                            resp = JSONResponse({"error": "Unauthorized"}, status_code=401)
                            await resp(scope, receive, send)
                            return
                await inner_app(scope, receive, send)

            app = authenticated_app
            print("🔒 Autenticação Bearer token ativada")
        else:
            app = starlette_app
            print("⚠️ ATENÇÃO: MCP_API_KEY não definida — servidor sem autenticação!")

        print(f"🚀 Iniciando Google Ads MCP via SSE na porta {SERVER_PORT}...")
        uvicorn.run(app, host="0.0.0.0", port=SERVER_PORT)
    else:
        mcp.run()  # stdio para uso local