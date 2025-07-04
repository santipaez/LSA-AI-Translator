import time
import os
import google.generativeai as genai

PROMPT_TEMPLATE_PATH = "prompt_template.md"

def load_prompt_template():
    try:
        with open(PROMPT_TEMPLATE_PATH, 'r', encoding='utf-8') as f:
            return f.read()
    except FileNotFoundError:
        raise RuntimeError(f"No se encontró el archivo de plantilla del prompt: {PROMPT_TEMPLATE_PATH}")
    except Exception as e:
        raise RuntimeError(f"Error al cargar la plantilla del prompt: {e}")

def validate_lsa_content(gemini_client, frame_paths):
    """
    Valida si los frames de muestra contienen contenido de Lengua de Señas Argentina (LSA).
    
    Args:
        gemini_client: Cliente de Gemini configurado
        frame_paths: Lista de rutas a los frames extraídos del video
    
    Returns:
        tuple: (is_lsa: bool, confidence_message: str)
    """
    if not frame_paths:
        return False, "No se pudieron extraer frames para validación"
    
    # Prompt específico para validación de contenido LSA
    validation_prompt = """
Analiza estas imágenes y determina si muestran contenido de Lengua de Señas Argentina (LSA).

CRITERIOS PARA IDENTIFICAR LSA:
✅ VÁLIDO: Personas usando las manos para comunicarse en lenguaje de señas
✅ VÁLIDO: Intérpretes de LSA activos con movimientos de manos y expresiones faciales
✅ VÁLIDO: Comunicación gestual estructurada con manos y brazos
✅ VÁLIDO: Presentadores o personas en videos informativos usando señas

❌ NO VÁLIDO: Videojuegos, deportes, animaciones sin personas reales
❌ NO VÁLIDO: Videos musicales, películas, contenido de entretenimiento general
❌ NO VÁLIDO: Personas hablando normalmente sin usar señas
❌ NO VÁLIDO: Contenido donde no hay personas visibles
❌ NO VÁLIDO: Mapas, gráficos, texto, logos sin intérpretes

INSTRUCCIONES:
- Analiza TODAS las imágenes proporcionadas
- Busca evidencia clara de comunicación en lenguaje de señas
- Responde ÚNICAMENTE con una de estas opciones:
  "SÍ" - si hay evidencia clara de contenido LSA
  "NO" - si no hay contenido LSA o es otro tipo de video
  "INCIERTO" - si no puedes determinar con certeza

Respuesta:"""

    uploaded_frames = []
    try:
        print(f"DEBUG: Validando contenido LSA con {len(frame_paths)} frames...")
        
        # Subir frames a Gemini
        for i, frame_path in enumerate(frame_paths):
            if not os.path.exists(frame_path):
                print(f"WARN: Frame no encontrado: {frame_path}")
                continue
                
            try:
                frame_file = genai.upload_file(
                    path=frame_path,
                    display_name=f"validation_frame_{i+1}",
                    mime_type="image/jpeg"
                )
                uploaded_frames.append(frame_file)
                print(f"DEBUG: Frame {i+1} subido para validación: {frame_file.name}")
            except Exception as e:
                print(f"WARN: Error subiendo frame {frame_path}: {e}")
        
        if not uploaded_frames:
            return False, "No se pudieron subir frames para validación"
        
        # Esperar a que los frames estén listos
        for frame_file in uploaded_frames:
            max_wait = 30  # Timeout más corto para frames
            start_time = time.time()
            
            while hasattr(frame_file, 'state') and frame_file.state.name == "PROCESSING" and (time.time() - start_time) < max_wait:
                time.sleep(2)
                try:
                    frame_file = genai.get_file(frame_file.name)
                except:
                    break
        
        # Generar contenido de validación
        contents = uploaded_frames + [validation_prompt]
        
        print("DEBUG: Enviando frames a Gemini para validación LSA...")
        response = gemini_client.generate_content(
            contents=contents,
            request_options={"timeout": 60}  # Timeout corto para validación
        )
        
        if not hasattr(response, 'text') or not response.text:
            return False, "No se recibió respuesta de validación de Gemini"
        
        validation_result = response.text.strip().upper()
        print(f"DEBUG: Resultado de validación LSA: '{validation_result}'")
        
        # Interpretar respuesta
        if "SÍ" in validation_result or "SI" in validation_result or "YES" in validation_result:
            return True, "Contenido LSA detectado - procediendo con transcripción completa"
        elif "NO" in validation_result:
            return False, "No se detectó contenido de Lengua de Señas en el video"
        elif "INCIERTO" in validation_result or "UNCERTAIN" in validation_result:
            return False, "No se pudo determinar si el video contiene contenido LSA"
        else:
            # Si la respuesta no es clara, ser conservador
            return False, f"Respuesta de validación no clara: {validation_result}"
        
    except Exception as e:
        print(f"DEBUG: Error durante validación LSA: {e}")
        return False, f"Error en la validación: {e}"
    
    finally:
        # Limpiar frames subidos
        for frame_file in uploaded_frames:
            try:
                if hasattr(frame_file, 'name') and frame_file.name:
                    genai.delete_file(frame_file.name)
                    print(f"DEBUG: Frame de validación eliminado: {frame_file.name}")
            except Exception as e:
                print(f"WARN: No se pudo eliminar frame de validación: {e}")

