import sys
import os
import socket
import tempfile
import pandas as pd
from datetime import datetime, timedelta
from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, 
    QLabel, QLineEdit, QPushButton, QFileDialog, QMessageBox, QTableWidget,
    QTableWidgetItem, QHeaderView, QGroupBox, QStatusBar, QGridLayout, QCheckBox,
    QCalendarWidget, QScrollArea, QDialog, QFrame, QStyle, QAbstractItemView,
    QTextEdit, QTabWidget
)
from PyQt6.QtCore import Qt, QThread, pyqtSignal, QObject, QDate, QPoint, QRect, QTimer, QPropertyAnimation, QEasingCurve
from PyQt6.QtGui import QColor, QAction, QIcon, QPalette, QPixmap, QTransform, QPainter, QBrush, QKeySequence, QShortcut
import re
import subprocess
import json
from approval_audit import (
    approval_confirmation_values,
    approval_flow,
    build_approval_precheck_decision,
    approval_template_name,
    build_approval_audit_html,
    compact_text,
    compare_payment_details,
    expected_to_bic,
    format_approved_payments_pdf_name,
    format_payment_copy,
    is_reportable_payment_copy_result,
    is_successful_approval_result_status,
    is_verify_no_search_item_warning,
    normalize_amount,
    normalize_date,
    parse_reference_lines,
)
from payment_mapping import (
    build_narrative,
    format_amount,
    get_pacs_amount_field_ids,
    is_valid_payment_code,
    resolve_payment_template,
)
from browser_launch import build_edge_cdp_args, get_browser_launch_options, wait_for_cdp_endpoint
from pdf_export import render_html_pdf_with_playwright

