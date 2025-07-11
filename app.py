import os
import uuid
import re
import subprocess
# import re # No más expresiones regulares por ahora
from flask import Flask, render_template, request, url_for, send_from_directory, make_response
from werkzeug.utils import secure_filename
import markdown

from config_loader import load_api_key, get_gemini_client
from doc_loader import load_lsa_document
from video_utils import download_video_and_get_info, incrustar_subtitulos, extract_sample_frames, cleanup_sample_frames
from lsa_transcriber import transcribe_lsa_video, validate_lsa_content
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
            
            # Obtener duración del video para validación
            video_duration = extract_video_duration(video_path_for_transcription)
            if video_duration:
                print(f"DEBUG app.py: Duración del video: {video_duration/60:.1f} minutos")
            
            # NUEVA VALIDACIÓN: Verificar si el video contiene contenido LSA
            print("DEBUG app.py: Iniciando validación de contenido LSA...")
            sample_frames = None
            try:
                # Extraer frames de muestra para validación
                sample_frames = extract_sample_frames(video_path_for_transcription, num_frames=2)
                print(f"DEBUG app.py: Extraídos {len(sample_frames)} frames para validación")
                
                # Validar contenido LSA
                is_lsa, validation_message = validate_lsa_content(GEMINI_CLIENT, sample_frames)
                print(f"DEBUG app.py: Resultado validación LSA: {is_lsa} - {validation_message}")
                
                if not is_lsa:
                    error = f"❌ Validación fallida: {validation_message}. " \
                           f"Este video no parece contener Lengua de Señas Argentina (LSA). " \
                           f"Por favor, sube un video donde personas estén comunicándose activamente en LSA."
                    return render_template('index.html', 
                                         error=error, 
                                         video_display_url=video_display_url)
                
                print(f"DEBUG app.py: ✅ Validación LSA exitosa: {validation_message}")
                
            except Exception as e_validation:
                print(f"WARN app.py: Error en validación LSA: {e_validation}")
                # En caso de error en validación, permitir continuar pero advertir al usuario
                validation_warning = f"⚠️ No se pudo validar el contenido del video ({e_validation}). Procediendo con precaución..."
                print(f"DEBUG app.py: {validation_warning}")
            
            finally:
                # Limpiar frames temporales
                if sample_frames:
                    cleanup_sample_frames(sample_frames)
            
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
            
            # Validar completitud de la transcripción
            if video_duration:
                is_complete, validation_msg = validate_transcription_completeness(transcription_markdown_raw, video_duration)
                print(f"DEBUG app.py: {validation_msg}")
                if not is_complete:
                    # Agregar advertencia a la transcripción para que sea visible al usuario
                    transcription_markdown_raw = f"**{validation_msg}**\n\n{transcription_markdown_raw}"
            
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

def extract_video_duration(video_path):
    """
    Extrae la duración del video usando ffprobe
    """
    try:
        cmd = [
            'ffprobe', '-v', 'quiet', '-show_entries', 'format=duration',
            '-of', 'default=noprint_wrappers=1:nokey=1', video_path
        ]
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        if result.returncode == 0:
            duration_seconds = float(result.stdout.strip())
            return duration_seconds
        else:
            print(f"WARN: No se pudo obtener duración del video: {result.stderr}")
            return None
    except Exception as e:
        print(f"WARN: Error obteniendo duración del video: {e}")
        return None

def validate_transcription_completeness(transcription_text, video_duration_seconds):
    """
    Valida si la transcripción parece completa comparando con la duración del video
    """
    if not transcription_text or not video_duration_seconds:
        return True, "No se puede validar - falta información"
    
    # Buscar todos los timestamps en la transcripción
    timestamp_pattern = r'\((\d{1,2}):(\d{2})(?::(\d{2}))?\-(\d{1,2}):(\d{2})(?::(\d{2}))?\)'
    matches = re.findall(timestamp_pattern, transcription_text)
    
    if not matches:
        return False, "No se encontraron timestamps en la transcripción"
    
    # Obtener el último timestamp
    last_match = matches[-1]
    end_hours = int(last_match[3])
    end_minutes = int(last_match[4])
    end_seconds = int(last_match[5]) if last_match[5] else 0
    
    last_timestamp_seconds = end_hours * 3600 + end_minutes * 60 + end_seconds
    
    # Considerar completo si está dentro del 90% de la duración total
    completion_ratio = last_timestamp_seconds / video_duration_seconds
    
    if completion_ratio < 0.9:
        warning_msg = f"⚠️ ADVERTENCIA: La transcripción parece incompleta. Video: {video_duration_seconds/60:.1f}min, Transcripción hasta: {last_timestamp_seconds/60:.1f}min ({completion_ratio*100:.1f}%)"
        return False, warning_msg
    else:
        success_msg = f"✅ Transcripción completa: {completion_ratio*100:.1f}% del video procesado"
        return True, success_msg

if __name__ == '__main__':
    app.run(debug=True) 