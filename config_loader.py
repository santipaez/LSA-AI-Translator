# config_loader.py

import os
from dotenv import load_dotenv
import google.generativeai as genai

def load_api_key(env_var_name="GOOGLE_API_KEY", dotenv_path=".env"):
    """
    Carga la API Key de Gemini desde un archivo .env o variable de entorno.
    Lanza una excepción si no se encuentra la clave.
    """
    load_dotenv(dotenv_path)
    api_key = os.getenv(env_var_name)
    if not api_key:
        raise ValueError(f"No se encontró la variable {env_var_name} en el entorno o en {dotenv_path}")
    return api_key

def get_gemini_client(api_key, model_name="models/gemini-2.5-flash-preview-04-17"):
    """
    Configura y retorna el cliente de Gemini listo para usar.
    """
    try:
        genai.configure(api_key=api_key)
        client = genai.GenerativeModel(model_name=model_name)
        return client
    except Exception as e:
        raise RuntimeError(f"Error configurando el cliente de Gemini: {e}")