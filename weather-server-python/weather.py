import asyncio
import httpx
from mcp.server.models import InitializationOptions
import mcp.types as types
from mcp.server import NotificationOptions, Server
import mcp.server.stdio

# Constantes NWS API
NWS_API_BASE = "https://api.weather.gov"
USER_AGENT = "weather-app/1.0"

# Créer une instance du serveur
server = Server("weather")

# Fonctions helper pour l'API NWS
async def fetch_with_retry(client: httpx.AsyncClient, url: str, max_retries: int = 3):
    """Fetch with retry logic for transient failures"""
    headers = {
        "User-Agent": USER_AGENT,
        "Accept": "application/geo+json"
    }
    
    for attempt in range(max_retries):
        try:
            response = await client.get(url, headers=headers, timeout=30.0)
            response.raise_for_status()
            return response
        except (httpx.TimeoutException, httpx.HTTPStatusError) as e:
            if attempt == max_retries - 1:
                raise
            await asyncio.sleep(2 ** attempt)

def format_alert(feature: dict) -> str:
    """Format an alert feature into a readable string"""
    props = feature["properties"]
    return f"""
Event: {props.get('event', 'Unknown')}
Area: {props.get('areaDesc', 'Unknown')}
Severity: {props.get('severity', 'Unknown')}
Status: {props.get('status', 'Unknown')}
Headline: {props.get('headline', 'No headline')}
Description: {props.get('description', 'No description')}
Instructions: {props.get('instruction', 'No instructions')}
"""

# Gestionnaire de liste d'outils
@server.list_tools()
async def handle_list_tools() -> list[types.Tool]:
    """Liste les outils disponibles"""
    return [
        types.Tool(
            name="get_forecast",
            description="Obtenir les prévisions météo pour un lieu (coordonnées US uniquement)",
            inputSchema={
                "type": "object",
                "properties": {
                    "latitude": {
                        "type": "number",
                        "description": "Latitude du lieu"
                    },
                    "longitude": {
                        "type": "number",
                        "description": "Longitude du lieu"
                    }
                },
                "required": ["latitude", "longitude"]
            }
        ),
        types.Tool(
            name="get_alerts",
            description="Obtenir les alertes météo actives pour un État US",
            inputSchema={
                "type": "object",
                "properties": {
                    "state": {
                        "type": "string",
                        "description": "Code de l'État US à deux lettres (ex: CA, NY, TX)"
                    }
                },
                "required": ["state"]
            }
        )
    ]

# Gestionnaire d'exécution d'outils
@server.call_tool()
async def handle_call_tool(
    name: str,
    arguments: dict | None
) -> list[types.TextContent | types.ImageContent | types.EmbeddedResource]:
    """Exécute un outil demandé"""
    
    if not arguments:
        raise ValueError("Arguments manquants")
    
    async with httpx.AsyncClient() as client:
        if name == "get_forecast":
            latitude = arguments.get("latitude")
            longitude = arguments.get("longitude")
            
            if latitude is None or longitude is None:
                raise ValueError("Latitude et longitude requises")
            
            # Obtenir le point de grille
            points_url = f"{NWS_API_BASE}/points/{latitude},{longitude}"
            points_response = await fetch_with_retry(client, points_url)
            points_data = points_response.json()
            
            # Obtenir les prévisions
            forecast_url = points_data["properties"]["forecast"]
            forecast_response = await fetch_with_retry(client, forecast_url)
            forecast_data = forecast_response.json()
            
            # Formatter les périodes de prévisions
            periods = forecast_data["properties"]["periods"]
            forecast_text = "\n\n".join(
                f"{p['name']}:\nTemperature: {p['temperature']}°{p['temperatureUnit']}\n{p['detailedForecast']}"
                for p in periods[:5]
            )
            
            return [types.TextContent(
                type="text",
                text=forecast_text
            )]
        
        elif name == "get_alerts":
            state = arguments.get("state")
            if not state:
                raise ValueError("Code d'État requis")
            
            # Obtenir les alertes
            alerts_url = f"{NWS_API_BASE}/alerts/active?area={state}"
            alerts_response = await fetch_with_retry(client, alerts_url)
            alerts_data = alerts_response.json()
            
            features = alerts_data.get("features", [])
            
            if not features:
                return [types.TextContent(
                    type="text",
                    text=f"Aucune alerte active pour {state}"
                )]
            
            alerts_text = "\n---\n".join(format_alert(f) for f in features)
            
            return [types.TextContent(
                type="text",
                text=alerts_text
            )]
        
        else:
            raise ValueError(f"Outil inconnu: {name}")

async def main():
    """Fonction principale pour exécuter le serveur"""
    async with mcp.server.stdio.stdio_server() as (read_stream, write_stream):
        await server.run(
            read_stream,
            write_stream,
            InitializationOptions(
                server_name="weather",
                server_version="0.1.0",
                capabilities=server.get_capabilities(
                    notification_options=NotificationOptions(),
                    experimental_capabilities={}
                )
            )
        )

if __name__ == "__main__":
    asyncio.run(main())