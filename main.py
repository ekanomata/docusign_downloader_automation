# ESPEC - ENS001

import csv
import re
import os
import logging
from pathlib import Path
from pypdf import PdfReader
from playwright.sync_api import sync_playwright, Playwright, Page, TimeoutError as PlaywrightTimeoutError
from config import DOCUSIGN_USER, DOCUSIGN_PASS, SAVE_DIR, EXTRACT_DIR, LOG_ERROR_PATH, LOG_VAL_PATH

Path(LOG_ERROR_PATH).parent.mkdir(parents=True, exist_ok=True)
Path(LOG_VAL_PATH).parent.mkdir(parents=True, exist_ok=True)

Path(LOG_VAL_PATH).write_text("", encoding="utf-8")

logging.basicConfig( # Log configurations
    filename=LOG_ERROR_PATH,
    level=logging.ERROR,
    format="%(asctime)s | %(levelname)-8s | %(message)s",
    datefmt='%Y-%m-%d %H:%M:%S',
    encoding="utf-8"
)

 # Configuration for Validation Logger

val_logger = logging.getLogger("validation")
val_logger.setLevel(logging.INFO)
val_logger.propagate = False

val_handler = logging.FileHandler(LOG_VAL_PATH, encoding="utf-8")
val_handler.setFormatter(logging.Formatter("%(asctime)s | %(levelname)-2s | %(message)s", datefmt='%Y-%m-%d %H:%M:%S'))
val_logger.addHandler(val_handler)

class DocuSignSession:     # DocuSign Session Handler w/ msedge

    LOGIN_URL = "https://account.docusign.com/username"

    def __init__(self, playwright: Playwright, headless: bool = False): 
        self.context = playwright.chromium.launch_persistent_context(user_data_dir="./.playwright_profile", headless=headless)
        self.page: Page = self.context.new_page()

    def _is_login_page(self) -> bool:
        page = self.page

        if "account.docusign.com" in page.url.lower() and "/home" not in page.url.lower():
            return True

        return page.locator('input[name="email"]').count() > 0 or page.locator('input[name="password"]').count() > 0

    def login(self, max_attempts: int = 3): # Login Function
        last_error = None

        for attempt in range(1, max_attempts + 1):
            page = self.page

            try:
                page.goto(self.LOGIN_URL)

                # 1. Username
                page.locator('input[name="email"]').wait_for()
                page.fill('input[name="email"]', DOCUSIGN_USER)
                page.click('button[type="submit"]')

                # 2. Password
                page.locator('input[name="password"]').wait_for()
                page.fill('input[name="password"]', DOCUSIGN_PASS)
                page.click('button[type="submit"]')

                # 3. Verification Code
                try:
                    page.locator('input[name="security_code"]').wait_for(timeout=5000)
                    code = input("Digite o código de verificação do e-mail: ")
                    page.fill('input[name="security_code"]', code)
                    page.click('button[type="submit"]')
                except PlaywrightTimeoutError:
                    pass

                page.wait_for_url("**/home**", timeout=15000)
                print("\n===== Login feito com sucesso =====")

                page.wait_for_load_state("networkidle") # Espera estabilização no site
                return page

            except Exception as e:
                last_error = e
                logging.exception(f"Falha no login da DocuSign (tentativa {attempt}/{max_attempts}): {e}")

                if attempt < max_attempts:
                    page.wait_for_timeout(1000)

        logging.error(
            f"Não foi possível autenticar na DocuSign após {max_attempts} tentativas | url={self.page.url} | erro_final={last_error}"
        )
        raise RuntimeError("Falha ao autenticar na DocuSign após 3 tentativas") from last_error

    def ensure_authenticated(self):
        if self._is_login_page():
            logging.error(f"Sessão expirada detectada na URL {self.page.url}. Tentando autenticar novamente.")
            self.login(max_attempts=3)

        return True

    def close(self): # Close Browser Function
        self.context.close()


