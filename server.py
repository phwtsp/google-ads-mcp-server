import os
import re
import json
import functools
from mcp.server.fastmcp import FastMCP
from google.ads.googleads.client import GoogleAdsClient
from google.protobuf.json_format import MessageToDict

# Inicializa o servidor MCP
mcp = FastMCP("Google Ads")

# Caminho para o arquivo de mapeamento de contas
ACCOUNTS_FILE = os.path.join(os.path.dirname(__file__), "accounts.json")

@functools.lru_cache(maxsize=None)
def get_google_ads_client():
    """
    Cria e coloca em cache o cliente do Google Ads usando variáveis de ambiente.
    Isso evita recriar o cliente a cada requisição.
    """
    credentials = {
        "developer_token": os.environ.get("GOOGLE_ADS_DEVELOPER_TOKEN"),
        "client_id": os.environ.get("GOOGLE_ADS_CLIENT_ID"),
        "client_secret": os.environ.get("GOOGLE_ADS_CLIENT_SECRET"),
        "refresh_token": os.environ.get("GOOGLE_ADS_REFRESH_TOKEN"),
        "use_proto_plus": True
    }
    return GoogleAdsClient.load_from_dict(credentials)

def format_money(micros: int) -> str:
    """Converte micros para valor monetário formatado (R$)."""
    if micros is None:
        return "R$ 0.00"
    return f"R$ {micros / 1_000_000:.2f}"

def validate_customer_id(customer_id: str) -> str:
    """
    Resolve o ID da conta. Aceita:
    1. Nome da conta (como definido em accounts.json)
    2. ID numérico (com ou sem hífens)
    """
    identifier = str(customer_id).strip()
    
    # 1. Tenta buscar pelo nome no arquivo accounts.json
    try:
        if os.path.exists(ACCOUNTS_FILE):
            with open(ACCOUNTS_FILE, 'r', encoding='utf-8') as f:
                accounts = json.load(f)
                # Busca case-insensitive
                accounts_map = {k.lower(): v for k, v in accounts.items()}
                
                if identifier.lower() in accounts_map:
                    raw_id = accounts_map[identifier.lower()]
                    return re.sub(r"\D", "", raw_id)
    except Exception as e:
        # Em caso de erro na leitura do arquivo, segue tentando usar como ID numérico
        pass

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
    mcp.run()