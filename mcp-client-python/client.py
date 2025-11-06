import asyncio
import os
from contextlib import AsyncExitStack
from typing import Optional
import google.generativeai as genai
from dotenv import load_dotenv

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

# Charger les variables d'environnement avec gestion d'erreur
try:
    load_dotenv()
except UnicodeDecodeError:
    print("⚠️  Erreur de lecture du fichier .env (problème d'encodage)")
    print("Recréez le fichier .env en UTF-8 sans BOM avec cette commande :")
    print('Set-Content -Path .env -Value "GOOGLE_API_KEY=votre_clé" -Encoding UTF8')
    exit(1)

class MCPClient:
    def __init__(self):
        # Initialiser les sessions
        self.session: Optional[ClientSession] = None
        self.exit_stack = AsyncExitStack()
        
        # Configurer Gemini (accepte GEMINI_API_KEY ou GOOGLE_API_KEY)
        api_key = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
        if not api_key:
            print("\n❌ ERREUR : Clé API manquante !")
            print("\nCréez un fichier .env avec :")
            print("GOOGLE_API_KEY=votre_clé_api_ici")
            print("\nOu obtenez une clé gratuite sur : https://aistudio.google.com/app/apikey")
            exit(1)
        
        genai.configure(api_key=api_key)
        
        # Liste des modèles à essayer (noms corrects basés sur votre API)
        models_to_try = [
            'gemini-2.5-flash-lite',
            'gemini-2.5-flash',
            'gemini-2.0-flash-lite',
            'gemini-2.0-flash',
        ]
        
        # Essayer chaque modèle jusqu'à en trouver un qui fonctionne
        self.model = None
        for model_name in models_to_try:
            try:
                print(f"🔄 Tentative avec le modèle : {model_name}")
                self.model = genai.GenerativeModel(model_name)
                # Test rapide pour vérifier que le modèle fonctionne
                test_response = self.model.generate_content("test")
                print(f"✅ Modèle {model_name} chargé avec succès!")
                break
            except Exception as e:
                print(f"⚠️  {model_name} non disponible : {str(e)[:100]}")
                continue
        
        if self.model is None:
            print("\n❌ ERREUR : Aucun modèle Gemini disponible!")
            print("Vérifiez votre clé API et votre connexion internet.")
            exit(1)
        
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
        
        print("\n✅ Connecté au serveur!")
        print(f"🔧 Outils disponibles: {[tool.name for tool in self.tools]}")

    def convert_tools_to_gemini_format(self):
        """Convertir les outils MCP au format Gemini"""
        gemini_tools = []
        
        for tool in self.tools:
            gemini_tool = {
                "function_declarations": [{
                    "name": tool.name,
                    "description": tool.description,
                    "parameters": tool.inputSchema
                }]
            }
            gemini_tools.append(gemini_tool)
        
        return gemini_tools

    async def process_query(self, query: str) -> str:
        """Traiter une requête avec Gemini et les outils MCP"""
        
        # Créer le chat avec les outils
        gemini_tools = self.convert_tools_to_gemini_format()
        chat = self.model.start_chat(enable_automatic_function_calling=False)
        
        # Envoyer la requête initiale
        response = chat.send_message(
            query,
            tools=gemini_tools if gemini_tools else None
        )
        
        # Traiter les appels de fonction
        max_iterations = 5
        iteration = 0
        
        while iteration < max_iterations:
            iteration += 1
            
            # Vérifier s'il y a des candidats et des parts
            if not response.candidates:
                break
            
            candidate = response.candidates[0]
            if not hasattr(candidate, 'content') or not candidate.content:
                break
            
            # Vérification plus robuste des parts
            if not hasattr(candidate.content, 'parts'):
                break
            
            parts = candidate.content.parts
            if parts is None or len(parts) == 0:
                break
                
            # Extraire les appels de fonction de manière sécurisée
            function_calls = []
            for part in parts:
                if hasattr(part, 'function_call') and part.function_call:
                    function_calls.append(part)
            
            if not function_calls:
                break
            
            # Exécuter tous les appels de fonction
            function_responses = []
            
            for function_call in function_calls:
                tool_name = function_call.function_call.name
                tool_args = dict(function_call.function_call.args)
                
                print(f"\n🔧 Appel de l'outil: {tool_name}")
                print(f"   Arguments: {tool_args}")
                
                # Exécuter l'outil via MCP
                result = await self.session.call_tool(tool_name, tool_args)
                
                # Extraire le texte du résultat
                result_text = ""
                if result.content:
                    for content in result.content:
                        if hasattr(content, 'text'):
                            result_text += content.text
                
                function_responses.append(
                    genai.protos.Part(
                        function_response=genai.protos.FunctionResponse(
                            name=tool_name,
                            response={"result": result_text}
                        )
                    )
                )
            
            # Envoyer les résultats à Gemini
            response = chat.send_message(function_responses)
        
        # Extraire la réponse finale de manière sécurisée
        if response and hasattr(response, 'text') and response.text:
            final_response = response.text
        elif response and response.candidates:
            # Fallback pour extraire le texte manuellement
            final_response = ""
            for candidate in response.candidates:
                if hasattr(candidate, 'content') and candidate.content and hasattr(candidate.content, 'parts'):
                    parts = candidate.content.parts
                    if parts:
                        for part in parts:
                            if hasattr(part, 'text'):
                                final_response += part.text
        else:
            final_response = "Désolé, je n'ai pas pu générer une réponse."
        
        return final_response

    async def chat_loop(self):
        """Boucle de chat interactive"""
        print("\n🤖 Client MCP avec Gemini démarré!")
        print("💡 Exemples de questions :")
        print("   - Prévisions météo pour New York")
        print("   - Alertes météo en Californie (CA)")
        print("\nTape 'quit' pour quitter\n")
        
        while True:
            try:
                query = input("Vous: ").strip()
                
                if query.lower() == "quit":
                    print("\n👋 Au revoir !")
                    break
                
                if not query:
                    continue
                
                response = await self.process_query(query)
                print(f"\n💬 Gemini: {response}\n")
                
            except Exception as e:
                print(f"\n❌ Erreur: {str(e)}\n")

    async def cleanup(self):
        """Nettoyer les ressources"""
        await self.exit_stack.aclose()

async def main():
    if len(os.sys.argv) < 2:
        print("❌ Usage: python client.py <chemin_vers_serveur.py>")
        print("\n📁 Exemple:")
        print("   python client.py ../weather-server-python/weather.py")
        print("\n🔑 Assurez-vous d'avoir un fichier .env avec:")
        print("   GOOGLE_API_KEY=votre_clé_api")
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