class AgreementsPage: # Agreements Page Handler

    def __init__(self, page: Page):
        self.page = page

    def access_agreements(self): # Access Agreements Page
        page = self.page

        page.locator('button[data-qa="header-MANAGE-tab-button"]').wait_for()
        page.click('button[data-qa="header-MANAGE-tab-button"]')  # Access Agreements/Acordos

        page.locator('button[data-qa="date-filter-tag-dateFilter-dismiss"]').wait_for()
        page.click('button[data-qa="date-filter-tag-dateFilter-dismiss"]') # Dismisses current filters

        agreements_per_page = page.locator('select[data-qa="manage-envelopes-list.footer.pagination-pagination-dropdown"]')
        agreements_per_page.wait_for()
        agreements_per_page.select_option("50") # Determines how many agreements per page

    def select_all(self): # Select all agreements Function
        checkbox = self.page.locator('label[class="css-sbn6di"][data-qa="manage-envelopes-list.header.INTERNAL_DATA_TABLE_checkbox.checkbox-label"]')

        checkbox.wait_for()
        checkbox.click()

    def export_to_csv(self): # Export to CSV Function
        page = self.page
        csv_path = None
        
        page.locator('button[data-qa="manage-envelopes-header-actions-more"]').wait_for()
        page.click('button[data-qa="manage-envelopes-header-actions-more"]')  # Open dropdown

        export_button = page.locator('button[data-qa="manage-envelopes-header-actions-export_as_csv"]')

        try:    
            with page.expect_download() as extract_info:

                export_button.wait_for()
                export_button.click() # Click the extract button

            extracted = extract_info.value
            csv_path = os.path.join(EXTRACT_DIR, extracted.suggested_filename)
            extracted.save_as(csv_path)

        except Exception as e:
            logging.exception(f"Erro ao extrair CSV: {e}")
            raise RuntimeError(f"Falha ao exportar CSV: {e}") from e

        page.wait_for_timeout(3000)

        print(f"\n> Página exportada em CSV")

        if csv_path is None:
            raise RuntimeError("Falha ao exportar CSV: caminho do arquivo não foi definido")

        return csv_path

    def next_page(self): # Navigate to next page Function
        page = self.page

        page.locator('button[data-qa="manage-envelopes-list.footer.pagination-pagination-next"]').wait_for()
        page.click('button[data-qa="manage-envelopes-list.footer.pagination-pagination-next"]') # Avança próxima página

    def has_next_page(self): # Verifies the existence of next page Function
        next_button = self.page.locator('button[data-qa="manage-envelopes-list.footer.pagination-pagination-next"]')
        return not next_button.is_disabled()

    def restore_page(self, page_number: int):
        self.access_agreements()

        for _ in range(1, page_number):
            self.next_page()

