import sys
from config_loader import load_api_key, get_gemini_client
from doc_loader import load_lsa_document
from video_utils import download_video_and_get_info
from lsa_transcriber import transcribe_lsa_video


def main():
    print("--- LSA AI Translator ---")
    try:
        # Load API key and Gemini client
        api_key = load_api_key()
        gemini_client = get_gemini_client(api_key)
    except Exception as e:
        print(f"[ERROR] No se pudo cargar la API Key o inicializar Gemini: {e}")
        sys.exit(1)

    # Get YouTube URL from user
    youtube_url = input("Ingresa la URL del video de YouTube en LSA: ").strip()
    if not youtube_url:
        print("[ERROR] Debes ingresar una URL de YouTube.")
        sys.exit(1)

    # Download video and get info
    try:
        video_path, video_title, video_description = download_video_and_get_info(youtube_url)
        print(f"Video descargado: {video_path}\nTítulo: {video_title}\nDescripción: {video_description[:100]}...")
    except Exception as e:
        print(f"[ERROR] No se pudo descargar el video o extraer metadatos: {e}")
        sys.exit(1)

    # Load LSA documentation
    lsa_doc_path = "documentation.md"  # Puedes cambiar esto si lo deseas
    try:
        lsa_doc_text = load_lsa_document(lsa_doc_path)
        print(f"Documentación LSA cargada ({len(lsa_doc_text)} caracteres).")
    except Exception as e:
        print(f"[ERROR] No se pudo cargar la documentación LSA: {e}")
        sys.exit(1)

    # Transcribe video
    try:
        print("Transcribiendo video con Gemini... Esto puede tardar varios minutos.")
        transcription = transcribe_lsa_video(
            gemini_client,
            video_path,
            lsa_doc_text,
            video_title,
            video_description,
            youtube_url
        )
        print("\n--- TRANSCRIPCIÓN GENERADA ---\n")
        print(transcription)
    except Exception as e:
        print(f"[ERROR] Error durante la transcripción: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main() 