def transcribe_lsa_video(gemini_client, video_path, lsa_doc_text, video_title, video_description, video_url):
    video_file_uploaded = None
    print(f"DEBUG: Iniciando transcribe_lsa_video para video_path: {video_path}")
    try:
        print(f"DEBUG: Current working directory: {os.getcwd()}")
        abs_video_path = os.path.abspath(video_path)
        print(f"DEBUG: Intentando subir video desde path (relativo): {video_path}, absoluto: {abs_video_path}")

        if not os.path.exists(abs_video_path):
            print(f"DEBUG: Error - El archivo de video NO existe en la ruta absoluta: {abs_video_path}")
            raise RuntimeError(f"El archivo de video no existe en la ruta absoluta especificada: {abs_video_path}")
        else:
            file_size = os.path.getsize(abs_video_path)
            print(f"DEBUG: El archivo de video SÍ existe en {abs_video_path}, tamaño: {file_size} bytes.")
            if file_size == 0:
                print("DEBUG: Error - El archivo de video está vacío (0 bytes).")
                raise RuntimeError("El archivo de video está vacío y no puede ser procesado.")

        print("DEBUG: Preparándose para llamar a genai.upload_file...")
        try:
            video_file_uploaded = genai.upload_file(
                path=abs_video_path,
                display_name=os.path.basename(video_path),
                mime_type="video/mp4"
            )
            print(f"DEBUG: Llamada a genai.upload_file completada. Objeto archivo: {video_file_uploaded}")
        except Exception as upload_exception:
            print(f"DEBUG: EXCEPCIÓN directa durante genai.upload_file: {type(upload_exception).__name__} - {upload_exception}")
            raise RuntimeError(f"Error crítico durante la subida del archivo a Gemini: {upload_exception}")
        
        initial_state = "N/A"
        if hasattr(video_file_uploaded, 'state') and video_file_uploaded.state is not None and hasattr(video_file_uploaded.state, 'name'):
            initial_state = video_file_uploaded.state.name
        elif hasattr(video_file_uploaded, 'state') and video_file_uploaded.state is not None:
             initial_state = str(video_file_uploaded.state)
        print(f"DEBUG: Estado inicial del archivo en API: {initial_state}, URI: {getattr(video_file_uploaded, 'uri', 'N/A')}")

        print("DEBUG: Esperando a que el archivo esté ACTIVO...")
        max_wait = 720
        start_time_wait = time.time()
        
        current_state_name = initial_state
        if hasattr(video_file_uploaded, 'state') and hasattr(video_file_uploaded.state, 'name'):
           current_state_name = video_file_uploaded.state.name

        while current_state_name == "PROCESSING" and (time.time() - start_time_wait) < max_wait:
            time.sleep(15)
            elapsed_time = int(time.time() - start_time_wait)
            print(f"DEBUG: Esperando... {elapsed_time}s transcurridos. Refrescando estado para {video_file_uploaded.name}...")
            
            try:
                updated_file = genai.get_file(video_file_uploaded.name)
                if updated_file:
                    video_file_uploaded = updated_file
                    if hasattr(video_file_uploaded, 'state') and hasattr(video_file_uploaded.state, 'name'):
                        current_state_name = video_file_uploaded.state.name
                        print(f"DEBUG: Estado actual del archivo: {current_state_name} (URI: {video_file_uploaded.uri})")
                    else:
                        print(f"DEBUG: Archivo actualizado pero falta state.name: {video_file_uploaded}")
                        current_state_name = "UNKNOWN_AFTER_REFRESH"
                        break
                else:
                    print(f"DEBUG: genai.get_file devolvió None para {video_file_uploaded.name}. Deteniendo espera.")
                    current_state_name = "ERROR_GET_FILE_RETURNED_NONE"
                    break 
            except Exception as e_get_file:
                print(f"DEBUG: Error al llamar a genai.get_file: {e_get_file}. Deteniendo espera.")
                current_state_name = "ERROR_DURING_GET_FILE"
                break
        
        elapsed_time_total = int(time.time() - start_time_wait)
        print(f"DEBUG: Bucle de espera finalizado después de {elapsed_time_total}s.")
        
        final_state_name = "UNKNOWN"
        if hasattr(video_file_uploaded, 'state') and hasattr(video_file_uploaded.state, 'name'):
            final_state_name = video_file_uploaded.state.name
        elif hasattr(video_file_uploaded, 'state'):
             final_state_name = str(video_file_uploaded.state)

        print(f"DEBUG: Estado final del archivo antes de generar contenido: {final_state_name}")

        if final_state_name != "ACTIVE":
            if final_state_name == "PROCESSING":
                 print(f"Advertencia: El archivo aún está en estado PROCESSING después de {max_wait}s. Se intentará usar, pero podría fallar o tomar más tiempo.")
            else:
                print(f"Error Crítico: El archivo no alcanzó el estado ACTIVE (estado final: {final_state_name}). No se puede proceder con la transcripción.")
                raise RuntimeError(f"El archivo no se procesó correctamente en la API de Gemini (estado: {final_state_name}). Imposible continuar.")

        print(f"DEBUG: Archivo en estado {final_state_name}. Cargando plantilla de prompt.")
        
        # Cargar plantilla de prompt y formatear
        prompt_template_content = load_prompt_template()
        prompt = prompt_template_content.format(
            video_title=video_title,
            video_description=video_description,
            video_url=video_url,
            lsa_doc_text_chunk=lsa_doc_text[:15000] # Mantener el chunking para el prompt
        )

        print("DEBUG: Enviando solicitud a Gemini para generar contenido...")
        print(f"DEBUG: Tamaño del prompt: {len(prompt)} caracteres")
        print(f"DEBUG: Video URI: {getattr(video_file_uploaded, 'uri', 'N/A')}")
        
        response = gemini_client.generate_content(
            contents=[video_file_uploaded, prompt],
            request_options={"timeout": 1800}  # Aumentar timeout a 30 minutos para videos largos
        )
        print("DEBUG: Respuesta recibida de Gemini.")
        print(f"DEBUG: Longitud de la respuesta: {len(response.text) if hasattr(response, 'text') else 'Sin texto'} caracteres")
        
        transcription = response.text.strip()
        
        if transcription.startswith("```markdown"):
            transcription = transcription[len("```markdown"):].strip()
        if transcription.endswith("```"):
            transcription = transcription[:-3].strip()
        
        return transcription
    except Exception as e:
        print(f"DEBUG: Excepción en transcribe_lsa_video: {type(e).__name__} - {e}")
        raise RuntimeError(f"Error en la transcripción con Gemini: {e}")
    finally:
        print(f"DEBUG: Bloque finally en transcribe_lsa_video. Archivo subido: {video_file_uploaded.name if video_file_uploaded and hasattr(video_file_uploaded, 'name') else 'Ninguno o falta nombre'}")
        if video_file_uploaded and hasattr(video_file_uploaded, 'name') and video_file_uploaded.name:
            try:
                print(f"DEBUG: Intentando eliminar archivo '{video_file_uploaded.name}' de la API de Gemini.")
                genai.delete_file(video_file_uploaded.name)
                print(f"DEBUG: Archivo '{video_file_uploaded.name}' eliminado exitosamente de la API.")
            except Exception as e_delete:
                print(f"DEBUG: Advertencia: No se pudo eliminar el archivo '{video_file_uploaded.name}' de la API de Gemini: {e_delete}")
        else:
            print("DEBUG: No hay archivo para eliminar de la API, falta el atributo 'name', o es None.") 