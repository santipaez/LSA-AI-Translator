import os
import uuid
# import re # No más expresiones regulares por ahora
from flask import Flask, render_template, request, url_for, send_from_directory, make_response
from werkzeug.utils import secure_filename
import markdown

from config_loader import load_api_key, get_gemini_client
from doc_loader import load_lsa_document
from video_utils import download_video_and_get_info, incrustar_subtitulos
from lsa_transcriber import transcribe_lsa_video
from srt_utils import markdown_to_srt

UPLOAD_FOLDER = 'uploads'
SUBTITLES_FOLDER = 'subtitles'
ALLOWED_EXTENSIONS = {'mp4', 'mov', 'avi', 'mkv'}

app = Flask(__name__)
app.secret_key = 'supersecretkey'
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.config['SUBTITLES_FOLDER'] = SUBTITLES_FOLDER
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
os.makedirs(SUBTITLES_FOLDER, exist_ok=True)

# Carga la documentación LSA una sola vez
LSA_DOC_PATH = "documentation.md"
try:
    LSA_DOC_TEXT = load_lsa_document(LSA_DOC_PATH)
except Exception as e:
    LSA_DOC_TEXT = ""
    print(f"Error cargando documentación LSA: {e}")

# Carga el cliente Gemini una sola vez
GEMINI_CLIENT = None
try:
    API_KEY = load_api_key()
    if API_KEY:
        GEMINI_CLIENT = get_gemini_client(API_KEY)
    else:
        print("Advertencia: API_KEY no cargada. La transcripción no funcionará.")
except Exception as e:
    print(f"Error inicializando Gemini: {e}")

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

@app.route('/uploads/<filename>')
def serve_uploaded_video(filename):
    return send_from_directory(app.config['UPLOAD_FOLDER'], filename)

@app.route('/', methods=['GET', 'POST'])
def index():
    transcription_main_html = None
    transcription_annotations_html = None
    error = None
    video_display_url = None
    raw_transcription_for_debug = None
    srt_download_url = None
    video_with_subs_url = None
    vtt_subtitles_url = None

    if request.method == 'POST':
        if not GEMINI_CLIENT:
            error = "El cliente de Gemini no está inicializado. Revisa la configuración de la API Key."
            return render_template('index.html', error=error)

        youtube_url = request.form.get('youtube_url', '').strip()
        file = request.files.get('video_file')
        
        video_path_for_transcription = None
        video_filename_for_web = None
        video_title = ""
        video_description = ""
        original_video_url_for_prompt = ""
        base_filename_for_srt = None

        try:
            if youtube_url:
                video_filename_for_web, video_title, video_description = download_video_and_get_info(youtube_url)
                video_path_for_transcription = os.path.join(UPLOAD_FOLDER, video_filename_for_web)
                original_video_url_for_prompt = youtube_url
                base_filename_for_srt = os.path.splitext(video_filename_for_web)[0]
                
            elif file and allowed_file(file.filename):
                original_filename = secure_filename(file.filename)
                unique_id = uuid.uuid4().hex
                video_filename_for_web = f"{unique_id}_{original_filename}"
                video_path_for_transcription = os.path.join(UPLOAD_FOLDER, video_filename_for_web)
                file.save(video_path_for_transcription)
                
                video_title = original_filename
                video_description = "Video subido localmente por el usuario."
                original_video_url_for_prompt = "Video subido localmente"
                base_filename_for_srt = f"{unique_id}_{os.path.splitext(original_filename)[0]}"
            else:
                error = "Debes ingresar una URL de YouTube válida o subir un archivo de video (mp4, mov, avi, mkv)."
                return render_template('index.html', error=error)

            if video_filename_for_web:
                 video_display_url = url_for('serve_uploaded_video', filename=video_filename_for_web)

            print(f"DEBUG app.py: Transcribiendo video desde: {video_path_for_transcription}")
            transcription_markdown_raw = transcribe_lsa_video(
                GEMINI_CLIENT,
                video_path_for_transcription,
                LSA_DOC_TEXT,
                video_title,
                video_description,
                original_video_url_for_prompt
            )
            raw_transcription_for_debug = transcription_markdown_raw 
            print(f"DEBUG app.py: Transcripción CRUDA de Gemini:\n{transcription_markdown_raw}")
            
            main_lines = []
            annotation_lines = []
            srt_content = ""

            if transcription_markdown_raw:
                for line in transcription_markdown_raw.split('\n'):
                    if line.strip().startswith("Anotaciones de LSA:"):
                        annotation_lines.append(line.strip()[len("Anotaciones de LSA:"):].strip())
                    else:
                        main_lines.append(line)
                
                if main_lines:
                    srt_content = markdown_to_srt("\n".join(main_lines))
                    if srt_content and base_filename_for_srt:
                        srt_filename = f"{base_filename_for_srt}.srt"
                        srt_filepath = os.path.join(app.config['SUBTITLES_FOLDER'], srt_filename)
                        with open(srt_filepath, 'w', encoding='utf-8') as f_srt:
                            f_srt.write(srt_content)
                        srt_download_url = url_for('download_srt', filename=srt_filename)
                        print(f"DEBUG app.py: Archivo SRT generado y guardado en {srt_filepath}")
                        print(f"DEBUG app.py: URL de descarga SRT: {srt_download_url}")
                        
                        # Generar archivo VTT para subtítulos HTML nativos
                        vtt_content = srt_to_vtt(srt_content)
                        if vtt_content:
                            vtt_filename = f"{base_filename_for_srt}.vtt"
                            vtt_filepath = os.path.join(app.config['SUBTITLES_FOLDER'], vtt_filename)
                            with open(vtt_filepath, 'w', encoding='utf-8') as f_vtt:
                                f_vtt.write(vtt_content)
                            vtt_subtitles_url = url_for('serve_subtitles', filename=vtt_filename)
                            print(f"DEBUG app.py: Archivo VTT generado y guardado en {vtt_filepath}")
                            print(f"DEBUG app.py: URL de subtítulos VTT: {vtt_subtitles_url}")
                        # Incrustar subtítulos en el video usando MoviePy/FFmpeg
                        try:
                            video_with_subs_path = os.path.join(app.config['UPLOAD_FOLDER'], f"{base_filename_for_srt}_con_subtitulos.mp4")
                            video_with_subs_path = incrustar_subtitulos(video_path_for_transcription, srt_filepath, video_with_subs_path, prefer_method='moviepy')
                            video_with_subs_url = url_for('serve_uploaded_video', filename=os.path.basename(video_with_subs_path))
                            print(f"DEBUG app.py: Video con subtítulos generado en {video_with_subs_path}")
                        except Exception as e_embed:
                            print(f"DEBUG app.py: Error al incrustar subtítulos: {e_embed}")
                            video_with_subs_url = None
                    else:
                        print("DEBUG app.py: No se generó contenido SRT o falta base_filename_for_srt.")
            
            transcription_main_html = markdown.markdown("\n".join(main_lines), extensions=['nl2br', 'fenced_code'])
            if annotation_lines:
                annotations_markdown = "\n".join([f"- {line}" for line in annotation_lines])
                transcription_annotations_html = markdown.markdown(annotations_markdown, extensions=['nl2br', 'fenced_code'])
            else:
                transcription_annotations_html = "<p>No se encontraron anotaciones de LSA específicas en esta transcripción.</p>"

            print(f"DEBUG app.py: Transcripción dividida y convertida a HTML.")

        except Exception as e:
            error = f"Ocurrió un error: {e}"
            print(f"DEBUG app.py: Error en el POST: {e}")
        
    return render_template('index.html', 
                           transcription_main_html=transcription_main_html,
                           transcription_annotations_html=transcription_annotations_html,
                           error=error, 
                           video_display_url=video_display_url,
                           raw_transcription_for_debug=raw_transcription_for_debug,
                           srt_download_url=srt_download_url,
                           video_with_subs_url=video_with_subs_url,
                           vtt_subtitles_url=vtt_subtitles_url
                           )

