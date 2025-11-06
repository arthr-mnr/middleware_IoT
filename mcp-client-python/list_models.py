import google.generativeai as genai
import os
from dotenv import load_dotenv

# Charger les variables d'environnement
load_dotenv()

# Configurer l'API
api_key = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
if not api_key:
    print("❌ Clé API manquante dans le fichier .env")
    exit(1)

genai.configure(api_key=api_key)

print("=" * 80)
print("📋 LISTE DES MODÈLES GEMINI DISPONIBLES")
print("=" * 80)

try:
    models = genai.list_models()
    
    # Filtrer les modèles qui supportent generateContent
    generate_content_models = []
    
    for model in models:
        print(f"\n🔹 Modèle: {model.name}")
        print(f"   Nom d'affichage: {model.display_name}")
        print(f"   Description: {model.description}")
        print(f"   Méthodes supportées: {model.supported_generation_methods}")
        
        if 'generateContent' in model.supported_generation_methods:
            generate_content_models.append(model.name)
            print(f"   ✅ Supporte generateContent")
        else:
            print(f"   ❌ Ne supporte pas generateContent")
    
    print("\n" + "=" * 80)
    print("🎯 MODÈLES COMPATIBLES AVEC VOTRE APPLICATION")
    print("=" * 80)
    
    if generate_content_models:
        print("\nVous pouvez utiliser ces modèles :")
        for i, model_name in enumerate(generate_content_models, 1):
            # Extraire juste le nom du modèle (sans le préfixe 'models/')
            clean_name = model_name.replace('models/', '')
            print(f"  {i}. {clean_name}")
        
        print("\n💡 Pour utiliser un modèle, copiez son nom (sans 'models/')")
        print("   Exemple: genai.GenerativeModel('gemini-1.5-flash-002')")
    else:
        print("❌ Aucun modèle compatible trouvé!")
        print("Vérifiez votre clé API et votre connexion internet.")
    
except Exception as e:
    print(f"\n❌ Erreur lors de la récupération des modèles: {str(e)}")
    print("\nVérifiez:")
    print("  1. Que votre clé API est valide")
    print("  2. Que vous avez une connexion internet")
    print("  3. Que le package google-generativeai est à jour:")
    print("     pip install --upgrade google-generativeai")