import asyncio
import os
from contextlib import AsyncExitStack
from typing import Optional

from anthropic import Anthropic
from dotenv import load_dotenv

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

# Charger les variables d'environnement
load_dotenv()

class MCPClient:
    def __init__(self):
        # Initialiser les sessions
        self.session: Optional[ClientSession] = None
        self.exit_stack = AsyncExitStack()
        self.anthropic = Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))
        self.tools: list = []

    async def connect_to_server(self, server_script_path: str):
        """Connexion au serveur MCP"""
        
        # Déterminer le type de serveur
        is_python = server_script_path.endswith(".py")
        is_node = server_script_path.endswith(".js")
        
        if not (is_python or is_node):
            raise ValueError("Le serveur doit être un fichier .py ou .js")
        
        # Configurer les paramètres du serveur
        command = "python" if is_python else "node"
        server_params = StdioServerParameters(
            command=command,
            args=[server_script_path],
            env=None
        )
        
        # Connexion au serveur
        stdio_transport = await self.exit_stack.enter_async_context(
            stdio_client(server_params)
        )
        
        self.stdio, self.write = stdio_transport
        self.session = await self.exit_stack.enter_async_context(
            ClientSession(self.stdio, self.write)
        )
        
        await self.session.initialize()
        
        # Lister les outils disponibles
        response = await self.session.list_tools()
        self.tools = response.tools
        
        print("\nConnecté au serveur!")
        print(f"Outils disponibles: {[tool.name for tool in self.tools]}")

    async def process_query(self, query: str) -> str:
        """Traiter une requête avec Claude et les outils MCP"""
        messages = [
            {
                "role": "user",
                "content": query
            }
        ]
        
        response = self.anthropic.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=4096,
            messages=messages,
            tools=[{
                "name": tool.name,
                "description": tool.description,
                "input_schema": tool.inputSchema
            } for tool in self.tools]
        )
        
        # Traiter les appels d'outils
        while response.stop_reason == "tool_use":
            tool_results = []
            
            for content in response.content:
                if content.type == "tool_use":
                    tool_name = content.name
                    tool_args = content.input
                    
                    # Exécuter l'outil
                    result = await self.session.call_tool(tool_name, tool_args)
                    
                    tool_results.append({
                        "type": "tool_result",
                        "tool_use_id": content.id,
                        "content": result.content
                    })
            
            # Continuer la conversation avec les résultats
            messages.append({
                "role": "assistant",
                "content": response.content
            })
            messages.append({
                "role": "user",
                "content": tool_results
            })
            
            response = self.anthropic.messages.create(
                model="claude-sonnet-4-20250514",
                max_tokens=4096,
                messages=messages,
                tools=[{
                    "name": tool.name,
                    "description": tool.description,
                    "input_schema": tool.inputSchema
                } for tool in self.tools]
            )
        
        # Extraire la réponse finale
        final_response = ""
        for content in response.content:
            if hasattr(content, "text"):
                final_response += content.text
        
        return final_response

    async def chat_loop(self):
        """Boucle de chat interactive"""
        print("\nClient MCP démarré!")
        print("Tape 'quit' pour quitter\n")
        
        while True:
            try:
                query = input("Vous: ").strip()
                
                if query.lower() == "quit":
                    break
                
                if not query:
                    continue
                
                response = await self.process_query(query)
                print(f"\nClaude: {response}\n")
                
            except Exception as e:
                print(f"\nErreur: {str(e)}\n")

    async def cleanup(self):
        """Nettoyer les ressources"""
        await self.exit_stack.aclose()

async def main():
    if len(os.sys.argv) < 2:
        print("Usage: python client.py <chemin_vers_serveur.py>")
        return
    
    server_script = os.sys.argv[1]
    
    client = MCPClient()
    
    try:
        await client.connect_to_server(server_script)
        await client.chat_loop()
    finally:
        await client.cleanup()

if __name__ == "__main__":
    import sys
    os.sys = sys
    asyncio.run(main())