from dotenv import load_dotenv
import os

load_dotenv()

DOCUSIGN_USER = os.getenv("DOCUSIGN_USER")
DOCUSIGN_PASS = os.getenv("DOCUSIGN_PASS")
SAVE_DIR = os.getenv("SAVE_DIR")
EXTRACT_DIR = os.getenv("EXTRACT_DIR")
LOG_ERROR_PATH = os.getenv("LOG_ERROR_PATH")
LOG_VAL_PATH = os.getenv("LOG_VAL_PATH")