class Downloader: # Download Archives Handler

    def __init__(self,page: Page):
        self.page = page

    def download_agreements(self):
        page = self.page

        buttons = page.locator('button[type="button"][data-qa^="manage-envelopes-list-row"][aria-label^="Baixar"]')
        checkbox = page.locator('label[class="css-sbn6di"][data-qa="download-combined-label-label"]')
        download_button = page.locator('button[class="olv-button olv-ignore-transform css-15q1h1y"][type="button"]')
        count = buttons.count()

        saved_paths = []

        for i in range(count):
            print(f"\n==== Baixando {i+1} de {count} arquivos. ====", end="\r", flush=True)


            try:
                button = buttons.nth(i)
                button.wait_for()

                # Grab the full, untruncated name from the title attribute before clicking
                full_title = button.get_attribute("aria-label")

                button.click()

                checkbox.wait_for()
                checkbox.click()

                with page.expect_download() as download_info:
                    download_button.wait_for(timeout=10000)
                    download_button.click()

                download = download_info.value
                _, extension = os.path.splitext(download.suggested_filename)

                safe_name = self._sanitize_filename(full_title)
                saved_path = self._get_unique_path(f"{safe_name}{extension}")
                download.save_as(saved_path)
                print(f"Baixado: {safe_name}{extension}", end="")

                saved_paths.append(saved_path)

                page.locator('#root[aria-hidden="true"]').wait_for(state="detached")

            except Exception as e:
                print(f"\nERRO no item {i}: {type(e).__name__}: {e}")
                logging.exception(f"Erro ao baixar o item {i}: {e}")

            page.wait_for_timeout(500)

        return saved_paths

    def _sanitize_filename(self, name: str) -> str: # Limpa caracteres especiais da string colocada
        invalid_chars = '<>:"/\\|?*'
        name = name.removeprefix("Baixar").strip()
        name = name.removesuffix(".pdf")
        for char in invalid_chars:
            name = name.replace(char, "_")
        return name.strip()

    def _get_unique_path(self, filename: str) -> str: # Verifica existência de arquivos com o mesmo nome no diretório
        name, extension = os.path.splitext(filename)
        candidate = os.path.join(SAVE_DIR, filename)
        counter = 1

        while os.path.exists(candidate):
            candidate = os.path.join(SAVE_DIR, f"{name}_{counter}{extension}")
            counter += 1

        return candidate     

class Validator:

    def __init__(self):
        pass

    def readid_csv(self, csv_path: str) -> set:
        completed_ids = set()

        with open(csv_path, newline="", encoding="utf-8") as f:
            reader = csv.reader(f)
            next(reader)

            for row in reader:
                envelope_id = row[0].strip().lower()
                status = row[2].strip()

                if status == "Completed":
                    completed_ids.add(envelope_id)

        return completed_ids
    
    def readid_pdf(self, pdf_path: str) -> str | None:
        try:
            reader = PdfReader(pdf_path)
            text = ""
            for page in reader.pages:
                text += page.extract_text() or ""

            match = re.search(r"Envelope ID:\s*([0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12})", text)
            if match:
                return match.group(1).strip().lower()
            return None
        
        except Exception as e:
            logging.exception(f"Erro ao ler PDF {pdf_path}: {e}")
            return None
        
    def matchid(self, csv_path: str, pdf_paths: list[str], page_number: int) -> None:
        completed_ids = self.readid_csv(csv_path)
        
        print("\n") # Newline

        print_counter = 0
        ok_count = 0
        total = len(pdf_paths)

        for pdf_path in pdf_paths:
            filename = os.path.basename(pdf_path)
            pdf_id = self.readid_pdf(pdf_path)
            
            print_counter += 1
            status_msg = f"> Validando {print_counter} de {total} arquivos"

            if pdf_id is None:
                val_logger.error(f"CORROMPIDO,FALHA,PAGINA={page_number},{filename}")
                print(f"{status_msg.ljust(80)}", end="\r", flush=True)
                continue

            if pdf_id in completed_ids:
                val_logger.info(f"VALIDADO,OK,PAGINA={page_number},{filename},{pdf_id}")
                print(f"{status_msg.ljust(80)}", end="\r", flush=True)
                ok_count += 1
            else:
                val_logger.warning(f"VALIDADO,ID_NAO_ENCONTRADO_NO_CSV,PAGINA={page_number},{filename}, {pdf_id}")
                print(f"{status_msg.ljust(80)}", end="\r", flush=True)
                


        print(f"\n\nValidação da página: {ok_count} de {total} PDFs validados com sucesso")

    def generate_report(self) -> None:
        expected = {}       # Completed agreements (should have been downloaded)
        not_downloadable = {}  # Any other status (never had a "Baixar" button)

        for csv_file in Path(EXTRACT_DIR).glob("*csv"):
            with open(csv_file, newline="", encoding="utf-8") as f:
                reader = csv.reader(f)
                next(reader)

                for row in reader:
                    if len(row) < 4:
                        continue

                    envelope_id = row[0].strip().lower()
                    status = row[2].strip()
                    name = row[3].strip()

                    if status == "Completed":
                        expected[envelope_id] = name
                    else:
                        not_downloadable[envelope_id] = (name, status, csv_file.name)  # keep source file too, useful info
        
        validated_ids = set()
        validated_pages = {}

        with open(LOG_VAL_PATH, encoding="utf-8") as f:
            for line in f:
                if "VALIDADO,OK" in line:
                    parts = line.strip().split(",")
                    if len(parts) >= 4:
                        page_part = parts[2].strip()
                        pdf_name = parts[3].strip()
                        pdf_id = parts[-1].strip().lower()

                        validated_ids.add(pdf_id)
                        validated_pages[pdf_id] = (page_part, pdf_name)

        missing = {eid: name for eid, name in expected.items() if eid not in validated_ids}

        report_lines = [
            "\n\n=================== RELATÓRIO FINAL ===================",
            f"Total de acordos Completed no CSV: {len(expected)}",
            f"Total validados com sucesso: {len(validated_ids)}",
            f"Acordos Completed sem validação bem-sucedida: {len(missing)}",
            f"Acordos não disponíveis para Download: {len(not_downloadable)}",
            "========================================================="
        ]

        if missing:
            report_lines.append("\nAcordos não validados:")
            for eid, name in missing.items():
                report_lines.append(f" - {eid} | {name}")
        if not_downloadable:
            report_lines.append("\nAcordos não disponíveis para download:")
            for eid, (name, status, source_csv) in not_downloadable.items():
                report_lines.append(f" - CSV: {source_csv} | {eid} | {name} | status={status}")

        if validated_pages:
            report_lines.append("\nAcordos validados por página:")
            for pdf_id, (page_part, pdf_name) in validated_pages.items():
                report_lines.append(f" - {page_part} | {pdf_id} | {pdf_name}")

        if not_downloadable and not missing:
            report_lines.append("\nTodos os acordos Completed foram validados com sucesso!")

        report_text = "\n".join(report_lines)
        val_logger.info(report_text)

