import os


def load_lsa_document(path):
    """
    Loads the LSA documentation from a .md file (or .docx in the future) and returns its content as a string.
    Raises FileNotFoundError if the file does not exist.
    Raises ValueError if the file is empty.
    """
    if not os.path.exists(path):
        raise FileNotFoundError(f"El archivo de documentación LSA no existe: {path}")

    with open(path, 'r', encoding='utf-8') as f:
        content = f.read()

    if not content.strip():
        raise ValueError(f"El archivo de documentación LSA está vacío: {path}")

    return content 