def srt_to_vtt(srt_content):
    """
    Convierte contenido SRT a formato WebVTT para usar en navegadores web.
    """
    if not srt_content.strip():
        return ""
    
    vtt_lines = ["WEBVTT", ""]
    
    # Procesar cada bloque SRT
    blocks = srt_content.strip().split('\n\n')
    for block in blocks:
        if not block.strip():
            continue
        
        lines = block.strip().split('\n')
        if len(lines) < 3:
            continue
        
        # Línea de tiempo (convertir comas a puntos para VTT)
        time_line = lines[1].replace(',', '.')
        
        # Texto (desde la línea 3 en adelante)
        text_content = '\n'.join(lines[2:])
        
        vtt_lines.append(time_line)
        vtt_lines.append(text_content)
        vtt_lines.append("")
    
    return '\n'.join(vtt_lines)

@app.route('/download_srt/<filename>')
def download_srt(filename):
    try:
        return send_from_directory(app.config['SUBTITLES_FOLDER'], filename, as_attachment=True,
                                 mimetype='text/plain', download_name=filename)
    except FileNotFoundError:
        return "Archivo SRT no encontrado.", 404

@app.route('/subtitles/<filename>')
def serve_subtitles(filename):
    """
    Sirve archivos de subtítulos VTT para usar en el elemento <track> del HTML.
    """
    try:
        # Determinar el tipo MIME basado en la extensión
        if filename.endswith('.vtt'):
            mimetype = 'text/vtt'
        elif filename.endswith('.srt'):
            mimetype = 'text/plain'
        else:
            mimetype = 'text/plain'
            
        return send_from_directory(app.config['SUBTITLES_FOLDER'], filename, mimetype=mimetype)
    except FileNotFoundError:
        return "Archivo de subtítulos no encontrado.", 404

if __name__ == '__main__':
    app.run(debug=True) 