# SpinningIcon class - a QLabel that displays a spinning image
class SpinningIcon(QLabel):
    def __init__(self, parent=None, size=24):
        super().__init__(parent)
        self.size = size
        self.angle = 0
        self.timer = QTimer(self)
        self.timer.timeout.connect(self._rotate_image)
        self.timer.setInterval(50)  # 20 frames per second
        self.setFixedSize(size, size)  # Fix the label size
        self._load_image()
        
    def _load_image(self):
        # Try to load logo.png from various locations
        logo_paths = [
            os.path.join(os.path.dirname(os.path.abspath(__file__)), "logo.png"),
            os.path.join(os.path.dirname(sys.executable), "logo.png") if getattr(sys, 'frozen', False) else None
        ]
        
        pixmap = None
        for path in logo_paths:
            if path and os.path.exists(path):
                pixmap = QPixmap(path)
                break
                
        if pixmap:
            # Scale the image to fit inside our fixed size while maintaining aspect ratio
            scaled_size = min(self.size, self.size)
            pixmap = pixmap.scaled(scaled_size, scaled_size, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
            self.original_pixmap = pixmap
            self.setPixmap(pixmap)
            
            # Center the pixmap in the label
            self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        else:
            # Fallback if image not found - make this label invisible
            self.original_pixmap = None
            self.setVisible(False)
    
    def _rotate_image(self):
        if not self.original_pixmap:
            return
            
        self.angle = (self.angle + 10) % 360
        
        # Create a square pixmap with transparent background
        target_size = max(self.original_pixmap.width(), self.original_pixmap.height())
        rotated_pixmap = QPixmap(target_size, target_size)
        rotated_pixmap.fill(Qt.GlobalColor.transparent)
        
        # Calculate center points - convert to int
        center_x = int((target_size - self.original_pixmap.width()) / 2)
        center_y = int((target_size - self.original_pixmap.height()) / 2)
        
        # Draw rotated image with antialiasing
        painter = QPainter(rotated_pixmap)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        
        # Set up the transform
        transform = QTransform()
        transform.translate(target_size/2, target_size/2)  # Move to center
        transform.rotate(self.angle)  # Rotate
        transform.translate(-target_size/2, -target_size/2)  # Move back
        painter.setTransform(transform)
        
        # Draw the pixmap centered - using integers
        painter.drawPixmap(center_x, center_y, self.original_pixmap)
        painter.end()
        
        # Scale the result to our fixed size if needed
        if rotated_pixmap.width() != self.size:
            rotated_pixmap = rotated_pixmap.scaled(self.size, self.size, 
                Qt.AspectRatioMode.KeepAspectRatio, 
                Qt.TransformationMode.SmoothTransformation)
        
        self.setPixmap(rotated_pixmap)
    
    def start_spinning(self):
        if self.original_pixmap:
            self.setVisible(True)
            self.timer.start()
    
    def stop_spinning(self):
        self.timer.stop()
        if self.original_pixmap:
            # Reset to original (non-rotated) image
            self.setPixmap(self.original_pixmap)

# Set the browser path dynamically
if getattr(sys, 'frozen', False):
    browser_path = os.path.join(sys._MEIPASS, 'browsers')
    if os.path.exists(browser_path):
        os.environ['PLAYWRIGHT_BROWSERS_PATH'] = browser_path

# Import Playwright - fail gracefully if not installed
try:
    from playwright.sync_api import sync_playwright
    PLAYWRIGHT_AVAILABLE = True
except ImportError:
    PLAYWRIGHT_AVAILABLE = False

# Dictionary mapping templates to units
TEMPLATE_TO_UNIT = {
    "APFUNDINGAUD": "TGBP", "APFUNDINGCHF": "TGBP", "BOV Platform (EUR)": "N/A",
    "EURPAYMENTAP2": "CCT_CHUK", "APFUNDINGHKD": "TGBP", "APFUNDINGJPY": "CCT_CHUK",
    "APFUNDINGGBP": "CCT_CHUK", "APFUNDINGGBP2": "CCT_CHUK", "APFUNDINGUSD": "CCT_CHUK",
    "APFUNDINGCAD": "CCT_CHUK", "APFUNDINGNZD": "CCT_CHUK", "APFUNDINGSGD": "CCT_CHUK",
    "APFUNDINGCZK": "CCT_CHUK", "APFUNDINGPLN": "CCT_CHUK"
}

# Dictionary mapping templates to codes and vice versa
TEMPLATE_CODE_MAP = {
    "APFUNDINGAUD": "AUDCUKBOA", "AUDCUKBOA": "APFUNDINGAUD",
    "APFUNDINGCHF": "CHFCUKCSB", "CHFCUKCSB": "APFUNDINGCHF",
    "BOV Platform (EUR)": "EURMALAP", "EURMALAP": "BOV Platform (EUR)",
    "EURPAYMENTAP2": "EURCHKING", "EURCHKING": "EURPAYMENTAP2",
    "APFUNDINGHKD": "HKDCUKBOA", "HKDCUKBOA": "APFUNDINGHKD",
    "APFUNDINGJPY": "JPYCUKCIT", "JPYCUKCIT": "APFUNDINGJPY",
    "APFUNDINGGBP": "GBPCHBARX", "GBPCHBARX": "APFUNDINGGBP",
    "APFUNDINGGBP2": "GBPCVBAROPS", "GBPCVBAROPS": "APFUNDINGGBP2",
    "APFUNDINGUSD": "USDBNYCHKINC", "USDBNYCHKINC": "APFUNDINGUSD",
    "APFUNDINGCAD": "CADCHKRBC", "CADCHKRBC": "APFUNDINGCAD",
    "CADBMOIN": "APFUNDINGCAD", # Added mapping for CADBMOIN
    "APFUNDINGNZD": "NZDCUKCIT", "NZDCUKCIT": "APFUNDINGNZD",
    "APFUNDINGSGD": "SGDCHKBNY", "SGDCHKBNY": "APFUNDINGSGD", 
    "APFUNDINGCZK": "CZKCUKKOM", "CZKCUKKOM": "APFUNDINGCZK",
    "APFUNDINGPLN": "PLNCUKING", "PLNCUKING": "APFUNDINGPLN"
}

# Worker signal class for threading
class WorkerSignals(QObject):
    finished = pyqtSignal(object)
    error = pyqtSignal(str)
    progress = pyqtSignal(str)

# Browser automation worker
class BrowserWorker(QObject):
    signals = WorkerSignals()
    
    def __init__(self, username, password, otp_code, payments_data):
        super().__init__()
        self.username = username
        self.password = password
        self.otp_code = otp_code
        self.payments_data = payments_data
        self.is_running = True
        self.payment_references = {}  # Dictionary to store payment references

    def _find_free_port(self):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.bind(("127.0.0.1", 0))
            return sock.getsockname()[1]

    def _launch_bundled_edge_over_cdp(self, playwright, launch_options):
        executable_path = launch_options["executable_path"]
        user_data_dir = tempfile.mkdtemp(prefix="gtx_playwright_edge_")
        port = self._find_free_port()
        endpoint = f"http://127.0.0.1:{port}"
        args = build_edge_cdp_args(executable_path, user_data_dir, port)
        self.signals.progress.emit(f"Starting bundled Edge with remote debugging on port {port}")
        process = subprocess.Popen(args, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        wait_for_cdp_endpoint(endpoint, process)
        browser = playwright.chromium.connect_over_cdp(endpoint)
        context = browser.contexts[0] if browser.contexts else browser.new_context()
        page = context.pages[0] if context.pages else context.new_page()
        return browser, context, page, process
        
    def _handle_license_popup(self, page):
        """Handle the 'License exceeded' popup if it appears"""
        try:
            if page.get_by_text("Licence exceeded, please").is_visible(timeout=100):
                self.signals.progress.emit("License exceeded popup detected, clicking OK...")
                page.get_by_role("button", name="OK").click(timeout=3000)
                return True
        except:
            pass
        return False

    def _click_create_message(self, page):
        try:
            page.get_by_role("button", name="Create Message").click()
            page.wait_for_load_state('networkidle', timeout=15000)
            return True
        except Exception as e:
            self.signals.progress.emit(f"Error clicking Create Message: {e}")
            try:
                page.locator('input[value="Create Message"]').click()
                page.wait_for_load_state('networkidle', timeout=15000)
                return True
            except Exception as fallback_e:
                self.signals.progress.emit(f"Create Message fallback failed: {fallback_e}")
                return False

    def _capture_correspondent_identifier(self, page):
        table = page.locator("#rightTree_table_FinInstnId-36")
        table.wait_for(timeout=15000)
        cell_texts = table.get_by_role("cell").all_inner_texts()

        for text in cell_texts:
            candidate = text.strip()
            if re.fullmatch(r"[A-Z0-9]{8}([A-Z0-9]{3})?", candidate):
                try:
                    table.get_by_role("cell", name=candidate).first.click()
                except Exception:
                    table.get_by_text(candidate).first.click()
                self.signals.progress.emit(f"Captured correspondent identifier: {candidate}")
                return candidate

        raise ValueError("Could not find correspondent identifier in template table")

    def _wait_for_jsf_settle(self, page, reason, delay_ms=1000):
        self.signals.progress.emit(f"Waiting for GTExchange refresh after {reason}...")
        page.wait_for_load_state('networkidle', timeout=15000)
        page.wait_for_timeout(delay_ms)

    def _set_owning_unit(self, page, unit):
        try:
            self.signals.progress.emit(f"Setting owning unit to {unit}")
            page.get_by_label("Owning Unit").select_option(unit)
            self._wait_for_jsf_settle(page, "owning unit change")
        except Exception as e:
            self.signals.progress.emit(f"Error setting owning unit: {e}")
            try:
                selects = page.locator('select').all()
                if len(selects) > 1:
                    selects[1].select_option(unit)
                    self._wait_for_jsf_settle(page, "owning unit fallback change")
            except Exception as fallback_e:
                self.signals.progress.emit(f"Owning unit fallback failed: {fallback_e}")

    def _fill_pacs_message_ids(self, page):
        msg_id = page.get_by_role("textbox", name="(MsgId) Message Identification")
        msg_id.wait_for(timeout=15000)
        message_id = msg_id.input_value().strip()
        if not message_id:
            page.wait_for_timeout(1000)
            message_id = msg_id.input_value().strip()
        if not message_id:
            raise ValueError("Message Identification is empty")

        self.signals.progress.emit(f"Using message id for InstrId/EndToEndId: {message_id}")
        page.get_by_role("textbox", name="(InstrId) Instruction").fill(message_id)
        end_to_end = page.get_by_role("textbox", name="(EndToEndId) End To End")
        end_to_end.fill(message_id)
        end_to_end.press("Tab")
        return message_id

    def _click_pacs_generate(self, page):
        uetr_field = page.get_by_role("textbox", name="(UETR) UETR")
        uetr_field.wait_for(state="visible", timeout=10000)
        old_uetr = uetr_field.input_value().strip()

        self.signals.progress.emit("Clicking Generate and waiting for UETR to change...")
        try:
            page.get_by_role("button", name="Generate").click(timeout=10000)
        except Exception as e:
            self.signals.progress.emit(f"Generate button role click failed: {e}")
            page.locator('input[value="Generate"]').click(timeout=10000)

        page.wait_for_function(
            """([label, oldValue]) => {
                const inputs = Array.from(document.querySelectorAll('input, textarea'));
                const uetr = inputs.find((input) => {
                    const aria = input.getAttribute('aria-label') || '';
                    const title = input.getAttribute('title') || '';
                    const id = input.getAttribute('id') || '';
                    return aria.includes(label) || title.includes(label) || id.toLowerCase().includes('uetr');
                });
                return uetr && uetr.value && uetr.value.trim() !== oldValue;
            }""",
            arg=["UETR", old_uetr],
            timeout=15000,
        )
        new_uetr = uetr_field.input_value().strip()
        self.signals.progress.emit(f"UETR changed after Generate: {new_uetr}")

    def _fill_pacs_amount(self, page, template_name, formatted_amount):
        self.signals.progress.emit("Waiting for PACS amount fields to finish loading...")
        page.wait_for_timeout(1000)

        filled = 0
        for field_id in get_pacs_amount_field_ids():
            try:
                self.signals.progress.emit(f"Setting PACS amount field {field_id} to {formatted_amount}")
                amount_field = page.locator(f'[id="{field_id}"]')
                amount_field.wait_for(state="visible", timeout=5000)
                amount_field.click()
                amount_field.fill(formatted_amount)
                filled += 1
            except Exception as e:
                self.signals.progress.emit(f"Could not fill PACS amount field {field_id}: {e}")

        if filled < 2:
            self.signals.progress.emit(f"Using row Value fallback for PACS amount {formatted_amount}")
            second_amount = page.get_by_role("row", name="Value", exact=True).get_by_label("Value")
            second_amount.click(timeout=5000)
            second_amount.fill(formatted_amount)
            filled += 1

        if filled < 2:
            raise ValueError(f"Could not fill both PACS amount fields for {template_name}")

    def _fill_pacs_date(self, page, formatted_date):
        self.signals.progress.emit(f"Clicking PACS date field and setting {formatted_date}")
        date_field = page.get_by_role("textbox", name="(IntrBkSttlmDt) Interbank")
        date_field.click(timeout=10000)
        date_field.fill(formatted_date)

    def _fill_pacs_narrative(self, page, narrative_text):
        self.signals.progress.emit(f"Setting unstructured remittance to: {narrative_text}")
        page.get_by_role("textbox", name="(Ustrd) Unstructured").click()
        page.get_by_role("textbox", name="(Ustrd) Unstructured").fill(narrative_text)
        try:
            page.get_by_role("cell", name=narrative_text, exact=True).click(timeout=3000)
        except Exception:
            page.get_by_role("textbox", name="(Ustrd) Unstructured").press("Tab")

    def _ensure_textbox_value(self, page, label, expected_value):
        field = page.get_by_role("textbox", name=label)
        field.wait_for(state="visible", timeout=10000)
        actual_value = field.input_value().strip()
        if actual_value != expected_value:
            self.signals.progress.emit(f"Repairing {label}: expected {expected_value}, found {actual_value}")
            field.click()
            field.fill(expected_value)
            actual_value = field.input_value().strip()
        if actual_value != expected_value:
            raise ValueError(f"{label} did not keep expected value")

    def _normalize_display_amount(self, value):
        return str(value or "").replace(" ", "").replace(",", "").strip()

    def _amount_values_match(self, actual_value, expected_value):
        actual_normalized = self._normalize_display_amount(actual_value)
        expected_normalized = self._normalize_display_amount(expected_value)
        try:
            return float(actual_normalized) == float(expected_normalized)
        except ValueError:
            return actual_normalized == expected_normalized

    def _ensure_pacs_amounts(self, page, formatted_amount):
        for field_id in get_pacs_amount_field_ids():
            field = page.locator(f'[id="{field_id}"]')
            field.wait_for(state="visible", timeout=10000)
            actual_value = field.input_value().strip()
            if not self._amount_values_match(actual_value, formatted_amount):
                self.signals.progress.emit(f"Repairing PACS amount field {field_id}: expected {formatted_amount}, found {actual_value}")
                field.click()
                field.fill(formatted_amount)
                actual_value = field.input_value().strip()
            if not self._amount_values_match(actual_value, formatted_amount):
                raise ValueError(f"PACS amount field {field_id} did not keep expected value")

    def _ensure_pacs_text_values(self, page, message_id, formatted_amount, formatted_date, narrative_text):
        self.signals.progress.emit("Verifying PACS fields after Generate...")
        self._ensure_textbox_value(page, "(InstrId) Instruction", message_id)
        self._ensure_textbox_value(page, "(EndToEndId) End To End", message_id)
        self._ensure_pacs_amounts(page, formatted_amount)
        self._ensure_textbox_value(page, "(IntrBkSttlmDt) Interbank", formatted_date)
        self._ensure_textbox_value(page, "(Ustrd) Unstructured", narrative_text)

    def _click_pacs_text_ok(self, page):
        try:
            page.locator('#rightTreeForm\\:ok').click(timeout=5000)
            self.signals.progress.emit("Clicked PACS Text OK button")
        except Exception as e:
            self.signals.progress.emit(f"Could not click PACS Text OK by id: {e}")
            page.get_by_role("button", name="Ok").click(timeout=5000)
            self.signals.progress.emit("Clicked PACS Text OK button by role")
        page.wait_for_load_state('networkidle', timeout=15000)
        validation_errors = page.locator('text=/Business element .* is mandatory|Format error/i')
        if validation_errors.count() > 0:
            first_error = validation_errors.first.inner_text(timeout=3000)
            raise ValueError(f"GTExchange validation error after Text OK: {first_error}")

    def _click_pacs_submit_ok(self, page):
        submit_attempts = [
            ('#createcriteriaform\\:ok', "PACS final submit OK"),
            ('input[id="createcriteriaform:ok"]', "PACS final submit OK input"),
            ("role:button:Ok", "visible final Ok button"),
        ]

        for selector, description in submit_attempts:
            try:
                if selector.startswith("role:button:"):
                    button_name = selector.split(":", 2)[2]
                    page.get_by_role("button", name=button_name).last.click(timeout=5000)
                else:
                    page.locator(selector).click(timeout=5000)
                self.signals.progress.emit(f"Clicked {description}")
                page.wait_for_load_state('networkidle', timeout=15000)
                return
            except Exception as e:
                self.signals.progress.emit(f"Could not click {description}: {e}")

        raise ValueError("Could not click PACS final submit OK button")

    def _confirm_pacs_reference_popup(self, page, row_num):
        payment_ref = ""
        try:
            page.wait_for_selector('#createcriteriaform\\:popup-generic\\:popup-confirm\\:uftc_confirm_msg_link', timeout=20000)
            ref_element = page.locator('#createcriteriaform\\:popup-generic\\:popup-confirm\\:uftc_confirm_msg_link')
            payment_ref = ref_element.inner_text().strip()
            if payment_ref:
                self.signals.progress.emit(f"Extracted payment reference: {payment_ref}")
                self.payment_references[row_num] = payment_ref
                self.signals.progress.emit(f"REF:{row_num}:{payment_ref}")
        except Exception as popup_e:
            self.signals.progress.emit(f"No reference link found in confirmation popup: {popup_e}")

        confirm_attempts = [
            ('#createcriteriaform\\:popup-generic\\:popup-confirm\\:confirmAction', "old popup OK"),
            ("role:button:Ok", "confirmation Ok button"),
            ("role:button:OK", "confirmation OK button"),
        ]

        for selector, description in confirm_attempts:
            try:
                if selector.startswith("role:button:"):
                    button_name = selector.split(":", 2)[2]
                    page.get_by_role("button", name=button_name).last.click(timeout=5000)
                else:
                    page.locator(selector).click(timeout=5000)
                self.signals.progress.emit(f"Clicked {description}")
                page.wait_for_load_state('networkidle', timeout=15000)
                self._handle_license_popup(page)
                return payment_ref
            except Exception as click_e:
                self.signals.progress.emit(f"Could not click {description}: {click_e}")

        raise ValueError("Could not click confirmation popup OK button")

    def _return_to_messages(self, page):
        try:
            self.signals.progress.emit("Returning to Messages menu...")
            page.wait_for_load_state('networkidle', timeout=15000)
            page.get_by_role("link", name="Messages").click()
            page.wait_for_load_state('networkidle', timeout=20000)
            self._handle_license_popup(page)
            page.get_by_role("link", name="Create a Message from a").wait_for(timeout=15000)
            return
        except Exception as e:
            self.signals.progress.emit(f"Error clicking Messages link: {e}")

        try:
            page.locator('a:has-text("Messages")').first.click()
            page.wait_for_load_state('networkidle', timeout=15000)
            self._handle_license_popup(page)
            page.get_by_role("link", name="Create a Message from a").wait_for(timeout=15000)
        except Exception as e:
            raise ValueError(f"Could not navigate to Messages menu: {e}")

    def _process_pacs_payment(self, page, payment):
        template_name = payment['template']
        amount = payment['amount']
        otr_number = payment['otr_number']
        unit = payment['unit']
        row_num = payment['row_num']

        try:
            correspondent_id = self._capture_correspondent_identifier(page)

            if not self._click_create_message(page):
                raise ValueError("Could not create PACS message")
            self._handle_license_popup(page)

            self._set_owning_unit(page, unit)

            self.signals.progress.emit(f"Setting correspondent identifier to {correspondent_id}")
            page.get_by_title("Correspondent identifier,").click()
            page.get_by_title("Correspondent identifier,").fill(correspondent_id)
            page.get_by_role("button", name="Add/Replace").click()
            self._wait_for_jsf_settle(page, "Add/Replace")
            page.get_by_role("link", name="Empty message Text").wait_for(timeout=30000)

            try:
                page.get_by_role("link", name="Empty message Text").click()
            except Exception:
                page.locator('a:has-text("Empty message Text")').first.click()
            page.wait_for_load_state('networkidle', timeout=15000)

            message_id = self._fill_pacs_message_ids(page)

            amount_code = payment.get('source_code') or template_name
            formatted_amount = format_amount(amount, amount_code)
            self._fill_pacs_amount(page, template_name, formatted_amount)

            formatted_date = self.get_formatted_date(template_name)
            self.signals.progress.emit(f"Setting settlement date to {formatted_date}")
            self._fill_pacs_date(page, formatted_date)

            narrative_text = build_narrative(payment.get('reference', 'CO5590'), otr_number)
            self._fill_pacs_narrative(page, narrative_text)

            self._click_pacs_generate(page)
            self._ensure_pacs_text_values(page, message_id, formatted_amount, formatted_date, narrative_text)

            self._click_pacs_text_ok(page)
            self._click_pacs_submit_ok(page)
            self._confirm_pacs_reference_popup(page, row_num)

            self._return_to_messages(page)
            self.signals.progress.emit(f"Successfully processed PACS payment {row_num}")
            self.signals.progress.emit(f"STATUS:{row_num}:Completed")
            return True
        except Exception as e:
            self.signals.progress.emit(f"Error processing PACS payment {row_num}: {e}")
            self.signals.progress.emit(f"STATUS:{row_num}:Error")
            return False
    
    def run(self):
        if not PLAYWRIGHT_AVAILABLE:
            self.signals.error.emit("Playwright not installed. Run: pip install playwright")
            return
            
        try:
            self.signals.progress.emit("Starting browser automation...")
            
            with sync_playwright() as p:
                launch_options = get_browser_launch_options()
                use_cdp = launch_options.pop("use_cdp", False)
                use_persistent_context = launch_options.pop("use_persistent_context", False)
                cdp_process = None
                if "executable_path" in launch_options:
                    self.signals.progress.emit(f"Launching bundled browser: {launch_options['executable_path']}")
                else:
                    self.signals.progress.emit("Launching installed Microsoft Edge")
                if use_cdp:
                    browser, context, page, cdp_process = self._launch_bundled_edge_over_cdp(p, launch_options)
                elif use_persistent_context:
                    user_data_dir = tempfile.mkdtemp(prefix="gtx_playwright_edge_")
                    context = p.chromium.launch_persistent_context(user_data_dir, **launch_options)
                    browser = None
                    page = context.pages[0] if context.pages else context.new_page()
                else:
                    browser = p.chromium.launch(**launch_options)
                    context = browser.new_context()
                    page = context.new_page()
                
                # Login process - follows the exact Playwright example flow
                self.signals.progress.emit("Navigating to login page...")
                page.goto("https://swift.gtxclient.converaextprod.net/web.uftc/standard.login.faces")
                
                # Enter username and password
                self.signals.progress.emit("Entering credentials...")
                page.get_by_role("textbox", name="Enter your user name").click()
                page.get_by_role("textbox", name="Enter your user name").fill(self.username)
                page.locator("[id=\"userloginform\\:password\"]").click()
                page.locator("[id=\"userloginform\\:password\"]").fill(self.password)
                page.get_by_role("button", name="Log in").click()
                
                # Check for license popup
                self._handle_license_popup(page)
                
                # Enter OTP if provided, or wait for manual entry
                if self.otp_code:
                    self.signals.progress.emit(f"Entering OTP: {self.otp_code}")
                    page.get_by_role("textbox", name="Validation code").click()
                    page.get_by_role("textbox", name="Validation code").fill(self.otp_code)
                    page.get_by_role("button", name="Log in").click()
                else:
                    self.signals.progress.emit("⚠️ Please enter OTP code manually and click login ⚠️")
                    # Wait for login completion - this is a signal that user has entered OTP and clicked login
                    try:
                        page.wait_for_selector('span:has-text("You are connected to GTExchange")', timeout=180000)
                        self.signals.progress.emit("Login successful")
                        # Check for license popup after successful login
                        self._handle_license_popup(page)
                    except Exception as e:
                        self.signals.progress.emit(f"Waiting for manual login completion: {e}")
                
                # Navigate to Messages - EXACTLY as in the Playwright example
                self.signals.progress.emit("Navigating to Messages menu...")
                try:
                    page.get_by_role("link", name="Messages").click()
                    page.wait_for_load_state('networkidle', timeout=15000) # Increased from 10000
                    # Check for license popup after navigation
                    self._handle_license_popup(page)
                except Exception as e:
                    self.signals.progress.emit(f"Error clicking Messages: {e}")
                    try:
                        # Direct navigation as fallback
                        page.goto("https://swift.gtxclient.converaextprod.net/web.uftc/messagemenu.faces")
                        page.wait_for_load_state('networkidle', timeout=15000) # Increased from 10000
                        # Check for license popup after navigation
                        self._handle_license_popup(page)
                    except Exception as e2:
                        self.signals.error.emit(f"Failed to navigate to Messages: {e2}")
                        return
                
                # Process each payment
                total_payments = len(self.payments_data)
                processed = 0
                errors = 0
                
                for i, payment in enumerate(self.payments_data):
                    if not self.is_running:
                        self.signals.error.emit("Process stopped by user")
                        break
                        
                    self.signals.progress.emit(f"Processing payment {i+1}/{total_payments}")
                    
                    # Check for license popup before processing payment
                    self._handle_license_popup(page)
                    
                    try:
                        # Extract payment details
                        template_name = payment['template']
                        amount = payment['amount']
                        otr_number = payment['otr_number'] 
                        unit = payment['unit']
                        row_num = payment['row_num']
                        uses_pacs_flow = payment.get('uses_pacs_flow', True)
                        
                        self.signals.progress.emit(f"Processing {template_name} for amount {amount}")
                        
                        # Click on Create a Message from a Template
                        try:
                            page.get_by_role("link", name="Create a Message from a").click()
                            page.wait_for_load_state('networkidle', timeout=15000) # Increased from 10000
                        except Exception as e:
                            self.signals.progress.emit(f"Error clicking Create Message from Template: {e}")
                            try:
                                # Try alternative selector
                                page.locator('a:has-text("Create a Message from a Template")').click()
                                page.wait_for_load_state('networkidle', timeout=15000) # Increased from 10000
                            except:
                                self.signals.progress.emit(f"STATUS:{row_num}:Error")
                                self.signals.error.emit(f"Could not navigate to template creation for {template_name}")
                                continue  # Skip to next payment
                        
                        # Set creating unit (CCT_CHUK or TGBP) based on template
                        try:
                            self.signals.progress.emit(f"Setting creating unit to: {unit}")
                            page.get_by_label("Creating unit").select_option(unit)
                        except Exception as e:
                            self.signals.progress.emit(f"Error setting creating unit: {e}")
                            try:
                                # Try alternative selector
                                page.locator('select').first.select_option(unit)
                            except:
                                self.signals.progress.emit("Could not set creating unit, continuing anyway")
                        
                        # Enter identifier and search
                        try:
                            # Get template value to search for
                            search_term = template_name
                            self.signals.progress.emit(f"Searching for template: {search_term}")
                            page.get_by_role("textbox", name="Identifier").click()
                            page.get_by_role("textbox", name="Identifier").fill(search_term)
                            page.get_by_role("button", name="Search").click()
                            page.wait_for_load_state('networkidle', timeout=15000) # Increased from 10000
                            
                            # Check if we need to try the alternative identifier
                            try:
                                # Wait to see if the template appears
                                if not page.locator(f'a:has-text("{search_term}")').count():
                                    # Try alternative code/template
                                    alt_search = TEMPLATE_CODE_MAP.get(search_term, "")
                                    if alt_search:
                                        self.signals.progress.emit(f"Template not found, trying alternative: {alt_search}")
                                        page.get_by_role("textbox", name="Identifier").click()
                                        page.get_by_role("textbox", name="Identifier").fill(alt_search)
                                        page.get_by_role("button", name="Search").click()
                                        page.wait_for_load_state('networkidle', timeout=15000) # Increased from 10000
                                        # Update template_name to the one that worked
                                        template_name = alt_search
                            except Exception as check_e:
                                self.signals.progress.emit(f"Error checking alternative template: {check_e}")
                                
                        except Exception as e:
                            self.signals.progress.emit(f"Error with identifier search: {e}")
                            # Try without clicking first
                            try:
                                page.get_by_role("textbox", name="Identifier").fill(template_name)
                                page.get_by_role("button", name="Search").click()
                                page.wait_for_load_state('networkidle', timeout=15000) # Increased from 10000
                            except:
                                self.signals.progress.emit(f"STATUS:{row_num}:Error")
                                self.signals.error.emit(f"Failed to search for template: {template_name}")
                                continue  # Skip to next payment
                        
                        # Click on template link
                        try:
                            # First attempt with original template name
                            template_link_found = False
                            
                            try:
                                # Wait for template link to appear
                                self.signals.progress.emit(f"Looking for template link: {template_name}")
                                page.wait_for_selector(f'a:has-text("{template_name}")', timeout=8000) # Increased from 5000
                                page.get_by_role("link", name=template_name).click()
                                template_link_found = True
                                self.signals.progress.emit(f"Clicked template link: {template_name}")
                            except Exception as e:
                                self.signals.progress.emit(f"Could not find template link for {template_name}: {e}")
                            
                            # If original template not found, try the alternative code
                            if not template_link_found:
                                alt_template = TEMPLATE_CODE_MAP.get(template_name, "")
                                if alt_template:
                                    try:
                                        self.signals.progress.emit(f"Trying alternative template link: {alt_template}")
                                        page.wait_for_selector(f'a:has-text("{alt_template}")', timeout=8000) # Increased from 5000
                                        page.get_by_role("link", name=alt_template).click()
                                        template_name = alt_template  # Update to the one that worked
                                        self.signals.progress.emit(f"Clicked alternative template link: {alt_template}")
                                    except Exception as alt_e:
                                        self.signals.progress.emit(f"Could not find alternative link either: {alt_e}")
                                        # Final attempt using locator
                                        page.locator(f'a:has-text("{template_name}"), a:has-text("{alt_template}")').first.click()
                            
                            page.wait_for_load_state('networkidle', timeout=15000) # Increased from 10000
                        except Exception as e:
                            self.signals.progress.emit(f"Error clicking template link: {e}")
                            try:
                                # Try using locator instead
                                page.locator(f'a:has-text("{template_name}")').first.click()
                                page.wait_for_load_state('networkidle', timeout=15000) # Increased from 10000
                            except:
                                self.signals.progress.emit(f"STATUS:{row_num}:Error")
                                self.signals.error.emit(f"Could not select template {template_name}")
                                continue  # Skip to next payment

                        if uses_pacs_flow:
                            if self._process_pacs_payment(page, payment):
                                processed += 1
                            else:
                                errors += 1
                            continue
                        
                        # Create message
                        try:
                            page.get_by_role("button", name="Create Message").click()
                            page.wait_for_load_state('networkidle', timeout=15000) # Increased from 10000
                        except Exception as e:
                            self.signals.progress.emit(f"Error clicking Create Message: {e}")
                            try:
                                # Try alternative selector
                                page.locator('input[value="Create Message"]').click()
                                page.wait_for_load_state('networkidle', timeout=15000) # Increased from 10000
                            except:
                                self.signals.error.emit("Could not create message")
                                continue  # Skip to next payment
                        
                        # Go to envelope tab
                        try:
                            page.get_by_role("link", name="Envelope").click()
                            page.wait_for_load_state('networkidle', timeout=15000) # Increased from 10000
                        except Exception as e:
                            self.signals.progress.emit(f"Error clicking Envelope tab: {e}")
                            try:
                                page.locator('a:has-text("Envelope")').first.click()
                                page.wait_for_load_state('networkidle', timeout=15000) # Increased from 10000
                            except:
                                self.signals.error.emit("Could not open envelope tab")
                                continue  # Skip to next payment
                        
                        # Set owning unit if needed (for CCT_CHUK)
                        if unit == "CCT_CHUK":
                            try:
                                self.signals.progress.emit("Setting owning unit to CCT_CHUK")
                                page.get_by_label("Owning Unit").select_option("CCT_CHUK")
                            except Exception as e:
                                self.signals.progress.emit(f"Error setting owning unit: {e}")
                                try:
                                    # Try alternative selector
                                    selects = page.locator('select').all()
                                    if len(selects) > 1:
                                        selects[1].select_option("CCT_CHUK")
                                except:
                                    self.signals.progress.emit("Could not set owning unit, continuing anyway")
                        
                        # Special handling for APFUNDINGCZK template
                        if template_name == "APFUNDINGCZK":
                            self.signals.progress.emit("⚠️ Special handling for APFUNDINGCZK template")
                            try:
                                # Add a 2-second timeout after setting owning unit before clicking Text
                                self.signals.progress.emit("Waiting 2 seconds for page to stabilize...")
                                page.wait_for_timeout(2000)
                                
                                # Click Text button directly instead of Generate
                                self.signals.progress.emit("Clicking Text tab")
                                try:
                                    # Try with ID selector first
                                    page.locator('#createcriteriaform\\:tabtext_lnk').click()
                                except Exception as text_tab_e:
                                    self.signals.progress.emit(f"ID selector failed, trying XPath: {text_tab_e}")
                                    try:
                                        # Use full XPath as fallback
                                        page.locator('xpath=/html/body/div[4]/div/form/div[10]/div[1]/ul/li[2]/a').click()
                                    except Exception as xpath_e:
                                        self.signals.progress.emit(f"XPath also failed: {xpath_e}")
                                        # Last resort: try to find any element containing "Text"
                                        page.locator('a:has-text("Text")').first.click()
                                
                                page.wait_for_load_state('networkidle', timeout=15000)
                                
                                # Wait for fields to be available
                                page.wait_for_selector('#rightTreeForm\\:SC_16x-3', timeout=15000) # Increased from 10000
                                
                                # Copy value from one field to another
                                reference_value = page.locator('#rightTreeForm\\:SC_16x-3').get_attribute('value')
                                self.signals.progress.emit(f"Copied reference value: {reference_value}")
                                page.locator('#rightTreeForm\\:SC_16x-46').fill(reference_value)
                                
                                # Set tomorrow's date
                                formatted_date = self.get_formatted_date(template_name)  # Already gets tomorrow's date for this template
                                self.signals.progress.emit(f"Setting date to {formatted_date}")
                                page.locator('#rightTreeForm\\:Date-41').fill(formatted_date)
                                
                                # Set amount without comma
                                formatted_amount = str(round(float(str(amount).replace(',', '')), 2))
                                self.signals.progress.emit(f"Setting amount to {formatted_amount}")
                                page.locator('#rightTreeForm\\:Amount-54').fill(formatted_amount)
                                
                                # Set "OUR" text
                                page.locator('#rightTreeForm\\:Code-126').fill("OUR")
                                self.signals.progress.emit("Set Code field to OUR")
                                
                                # Add narrative with OTR number
                                try:
                                    base_text = "Funding CO5590"
                                    
                                    # Format narrative for 4 lines, 35 chars per line
                                    lines = []
                                    
                                    if otr_number:
                                        # Combine base text and OTR with a space
                                        full_text = base_text + " " + otr_number
                                        
                                        # Split into 35-char chunks
                                        for i in range(0, min(140, len(full_text)), 35):
                                            lines.append(full_text[i:i+35])
                                    else:
                                        lines.append(base_text)
                                    
                                    # Join with line breaks
                                    narrative_text = "\n".join(lines[:4])  # Max 4 lines
                                    
                                    self.signals.progress.emit(f"Setting narrative to: {narrative_text}")
                                    page.get_by_label("(70) Remittance Information").click()
                                    page.get_by_label("(70) Remittance Information").fill(narrative_text)
                                except Exception as e:
                                    self.signals.progress.emit(f"Error setting narrative: {e}")
                                
                                # Click first OK button
                                page.locator('#rightTreeForm\\:ok').click()
                                self.signals.progress.emit("Clicked first OK button")
                                page.wait_for_load_state('networkidle', timeout=15000) # Increased from 10000
                                
                                # Click second OK button
                                page.locator('#createcriteriaform\\:ok').click()
                                self.signals.progress.emit("Clicked second OK button")
                                page.wait_for_load_state('networkidle', timeout=15000) # Increased from 10000
                                
                                # Go to next section for extracting reference and continuing
                                
                            except Exception as e:
                                self.signals.progress.emit(f"Error in APFUNDINGCZK special handling: {e}")
                                continue  # Skip to next payment
                                
                            # Save the reference value as the payment reference
                            payment_ref = reference_value
                            self.signals.progress.emit(f"✅ Using reference: {payment_ref}")
                            self.payment_references[row_num] = payment_ref
                            self.signals.progress.emit(f"REF:{row_num}:{payment_ref}")
                            
                            # Click OK button in the popup
                            self.signals.progress.emit("Clicking OK button in popup...")
                            page.locator('#createcriteriaform\\:popup-generic\\:popup-confirm\\:confirmAction').click()
                            page.wait_for_load_state('networkidle', timeout=15000) # Increased from 10000
                            
                            processed += 1
                            self.signals.progress.emit(f"Successfully processed APFUNDINGCZK payment {i+1}")
                            
                            # Update payment status in the UI
                            self.signals.progress.emit(f"STATUS:{row_num}:Completed")
                            
                            # Return to Messages to start next payment
                            try:
                                self.signals.progress.emit("Returning to Messages menu...")
                                page.wait_for_load_state('networkidle', timeout=15000) # Increased from 10000
                                page.get_by_role("link", name="Messages").click()
                                self.signals.progress.emit("Clicked Messages link")
                                page.wait_for_load_state('networkidle', timeout=20000) # Increased from 15000
                            except Exception as e:
                                self.signals.progress.emit(f"Error clicking Messages link: {e}")
                                try:
                                    page.locator('a:has-text("Messages")').first.click()
                                    page.wait_for_load_state('networkidle', timeout=15000) # Increased from 10000
                                except Exception as e2:
                                    self.signals.error.emit(f"Could not navigate to Messages. Please do so manually: {e2}")
                                    page.wait_for_timeout(8000)
                            
                            # Skip the rest of the normal flow for this payment
                            continue
                        
                        # Wait 1 second as per example
                        page.wait_for_timeout(1500) # Increased from 1000
                        
                        # Click generate
                        try:
                            page.get_by_role("button", name="Generate").click()
                            # Wait for UETR field to be populated instead of just waiting for networkidle
                            self.signals.progress.emit("Waiting for UETR field to be populated...")
                            page.wait_for_selector('input[id="createcriteriaform:gpiiEutr"][value]:not([value=""])', timeout=5000) # Increased from 2000
                            uetr_value = page.locator('input[id="createcriteriaform:gpiiEutr"]').get_attribute('value')
                            self.signals.progress.emit(f"UETR field populated: {uetr_value}")
                        except Exception as e:
                            self.signals.progress.emit(f"Error clicking Generate or waiting for UETR: {e}")
                            try:
                                page.locator('input[value="Generate"]').click()
                                page.wait_for_selector('input[id="createcriteriaform:gpiiEutr"][value]:not([value=""])', timeout=30000)
                            except:
                                self.signals.error.emit("Could not generate message or UETR not populated")
                                continue  # Skip to next payment
                        
                        # No need for separate Wait for UETR section since we integrated it above
                        # Wait 1 second before continuing just to be safe
                        page.wait_for_timeout(1500) # Increased from 1000
                        
                        # Go to text tab
                        try:
                            page.get_by_role("link", name="Format error Text").click()
                            page.wait_for_load_state('networkidle', timeout=15000) # Increased from 10000
                        except Exception as e:
                            self.signals.progress.emit(f"Error clicking Format error Text link: {e}")
                            try:
                                page.locator('a:has-text("Format error Text")').first.click()
                                page.wait_for_load_state('networkidle', timeout=15000) # Increased from 10000
                            except:
                                self.signals.error.emit("Could not open text tab")
                                continue  # Skip to next payment
                        
                        # Enter date based on template
                        try:
                            formatted_date = self.get_formatted_date(template_name)
                            self.signals.progress.emit(f"Setting date to {formatted_date}")
                            page.get_by_role("textbox", name="Date").click()
                            page.get_by_role("textbox", name="Date").fill(formatted_date)
                        except Exception as e:
                            self.signals.progress.emit(f"Error setting date: {e}")
                            try:
                                page.locator('input[id*="Date"]').first.fill(formatted_date)
                            except:
                                self.signals.error.emit("Could not set date")
                                continue  # Skip to next payment
                        
                        # Format and enter amount (exactly as in the example)
                        try:
                            formatted_amount = str(round(float(str(amount).replace(',', '')), 2))
                            self.signals.progress.emit(f"Setting amount to {formatted_amount}")
                            
                            # First amount field
                            page.locator("[id=\"rightTreeForm\\:Amount-18\"]").click()
                            page.locator("[id=\"rightTreeForm\\:Amount-18\"]").fill(formatted_amount)
                            
                            # Second amount field
                            page.locator("[id=\"rightTreeForm\\:Amount-21\"]").click()
                            page.locator("[id=\"rightTreeForm\\:Amount-21\"]").fill(formatted_amount)
                        except Exception as e:
                            self.signals.progress.emit(f"Error setting amounts: {e}")
                            try:
                                # Try alternative selector
                                amount_fields = page.locator('input[id*="Amount"]').all()
                                if len(amount_fields) >= 2:
                                    amount_fields[0].fill(formatted_amount)
                                    amount_fields[1].fill(formatted_amount)
                            except:
                                self.signals.error.emit("Could not set amounts")
                                continue  # Skip to next payment
                        
                        # Enter narrative with OTR number
                        try:
                            # Base text with spaces included
                            base_text = "Funding CO5590"
                            
                            # Format narrative for 4 lines, 35 chars per line
                            lines = []
                            
                            if otr_number:
                                # Combine base text and OTR with a space
                                full_text = base_text + " " + otr_number
                                
                                # Split into 35-char chunks
                                for i in range(0, min(140, len(full_text)), 35):
                                    lines.append(full_text[i:i+35])
                            else:
                                lines.append(base_text)
                            
                            # Join with line breaks
                            narrative_text = "\n".join(lines[:4])  # Max 4 lines
                            
                            self.signals.progress.emit(f"Setting narrative to: {narrative_text}")
                            page.get_by_role("textbox", name="(70) Remittance Information").click()
                            page.get_by_role("textbox", name="(70) Remittance Information").fill(narrative_text)
                        except Exception as e:
                            self.signals.progress.emit(f"Error setting narrative: {e}")
                            try:
                                # Try alternative selector
                                page.locator('textarea[id*="Narrative"]').first.fill(narrative_text)
                            except:
                                self.signals.error.emit("Could not set narrative")
                                continue  # Skip to next payment
                        
                        # Go back to Envelope tab (as per example)
                        try:
                            page.get_by_role("link", name="Envelope").click()
                            page.wait_for_load_state('networkidle', timeout=15000) # Increased from 10000
                        except Exception as e:
                            self.signals.progress.emit(f"Error returning to Envelope tab: {e}")
                        
                        # Click first OK button (on envelope page)
                        try:
                            page.get_by_role("button", name="Ok").click()
                            self.signals.progress.emit("Clicked first OK button")
                            page.wait_for_load_state('networkidle', timeout=15000) # Increased from 10000
                        except Exception as e:
                            self.signals.progress.emit(f"Error clicking first OK button: {e}")
                            try:
                                page.locator('input[value="Ok"]').click()
                                page.wait_for_load_state('networkidle', timeout=15000) # Increased from 10000
                            except:
                                self.signals.error.emit("Could not click first OK button")
                                continue  # Skip to next payment
                        
                        # Wait for popup to appear and extract reference
                        try:
                            self.signals.progress.emit("Waiting for confirmation popup...")
                            page.wait_for_selector('#createcriteriaform\\:popup-generic\\:popup-confirm\\:uftc_confirm_msg_link', timeout=20000) # Increased from 15000
                            
                            # Get reference text
                            ref_element = page.locator('#createcriteriaform\\:popup-generic\\:popup-confirm\\:uftc_confirm_msg_link')
                            payment_ref = ref_element.inner_text()
                            self.signals.progress.emit(f"✅ Extracted payment reference: {payment_ref}")
                            
                            # Save reference and update UI
                            self.payment_references[row_num] = payment_ref
                            self.signals.progress.emit(f"REF:{row_num}:{payment_ref}")
                            
                            # Click second OK button (in popup)
                            page.locator('#createcriteriaform\\:popup-generic\\:popup-confirm\\:confirmAction').click()
                            self.signals.progress.emit("Clicked second OK button in popup")
                            page.wait_for_load_state('networkidle', timeout=15000) # Increased from 10000
                            # Check for license popup after clicking OK
                            self._handle_license_popup(page)
                        except Exception as e:
                            self.signals.progress.emit(f"Error with popup handling: {e}")
                            # Try clicking the popup OK button anyway
                            try:
                                page.locator('#createcriteriaform\\:popup-generic\\:popup-confirm\\:confirmAction').click()
                            except:
                                self.signals.progress.emit("Could not click popup OK button")
                        
                        processed += 1
                        self.signals.progress.emit(f"Successfully processed payment {i+1}")
                        
                        # Update payment status in the UI
                        self.signals.progress.emit(f"STATUS:{row_num}:Completed")
                        
                        # Return to Messages to start next payment (as per example)
                        try:
                            self.signals.progress.emit("Returning to Messages menu...")
                            
                            # Wait for page to settle after confirmation
                            page.wait_for_load_state('networkidle', timeout=15000) # Increased from 10000
                            
                            # Simple direct click on Messages link
                            page.get_by_role("link", name="Messages").click()
                            self.signals.progress.emit("Clicked Messages link")
                            page.wait_for_load_state('networkidle', timeout=20000) # Increased from 15000
                        except Exception as e:
                            self.signals.progress.emit(f"Error clicking Messages link: {e}")
                            try:
                                # First option: Try to click on home icon first
                                page.locator('a.home-icon').click()
                                page.wait_for_timeout(2000)
                                page.get_by_role("link", name="Messages").click()
                                page.wait_for_load_state('networkidle', timeout=15000) # Increased from 10000
                            except Exception as e2:
                                self.signals.progress.emit(f"Error with home navigation approach: {e2}")
                                try:
                                    # Second option: Try a different selector for Messages
                                    page.locator('a:has-text("Messages")').first.click()
                                    page.wait_for_load_state('networkidle', timeout=15000) # Increased from 10000
                                except Exception as e3:
                                    self.signals.error.emit(f"Could not navigate to Messages. Please do so manually: {e3}")
                                    page.wait_for_timeout(8000)  # Longer wait for manual intervention
                        
                    except Exception as e:
                        self.signals.progress.emit(f"Error processing payment {i+1}: {str(e)}")
                        # Send status update signal for the UI
                        self.signals.progress.emit(f"STATUS:{payment['row_num']}:Error")
                        errors += 1
                
                # Close browser at the end
                context.close()
                if browser:
                    browser.close()
                if cdp_process and cdp_process.poll() is None:
                    cdp_process.terminate()
                
                # Include payment references in the result
                result = {
                    "status": "completed",
                    "message": f"Complete: Processed {processed} payments with {errors} errors",
                    "payment_references": self.payment_references
                }
                self.signals.finished.emit(result)
                
        except Exception as e:
            self.signals.error.emit(f"Automation error: {str(e)}")
    
    def stop(self):
        self.is_running = False
    
    def get_formatted_date(self, template_name):
        """Get formatted date for a payment based on saved value date or calculate it"""
        # Find the payment data for this template
        for payment in self.payments_data:
            if payment['template'] == template_name:
                # Use the value date from payment data if it exists
                if 'value_date' in payment and payment['value_date']:
                    return payment['value_date']
                
        # Fallback to calculating the date if not found or empty
        today = datetime.now()
        next_day_templates = [
            "APFUNDINGAUD", "APFUNDINGCHF", "APFUNDINGCZK", "APFUNDINGGBP",
            "APFUNDINGGBP2", "APFUNDINGHKD", "APFUNDINGJPY", "APFUNDINGNZD",
            "APFUNDINGPLN", "APFUNDINGSGD", "EURPAYMENTAP2",
            "APAUDPACS", "APCHFPACS", "APGBPPACS", "APGBPPACS2",
            "APHKDPACS", "APJPYPACS", "APNZDPACS", "APPLNPACS",
            "APSGDPACS", "EURPMTAP2PACS"
        ]
        
        if template_name in next_day_templates:
            # Add one day initially
            target_date = today + timedelta(days=1)
            
            # Check if it's a weekend and adjust to next Monday if needed
            weekday = target_date.weekday()  # 0=Monday, 5=Saturday, 6=Sunday
            
            if weekday == 5:  # Saturday
                target_date += timedelta(days=2)  # Move to Monday
                self.signals.progress.emit(f"Next day would be weekend; using Monday instead")
            elif weekday == 6:  # Sunday
                target_date += timedelta(days=1)  # Move to Monday
                self.signals.progress.emit(f"Next day would be weekend; using Monday instead")
        else:
            target_date = today
            
        return target_date.strftime("%d.%m.%Y")


class ApprovalAuditWorker(BrowserWorker):
    def __init__(self, username, password, approval_references, payments_data):
        super().__init__(username, password, "", payments_data)
        self.approval_references = approval_references

    def _emit_result_update(self, result):
        self.signals.progress.emit(f"APPROVAL_RESULT:{json.dumps(result)}")

    def _launch_page(self, playwright):
        launch_options = get_browser_launch_options()
        use_cdp = launch_options.pop("use_cdp", False)
        use_persistent_context = launch_options.pop("use_persistent_context", False)
        cdp_process = None
        if "executable_path" in launch_options:
            self.signals.progress.emit(f"Launching bundled browser: {launch_options['executable_path']}")
        else:
            self.signals.progress.emit("Launching installed Microsoft Edge")

        if use_cdp:
            browser, context, page, cdp_process = self._launch_bundled_edge_over_cdp(playwright, launch_options)
        elif use_persistent_context:
            user_data_dir = tempfile.mkdtemp(prefix="gtx_playwright_edge_")
            context = playwright.chromium.launch_persistent_context(user_data_dir, **launch_options)
            browser = None
            page = context.pages[0] if context.pages else context.new_page()
        else:
            browser = playwright.chromium.launch(**launch_options)
            context = browser.new_context()
            page = context.new_page()
        return browser, context, page, cdp_process

    def _login(self, page):
        self.signals.progress.emit("Navigating to login page...")
        page.goto("https://swift.gtxclient.converaextprod.net/web.uftc/standard.login.faces")
        self.signals.progress.emit("Entering credentials...")
        page.get_by_role("textbox", name="Enter your user name").click()
        page.get_by_role("textbox", name="Enter your user name").fill(self.username)
        page.locator("[id=\"userloginform\\:password\"]").click()
        page.locator("[id=\"userloginform\\:password\"]").fill(self.password)
        page.get_by_role("button", name="Log in").click()
        self._handle_license_popup(page)

        try:
            validation_code = page.get_by_role("textbox", name="Validation code")
            validation_code.wait_for(timeout=15000)
            if self.otp_code:
                validation_code.fill(self.otp_code)
                validation_code.press("Enter")
            else:
                self.signals.progress.emit("Please enter OTP manually and press Enter")
        except Exception:
            self.signals.progress.emit("OTP field not shown; waiting for GTExchange menu")

        page.get_by_role("link", name="Messages").wait_for(timeout=180000)
        self._handle_license_popup(page)
        self.signals.progress.emit("Login complete; preparing Search page")

    def _open_search_page(self, page):
        self.signals.progress.emit("Opening Search Messages page...")
        try:
            search_messages_link = page.get_by_role("link", name="Search Messages")
            search_messages_link.wait_for(timeout=2000)
            page.wait_for_timeout(500)
            search_messages_link.click(timeout=15000)
        except Exception:
            self.signals.progress.emit("Opening Messages menu...")
            try:
                page.get_by_role("link", name="Messages").click(timeout=15000)
            except Exception as messages_exc:
                self.signals.progress.emit(f"Messages menu click fallback: {messages_exc}")
                try:
                    page.locator('a:has-text("Messages")').first.click(timeout=15000)
                except Exception as fallback_exc:
                    self.signals.progress.emit(f"Messages fallback failed: {fallback_exc}")

            page.wait_for_timeout(1000)
            self.signals.progress.emit("Opening Search Messages page...")
            try:
                search_messages_link = page.get_by_role("link", name="Search Messages")
                search_messages_link.wait_for(timeout=30000)
                page.wait_for_timeout(500)
                search_messages_link.click(timeout=15000)
            except Exception as search_exc:
                self.signals.progress.emit(f"Search Messages click fallback: {search_exc}")
                try:
                    fallback_link = page.locator('a:has-text("Search Messages")').first
                    fallback_link.wait_for(timeout=30000)
                    page.wait_for_timeout(500)
                    fallback_link.click(timeout=15000)
                except Exception as fallback_exc:
                    self.signals.progress.emit(f"Direct Search Messages URL fallback: {fallback_exc}")
                    page.goto("https://swift.gtxclient.converaextprod.net/web.uftc/message/search/search.message.faces")

        page.get_by_role("textbox", name="GTX Reference").wait_for(timeout=30000)
        page.wait_for_timeout(500)
        self.signals.progress.emit("Search page ready")

    def _ensure_search_page(self, page):
        try:
            page.get_by_role("textbox", name="GTX Reference").wait_for(timeout=1000)
            return
        except Exception:
            self._open_search_page(page)

    def _payment_for_reference(self, approval_reference, used_rows, mark_used=True):
        for payment in self.payments_data:
            row_num = payment.get("row_num")
            if row_num in used_rows:
                continue
            if approval_template_name(payment) == approval_reference.template:
                if mark_used:
                    used_rows.add(row_num)
                return payment
        return None

    def _search_details(self, page, gtx_reference):
        self._open_search_page(page)
        self.signals.progress.emit(f"Searching GTX reference {gtx_reference}...")
        reference_input = page.get_by_role("textbox", name="GTX Reference")
        reference_input.click()
        page.wait_for_timeout(500)
        reference_input.press("ControlOrMeta+a")
        reference_input.fill(gtx_reference)
        page.wait_for_timeout(500)
        page.get_by_role("button", name="Search").click()
        page.get_by_role("link", name=gtx_reference).wait_for(timeout=30000)
        self.signals.progress.emit(f"Opening details for {gtx_reference}...")
        try:
            page.get_by_role("link", name=gtx_reference).click(timeout=30000)
        except Exception:
            page.locator(f'a:has-text("{gtx_reference}")').first.click(timeout=30000)
        page.locator("#container-body").wait_for(timeout=30000)
        page.wait_for_timeout(500)
        self.signals.progress.emit(f"Reading details for {gtx_reference}...")
        details_locator = page.locator("#container-body")
        return {
            "text": details_locator.inner_text(),
            "html": details_locator.inner_html(),
        }

    def _search_details_text(self, page, gtx_reference):
        return self._search_details(page, gtx_reference)["text"]

    def run(self):
        if not PLAYWRIGHT_AVAILABLE:
            self.signals.error.emit("Playwright not installed. Run: pip install playwright")
            return

        browser = None
        context = None
        cdp_process = None
        results = []
        used_rows = set()

        try:
            self.signals.progress.emit("Starting approval dry-run audit...")
            with sync_playwright() as p:
                browser, context, page, cdp_process = self._launch_page(p)
                self._login(page)

                for index, approval_reference in enumerate(self.approval_references, start=1):
                    if not self.is_running:
                        break

                    self.signals.progress.emit(
                        f"Dry-run audit {index}/{len(self.approval_references)}: {approval_reference.reference}"
                    )
                    try:
                        details = self._search_details(page, approval_reference.reference)
                        details_text = details["text"]
                        details_html = details["html"]
                        payment_copy = format_payment_copy(
                            approval_reference.template,
                            approval_reference.reference,
                            details_text,
                        )
                        payment = self._payment_for_reference(approval_reference, used_rows)
                        if not payment:
                            result = {
                                "template": approval_reference.template,
                                "reference": approval_reference.reference,
                                "expected_amount": "",
                                "expected_date": "",
                                "status": "Needs manual review",
                                "details": "GTExchange details opened, but no matching Excel row found for this template",
                                "payment_copy": payment_copy,
                                "payment_copy_html": details_html,
                            }
                            results.append(result)
                            self._emit_result_update(result)
                            continue

                        audit_result = compare_payment_details(payment, approval_reference.reference, details_text)
                        details = "; ".join(audit_result.issues) if audit_result.issues else "All checked fields match"
                        result = {
                            "template": approval_reference.template,
                            "reference": approval_reference.reference,
                            "expected_amount": f"{payment.get('amount', 0):,.2f}",
                            "expected_date": payment.get("value_date", ""),
                            "status": audit_result.status,
                            "details": details,
                            "payment_copy": payment_copy,
                            "payment_copy_html": details_html,
                        }
                        results.append(result)
                        self._emit_result_update(result)
                    except Exception as exc:
                        payment = self._payment_for_reference(approval_reference, used_rows, mark_used=False)
                        result = {
                            "template": approval_reference.template,
                            "reference": approval_reference.reference,
                            "expected_amount": f"{payment.get('amount', 0):,.2f}" if payment else "",
                            "expected_date": payment.get("value_date", "") if payment else "",
                            "status": "Needs manual review",
                            "details": f"Search/read failed: {exc}",
                        }
                        results.append(result)
                        self._emit_result_update(result)

                self.signals.finished.emit({
                    "status": "approval_audit",
                    "message": f"Approval dry-run complete: {len(results)} references checked",
                    "results": results,
                })
        except Exception as exc:
            self.signals.error.emit(f"Approval audit error: {exc}")
        finally:
            try:
                if context:
                    context.close()
                if browser:
                    browser.close()
                if cdp_process and cdp_process.poll() is None:
                    cdp_process.terminate()
            except Exception:
                pass


class VerifyReferenceNotFound(Exception):
    pass


class ApprovalRunWorker(ApprovalAuditWorker):
    def _open_verify_page(self, page):
        self.signals.progress.emit("Opening Verify Messages page...")
        try:
            verify_messages_link = page.get_by_role("link", name="Verify Messages")
            verify_messages_link.wait_for(timeout=2000)
            page.wait_for_timeout(500)
            verify_messages_link.click(timeout=15000)
        except Exception:
            self.signals.progress.emit("Opening Messages menu...")
            try:
                page.get_by_role("link", name="Messages").click(timeout=15000)
            except Exception as messages_exc:
                self.signals.progress.emit(f"Messages menu click fallback: {messages_exc}")
                page.locator('a:has-text("Messages")').first.click(timeout=15000)

            page.wait_for_timeout(1000)
            verify_messages_link = page.get_by_role("link", name="Verify Messages")
            verify_messages_link.wait_for(timeout=30000)
            page.wait_for_timeout(500)
            verify_messages_link.click(timeout=15000)

        page.get_by_role("textbox", name="GTX Reference").wait_for(timeout=30000)
        page.wait_for_timeout(500)
        self.signals.progress.emit("Verify page ready")

    def _dismiss_verify_no_search_warning(self, page):
        try:
            warning_text = page.get_by_text("No search item found").first
            warning_text.wait_for(timeout=1500)
            text = warning_text.inner_text(timeout=1500)
            if not is_verify_no_search_item_warning(text):
                return False

            self.signals.progress.emit("Verify search returned no item; closing warning popup")
            try:
                page.get_by_role("button", name="OK").click(timeout=5000)
            except Exception:
                page.locator('input[value="OK"], button:has-text("OK")').first.click(timeout=5000)
            page.wait_for_timeout(500)
            return True
        except Exception:
            return False

    def _search_verify_details(self, page, gtx_reference):
        self._open_verify_page(page)
        self.signals.progress.emit(f"Searching verify queue for {gtx_reference}...")
        reference_input = page.get_by_role("textbox", name="GTX Reference")
        reference_input.click()
        page.wait_for_timeout(500)
        reference_input.press("ControlOrMeta+a")
        reference_input.fill(gtx_reference)
        page.wait_for_timeout(500)
        page.get_by_role("button", name="Search").click()
        try:
            page.get_by_role("link", name=gtx_reference).wait_for(timeout=15000)
        except Exception as exc:
            self._dismiss_verify_no_search_warning(page)
            raise VerifyReferenceNotFound(f"{gtx_reference} was not found in Verify Messages") from exc
        self.signals.progress.emit(f"Opening verify details for {gtx_reference}...")
        try:
            page.get_by_role("link", name=gtx_reference).click(timeout=30000)
        except Exception:
            page.locator(f'a:has-text("{gtx_reference}")').first.click(timeout=30000)
        page.locator("#container-body").wait_for(timeout=30000)
        page.wait_for_timeout(500)
        details_locator = page.locator("#container-body")
        return {
            "text": details_locator.inner_text(),
            "html": details_locator.inner_html(),
        }

    def _build_result(self, approval_reference, payment, status, details, detail_payload=None):
        result = {
            "template": approval_reference.template,
            "reference": approval_reference.reference,
            "expected_amount": f"{payment.get('amount', 0):,.2f}" if payment else "",
            "expected_date": payment.get("value_date", "") if payment else "",
            "status": status,
            "details": details,
        }
        if detail_payload:
            result["payment_copy"] = format_payment_copy(
                approval_reference.template,
                approval_reference.reference,
                detail_payload.get("text", ""),
            )
            result["payment_copy_html"] = detail_payload.get("html", "")
        return result

    def _emit_and_store(self, results, result):
        results.append(result)
        self._emit_result_update(result)

    def _emit_live_result(self, approval_reference, payment, status, details):
        self._emit_result_update(
            self._build_result(
                approval_reference,
                payment,
                status,
                details,
            )
        )

    def _click_verify(self, page, gtx_reference):
        self.signals.progress.emit(f"Clicking Verify for {gtx_reference}...")
        try:
            page.get_by_role("button", name="Verify").click(timeout=15000)
        except Exception:
            page.locator('input[value="Verify"], button:has-text("Verify")').first.click(timeout=15000)
        page.locator("#container-body").wait_for(timeout=30000)
        page.wait_for_timeout(500)
        page.locator("#container-body").get_by_text(gtx_reference).first.wait_for(timeout=30000)

    def _visible_title_input(self, page, title_prefix):
        locator = page.locator(f'[title^="{title_prefix}"]:visible')
        locator.first.wait_for(timeout=15000)
        count = locator.count()
        if count != 1:
            raise ValueError(f"Expected one visible input titled '{title_prefix}', found {count}")
        return locator.first

    def _fill_and_read_input(self, page, title_prefix, value):
        field = self._visible_title_input(page, title_prefix)
        field.click()
        page.wait_for_timeout(200)
        field.press("ControlOrMeta+a")
        field.fill(value)
        page.wait_for_timeout(200)
        return field.input_value().strip()

    def _assert_verify_edit_page_matches_locked_payment(self, page, payment, gtx_reference):
        container = page.locator("#container-body")
        container.wait_for(timeout=30000)
        edit_text = container.inner_text()
        if gtx_reference not in edit_text:
            raise ValueError(f"Verify edit page reference mismatch: expected {gtx_reference}")

        expected_bic = expected_to_bic(payment)
        if expected_bic and expected_bic not in edit_text.replace(" ", ""):
            raise ValueError(f"Verify edit page missing expected To BIC {expected_bic}")

        expected_narrative = compact_text(
            build_narrative(payment.get("reference", "CO5590"), payment.get("otr_number", ""))
        )
        if expected_narrative and expected_narrative not in compact_text(edit_text):
            raise ValueError("Verify edit page missing expected remittance narrative")

    def _fill_pacs_verify_form(self, page, payment, gtx_reference):
        self._assert_verify_edit_page_matches_locked_payment(page, payment, gtx_reference)
        values = approval_confirmation_values(payment)
        if not values.currency or not values.amount or not values.value_date:
            raise ValueError("Missing expected currency, amount, or value date for approval confirmation")

        entered_currency = self._fill_and_read_input(page, "You can enter currency ISO", values.currency)
        entered_amount = self._fill_and_read_input(page, "Enter amount with a dot as", values.amount)
        entered_date = self._fill_and_read_input(page, "You can enter date in format", values.value_date)

        if entered_currency.upper() != values.currency:
            raise ValueError(f"Currency read-back mismatch: expected {values.currency}, found {entered_currency}")

        if normalize_amount(entered_amount) != normalize_amount(values.amount):
            raise ValueError(f"Amount read-back mismatch: expected {values.amount}, found {entered_amount}")

        if normalize_date(entered_date) != values.value_date:
            raise ValueError(f"Date read-back mismatch: expected {values.value_date}, found {entered_date}")

        self._assert_verify_edit_page_matches_locked_payment(page, payment, gtx_reference)
        return values

    def _click_verify_cell(self, page, name):
        cell = page.get_by_role("cell", name=name, exact=True).first
        cell.wait_for(timeout=15000)
        cell.click(timeout=15000)
        page.wait_for_timeout(200)

    def _fill_mt101_verify_form(self, page, payment, gtx_reference):
        self._assert_verify_edit_page_matches_locked_payment(page, payment, gtx_reference)
        values = approval_confirmation_values(payment)
        if not values.currency or not values.amount:
            raise ValueError("Missing expected currency or amount for CZK/MT101 approval confirmation")

        self._click_verify_cell(page, "Currency")
        entered_currency = self._fill_and_read_input(page, "You can enter currency ISO", values.currency)

        self._click_verify_cell(page, "Amount")
        entered_amount = self._fill_and_read_input(page, "Enter amount with a dot as", values.amount)

        if entered_currency.upper() != values.currency:
            raise ValueError(f"CZK/MT101 currency read-back mismatch: expected {values.currency}, found {entered_currency}")

        if normalize_amount(entered_amount) != normalize_amount(values.amount):
            raise ValueError(f"CZK/MT101 amount read-back mismatch: expected {values.amount}, found {entered_amount}")

        self._assert_verify_edit_page_matches_locked_payment(page, payment, gtx_reference)
        return values

    def _fill_verify_form(self, page, payment, gtx_reference):
        flow = approval_flow(payment)
        if flow == "pacs":
            return self._fill_pacs_verify_form(page, payment, gtx_reference)
        if flow == "mt101":
            return self._fill_mt101_verify_form(page, payment, gtx_reference)
        raise ValueError("No automated approval form flow is configured for this payment")

    def _submit_verify_form(self, page, gtx_reference):
        self.signals.progress.emit(f"Submitting approval for {gtx_reference}...")
        page.get_by_role("button", name="Ok").click(timeout=15000)
        success_message = page.get_by_text("Message is successfully").first
        success_message.wait_for(timeout=30000)
        return success_message.inner_text()

    def _search_processed_skip_result(self, page, approval_reference, payment, verify_exc):
        self.signals.progress.emit(
            f"{approval_reference.reference} is not in Verify; checking Search before skipping..."
        )
        search_details = self._search_details(page, approval_reference.reference)
        search_decision = build_approval_precheck_decision(
            payment,
            approval_reference.reference,
            search_details["text"],
        )
        if search_decision.status == "Skipped - already processed":
            return self._build_result(
                approval_reference,
                payment,
                "Skipped - already processed",
                f"{search_decision.details}; not found in Verify queue",
            )

        status = "Failed before approval" if search_decision.status == "Ready for approval" else search_decision.status
        return self._build_result(
            approval_reference,
            payment,
            status,
            f"{verify_exc}; Search-page check did not confirm safe skip: {search_decision.details}",
        )

    def _attach_payment_copies_for_results(self, page, results, payments_by_reference):
        for result in results:
            if result.get("status") not in {"Approved", "Skipped - already processed"}:
                continue

            reference = str(result.get("reference") or "").strip()
            payment = payments_by_reference.get(reference)
            try:
                details = self._search_details(page, reference)
                if payment:
                    audit_result = compare_payment_details(payment, reference, details["text"])
                    if audit_result.issues:
                        result["status"] = "Status unknown" if result.get("status") == "Approved" else "Needs manual review"
                        result["details"] = (
                            f"{result.get('details', '')}; final Search copy check found: "
                            + "; ".join(audit_result.issues)
                        )
                        self._emit_result_update(result)
                        continue

                result["payment_copy"] = format_payment_copy(result.get("template", ""), reference, details["text"])
                result["payment_copy_html"] = details["html"]
                self._emit_result_update(result)
            except Exception as exc:
                result["details"] = f"{result.get('details', '')}; payment copy capture failed: {exc}"
                self._emit_result_update(result)

    def run(self):
        if not PLAYWRIGHT_AVAILABLE:
            self.signals.error.emit("Playwright not installed. Run: pip install playwright")
            return

        browser = None
        context = None
        cdp_process = None
        results = []
        used_rows = set()
        payments_by_reference = {}

        try:
            self.signals.progress.emit("Starting approval run...")
            with sync_playwright() as p:
                browser, context, page, cdp_process = self._launch_page(p)
                self._login(page)

                for index, approval_reference in enumerate(self.approval_references, start=1):
                    if not self.is_running:
                        break

                    self.signals.progress.emit(
                        f"Approval {index}/{len(self.approval_references)}: {approval_reference.reference}"
                    )
                    payment = self._payment_for_reference(approval_reference, used_rows)
                    if not payment:
                        result = self._build_result(
                            approval_reference,
                            None,
                            "Needs manual review",
                            "No matching Excel row found for this template; approval run stopped",
                        )
                        self._emit_and_store(results, result)
                        break

                    payments_by_reference[approval_reference.reference] = payment
                    stage = "before approval"
                    try:
                        try:
                            verify_details = self._search_verify_details(page, approval_reference.reference)
                        except VerifyReferenceNotFound as verify_exc:
                            result = self._search_processed_skip_result(
                                page,
                                approval_reference,
                                payment,
                                verify_exc,
                            )
                            self._emit_and_store(results, result)
                            if result.get("status") == "Skipped - already processed":
                                continue
                            break

                        verify_decision = build_approval_precheck_decision(
                            payment,
                            approval_reference.reference,
                            verify_details["text"],
                        )
                        if not verify_decision.can_approve:
                            result = self._build_result(
                                approval_reference,
                                payment,
                                verify_decision.status,
                                f"Verify-page gate failed: {verify_decision.details}",
                            )
                            self._emit_and_store(results, result)
                            break

                        self._emit_live_result(
                            approval_reference,
                            payment,
                            "Verify details matched",
                            "All checked fields match; Verify details checked against Excel",
                        )
                        stage = "after verify click before OK"
                        self._click_verify(page, approval_reference.reference)
                        self._fill_verify_form(page, payment, approval_reference.reference)
                        self._emit_live_result(
                            approval_reference,
                            payment,
                            "Confirmation values checked",
                            "All checked fields match; confirmation values entered and read back",
                        )
                        stage = "after OK click"
                        success_text = self._submit_verify_form(page, approval_reference.reference)
                        result = self._build_result(
                            approval_reference,
                            payment,
                            "Approved",
                            success_text or "Message is successfully approved",
                        )
                        self._emit_and_store(results, result)
                    except Exception as exc:
                        if stage == "after verify click before OK":
                            status = "Failed after verify click before OK"
                        elif stage == "after OK click":
                            status = "Status unknown"
                        else:
                            status = "Failed before approval"
                        result = self._build_result(
                            approval_reference,
                            payment,
                            status,
                            f"Approval run failed at stage '{stage}': {exc}",
                        )
                        self._emit_and_store(results, result)
                        break

                self._attach_payment_copies_for_results(page, results, payments_by_reference)
                approved_count = sum(1 for result in results if result.get("status") == "Approved")
                self.signals.finished.emit({
                    "status": "approval_run",
                    "message": f"Approval run complete: {approved_count} approved, {len(results)} checked",
                    "results": results,
                })
        except Exception as exc:
            self.signals.error.emit(f"Approval run error: {exc}")
        finally:
            try:
                if context:
                    context.close()
                if browser:
                    browser.close()
                if cdp_process and cdp_process.poll() is None:
                    cdp_process.terminate()
            except Exception:
                pass


# Main application window
class SimplePaymentApp(QMainWindow):
    # Class variable for storing the original window title
    BASE_WINDOW_TITLE = "Payments Release - GTExchange Payment Automation"
    
    def __init__(self):
        super().__init__()
        self.setWindowTitle(self.BASE_WINDOW_TITLE)
        self.setGeometry(100, 100, 1035, 805)  # Increased by 15% from 900x700
        
        # Set application icon
        icon_found = False
        
        # Check in current directory
        icon_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "icon.ico")
        if os.path.exists(icon_path):
            self.setWindowIcon(QIcon(icon_path))
            icon_found = True
        
        # Check in executable directory if frozen
        if not icon_found and getattr(sys, 'frozen', False):
            icon_path = os.path.join(os.path.dirname(sys.executable), "icon.ico")
            if os.path.exists(icon_path):
                self.setWindowIcon(QIcon(icon_path))
                icon_found = True
        
        # Position window on the right side of the screen
        self._position_window_right()
        
        # State variables
        self.payments_data = []
        self.worker_thread = None
        self.worker = None
        self.dark_mode = False
        self.summary_labels = {}
        self.status_spinner = None  # Will hold the status bar spinner
        self.last_error_message = ""
        self.payment_copies_by_reference = {}
        self.last_approval_results = []
        
        # Setup UI
        self._setup_ui()
        self.apply_style()
        
        # Check Playwright availability
        if not PLAYWRIGHT_AVAILABLE:
            self.statusBar.showMessage("Warning: Playwright not installed.")
    
    def _position_window_right(self):
        """Position the window on the right side of the screen"""
        screen = QApplication.primaryScreen().availableGeometry()
        window_width = self.width()
        window_height = self.height()
        
        # Position on right side with a small margin
        x_position = screen.width() - window_width - 20
        y_position = (screen.height() - window_height) // 2
        
        self.setGeometry(x_position, y_position, window_width, window_height)
    
    def _setup_ui(self):
        # Main widget and layout
        main_widget = QWidget()
        main_widget.setObjectName("appRoot")
        self.setCentralWidget(main_widget)
        main_layout = QVBoxLayout(main_widget)
        main_layout.setContentsMargins(18, 16, 18, 12)
        main_layout.setSpacing(12)

        header_frame = QFrame()
        header_frame.setObjectName("headerFrame")
        header_layout = QHBoxLayout(header_frame)
        header_layout.setContentsMargins(16, 12, 16, 12)
        header_layout.setSpacing(12)

        title_block = QVBoxLayout()
        title_block.setSpacing(2)
        title_label = QLabel("GTExchange Payment Automation")
        title_label.setObjectName("appTitle")
        subtitle_label = QLabel("Weekly funding entries from Excel to GTExchange")
        subtitle_label.setObjectName("appSubtitle")
        title_block.addWidget(title_label)
        title_block.addWidget(subtitle_label)

        self.header_status_label = QLabel("Ready")
        self.header_status_label.setObjectName("statusPill")

        self.readme_btn = QPushButton("Read Me")
        self.readme_btn.setObjectName("secondaryButton")
        self.readme_btn.clicked.connect(self._show_instructions)

        self.copy_error_btn = QPushButton("Copy Last Error")
        self.copy_error_btn.setObjectName("secondaryButton")
        self.copy_error_btn.clicked.connect(self._copy_last_error)
        self.copy_error_btn.setEnabled(False)

        self.dark_mode_toggle = QPushButton("Dark Mode")
        self.dark_mode_toggle.setObjectName("secondaryButton")
        self.dark_mode_toggle.setCheckable(True)
        self.dark_mode_toggle.clicked.connect(self.toggle_dark_mode)

        header_layout.addLayout(title_block)
        header_layout.addStretch()
        header_layout.addWidget(self.header_status_label)
        header_layout.addWidget(self.readme_btn)
        header_layout.addWidget(self.copy_error_btn)
        header_layout.addWidget(self.dark_mode_toggle)

        self.workflow_tabs = QTabWidget()
        self.workflow_tabs.setObjectName("workflowTabs")
        entry_tab = QWidget()
        entry_tab.setObjectName("entryTab")
        entry_layout = QVBoxLayout(entry_tab)
        entry_layout.setContentsMargins(0, 0, 0, 0)
        entry_layout.setSpacing(12)
        
        # Create compact setup area
        setup_layout = QHBoxLayout()
        setup_layout.setSpacing(12)

        login_group = QGroupBox("Login Details")
        login_layout = QVBoxLayout(login_group)
        login_layout.setContentsMargins(14, 18, 14, 14)
        login_layout.setSpacing(9)
        
        # Username field
        username_layout = QHBoxLayout()
        username_label = QLabel("Username:")
        username_label.setFixedWidth(72)
        self.username_input = QLineEdit()
        username_layout.addWidget(username_label)
        username_layout.addWidget(self.username_input)
        
        # Password field
        password_layout = QHBoxLayout()
        password_label = QLabel("Password:")
        password_label.setFixedWidth(72)
        self.password_input = QLineEdit()
        self.password_input.setEchoMode(QLineEdit.EchoMode.Password)
        password_layout.addWidget(password_label)
        password_layout.addWidget(self.password_input)
        
        # Remember me checkbox
        checkbox_layout = QHBoxLayout()
        self.remember_checkbox = QCheckBox("Remember me")
        self.remember_checkbox.setChecked(self._has_saved_credentials())
        checkbox_layout.addWidget(self.remember_checkbox)
        checkbox_layout.addStretch()
        
        login_layout.addLayout(username_layout)
        login_layout.addLayout(password_layout)
        login_layout.addLayout(checkbox_layout)
        
        # Excel import group
        excel_group = QGroupBox("Excel Import")
        excel_layout = QVBoxLayout(excel_group)
        excel_layout.setContentsMargins(14, 18, 14, 14)
        excel_layout.setSpacing(10)
        
        self.file_path_input = QLineEdit()
        self.file_path_input.setReadOnly(True)
        self.file_path_input.setPlaceholderText("Select the weekly funding Excel file")
        excel_layout.addWidget(self.file_path_input)
        
        button_layout = QHBoxLayout()
        button_layout.setSpacing(8)
        button_layout.addStretch()
        
        self.browse_btn = QPushButton("Browse")
        self.browse_btn.setObjectName("secondaryButton")
        self.browse_btn.clicked.connect(self._browse_and_load)
        self.browse_btn.setFixedWidth(80)
        button_layout.addWidget(self.browse_btn)
        
        self.clear_btn = QPushButton("Clear")
        self.clear_btn.setObjectName("secondaryButton")
        self.clear_btn.clicked.connect(self._clear_data)
        self.clear_btn.setFixedWidth(80)
        button_layout.addWidget(self.clear_btn)
        
        excel_layout.addLayout(button_layout)

        setup_layout.addWidget(login_group, 1)
        setup_layout.addWidget(excel_group, 2)

        # Data preview group
        data_group = QGroupBox("Payment Data")
        data_layout = QVBoxLayout(data_group)
        data_layout.setContentsMargins(14, 18, 14, 14)
        data_layout.setSpacing(10)

        table_toolbar_layout = QHBoxLayout()
        table_toolbar_layout.setSpacing(10)
        for key, label_text in (
            ("total", "Total: 0"),
            ("pending", "Pending: 0"),
            ("completed", "Completed: 0"),
            ("errors", "Errors: 0"),
        ):
            summary_label = QLabel(label_text)
            summary_label.setObjectName(f"{key}Summary")
            table_toolbar_layout.addWidget(summary_label)
            self.summary_labels[key] = summary_label
        table_toolbar_layout.addStretch()

        self.copy_refs_btn = QPushButton("Copy References")
        self.copy_refs_btn.setObjectName("secondaryButton")
        self.copy_refs_btn.clicked.connect(self._copy_references)
        self.copy_refs_btn.setFixedWidth(130)
        table_toolbar_layout.addWidget(self.copy_refs_btn)
        data_layout.addLayout(table_toolbar_layout)
        
        self.table_widget = QTableWidget()
        self.table_widget.setColumnCount(7)  # Removed Row# column
        self.table_widget.setHorizontalHeaderLabels([
            "Amount", "Template", "OTR Number", "Unit", "Status", "Reference", "Value Date"
        ])
        self.table_widget.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.table_widget.setAlternatingRowColors(True)
        self.table_widget.verticalHeader().setVisible(False)
        self.table_widget.setShowGrid(False)
        self.table_widget.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table_widget.setEditTriggers(
            QAbstractItemView.EditTrigger.DoubleClicked | QAbstractItemView.EditTrigger.SelectedClicked
        )
        self.table_widget.setWordWrap(False)
        
        # Connect double-click event for Value Date column
        self.table_widget.cellDoubleClicked.connect(self._show_calendar)
        
        data_layout.addWidget(self.table_widget)
        
        # Start button with better styling
        self.start_btn = QPushButton("Start Automation")
        self.start_btn.setObjectName("primaryButton")
        self.start_btn.clicked.connect(self._start_automation)
        self.start_btn.setEnabled(False)
        self.start_btn.setMinimumHeight(36)  # Make button taller
        
        # Create start button layout with spinner icon
        start_btn_layout = QHBoxLayout()
        self.start_spinner = SpinningIcon(size=24)
        self.start_spinner.setVisible(False)  # Hidden by default
        start_btn_layout.addWidget(self.start_spinner)
        start_btn_layout.addWidget(self.start_btn)
        start_btn_layout.setAlignment(self.start_spinner, Qt.AlignmentFlag.AlignVCenter)
        
        # Add widgets to main layout
        entry_layout.addLayout(setup_layout)
        entry_layout.addWidget(data_group)
        entry_layout.addLayout(start_btn_layout)

        self.workflow_tabs.addTab(entry_tab, "Payment Entry")
        self.workflow_tabs.addTab(self._build_approval_tab(), "Approval")

        main_layout.addWidget(header_frame)
        main_layout.addWidget(self.workflow_tabs)
        
        # Status bar with better styling
        self.statusBar = QStatusBar()
        self.setStatusBar(self.statusBar)
        
        # Create status bar spinner and add it to status bar
        self.status_spinner = SpinningIcon(size=16)
        self.status_spinner.setVisible(False)
        self.statusBar.addPermanentWidget(self.status_spinner)
        self.statusBar.showMessage("Ready")
        self._update_summary()
        
        # Load saved credentials if available
        self._load_credentials()

    def _build_approval_tab(self):
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(12)

        excel_group = QGroupBox("Excel Import")
        excel_layout = QVBoxLayout(excel_group)
        excel_layout.setContentsMargins(14, 18, 14, 14)
        excel_layout.setSpacing(10)

        self.approval_file_path_input = QLineEdit()
        self.approval_file_path_input.setReadOnly(True)
        self.approval_file_path_input.setPlaceholderText("Select the weekly funding Excel file")
        excel_layout.addWidget(self.approval_file_path_input)

        approval_button_layout = QHBoxLayout()
        approval_button_layout.setSpacing(8)
        approval_button_layout.addStretch()

        self.approval_browse_btn = QPushButton("Browse")
        self.approval_browse_btn.setObjectName("secondaryButton")
        self.approval_browse_btn.clicked.connect(self._browse_and_load)
        self.approval_browse_btn.setFixedWidth(80)
        approval_button_layout.addWidget(self.approval_browse_btn)

        self.approval_clear_btn = QPushButton("Clear")
        self.approval_clear_btn.setObjectName("secondaryButton")
        self.approval_clear_btn.clicked.connect(self._clear_data)
        self.approval_clear_btn.setFixedWidth(80)
        approval_button_layout.addWidget(self.approval_clear_btn)

        excel_layout.addLayout(approval_button_layout)

        refs_group = QGroupBox("Approval References")
        refs_layout = QVBoxLayout(refs_group)
        refs_layout.setContentsMargins(14, 18, 14, 14)
        refs_layout.setSpacing(10)

        self.approval_refs_input = QTextEdit()
        self.approval_refs_input.setPlaceholderText("APAUDPACS: E008260612AOCYOF\nAPCHFPACS: E008260612AOCYOI")
        self.approval_refs_input.setMinimumHeight(110)
        refs_layout.addWidget(self.approval_refs_input)

        action_layout = QHBoxLayout()
        action_layout.addStretch()

        self.approval_run_btn = QPushButton("Run Approval")
        self.approval_run_btn.setObjectName("primaryButton")
        self.approval_run_btn.clicked.connect(self._start_approval_run)
        action_layout.addWidget(self.approval_run_btn)
        refs_layout.addLayout(action_layout)

        results_group = QGroupBox("Approval Results")
        results_layout = QVBoxLayout(results_group)
        results_layout.setContentsMargins(14, 18, 14, 14)
        results_layout.setSpacing(10)

        results_action_layout = QHBoxLayout()
        results_action_layout.addStretch()

        self.copy_payment_copies_btn = QPushButton("Copy Payment Copies")
        self.copy_payment_copies_btn.setObjectName("secondaryButton")
        self.copy_payment_copies_btn.clicked.connect(self._copy_payment_copies)
        self.copy_payment_copies_btn.setEnabled(False)
        results_action_layout.addWidget(self.copy_payment_copies_btn)

        self.export_audit_pdf_btn = QPushButton("Export Matched Copies PDF")
        self.export_audit_pdf_btn.setObjectName("secondaryButton")
        self.export_audit_pdf_btn.clicked.connect(self._export_approval_audit_pdf)
        self.export_audit_pdf_btn.setEnabled(False)
        results_action_layout.addWidget(self.export_audit_pdf_btn)
        results_layout.addLayout(results_action_layout)

        self.approval_results_table = QTableWidget()
        self.approval_results_table.setColumnCount(6)
        self.approval_results_table.setHorizontalHeaderLabels([
            "Template", "GTX Reference", "Expected Amount", "Value Date", "Result", "Details"
        ])
        approval_header = self.approval_results_table.horizontalHeader()
        for col in range(5):
            approval_header.setSectionResizeMode(col, QHeaderView.ResizeMode.Fixed)
        approval_header.setSectionResizeMode(5, QHeaderView.ResizeMode.Stretch)
        self.approval_results_table.setColumnWidth(0, 105)
        self.approval_results_table.setColumnWidth(1, 143)
        self.approval_results_table.setColumnWidth(2, 116)
        self.approval_results_table.setColumnWidth(3, 85)
        self.approval_results_table.setColumnWidth(4, 127)
        self.approval_results_table.setAlternatingRowColors(True)
        self.approval_results_table.verticalHeader().setVisible(False)
        self.approval_results_table.setShowGrid(False)
        self.approval_results_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.approval_results_table.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.approval_results_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.approval_results_table.setWordWrap(False)
        self.approval_results_table.setMinimumHeight(320)
        self.approval_results_table.cellDoubleClicked.connect(self._show_approval_result_details)
        self.approval_select_all_shortcut = QShortcut(QKeySequence.StandardKey.SelectAll, self.approval_results_table)
        self.approval_select_all_shortcut.setContext(Qt.ShortcutContext.WidgetWithChildrenShortcut)
        self.approval_select_all_shortcut.activated.connect(self.approval_results_table.selectAll)
        self.approval_copy_shortcut = QShortcut(QKeySequence.StandardKey.Copy, self.approval_results_table)
        self.approval_copy_shortcut.setContext(Qt.ShortcutContext.WidgetWithChildrenShortcut)
        self.approval_copy_shortcut.activated.connect(self._copy_approval_results_selection)
        results_layout.addWidget(self.approval_results_table)

        layout.addWidget(excel_group, 0)
        layout.addWidget(refs_group, 0)
        layout.addWidget(results_group, 2)
        return tab
    
    def _browse_and_load(self):
        default_folder = os.path.join(os.path.expanduser("~"), "Downloads")
        if not os.path.isdir(default_folder):
            default_folder = os.path.expanduser("~")

        file_path, _ = QFileDialog.getOpenFileName(
            self, "Select Excel File", default_folder, "Excel Files (*.xlsx *.xls)"
        )
        
        if not file_path:
            return
            
        self.file_path_input.setText(file_path)
        if hasattr(self, "approval_file_path_input"):
            self.approval_file_path_input.setText(file_path)
        self.statusBar.showMessage("Loading Excel file...")
        
        try:
            # Load the Excel file
            df = pd.read_excel(file_path)
            
            # Check if file is empty
            if df.empty:
                self.statusBar.showMessage("Error: Excel file is empty")
                return
                
            # Process the data
            self._process_data(df)
            
        except Exception as e:
            self.statusBar.showMessage(f"Error: Failed to load Excel file: {str(e)}")
    
    def _process_data(self, df):
        # Clear existing data
        self.table_widget.setRowCount(0)
        self.payments_data = []
        self._clear_payment_copies()
        
        # Expected columns with alternatives - each list contains valid alternatives for one column type
        required_columns = [
            ['Amount', 'Amounts', 'amount', 'amounts'],  # Amount variations
            ['Template', 'Templete', 'Code', 'template', 'templete', 'code'],  # Template variations
            ['OTR Number', 'OTR Numbers', 'OTR number', 'OTR numbers', 
             'Confirmation Number', 'Confirmation Numbers', 'confirmation number', 'confirmation numbers']  # OTR variations
        ]
        
        # Normalize column names by removing extra spaces and converting to lowercase
        normalized_columns = {col.lower().strip(): col for col in df.columns}
        
        # Check for required columns
        missing_columns = []
        for required_options in required_columns:
            normalized_options = [opt.lower().strip() for opt in required_options]
            if not any(norm_col in normalized_options for norm_col in normalized_columns.keys()):
                missing_columns.append(" or ".join(required_options[:2]))  # Show just a couple options in error message
        
        if missing_columns:
            missing_str = ", ".join(missing_columns)
            self.statusBar.showMessage(f"Error: Missing columns: {missing_str}")
            self.header_status_label.setText("Import error")
            self._update_summary()
            return
            
        # Find the actual column names using normalized lookup
        amount_col = None
        for amount_option in ['amount', 'amounts']:
            for col in normalized_columns.keys():
                if amount_option in col:
                    amount_col = normalized_columns[col]
                    break
            if amount_col:
                break
        
        # Find template column with similar approach
        template_col = None
        for template_option in ['template', 'templete', 'code']:
            for col in normalized_columns.keys():
                if template_option in col:
                    template_col = normalized_columns[col]
                    break
            if template_col:
                break
                
        # Find OTR column with similar approach
        otr_col = None
        for otr_option in ['otr', 'confirmation']:
            for col in normalized_columns.keys():
                if otr_option in col:
                    otr_col = normalized_columns[col]
                    break
            if otr_col:
                break

        reference_col = None
        for col in normalized_columns.keys():
            if col == 'reference':
                reference_col = normalized_columns[col]
                break
        
        # Process rows
        row_index = 1
        for _, row in df.iterrows():
            try:
                # Get template value first
                template = str(row[template_col]).strip()
                
                # Skip empty templates
                if not template:
                    continue
                    
                # Skip rows with NaN template values
                if pd.isna(row[template_col]):
                    continue

                resolved_template = resolve_payment_template(template)
                if not resolved_template or not is_valid_payment_code(template):
                    continue
                    
                # Get amount
                try:
                    # Parse the amount and ensure exactly 2 decimal places
                    amount = float(format_amount(row[amount_col]))
                except:
                    continue  # Skip invalid amounts
                    
                if amount <= 0:
                    continue
                
                # Get OTR number
                otr = str(row[otr_col]).strip() if not pd.isna(row[otr_col]) else ""
                reference = str(row[reference_col]).strip() if reference_col and not pd.isna(row[reference_col]) else "CO5590"
                
                template = resolved_template.template
                unit = resolved_template.unit
                
                # Calculate the default value date for this template
                value_date = self._get_default_value_date(template)
                
                # Add to payments data
                payment = {
                    'row_num': row_index,
                    'amount': amount,
                    'template': template,
                    'source_code': resolved_template.source_code,
                    'uses_pacs_flow': resolved_template.uses_pacs_flow,
                    'otr_number': otr,
                    'reference': reference,
                    'unit': unit,
                    'status': 'Pending',
                    'value_date': value_date
                }
                self.payments_data.append(payment)
                
                # Add row to table
                table_row = self.table_widget.rowCount()
                self.table_widget.insertRow(table_row)
                self.table_widget.setItem(table_row, 0, QTableWidgetItem(f"{amount:,.2f}"))
                self.table_widget.setItem(table_row, 1, QTableWidgetItem(template))
                self.table_widget.setItem(table_row, 2, QTableWidgetItem(otr))
                self.table_widget.setItem(table_row, 3, QTableWidgetItem(unit))
                self.table_widget.setItem(table_row, 4, QTableWidgetItem("Pending"))
                self.table_widget.setItem(table_row, 5, QTableWidgetItem(""))  # Empty reference
                
                # Add value date column (editable)
                date_item = QTableWidgetItem(value_date)
                date_item.setFlags(date_item.flags() | Qt.ItemFlag.ItemIsEditable)
                self.table_widget.setItem(table_row, 6, date_item)
                self.table_widget.setRowHeight(table_row, 30)
                
                row_index += 1
                
            except Exception as e:
                print(f"Error processing row: {e}")
        
        # Update status
        if self.payments_data:
            self.statusBar.showMessage(f"Loaded {len(self.payments_data)} payments")
            self.header_status_label.setText(f"{len(self.payments_data)} loaded")
            self.start_btn.setEnabled(True)
        else:
            self.statusBar.showMessage("No valid payments found in file")
            self.header_status_label.setText("No valid payments")
            self.start_btn.setEnabled(False)
        self._populate_approval_preview_from_payments()
        self._update_summary()
    
    def _get_default_value_date(self, template_name):
        """Calculate the default value date based on template rules and skip weekends"""
        today = datetime.now()
        next_day_templates = [
            "APFUNDINGAUD", "APFUNDINGCHF", "APFUNDINGCZK", "APFUNDINGGBP",
            "APFUNDINGGBP2", "APFUNDINGHKD", "APFUNDINGJPY", "APFUNDINGNZD",
            "APFUNDINGPLN", "APFUNDINGSGD", "EURPAYMENTAP2",
            "APAUDPACS", "APCHFPACS", "APGBPPACS", "APGBPPACS2",
            "APHKDPACS", "APJPYPACS", "APNZDPACS", "APPLNPACS",
            "APSGDPACS", "EURPMTAP2PACS"
        ]
        
        if template_name in next_day_templates:
            # Add one day initially
            target_date = today + timedelta(days=1)
            
            # Check if it's a weekend and adjust to next Monday if needed
            weekday = target_date.weekday()  # 0=Monday, 5=Saturday, 6=Sunday
            
            if weekday == 5:  # Saturday
                target_date += timedelta(days=2)  # Move to Monday
            elif weekday == 6:  # Sunday
                target_date += timedelta(days=1)  # Move to Monday
        else:
            target_date = today
            
        return target_date.strftime("%d.%m.%Y")
    
    def _clear_data(self):
        self.file_path_input.clear()
        if hasattr(self, "approval_file_path_input"):
            self.approval_file_path_input.clear()
        if hasattr(self, "approval_results_table"):
            self.approval_results_table.setRowCount(0)
        self._clear_payment_copies()
        self.table_widget.setRowCount(0)
        self.payments_data = []
        self.start_btn.setEnabled(False)
        self.statusBar.showMessage("Data cleared")
        self.header_status_label.setText("Ready")
        self._update_summary()
    
    def _start_automation(self):
        if not self.payments_data:
            self.statusBar.showMessage("Error: No payment data loaded")
            return
            
        username = self.username_input.text()
        password = self.password_input.text()
        
        if not username or not password:
            self.statusBar.showMessage("Error: Username and password are required")
            return
        
        # Save credentials if remember me is checked
        if self.remember_checkbox.isChecked():
            self._save_credentials()
        elif not self.remember_checkbox.isChecked():
            self._clear_credentials()
        
        # Update value dates from the table before starting automation
        self._update_value_dates_from_table()
        self.last_error_message = ""
        self.copy_error_btn.setEnabled(False)
            
        # Start immediately without confirmation popup
        # Disable inputs during automation
        self.username_input.setEnabled(False)
        self.password_input.setEnabled(False)
        self.remember_checkbox.setEnabled(False)
        self.browse_btn.setEnabled(False)
        self.clear_btn.setEnabled(False)
        self.start_btn.setEnabled(False)
        if hasattr(self, "approval_browse_btn"):
            self.approval_browse_btn.setEnabled(False)
        if hasattr(self, "approval_clear_btn"):
            self.approval_clear_btn.setEnabled(False)
        if hasattr(self, "approval_audit_btn"):
            self.approval_audit_btn.setEnabled(False)
        if hasattr(self, "approval_run_btn"):
            self.approval_run_btn.setEnabled(False)
        
        # Start the spinner animations
        self.start_spinner.setVisible(True)
        self.start_spinner.start_spinning()
        self.status_spinner.setVisible(True)
        self.status_spinner.start_spinning()
        self.header_status_label.setText("Running")
        
        # Create and start worker thread
        self.worker = BrowserWorker(username, password, "", self.payments_data)
        self.worker_thread = QThread()
        self.worker.moveToThread(self.worker_thread)
        
        # Connect signals
        self.worker.signals.progress.connect(self._update_progress)
        self.worker.signals.error.connect(self._handle_error)
        self.worker.signals.finished.connect(self._handle_finished)
        self.worker_thread.started.connect(self.worker.run)
        
        # Start the thread
        self.worker_thread.start()

    def _start_approval_audit(self):
        if not self.payments_data:
            self.statusBar.showMessage("Error: Load the Excel file before running approval audit")
            return

        approval_references = parse_reference_lines(self.approval_refs_input.toPlainText())
        if not approval_references:
            self.statusBar.showMessage("Error: Paste approval references before running approval")
            return

        username = self.username_input.text()
        password = self.password_input.text()
        if not username or not password:
            self.statusBar.showMessage("Error: Username and password are required")
            return

        self._update_value_dates_from_table()
        self._populate_approval_pending_results(approval_references)
        self._clear_payment_copies()
        self.last_error_message = ""
        self.copy_error_btn.setEnabled(False)

        self.username_input.setEnabled(False)
        self.password_input.setEnabled(False)
        self.remember_checkbox.setEnabled(False)
        self.browse_btn.setEnabled(False)
        self.clear_btn.setEnabled(False)
        self.start_btn.setEnabled(False)
        if hasattr(self, "approval_audit_btn"):
            self.approval_audit_btn.setEnabled(False)
        self.approval_run_btn.setEnabled(False)
        self.approval_browse_btn.setEnabled(False)
        self.approval_clear_btn.setEnabled(False)

        self.status_spinner.setVisible(True)
        self.status_spinner.start_spinning()
        self.header_status_label.setText("Audit running")

        self.worker = ApprovalAuditWorker(username, password, approval_references, self.payments_data)
        self.worker_thread = QThread()
        self.worker.moveToThread(self.worker_thread)
        self.worker.signals.progress.connect(self._update_progress)
        self.worker.signals.error.connect(self._handle_error)
        self.worker.signals.finished.connect(self._handle_finished)
        self.worker_thread.started.connect(self.worker.run)
        self.worker_thread.start()

    def _start_approval_run(self):
        if not self.payments_data:
            self.statusBar.showMessage("Error: Load the Excel file before running approval")
            return

        approval_references = parse_reference_lines(self.approval_refs_input.toPlainText())
        if not approval_references:
            self.statusBar.showMessage("Error: Paste approval references before running approval")
            return

        username = self.username_input.text()
        password = self.password_input.text()
        if not username or not password:
            self.statusBar.showMessage("Error: Username and password are required")
            return

        confirmation = QMessageBox.question(
            self,
            "Run Approval",
            "This will approve matching PACS and CZK/MT101 payments in GTExchange by clicking Verify and Ok. "
            "Continue?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if confirmation != QMessageBox.StandardButton.Yes:
            self.statusBar.showMessage("Approval cancelled")
            return

        self._update_value_dates_from_table()
        self._populate_approval_pending_results(approval_references)
        self._clear_payment_copies()
        self.last_error_message = ""
        self.copy_error_btn.setEnabled(False)

        self.username_input.setEnabled(False)
        self.password_input.setEnabled(False)
        self.remember_checkbox.setEnabled(False)
        self.browse_btn.setEnabled(False)
        self.clear_btn.setEnabled(False)
        self.start_btn.setEnabled(False)
        if hasattr(self, "approval_audit_btn"):
            self.approval_audit_btn.setEnabled(False)
        self.approval_run_btn.setEnabled(False)
        self.approval_browse_btn.setEnabled(False)
        self.approval_clear_btn.setEnabled(False)

        self.status_spinner.setVisible(True)
        self.status_spinner.start_spinning()
        self.header_status_label.setText("Approval running")

        self.worker = ApprovalRunWorker(username, password, approval_references, self.payments_data)
        self.worker_thread = QThread()
        self.worker.moveToThread(self.worker_thread)
        self.worker.signals.progress.connect(self._update_progress)
        self.worker.signals.error.connect(self._handle_error)
        self.worker.signals.finished.connect(self._handle_finished)
        self.worker_thread.started.connect(self.worker.run)
        self.worker_thread.start()
    
    def _update_value_dates_from_table(self):
        """Update the payment data with user-edited value dates from the table"""
        for row_idx in range(self.table_widget.rowCount()):
            # Get the value date from the date column (column 6)
            date_item = self.table_widget.item(row_idx, 6)
            if not date_item:
                continue
                
            value_date = date_item.text().strip()
            
            # Update the corresponding payment data
            for payment in self.payments_data:
                if payment['row_num'] == row_idx + 1:
                    payment['value_date'] = value_date
                    break
    
    def _update_progress(self, message):
        if message.startswith("APPROVAL_RESULT:"):
            try:
                result = json.loads(message.split(":", 1)[1])
                self._update_approval_result_row(result)
                self._update_payment_copy_output(result)
            except Exception as exc:
                self.statusBar.showMessage(f"Could not update approval result: {exc}")
            return

        # Check if this is a status update for a specific payment
        if message.startswith("REF:"):
            # Format is REF:row_num:reference
            parts = message.split(":", 2)
            if len(parts) == 3:
                try:
                    row_num = int(parts[1])
                    reference = parts[2]
                    self._update_payment_reference(row_num, reference)
                    return
                except ValueError:
                    pass
        
        # Check if this is a status update
        status_update_match = re.match(r"STATUS:(\d+):(.+)", message)
        if status_update_match:
            row_num = int(status_update_match.group(1))
            status = status_update_match.group(2)
            self._update_payment_status(row_num, status)
            return
            
        # Regular progress message
        self.statusBar.showMessage(message)
        if hasattr(self, "header_status_label"):
            if isinstance(self.worker, ApprovalRunWorker):
                running_text = "Approval running"
            elif isinstance(self.worker, ApprovalAuditWorker):
                running_text = "Audit running"
            else:
                running_text = "Running"
            self.header_status_label.setText(running_text if self.worker else "Ready")
        QApplication.processEvents()  # Process UI events to update immediately
    
    def _table_row_for_payment(self, row_num):
        row_idx = row_num - 1
        if 0 <= row_idx < self.table_widget.rowCount():
            return row_idx
        return None

    def _apply_row_status_style(self, row_idx, status):
        if status == "Completed":
            bg_color = QColor(24, 84, 58) if self.dark_mode else QColor(222, 247, 232)
            text_color = QColor(235, 255, 244) if self.dark_mode else QColor(18, 83, 48)
        elif status == "Error":
            bg_color = QColor(112, 42, 48) if self.dark_mode else QColor(255, 226, 226)
            text_color = QColor(255, 241, 241) if self.dark_mode else QColor(126, 30, 30)
        else:
            bg_color = None
            text_color = None

        for col in range(self.table_widget.columnCount()):
            item = self.table_widget.item(row_idx, col)
            if item:
                item.setBackground(QBrush(bg_color) if bg_color else QBrush())
                item.setForeground(QBrush(text_color) if text_color else QBrush())

    def _refresh_table_theme(self):
        if not hasattr(self, "table_widget"):
            return

        for row in range(self.table_widget.rowCount()):
            status_item = self.table_widget.item(row, 4)
            status = status_item.text().strip() if status_item else ""
            self._apply_row_status_style(row, status)

        if hasattr(self, "approval_results_table"):
            for row in range(self.approval_results_table.rowCount()):
                status_item = self.approval_results_table.item(row, 4)
                status = status_item.text().strip() if status_item else ""
                self._apply_approval_result_style(row, status)

    def _update_payment_status(self, row_num, status):
        """Update the status of a specific payment in the table."""
        row_idx = self._table_row_for_payment(row_num)
        if row_idx is None:
            self.statusBar.showMessage(f"Could not update status for payment #{row_num}: row not found")
            return

        self.table_widget.setItem(row_idx, 4, QTableWidgetItem(status))
        self._apply_row_status_style(row_idx, status)
        self._update_summary()
        QApplication.processEvents()
    
    def _update_payment_reference(self, row_num, reference):
        """Update the reference for a specific payment row in the UI table"""
        self.statusBar.showMessage(f"Reference extracted: {reference} for payment #{row_num}")
        
        row_idx = self._table_row_for_payment(row_num)
        if row_idx is None:
            self.statusBar.showMessage(f"Could not update reference for payment #{row_num}: row not found")
            return

        self.table_widget.setItem(row_idx, 5, QTableWidgetItem(reference))
        self.table_widget.setItem(row_idx, 4, QTableWidgetItem("Completed"))
        self._apply_row_status_style(row_idx, "Completed")
        self._update_summary()
        QApplication.processEvents()
    
    def _handle_error(self, error_message):
        self.last_error_message = error_message
        self.statusBar.showMessage(f"ERROR: {error_message}")
        self.header_status_label.setText("Error")
        self.copy_error_btn.setEnabled(True)
        self._cleanup_worker()
        self._show_error_details(error_message)

    def _show_error_details(self, error_message):
        dialog = QDialog(self)
        dialog.setWindowTitle("Automation Error")
        dialog.resize(720, 360)

        layout = QVBoxLayout(dialog)
        layout.setContentsMargins(14, 14, 14, 14)
        layout.setSpacing(10)

        summary_label = QLabel("Automation failed. Full error details are below.")
        summary_label.setWordWrap(True)
        layout.addWidget(summary_label)

        error_text = QTextEdit()
        error_text.setReadOnly(True)
        error_text.setPlainText(error_message)
        error_text.selectAll()
        layout.addWidget(error_text)

        button_layout = QHBoxLayout()
        button_layout.addStretch()

        copy_btn = QPushButton("Copy Error")
        copy_btn.setObjectName("secondaryButton")
        copy_btn.clicked.connect(lambda: self._copy_error_text(error_message, copy_btn))
        button_layout.addWidget(copy_btn)

        close_btn = QPushButton("Close")
        close_btn.setObjectName("secondaryButton")
        close_btn.clicked.connect(dialog.accept)
        button_layout.addWidget(close_btn)

        layout.addLayout(button_layout)
        dialog.exec()

    def _copy_error_text(self, error_message, button=None, status_message="Error details copied to clipboard"):
        QApplication.clipboard().setText(error_message)
        self.statusBar.showMessage(status_message)
        if button:
            original_text = button.text()
            button.setText("Copied")
            QTimer.singleShot(1500, lambda: button.setText(original_text))

    def _copy_last_error(self):
        if not self.last_error_message:
            self.statusBar.showMessage("No automation error to copy")
            return
        self._copy_error_text(self.last_error_message, self.copy_error_btn)

    def _clear_payment_copies(self):
        self.payment_copies_by_reference = {}
        self.last_approval_results = []
        if hasattr(self, "copy_payment_copies_btn"):
            self.copy_payment_copies_btn.setEnabled(False)
        if hasattr(self, "view_payment_copies_btn"):
            self.view_payment_copies_btn.setEnabled(False)
        if hasattr(self, "export_audit_pdf_btn"):
            self.export_audit_pdf_btn.setEnabled(False)

    def _populate_payment_copies(self, results):
        self.last_approval_results = list(results or [])
        self.payment_copies_by_reference = {}
        for result in results:
            payment_copy = str(result.get("payment_copy") or "").strip()
            reference = str(result.get("reference") or "").strip()
            if payment_copy and reference:
                self.payment_copies_by_reference[reference] = payment_copy
        self._refresh_payment_copies_output()

    def _update_payment_copy_output(self, result):
        self._store_live_approval_result(result)
        payment_copy = str(result.get("payment_copy") or "").strip()
        reference = str(result.get("reference") or "").strip()
        if not payment_copy or not reference:
            self._refresh_payment_copies_output()
            return

        self.payment_copies_by_reference[reference] = payment_copy
        self._refresh_payment_copies_output()

    def _store_live_approval_result(self, result):
        reference = str(result.get("reference") or "").strip()
        for index, stored_result in enumerate(self.last_approval_results):
            if reference and str(stored_result.get("reference") or "").strip() == reference:
                self.last_approval_results[index] = result
                return
        self.last_approval_results.append(result)

    def _refresh_payment_copies_output(self):
        has_payment_copies = bool(self._payment_copies_text().strip())
        if hasattr(self, "copy_payment_copies_btn"):
            self.copy_payment_copies_btn.setEnabled(has_payment_copies)
        if hasattr(self, "view_payment_copies_btn"):
            self.view_payment_copies_btn.setEnabled(has_payment_copies)
        if hasattr(self, "export_audit_pdf_btn"):
            self.export_audit_pdf_btn.setEnabled(self._has_matched_approval_results())

    def _has_matched_approval_results(self):
        return any(is_reportable_payment_copy_result(result) for result in self.last_approval_results)

    def _payment_copies_text(self):
        text = "\n\n".join(self.payment_copies_by_reference.values())
        if text:
            text += "\n"
        return text

    def _copy_payment_copies(self):
        text = self._payment_copies_text().strip()
        if not text:
            self.statusBar.showMessage("No payment copies to copy yet")
            return

        self._copy_error_text(
            text + "\n",
            self.copy_payment_copies_btn,
            "Payment copies copied to clipboard",
        )

    def _show_payment_copies(self):
        text = self._payment_copies_text().strip()
        if not text:
            self.statusBar.showMessage("No payment copies to view yet")
            return

        dialog = QDialog(self)
        dialog.setWindowTitle("Payment Copies")
        dialog.resize(820, 520)

        layout = QVBoxLayout(dialog)
        layout.setContentsMargins(14, 14, 14, 14)
        layout.setSpacing(10)

        copies_text = QTextEdit()
        copies_text.setReadOnly(True)
        copies_text.setPlainText(text + "\n")
        copies_text.selectAll()
        layout.addWidget(copies_text)

        button_layout = QHBoxLayout()
        button_layout.addStretch()

        copy_btn = QPushButton("Copy Payment Copies")
        copy_btn.setObjectName("secondaryButton")
        copy_btn.clicked.connect(
            lambda: self._copy_error_text(copies_text.toPlainText(), copy_btn, "Payment copies copied")
        )
        button_layout.addWidget(copy_btn)

        close_btn = QPushButton("Close")
        close_btn.setObjectName("secondaryButton")
        close_btn.clicked.connect(dialog.accept)
        button_layout.addWidget(close_btn)

        layout.addLayout(button_layout)
        dialog.exec()

    def _export_approval_audit_pdf(self):
        matched_results = [
            result for result in self.last_approval_results if is_reportable_payment_copy_result(result)
        ]
        if not matched_results:
            self.statusBar.showMessage("No matched approval payment copies to export")
            return

        default_name = format_approved_payments_pdf_name(datetime.now())
        default_path = os.path.join(os.path.expanduser("~"), "Downloads", default_name)
        if not os.path.isdir(os.path.dirname(default_path)):
            default_path = os.path.join(os.path.expanduser("~"), default_name)

        file_path, _ = QFileDialog.getSaveFileName(
            self,
            "Export Approval PDF",
            default_path,
            "PDF Files (*.pdf)",
        )
        if not file_path:
            return
        if not file_path.lower().endswith(".pdf"):
            file_path += ".pdf"

        excel_file = ""
        if hasattr(self, "approval_file_path_input"):
            excel_file = self.approval_file_path_input.text().strip()
        if not excel_file:
            excel_file = self.file_path_input.text().strip()

        report_html = build_approval_audit_html(
            matched_results,
            excel_file=os.path.basename(excel_file) if excel_file else "",
            run_date=datetime.now().strftime("%d-%b-%Y %H:%M"),
        )

        if not PLAYWRIGHT_AVAILABLE:
            error_message = "PDF export failed: Playwright is not installed."
            self.last_error_message = error_message
            self.copy_error_btn.setEnabled(True)
            self.statusBar.showMessage(error_message)
            self._show_error_details(error_message)
            return

        try:
            self.statusBar.showMessage("Rendering matched payment copies PDF with browser...")
            QApplication.processEvents()
            render_html_pdf_with_playwright(report_html, file_path, sync_playwright)
        except Exception as exc:
            error_message = f"PDF export failed: {exc}"
            self.last_error_message = error_message
            self.copy_error_btn.setEnabled(True)
            self.statusBar.showMessage(error_message)
            self._show_error_details(error_message)
            return

        self.statusBar.showMessage(f"Matched payment copies PDF exported: {file_path}")

    def _auto_export_approval_run_pdf(self, results):
        reportable_results = [
            result for result in (results or []) if is_reportable_payment_copy_result(result)
        ]
        if not reportable_results:
            return ""

        downloads_dir = os.path.join(os.path.expanduser("~"), "Downloads")
        if not os.path.isdir(downloads_dir):
            downloads_dir = os.path.expanduser("~")
        file_path = os.path.join(downloads_dir, format_approved_payments_pdf_name(datetime.now()))

        excel_file = ""
        if hasattr(self, "approval_file_path_input"):
            excel_file = self.approval_file_path_input.text().strip()
        if not excel_file:
            excel_file = self.file_path_input.text().strip()

        report_html = build_approval_audit_html(
            reportable_results,
            excel_file=os.path.basename(excel_file) if excel_file else "",
            run_date=datetime.now().strftime("%d-%b-%Y %H:%M"),
        )
        render_html_pdf_with_playwright(report_html, file_path, sync_playwright)
        return file_path
        
    def _handle_finished(self, result):
        if isinstance(result, dict):
            if result.get("status") == "approval_audit":
                results = result.get("results", [])
                self._populate_approval_results(results)
                self._populate_payment_copies(results)
                self.statusBar.showMessage(result.get("message", "Approval dry-run complete"))
                self.header_status_label.setText("Audit complete")
                self._cleanup_worker()
                return

            if result.get("status") == "approval_run":
                results = result.get("results", [])
                self._populate_approval_results(results)
                self._populate_payment_copies(results)
                self.header_status_label.setText("Approval complete")
                self._cleanup_worker()
                try:
                    pdf_path = self._auto_export_approval_run_pdf(results)
                except Exception as exc:
                    error_message = f"Approval run complete, but PDF export failed: {exc}"
                    self.last_error_message = error_message
                    self.copy_error_btn.setEnabled(True)
                    self.statusBar.showMessage(error_message)
                    self._show_error_details(error_message)
                    return

                if pdf_path:
                    self.statusBar.showMessage(
                        f"{result.get('message', 'Approval run complete')} - PDF saved: {pdf_path}"
                    )
                else:
                    self.statusBar.showMessage(
                        f"{result.get('message', 'Approval run complete')} - no payment copies to export"
                    )
                return

            message = result.get("message", "Automation completed")
            payment_references = result.get("payment_references", {})
            
            # Create status message with references
            if payment_references:
                ref_count = len(payment_references)
                status_message = f"{message} - {ref_count} references captured"
            else:
                status_message = message
            
            self.statusBar.showMessage(status_message)
            self.header_status_label.setText("Completed")
        else:
            self.statusBar.showMessage("Automation completed")
            self.header_status_label.setText("Completed")
            
        self._cleanup_worker()
        self._update_summary()

    def _populate_approval_results(self, results):
        self.approval_results_table.setRowCount(0)
        for result in results:
            row = self.approval_results_table.rowCount()
            self.approval_results_table.insertRow(row)
            self._set_approval_result_row(row, result)

    def _approval_result_from_payment(self, payment, reference="", status="Pending", details="Waiting for audit"):
        return {
            "template": approval_template_name(payment),
            "reference": reference,
            "expected_amount": f"{payment.get('amount', 0):,.2f}",
            "expected_date": payment.get("value_date", ""),
            "status": status,
            "details": details,
        }

    def _payment_for_approval_reference_preview(self, approval_reference, used_rows):
        for payment in self.payments_data:
            row_num = payment.get("row_num")
            if row_num in used_rows:
                continue
            if approval_template_name(payment) == approval_reference.template:
                used_rows.add(row_num)
                return payment
        return None

    def _populate_approval_preview_from_payments(self):
        if not hasattr(self, "approval_results_table"):
            return

        self.approval_results_table.setRowCount(0)
        for payment in self.payments_data:
            row = self.approval_results_table.rowCount()
            self.approval_results_table.insertRow(row)
            self._set_approval_result_row(
                row,
                self._approval_result_from_payment(
                    payment,
                    details="Paste approval references, then run approval",
                ),
            )

    def _populate_approval_pending_results(self, approval_references):
        self.approval_results_table.setRowCount(0)
        used_rows = set()
        for approval_reference in approval_references:
            payment = self._payment_for_approval_reference_preview(approval_reference, used_rows)
            if payment:
                result = self._approval_result_from_payment(
                    payment,
                    reference=approval_reference.reference,
                    details="Waiting for audit",
                )
            else:
                result = {
                    "template": approval_reference.template,
                    "reference": approval_reference.reference,
                    "expected_amount": "",
                    "expected_date": "",
                    "status": "Pending",
                    "details": "Waiting for audit; no matching Excel row found yet",
                }
            row = self.approval_results_table.rowCount()
            self.approval_results_table.insertRow(row)
            self._set_approval_result_row(row, result)

    def _set_approval_result_row(self, row, result):
        full_details = str(result.get("details", ""))
        display_status = str(result.get("status", ""))
        display_details = self._summarize_approval_details(full_details)
        values = [
            result.get("template", ""),
            result.get("reference", ""),
            result.get("expected_amount", ""),
            result.get("expected_date", ""),
            display_status,
            display_details,
        ]
        for col, value in enumerate(values):
            item = QTableWidgetItem(str(value))
            if col == 5:
                item.setData(Qt.ItemDataRole.UserRole, full_details)
                item.setToolTip(full_details)
            elif full_details:
                item.setToolTip(full_details)
            self.approval_results_table.setItem(row, col, item)
        self._apply_approval_result_style(row, result.get("status", ""))

    def _summarize_approval_details(self, details):
        text = str(details or "").strip()
        if not text:
            return ""
        if text.startswith("All checked fields match"):
            return text
        if text in {"Waiting for audit", "Paste approval references, then run approval"}:
            return text
        if text.startswith("Search/read failed"):
            return "Search/read failed"
        if "no matching Excel row" in text:
            return "No matching Excel row"

        labels = []
        for issue in [part.strip() for part in text.split(";") if part.strip()]:
            lower_issue = issue.lower()
            if "amount mismatch" in lower_issue:
                label = "Amount mismatch"
            elif "settlement date mismatch" in lower_issue:
                label = "Date mismatch"
            elif "unstructured remittance mismatch" in lower_issue:
                label = "Remittance mismatch"
            elif "to bic mismatch" in lower_issue:
                label = "To BIC mismatch"
            elif lower_issue.startswith("missing "):
                label = "Missing fields"
            elif "currency" in lower_issue and "mismatch" in lower_issue:
                label = "Currency mismatch"
            elif "id mismatch" in lower_issue:
                label = "Reference ID mismatch"
            else:
                label = issue

            if label not in labels:
                labels.append(label)

        return "; ".join(labels) if labels else text

    def _find_approval_result_row(self, result):
        reference = str(result.get("reference", ""))
        template = str(result.get("template", ""))
        fallback_row = None

        for row in range(self.approval_results_table.rowCount()):
            reference_item = self.approval_results_table.item(row, 1)
            template_item = self.approval_results_table.item(row, 0)
            status_item = self.approval_results_table.item(row, 4)
            row_reference = reference_item.text() if reference_item else ""
            row_template = template_item.text() if template_item else ""
            row_status = status_item.text() if status_item else ""

            if reference and row_reference == reference:
                return row
            if fallback_row is None and row_template == template and row_status == "Pending":
                fallback_row = row

        return fallback_row

    def _update_approval_result_row(self, result):
        if not hasattr(self, "approval_results_table"):
            return

        row = self._find_approval_result_row(result)
        if row is None:
            row = self.approval_results_table.rowCount()
            self.approval_results_table.insertRow(row)
        self._set_approval_result_row(row, result)
        QApplication.processEvents()

    def _copy_approval_results_selection(self):
        if not hasattr(self, "approval_results_table"):
            return

        table = self.approval_results_table
        selected_indexes = table.selectedIndexes()
        if selected_indexes:
            rows = sorted({index.row() for index in selected_indexes})
            cols = sorted({index.column() for index in selected_indexes})
        else:
            rows = list(range(table.rowCount()))
            cols = list(range(table.columnCount()))

        if not rows or not cols:
            self.statusBar.showMessage("No approval results to copy")
            return

        lines = []
        headers = []
        for col in cols:
            header_item = table.horizontalHeaderItem(col)
            headers.append(header_item.text() if header_item else "")
        lines.append("\t".join(headers))

        for row in rows:
            values = []
            for col in cols:
                values.append(self._approval_cell_copy_text(row, col))
            lines.append("\t".join(values))

        QApplication.clipboard().setText("\n".join(lines))
        self.statusBar.showMessage(f"Copied {len(rows)} approval result rows")

    def _approval_cell_copy_text(self, row, col):
        item = self.approval_results_table.item(row, col)
        if not item:
            return ""
        if col == 5:
            return item.data(Qt.ItemDataRole.UserRole) or item.text()
        return item.text()

    def _approval_result_full_text_from_row(self, row):
        labels = ["Template", "GTX Reference", "Expected Amount", "Value Date", "Result", "Details"]
        lines = []
        for col, label in enumerate(labels):
            lines.append(f"{label}: {self._approval_cell_copy_text(row, col)}")
        return "\n".join(lines)

    def _show_approval_result_details(self, row, _col):
        if row < 0 or row >= self.approval_results_table.rowCount():
            return

        dialog = QDialog(self)
        dialog.setWindowTitle("Approval Details")
        dialog.resize(760, 420)

        layout = QVBoxLayout(dialog)
        layout.setContentsMargins(14, 14, 14, 14)
        layout.setSpacing(10)

        details_text = QTextEdit()
        details_text.setReadOnly(True)
        details_text.setPlainText(self._approval_result_full_text_from_row(row))
        layout.addWidget(details_text)

        button_layout = QHBoxLayout()
        button_layout.addStretch()

        copy_btn = QPushButton("Copy")
        copy_btn.setObjectName("secondaryButton")
        copy_btn.clicked.connect(
            lambda: self._copy_error_text(details_text.toPlainText(), copy_btn, "Approval details copied")
        )
        button_layout.addWidget(copy_btn)

        close_btn = QPushButton("Close")
        close_btn.setObjectName("secondaryButton")
        close_btn.clicked.connect(dialog.accept)
        button_layout.addWidget(close_btn)

        layout.addLayout(button_layout)
        dialog.exec()

    def _apply_approval_result_style(self, row, status):
        if is_successful_approval_result_status(status):
            bg_color = QColor(24, 84, 58) if self.dark_mode else QColor(222, 247, 232)
            text_color = QColor(235, 255, 244) if self.dark_mode else QColor(18, 83, 48)
        elif status in {
            "Needs manual review",
            "Failed before approval",
            "Failed after verify click before OK",
            "Status unknown",
            "Search/read failed",
        }:
            bg_color = QColor(112, 42, 48) if self.dark_mode else QColor(255, 226, 226)
            text_color = QColor(255, 241, 241) if self.dark_mode else QColor(126, 30, 30)
        else:
            bg_color = None
            text_color = None

        for col in range(self.approval_results_table.columnCount()):
            item = self.approval_results_table.item(row, col)
            if item:
                item.setBackground(QBrush(bg_color) if bg_color else QBrush())
                item.setForeground(QBrush(text_color) if text_color else QBrush())
        
    def _cleanup_worker(self):
        # Stop spinners
        self.start_spinner.stop_spinning()
        self.start_spinner.setVisible(False)
        self.status_spinner.stop_spinning()
        self.status_spinner.setVisible(False)
        
        # Re-enable inputs
        self.username_input.setEnabled(True)
        self.password_input.setEnabled(True)
        self.remember_checkbox.setEnabled(True)
        self.browse_btn.setEnabled(True)
        self.clear_btn.setEnabled(True)
        self.start_btn.setEnabled(bool(self.payments_data))
        if hasattr(self, "approval_audit_btn"):
            self.approval_audit_btn.setEnabled(True)
        if hasattr(self, "approval_run_btn"):
            self.approval_run_btn.setEnabled(True)
        if hasattr(self, "approval_browse_btn"):
            self.approval_browse_btn.setEnabled(True)
        if hasattr(self, "approval_clear_btn"):
            self.approval_clear_btn.setEnabled(True)
        
        # Clean up thread
        if self.worker_thread and self.worker_thread.isRunning():
            self.worker_thread.quit()
            self.worker_thread.wait()
        self.worker_thread = None
        self.worker = None

    def _update_summary(self):
        if not hasattr(self, "summary_labels"):
            return

        counts = {"total": self.table_widget.rowCount(), "pending": 0, "completed": 0, "errors": 0}
        for row in range(self.table_widget.rowCount()):
            status_item = self.table_widget.item(row, 4)
            status = status_item.text().strip().lower() if status_item else ""
            if status == "completed":
                counts["completed"] += 1
            elif status == "error":
                counts["errors"] += 1
            else:
                counts["pending"] += 1

        labels = {
            "total": f"Total: {counts['total']}",
            "pending": f"Pending: {counts['pending']}",
            "completed": f"Completed: {counts['completed']}",
            "errors": f"Errors: {counts['errors']}",
        }
        for key, text in labels.items():
            label = self.summary_labels.get(key)
            if label:
                label.setText(text)
        
    def show_message(self, title, message, icon=QMessageBox.Icon.Information):
        msg_box = QMessageBox(self)
        msg_box.setWindowTitle(title)
        msg_box.setText(message)
        msg_box.setIcon(icon)
        msg_box.exec()
        
    def closeEvent(self, event):
        # Stop worker if running
        if self.worker and hasattr(self.worker, 'stop'):
            self.worker.stop()
            
        # Clean up thread
        if self.worker_thread and self.worker_thread.isRunning():
            self.worker_thread.quit()
            self.worker_thread.wait()
            
        event.accept()

    def _save_credentials(self):
        """Save username and password to file"""
        try:
            import os
            import json
            creds_dir = os.path.join(os.path.expanduser("~"), ".gtexchange")
            
            # Create directory if it doesn't exist
            if not os.path.exists(creds_dir):
                os.makedirs(creds_dir)
            
            creds_file = os.path.join(creds_dir, "credentials.json")
            
            # Save credentials
            creds = {
                "username": self.username_input.text(),
                "password": self.password_input.text()
            }
            
            with open(creds_file, "w") as f:
                json.dump(creds, f)
            
            self.statusBar.showMessage("Credentials saved successfully")
        except Exception as e:
            self.statusBar.showMessage(f"Error: Failed to save credentials: {str(e)}")

    def _load_credentials(self):
        """Load saved username and password if available"""
        try:
            import os
            import json
            creds_file = os.path.join(os.path.expanduser("~"), ".gtexchange", "credentials.json")
            
            if os.path.exists(creds_file):
                with open(creds_file, "r") as f:
                    creds = json.load(f)
                
                self.username_input.setText(creds.get("username", ""))
                self.password_input.setText(creds.get("password", ""))
        except Exception as e:
            self.statusBar.showMessage(f"Could not load credentials: {str(e)}")

    def _has_saved_credentials(self):
        """Check if saved credentials exist"""
        import os
        creds_file = os.path.join(os.path.expanduser("~"), ".gtexchange", "credentials.json")
        return os.path.exists(creds_file)

    def _clear_credentials(self):
        """Remove saved credentials if they exist"""
        try:
            import os
            creds_file = os.path.join(os.path.expanduser("~"), ".gtexchange", "credentials.json")
            if os.path.exists(creds_file):
                os.remove(creds_file)
        except Exception as e:
            self.statusBar.showMessage(f"Could not clear credentials: {str(e)}")

    def _show_calendar(self, row, column):
        if column == 6:  # Value Date column
            # Create calendar with fixed size
            calendar = QCalendarWidget(self)
            calendar.setFixedSize(300, 250)
            
            # Set as popup window - key improvement for automatic handling of clicks outside
            calendar.setWindowFlags(Qt.WindowType.Popup)
            
            # Set minimum date to today to prevent selecting past dates
            calendar.setMinimumDate(QDate.currentDate())
            
            # Parse the existing date if available
            current_item = self.table_widget.item(row, 6)
            if current_item and current_item.text().strip():
                try:
                    parts = current_item.text().split('.')
                    if len(parts) == 3:
                        day, month, year = map(int, parts)
                        selected_date = QDate(year, month, day)
                        # Only set the date if it's not in the past
                        if selected_date >= QDate.currentDate():
                            calendar.setSelectedDate(selected_date)
                except:
                    pass  # If parse fails, just use current date
            
            # Store row information as widget property for retrieval in the callback
            calendar.setProperty("target_row", row)
            
            # Connect both clicked and activated (for Enter key) signals
            calendar.clicked.connect(self._update_value_date_from_calendar)
            calendar.activated.connect(self._update_value_date_from_calendar)
            
            # Position calendar relative to the clicked cell
            cell_rect = self.table_widget.visualItemRect(current_item)
            global_pos = self.table_widget.mapToGlobal(cell_rect.bottomLeft())
            
            # Move calendar down by 12.5% of its height
            vertical_offset = int(calendar.height() * 0.125)
            global_pos.setY(global_pos.y() + vertical_offset)
            
            # Adjust if calendar would go off screen
            screen_rect = QApplication.primaryScreen().geometry()
            if global_pos.x() + calendar.width() > screen_rect.right():
                global_pos.setX(screen_rect.right() - calendar.width() - 10)
            if global_pos.y() + calendar.height() > screen_rect.bottom():
                global_pos.setY(cell_rect.top() - calendar.height())
                global_pos = self.table_widget.mapToGlobal(global_pos)
            
            calendar.move(global_pos)
            
            # Apply appropriate styling
            self._apply_calendar_style(calendar)
            
            calendar.show()
    
    def _apply_calendar_style(self, calendar_widget):
        """Apply appropriate styling to calendar widget based on current theme"""
        if hasattr(self, 'dark_mode') and self.dark_mode:
            calendar_widget.setStyleSheet("""
                QCalendarWidget { 
                    background-color: #2D2D30; 
                    color: #E1E1E1; 
                }
                QCalendarWidget QToolButton { 
                    color: #E1E1E1; 
                    background-color: #333333; 
                    border: none;
                    font-weight: bold;
                    padding: 3px;
                }
                QCalendarWidget QMenu { 
                    background-color: #2D2D30; 
                    color: #E1E1E1; 
                    border: 1px solid #3F3F46;
                }
                QCalendarWidget QSpinBox { 
                    background-color: #1E1E1E; 
                    color: #E1E1E1; 
                    selection-background-color: #264F78;
                    selection-color: white;
                }
                QCalendarWidget QWidget { 
                    background-color: #2D2D30; 
                    color: #E1E1E1;
                }
                QCalendarWidget QWidget#qt_calendar_navigationbar { 
                    background-color: #333333; 
                }
                QCalendarWidget QTableView { 
                    background-color: #252526;
                    alternate-background-color: #2D2D30;
                    selection-background-color: #264F78;
                    selection-color: white;
                    color: #E1E1E1;
                    border: none;
                }
                QCalendarWidget QAbstractItemView:enabled { 
                    color: #E1E1E1; 
                }
                QCalendarWidget QTableView QTableCornerButton::section { 
                    background-color: #333333; 
                }
                QCalendarWidget QTableView QAbstractItemView::item {
                    color: #E1E1E1;
                }
                QCalendarWidget QTableView QAbstractItemView::item:selected {
                    background-color: #264F78;
                    color: white;
                }
            """)
    
    def _update_value_date_from_calendar(self):
        """Update the value date from calendar selection using widget properties"""
        sender_calendar = self.sender()
        row = sender_calendar.property("target_row")
        
        date = sender_calendar.selectedDate()
        today = QDate.currentDate()
        
        # Validate that selected date is not in the past
        if date < today:
            self.statusBar.showMessage("Error: Cannot select past dates for Value Date")
            return
        
        formatted_date = date.toString("dd.MM.yyyy")
        
        # Update the table UI
        self.table_widget.setItem(row, 6, QTableWidgetItem(formatted_date))
        
        # Also update the underlying data model
        for payment in self.payments_data:
            if payment['row_num'] == row + 1:  # Adjust for 0-based vs 1-based indexing
                payment['value_date'] = formatted_date
                break
                
        self.statusBar.showMessage(f"Value date updated to {formatted_date}")

    def _copy_references(self):
        """Copy all payment references to clipboard"""
        refs = []
        for row in range(self.table_widget.rowCount()):
            ref_item = self.table_widget.item(row, 5)  # Reference column
            if ref_item and ref_item.text().strip():
                template_item = self.table_widget.item(row, 1)  # Template column
                refs.append(f"{template_item.text()}: {ref_item.text()}")
        
        if refs:
            QApplication.clipboard().setText("\n".join(refs))
            self.statusBar.showMessage("References copied to clipboard")
            
            # Change button appearance to provide visual feedback
            original_text = self.copy_refs_btn.text()
            original_style = self.copy_refs_btn.styleSheet()
            
            # Set "Copied!" text with green background
            self.copy_refs_btn.setText("Copied!")
            self.copy_refs_btn.setStyleSheet("""
                QPushButton { 
                    background-color: #4CAF50; 
                    color: white; 
                    padding: 4px;
                    border-radius: 3px;
                    font-weight: bold;
                }
            """)
            
            # Reset button after 1.5 seconds
            QTimer.singleShot(1500, lambda: self._reset_copy_button(original_text, original_style))
        else:
            self.statusBar.showMessage("No references to copy")

    def _reset_copy_button(self, original_text, original_style):
        """Reset the copy button to its original state"""
        self.copy_refs_btn.setText(original_text)
        self.copy_refs_btn.setStyleSheet("")
        self.apply_style()

    def apply_style(self):
        if self.dark_mode:
            self.setStyleSheet("""
                QMainWindow, QWidget, QDialog {
                    background-color: #1f2329;
                    color: #e6edf3;
                    font-size: 12px;
                }
                QWidget#appRoot {
                    background-color: #1f2329;
                }
                QFrame#headerFrame {
                    background-color: #272c34;
                    border: 1px solid #3a414c;
                    border-radius: 8px;
                }
                QLabel#appTitle {
                    color: #f4f7fb;
                    font-size: 18px;
                    font-weight: 700;
                }
                QLabel#appSubtitle {
                    color: #9aa8b7;
                }
                QLabel#statusPill,
                QLabel#totalSummary,
                QLabel#pendingSummary,
                QLabel#completedSummary,
                QLabel#errorsSummary {
                    padding: 5px 9px;
                    border-radius: 4px;
                    font-weight: 600;
                    background-color: #303743;
                    color: #d5dde8;
                    border: 1px solid #444d5a;
                }
                QLabel#completedSummary {
                    background-color: #163d2b;
                    color: #bdf2cf;
                    border-color: #245a3e;
                }
                QLabel#errorsSummary {
                    background-color: #4a2428;
                    color: #ffc6c6;
                    border-color: #693238;
                }
                QGroupBox {
                    background-color: #272c34;
                    border: 1px solid #3a414c;
                    border-radius: 8px;
                    margin-top: 10px;
                    font-weight: 700;
                }
                QGroupBox::title {
                    subcontrol-origin: margin;
                    left: 12px;
                    padding: 0 5px;
                    color: #cbd5e1;
                    background-color: #272c34;
                }
                QLabel, QCheckBox {
                    background-color: transparent;
                    color: #d7dee8;
                }
                QCheckBox::indicator {
                    width: 14px;
                    height: 14px;
                    border: 1px solid #667085;
                    border-radius: 3px;
                    background-color: #171b21;
                }
                QCheckBox::indicator:checked {
                    background-color: #2c8c6a;
                    border-color: #2c8c6a;
                }
                QLineEdit, QTextEdit, QPlainTextEdit {
                    background-color: #171b21;
                    color: #edf2f7;
                    border: 1px solid #404853;
                    border-radius: 5px;
                    padding: 6px 8px;
                    selection-background-color: #2c6f9f;
                }
                QLineEdit:read-only {
                    color: #aeb8c5;
                    background-color: #20252d;
                }
                QPushButton {
                    border: 1px solid #4b5563;
                    border-radius: 5px;
                    padding: 7px 12px;
                    font-weight: 600;
                    background-color: #303743;
                    color: #edf2f7;
                }
                QPushButton:hover {
                    background-color: #3a4350;
                }
                QPushButton:pressed {
                    background-color: #252b34;
                }
                QPushButton:disabled {
                    background-color: #242932;
                    color: #6b7280;
                    border-color: #343b46;
                }
                QPushButton#primaryButton {
                    background-color: #13795b;
                    border-color: #13795b;
                    color: white;
                    font-size: 13px;
                    padding: 9px 14px;
                }
                QPushButton#primaryButton:hover {
                    background-color: #16966f;
                }
                QPushButton#primaryButton:disabled {
                    background-color: #313844;
                    border-color: #3b4450;
                    color: #8c96a3;
                }
                QTabWidget::pane {
                    border: none;
                    background-color: transparent;
                    margin-top: 8px;
                }
                QTabBar::tab {
                    background-color: #272c34;
                    color: #cbd5e1;
                    border: 1px solid #3a414c;
                    border-bottom-color: #3a414c;
                    padding: 8px 14px;
                    margin-right: 4px;
                    border-top-left-radius: 5px;
                    border-top-right-radius: 5px;
                }
                QTabBar::tab:selected {
                    background-color: #13795b;
                    color: #ffffff;
                    border-color: #13795b;
                }
                QTableWidget {
                    background-color: #20252d;
                    alternate-background-color: #252b34;
                    border: 1px solid #3a414c;
                    border-radius: 6px;
                    gridline-color: #303743;
                    selection-background-color: #315a75;
                    selection-color: #ffffff;
                }
                QTableWidget::item {
                    padding: 5px;
                    border-bottom: 1px solid #303743;
                }
                QHeaderView::section {
                    background-color: #303743;
                    color: #dce5ef;
                    padding: 7px 6px;
                    border: none;
                    border-right: 1px solid #424b58;
                    font-weight: 700;
                }
                QStatusBar {
                    background-color: #272c34;
                    color: #cdd7e3;
                    border-top: 1px solid #3a414c;
                    padding: 3px;
                }
                QScrollBar:vertical, QScrollBar:horizontal {
                    background: #20252d;
                    border: none;
                    margin: 0px;
                }
                QScrollBar:vertical { width: 10px; }
                QScrollBar:horizontal { height: 10px; }
                QScrollBar::handle:vertical, QScrollBar::handle:horizontal {
                    background: #4b5563;
                    border-radius: 5px;
                    min-height: 24px;
                    min-width: 24px;
                }
                QScrollBar::add-line, QScrollBar::sub-line {
                    width: 0px;
                    height: 0px;
                }
            """)
        else:
            self.setStyleSheet("""
                QMainWindow, QWidget, QDialog {
                    background-color: #f4f6f8;
                    color: #1f2933;
                    font-size: 12px;
                }
                QWidget#appRoot {
                    background-color: #f4f6f8;
                }
                QFrame#headerFrame {
                    background-color: #ffffff;
                    border: 1px solid #d9e2ec;
                    border-radius: 8px;
                }
                QLabel#appTitle {
                    color: #102a43;
                    font-size: 18px;
                    font-weight: 700;
                }
                QLabel#appSubtitle {
                    color: #627d98;
                }
                QLabel#statusPill,
                QLabel#totalSummary,
                QLabel#pendingSummary,
                QLabel#completedSummary,
                QLabel#errorsSummary {
                    padding: 5px 9px;
                    border-radius: 4px;
                    font-weight: 600;
                    background-color: #eef2f6;
                    color: #334e68;
                    border: 1px solid #d9e2ec;
                }
                QLabel#pendingSummary {
                    background-color: #fff8e6;
                    color: #8a5a00;
                    border-color: #f0d89a;
                }
                QLabel#completedSummary {
                    background-color: #e3f8e9;
                    color: #125330;
                    border-color: #b7e4c7;
                }
                QLabel#errorsSummary {
                    background-color: #ffe7e7;
                    color: #7e1e1e;
                    border-color: #ffc9c9;
                }
                QGroupBox {
                    background-color: #ffffff;
                    border: 1px solid #d9e2ec;
                    border-radius: 8px;
                    margin-top: 10px;
                    font-weight: 700;
                }
                QGroupBox::title {
                    subcontrol-origin: margin;
                    left: 12px;
                    padding: 0 5px;
                    color: #334e68;
                    background-color: #ffffff;
                }
                QLabel, QCheckBox {
                    background-color: transparent;
                    color: #334e68;
                }
                QCheckBox::indicator {
                    width: 14px;
                    height: 14px;
                    border: 1px solid #7b8794;
                    border-radius: 3px;
                    background-color: #ffffff;
                }
                QCheckBox::indicator:hover {
                    border-color: #2f80b7;
                }
                QCheckBox::indicator:checked {
                    background-color: #1f7a4d;
                    border-color: #1f7a4d;
                }
                QLineEdit, QTextEdit, QPlainTextEdit {
                    background-color: #ffffff;
                    color: #1f2933;
                    border: 1px solid #bcccdc;
                    border-radius: 5px;
                    padding: 6px 8px;
                    selection-background-color: #2f80b7;
                    selection-color: white;
                }
                QLineEdit:focus {
                    border-color: #2f80b7;
                }
                QLineEdit:read-only {
                    color: #52606d;
                    background-color: #f8fafc;
                }
                QPushButton {
                    border: 1px solid #bcccdc;
                    border-radius: 5px;
                    padding: 7px 12px;
                    font-weight: 600;
                    background-color: #ffffff;
                    color: #243b53;
                }
                QPushButton:hover {
                    background-color: #f0f4f8;
                    border-color: #9fb3c8;
                }
                QPushButton:pressed {
                    background-color: #d9e2ec;
                }
                QPushButton:disabled {
                    background-color: #edf1f5;
                    color: #9aa5b1;
                    border-color: #d9e2ec;
                }
                QPushButton#primaryButton {
                    background-color: #1f7a4d;
                    border-color: #1f7a4d;
                    color: white;
                    font-size: 13px;
                    padding: 9px 14px;
                }
                QPushButton#primaryButton:hover {
                    background-color: #24935d;
                }
                QPushButton#primaryButton:disabled {
                    background-color: #d9e2ec;
                    border-color: #d9e2ec;
                    color: #8a98a8;
                }
                QTabWidget::pane {
                    border: none;
                    background-color: transparent;
                    margin-top: 8px;
                }
                QTabBar::tab {
                    background-color: #ffffff;
                    color: #334e68;
                    border: 1px solid #d9e2ec;
                    border-bottom-color: #d9e2ec;
                    padding: 8px 14px;
                    margin-right: 4px;
                    border-top-left-radius: 5px;
                    border-top-right-radius: 5px;
                }
                QTabBar::tab:selected {
                    background-color: #1f7a4d;
                    color: #ffffff;
                    border-color: #1f7a4d;
                }
                QTableWidget {
                    background-color: #ffffff;
                    alternate-background-color: #f8fafc;
                    border: 1px solid #d9e2ec;
                    border-radius: 6px;
                    gridline-color: #edf2f7;
                    selection-background-color: #d7ecfa;
                    selection-color: #102a43;
                }
                QTableWidget::item {
                    padding: 5px;
                    border-bottom: 1px solid #edf2f7;
                }
                QHeaderView::section {
                    background-color: #edf2f7;
                    color: #334e68;
                    padding: 7px 6px;
                    border: none;
                    border-right: 1px solid #d9e2ec;
                    font-weight: 700;
                }
                QStatusBar {
                    background-color: #ffffff;
                    color: #52606d;
                    border-top: 1px solid #d9e2ec;
                    padding: 3px;
                }
                QScrollBar:vertical, QScrollBar:horizontal {
                    background: #f4f6f8;
                    border: none;
                    margin: 0px;
                }
                QScrollBar:vertical { width: 10px; }
                QScrollBar:horizontal { height: 10px; }
                QScrollBar::handle:vertical, QScrollBar::handle:horizontal {
                    background: #bcccdc;
                    border-radius: 5px;
                    min-height: 24px;
                    min-width: 24px;
                }
                QScrollBar::add-line, QScrollBar::sub-line {
                    width: 0px;
                    height: 0px;
                }
            """)
        self._refresh_table_theme()

    def toggle_dark_mode(self):
        self.dark_mode = not self.dark_mode
        self.dark_mode_toggle.setText("Light Mode" if self.dark_mode else "Dark Mode")
        self.apply_style()

    def _show_instructions(self):
        """Show user-friendly instructions in an elegant dialog window"""
        dialog = InstructionsDialog(self, dark_mode=self.dark_mode)
        dialog.exec()

# Add this class before the main entry point
class InstructionsDialog(QDialog):
    """An elegant dialog for displaying application instructions"""
    def __init__(self, parent=None, dark_mode=False):
        super().__init__(parent)
        self.dark_mode = dark_mode
        self.setWindowTitle("GTExchange Payment Automation - Guide")
        self.setMinimumSize(500, 500)  # Larger size for better readability
        
        # Use a layout to organize the content
        layout = QVBoxLayout(self)
        layout.setSpacing(15)
        layout.setContentsMargins(20, 20, 20, 20)
        
        # Set dialog background color based on theme
        if self.dark_mode:
            self.setStyleSheet("QDialog { background-color: #2D2D30; color: #E1E1E1; }")
        
        # Create a title with styling
        title_label = QLabel("GTExchange Payment Automation")
        title_color = "#007ACC" if self.dark_mode else "#0066cc"
        title_label.setStyleSheet(f"font-size: 18px; font-weight: bold; color: {title_color};")
        title_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(title_label)
        
        # Create a scroll area for the instructions
        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_area.setFrameShape(QFrame.Shape.NoFrame)
        
        # Container widget for the scrollable content
        content_widget = QWidget()
        if self.dark_mode:
            content_widget.setStyleSheet("QWidget { background-color: #2D2D30; color: #E1E1E1; }")
        content_layout = QVBoxLayout(content_widget)
        content_layout.setSpacing(15)
        
        # Set colors based on theme
        section_color = "#E1E1E1" if self.dark_mode else "#333333"
        bullet_color = "#CCCCCC" if self.dark_mode else "#444444"
        tip_color = "#AAAAAA" if self.dark_mode else "#666666"
        
        # Add the instruction sections
        sections = [
            ("1. Login", [
                "• Enter your GTExchange username and password",
                "• Check \"Remember me\" to save credentials for future sessions"
            ]),
            ("2. Load Payments", [
                "• Click \"Browse\" to select an Excel file with payment data",
                "• Required columns: Amount, Template, OTR Number",
                "• Invalid rows will be automatically skipped",
                "• ⚠️ IMPORTANT: Close Excel files before uploading - cannot access files that are open in Excel"
            ]),
            ("3. Review Payments", [
                "• Check payment details in the table before processing",
                "• Double-click on Value Date cells to modify dates using the calendar",
                "• Dates cannot be set in the past"
            ]),
            ("4. Start Automation", [
                "• Click \"Start Automation\" to begin processing payments",
                "• When prompted, enter the OTP code in the browser window",
                "• The status bar will show real-time progress updates"
            ]),
            ("5. After Completion", [
                "• Successfully processed payments will be highlighted in green",
                "• Each payment will display its reference number",
                "• Click \"Copy References\" to copy all references to clipboard"
            ])
        ]
        
        for title, bullets in sections:
            # Section title
            section_label = QLabel(title)
            section_label.setStyleSheet(f"font-size: 16px; font-weight: bold; color: {section_color};")
            content_layout.addWidget(section_label)
            
            # Bullets
            for bullet in bullets:
                bullet_label = QLabel(bullet)
                bullet_label.setWordWrap(True)
                bullet_label.setStyleSheet(f"font-size: 14px; margin-left: 20px; color: {bullet_color};")
                content_layout.addWidget(bullet_label)
            
            # Add some space between sections
            content_layout.addSpacing(10)
        
        # Add disclaimer or tips
        tip_label = QLabel("abdutas@convera.com")
        tip_label.setWordWrap(True)
        tip_label.setStyleSheet(f"font-style: italic; color: {tip_color}; margin-top: 10px;")
        content_layout.addWidget(tip_label)
        
        # Add the content widget to the scroll area
        scroll_area.setWidget(content_widget)
        layout.addWidget(scroll_area)
        
        # Close button at the bottom
        close_button = QPushButton("Close")
        close_button.setFixedWidth(120)
        close_button.clicked.connect(self.accept)
        
        # Button styling based on theme
        button_bg = "#36393F" if self.dark_mode else "#0066cc"
        button_hover = "#4752C4" if self.dark_mode else "#0077ee"
        
        close_button.setStyleSheet(f"""
            QPushButton {{
                background-color: {button_bg};
                color: white;
                border-radius: 4px;
                padding: 8px;
                font-weight: bold;
            }}
            QPushButton:hover {{
                background-color: {button_hover};
            }}
        """)
        
        button_layout = QHBoxLayout()
        button_layout.addStretch()
        button_layout.addWidget(close_button)
        layout.addLayout(button_layout)
        
    def keyPressEvent(self, event):
        # Close dialog when Escape key is pressed
        if event.key() == Qt.Key.Key_Escape:
            self.accept()
        else:
            super().keyPressEvent(event)

# Main entry point
if __name__ == "__main__":
    app = QApplication(sys.argv)
    
    window = SimplePaymentApp()
    window.show()
    sys.exit(app.exec())