def main():
    with sync_playwright() as playwright:
        session = DocuSignSession(playwright, headless=False)
        try:
            page_counter = 1
            
            session.login() # 1. Login Inicial + 2FA

            download = Downloader(session.page)
            agreements = AgreementsPage(session.page)
            validator = Validator()

            validator.generate_report()

            agreements.access_agreements() # 2. Ir para a página de acordos

            while True:    
                page_finished = False

                for recovery_attempt in range(2):
                    try:
                        session.ensure_authenticated()

                        print(f"\n=============== Página {page_counter} ===============")

                        agreements.select_all() # 3. Seleciona todos os arquivos da página
                        csv_path = agreements.export_to_csv() # 4. Exporta todos para .csv
                        saved_paths = download.download_agreements() # 5. Download de todos os acordos da página
                        validator.matchid(csv_path, saved_paths, page_counter) # 6. Verifica os IDs dos PDFs no CSV

                        if not agreements.has_next_page():
                            print("\n", "=" * 20, "\nFinalizado!\n", "=" * 20)
                            page_finished = True
                        else:
                            agreements.next_page() # 6. Pula para a próxima página
                            page_counter += 1

                        break

                    except Exception as e:
                        if session._is_login_page() and recovery_attempt == 0:
                            logging.error(
                                f"Sessão encerrada durante o processamento da página {page_counter}. "
                                f"Tentando recuperar e repetir a página. Motivo: {e}"
                            )
                            session.login(max_attempts=3)
                            agreements = AgreementsPage(session.page)
                            download = Downloader(session.page)
                            agreements.restore_page(page_counter)
                            continue

                        logging.exception(f"Erro ao processar a página {page_counter}: {e}")
                        raise

                if page_finished:
                    break

            validator.generate_report()

            session.page.wait_for_timeout(5000)  # give download time to start
        finally:
            session.close()


if __name__ == "__main__":
    main()