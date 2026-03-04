# Google Ads MCP Server for LLMs 🚀

[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![MCP Standard](https://img.shields.io/badge/MCP-Standard-green)](https://modelcontextprotocol.io/)

A powerful **Model Context Protocol (MCP)** server that connects **Google Ads API** with AI assistants like **Claude Desktop** and **Cursor IDE**.

This tool empowers your LLM workflow to **automate campaign management**, **analyze search terms**, and **execute complex GAQL queries** purely through natural language. No more manual dashboard toggling—chat with your ads data directly.

## ✨ Features

Unlock the full potential of AI-driven marketing with these core capabilities:

- **📊 Campaign Reporting**:
  - **`google_ads_list_campaigns`**: Instantly retrieve performance metrics (Impressions, Clicks, CTR, Cost, CPC) for your enabled campaigns.
- **🔍 Search Term Audits**:
  - **`google_ads_get_search_terms`**: Discover exactly what users are typing to find your ads. Optimize spend by identifying excessive costs or high-converting terms.
- **💪 Power User Queries (GAQL)**:
  - **`google_ads_run_gaql`**: Run any custom **Google Ads Query Language** statement for bespoke reporting needs.

## 🛠️ Prerequisites

- **Python 3.10** or higher.
- **Google Ads Account**: A Manager Account (MCC) or Standard Account with API access enabled.
- **API Credentials**: Developer Token, Client ID, Client Secret, and Refresh Token.
- **Package Manager**: [`uv`](https://github.com/astral-sh/uv) (recommended for speed) or standard `pip`.

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
pip install "mcp[cli]" google-ads
```

## ⚙️ Configuration

### Environment Variables

For security, credentials are passed via environment variables. Add these to your `.env` file or export them in your shell:

| Variable                     | Description                     |
| :--------------------------- | :------------------------------ |
| `GOOGLE_ADS_DEVELOPER_TOKEN` | Your Google Ads Developer Token |
| `GOOGLE_ADS_CLIENT_ID`       | OAuth2 Client ID                |
| `GOOGLE_ADS_CLIENT_SECRET`   | OAuth2 Client Secret            |
| `GOOGLE_ADS_REFRESH_TOKEN`   | OAuth2 Refresh Token            |

### Account Mapping (`accounts.json`)

Manage multiple accounts easily by mapping friendly names to Customer IDs. Create an `accounts.json` file in the root:

```json
{
  "My Client A": "123-456-7890",
  "Agency Account": "987-654-3210"
}
```

_Note: The server automatically handles hyphens, so "123-456-7890" is processed as "1234567890"._

## 📖 Usage

### Testing with MCP CLI

Run the server interactively using the MCP Inspector:

```bash
mcp dev server.py
```

### Integration: Cursor & Claude Desktop

Add this configuration to your MCP settings file (typically `~/.cursor/mcp.json` or `claude_desktop_config.json`):

```json
{
  "mcpServers": {
    "google-ads": {
      "command": "/absolute/path/to/your/venv/bin/python",
      "args": ["/absolute/path/to/mcp-google-ads/server.py"],
      "env": {
        "GOOGLE_ADS_DEVELOPER_TOKEN": "your_token",
        "GOOGLE_ADS_CLIENT_ID": "your_client_id",
        "GOOGLE_ADS_CLIENT_SECRET": "your_client_secret",
        "GOOGLE_ADS_REFRESH_TOKEN": "your_refresh_token"
      }
    }
  }
}
```

## 📄 License

This project is licensed under the [MIT License](LICENSE).
