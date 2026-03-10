# Google Ads MCP Server for LLMs

[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![MCP Standard](https://img.shields.io/badge/MCP-Standard-green)](https://modelcontextprotocol.io/)

An MCP server that connects the **Google Ads API** to assistants like **Claude Desktop** and **Cursor**.

It supports campaign analysis, search term inspection, and custom GAQL execution over a safer runtime configuration for local `stdio` use or HTTP deployment.

## Features

- `google_ads_list_accounts`
- `google_ads_list_campaigns`
- `google_ads_get_search_terms`
- `google_ads_run_gaql`

## 🛠️ Prerequisites

- **Python 3.10** or higher.
- **Google Ads Account**: A Manager Account (MCC) or Standard Account with API access enabled.
- **API Credentials**: Developer Token, Client ID, Client Secret, and Refresh Token.
- `pip` or [`uv`](https://github.com/astral-sh/uv)

## 🚀 Installation

### 1. Clone the Repository

```bash
git clone https://github.com/phwtsp/mcp-google-ads.git
cd mcp-google-ads
```

### 2. Set Up Virtual Environment

**Option A: Using `uv` (Fastest)**

```bash
uv venv
source .venv/bin/activate
```

**Option B: Using standard Python**

```bash
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate
```

### 3. Install Dependencies

```bash
pip install -r requirements.txt
```

## ⚙️ Configuration

### Environment Variables

Set these environment variables:

| Variable                     | Description                     |
| :--------------------------- | :------------------------------ |
| `GOOGLE_ADS_DEVELOPER_TOKEN` | Your Google Ads Developer Token |
| `GOOGLE_ADS_CLIENT_ID`       | OAuth2 Client ID                |
| `GOOGLE_ADS_CLIENT_SECRET`   | OAuth2 Client Secret            |
| `GOOGLE_ADS_REFRESH_TOKEN`   | OAuth2 Refresh Token            |
| `GOOGLE_ADS_LOGIN_CUSTOMER_ID` | Optional manager account ID   |
| `ACCOUNTS_JSON`              | Optional JSON map of aliases to customer IDs |
| `MCP_TRANSPORT`              | `stdio` or `streamable-http`   |
| `MCP_MOUNT_PATH`             | HTTP mount path. Default: `/mcp` |
| `MCP_API_KEY`                | Optional bearer token for HTTP mode |
| `HOST`                       | HTTP bind host. Default: `0.0.0.0` |
| `PORT`                       | HTTP bind port. Default: `8000` |

### Account Mapping (`accounts.json`)

Manage multiple accounts easily by mapping friendly names to Customer IDs. Create an `accounts.json` file in the root:

```json
{
  "My Client A": "123-456-7890",
  "Agency Account": "987-654-3210"
}
```

The server strips hyphens and validates the final ID as 10 digits.

## Usage

### Local `stdio`

This is the default mode and is the right choice for Claude Desktop or Cursor local process integrations.

```bash
python3 server.py
```

### Local inspector

```bash
mcp dev server.py
```

### HTTP deployment

Use explicit transport selection:

```bash
export MCP_TRANSPORT=streamable-http
export MCP_API_KEY=change-me
python3 server.py
```

Endpoints:

- `GET /health`
- `GET /ready`
- MCP mounted at `${MCP_MOUNT_PATH:-/mcp}`

Example with default mount path:

- `http://localhost:8000/mcp`

### Cursor or Claude Desktop config

Add this to your MCP settings:

```json
{
  "mcpServers": {
    "google-ads": {
      "command": "/absolute/path/to/your/venv/bin/python",
      "args": ["/absolute/path/to/mcp-google-ads/server.py"],
      "env": {
        "MCP_TRANSPORT": "stdio",
        "GOOGLE_ADS_DEVELOPER_TOKEN": "your_token",
        "GOOGLE_ADS_CLIENT_ID": "your_client_id",
        "GOOGLE_ADS_CLIENT_SECRET": "your_client_secret",
        "GOOGLE_ADS_REFRESH_TOKEN": "your_refresh_token"
      }
    }
  }
}
```

## Operational Notes

- `google_ads_run_gaql` only accepts read-only queries starting with `SELECT`.
- `google_ads_list_campaigns` caps `limit` at `100`.
- `google_ads_get_search_terms` caps `days` at `365`.
- Raw GAQL responses are capped at `500` rows per execution.
- In HTTP mode, `/ready` returns `503` if required Google Ads credentials are missing.

## License

This project is licensed under the [MIT License](LICENSE).
