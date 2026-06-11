import sys
import os
import pandas as pd
from datetime import datetime, timedelta
from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, 
    QLabel, QLineEdit, QPushButton, QFileDialog, QMessageBox, QTableWidget,
    QTableWidgetItem, QHeaderView, QGroupBox, QStatusBar, QGridLayout, QCheckBox,
    QCalendarWidget, QScrollArea, QDialog, QFrame, QStyle
)
from PyQt6.QtCore import Qt, QThread, pyqtSignal, QObject, QDate, QPoint, QRect, QTimer, QPropertyAnimation, QEasingCurve
from PyQt6.QtGui import QColor, QAction, QIcon, QPalette, QPixmap, QTransform, QPainter
import re
import subprocess
from payment_mapping import (
    build_narrative,
    format_amount,
    get_pacs_first_amount_field_id,
    is_valid_payment_code,
    resolve_payment_template,
)
from browser_launch import get_browser_launch_options

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
        page.get_by_role("textbox", name="(EndToEndId) End To End").fill(message_id)
        return message_id

    def _fill_pacs_amount(self, page, template_name, formatted_amount):
        first_amount_field_id = get_pacs_first_amount_field_id(template_name)
        if not first_amount_field_id:
            raise ValueError(f"Need first amount field id for {template_name}. Please record this template with Playwright codegen.")

        self.signals.progress.emit("Waiting for PACS amount fields to finish loading...")
        page.wait_for_timeout(1000)

        self.signals.progress.emit(f"Setting first PACS amount field {first_amount_field_id} to {formatted_amount}")
        first_amount = page.locator(f'[id="{first_amount_field_id}"]')
        first_amount.wait_for(state="visible", timeout=30000)
        first_amount.click()
        first_amount.fill(formatted_amount)
        if first_amount.input_value().strip() != formatted_amount:
            page.wait_for_timeout(1000)
            first_amount.fill(formatted_amount)
        if first_amount.input_value().strip() != formatted_amount:
            raise ValueError(f"First PACS amount field {first_amount_field_id} did not keep value")

        self.signals.progress.emit(f"Setting second PACS Value row to {formatted_amount}")
        second_amount = page.get_by_role("row", name="Value", exact=True).get_by_label("Value")
        second_amount.wait_for(state="visible", timeout=30000)
        second_amount.click()
        second_amount.fill(formatted_amount)
        if second_amount.input_value().strip() != formatted_amount:
            page.wait_for_timeout(1000)
            second_amount.fill(formatted_amount)
        if second_amount.input_value().strip() != formatted_amount:
            raise ValueError("Second PACS amount field did not keep value")

    def _click_pacs_text_ok(self, page):
        try:
            page.locator('#rightTreeForm\\:ok').click(timeout=5000)
            self.signals.progress.emit("Clicked PACS Text OK button")
        except Exception as e:
            self.signals.progress.emit(f"Could not click PACS Text OK by id: {e}")
            page.get_by_role("button", name="Ok").click(timeout=5000)
            self.signals.progress.emit("Clicked PACS Text OK button by role")
        page.wait_for_load_state('networkidle', timeout=15000)

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
            return
        except Exception as e:
            self.signals.progress.emit(f"Error clicking Messages link: {e}")

        try:
            page.locator('a:has-text("Messages")').first.click()
            page.wait_for_load_state('networkidle', timeout=15000)
            self._handle_license_popup(page)
        except Exception as e:
            self.signals.error.emit(f"Could not navigate to Messages. Please do so manually: {e}")
            page.wait_for_timeout(8000)

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

            self._fill_pacs_message_ids(page)

            page.get_by_role("button", name="Generate").click()
            page.wait_for_load_state('networkidle', timeout=15000)

            amount_code = payment.get('source_code') or template_name
            self._fill_pacs_amount(page, template_name, format_amount(amount, amount_code))

            formatted_date = self.get_formatted_date(template_name)
            self.signals.progress.emit(f"Setting settlement date to {formatted_date}")
            page.get_by_role("textbox", name="(IntrBkSttlmDt) Interbank").click()
            page.get_by_role("textbox", name="(IntrBkSttlmDt) Interbank").fill(formatted_date)

            narrative_text = build_narrative(payment.get('reference', 'CO5590'), otr_number)
            self.signals.progress.emit(f"Setting unstructured remittance to: {narrative_text}")
            page.get_by_role("textbox", name="(Ustrd) Unstructured").click()
            page.get_by_role("textbox", name="(Ustrd) Unstructured").fill(narrative_text)
            try:
                page.get_by_role("cell", name=narrative_text, exact=True).click(timeout=3000)
            except Exception:
                page.get_by_role("textbox", name="(Ustrd) Unstructured").press("Tab")

            self._click_pacs_text_ok(page)
            self._click_pacs_submit_ok(page)
            self._confirm_pacs_reference_popup(page, row_num)

            self.signals.progress.emit(f"Successfully processed PACS payment {row_num}")
            self.signals.progress.emit(f"STATUS:{row_num}:Completed")
            self._return_to_messages(page)
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
                if "executable_path" in launch_options:
                    self.signals.progress.emit(f"Launching bundled browser: {launch_options['executable_path']}")
                else:
                    self.signals.progress.emit("Launching installed Microsoft Edge")
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
                                self.signals.error.emit("Could not navigate to template creation")
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
                browser.close()
                
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
        self.status_spinner = None  # Will hold the status bar spinner
        
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
        self.setCentralWidget(main_widget)
        main_layout = QVBoxLayout(main_widget)
        main_layout.setSpacing(10)
        
        # Create login group with vertical layout
        login_group = QGroupBox("Login Details")
        login_layout = QVBoxLayout(login_group)
        login_layout.setContentsMargins(15, 15, 15, 15)
        
        # Username field
        username_layout = QHBoxLayout()
        username_label = QLabel("Username:")
        username_label.setFixedWidth(80)
        self.username_input = QLineEdit()
        self.username_input.setMaximumWidth(130)
        username_layout.addWidget(username_label)
        username_layout.addWidget(self.username_input)
        username_layout.addStretch()
        
        # Password field
        password_layout = QHBoxLayout()
        password_label = QLabel("Password:")
        password_label.setFixedWidth(80)
        self.password_input = QLineEdit()
        self.password_input.setMaximumWidth(130)
        self.password_input.setEchoMode(QLineEdit.EchoMode.Password)
        password_layout.addWidget(password_label)
        password_layout.addWidget(self.password_input)
        password_layout.addStretch()
        
        # Remember me checkbox and dark mode toggle
        checkbox_layout = QHBoxLayout()
        self.remember_checkbox = QCheckBox("Remember me")
        self.remember_checkbox.setChecked(self._has_saved_credentials())
        
        self.readme_btn = QPushButton("📖 Read Me")
        self.readme_btn.clicked.connect(self._show_instructions)
        
        self.dark_mode_toggle = QPushButton("🌙 Dark Mode")
        self.dark_mode_toggle.setCheckable(True)
        self.dark_mode_toggle.clicked.connect(self.toggle_dark_mode)
        
        checkbox_layout.addWidget(self.remember_checkbox)
        checkbox_layout.addStretch()
        checkbox_layout.addWidget(self.readme_btn)
        checkbox_layout.addWidget(self.dark_mode_toggle)
        
        login_layout.addLayout(username_layout)
        login_layout.addLayout(password_layout)
        login_layout.addLayout(checkbox_layout)
        
        # Excel import group
        excel_group = QGroupBox("Excel Import")
        excel_layout = QHBoxLayout(excel_group)
        excel_layout.setContentsMargins(15, 15, 15, 15)  # Add padding inside the group box
        
        self.file_path_input = QLineEdit()
        self.file_path_input.setReadOnly(True)
        self.file_path_input.setPlaceholderText("No file selected")
        excel_layout.addWidget(self.file_path_input)
        
        button_layout = QHBoxLayout()
        button_layout.setSpacing(8)  # Space between buttons
        
        self.browse_btn = QPushButton("Browse")
        self.browse_btn.clicked.connect(self._browse_and_load)
        self.browse_btn.setFixedWidth(80)
        self.browse_btn.setStyleSheet("QPushButton { padding: 4px; }")
        button_layout.addWidget(self.browse_btn)
        
        self.clear_btn = QPushButton("Clear")
        self.clear_btn.clicked.connect(self._clear_data)
        self.clear_btn.setFixedWidth(80)
        self.clear_btn.setStyleSheet("QPushButton { padding: 4px; }")
        button_layout.addWidget(self.clear_btn)
        
        excel_layout.addLayout(button_layout)
        
        # Data preview group
        data_group = QGroupBox("Payment Data")
        data_layout = QVBoxLayout(data_group)
        data_layout.setContentsMargins(15, 15, 15, 15)
        
        # Add Copy References button
        copy_refs_layout = QHBoxLayout()
        copy_refs_layout.addStretch()
        self.copy_refs_btn = QPushButton("Copy References")
        self.copy_refs_btn.clicked.connect(self._copy_references)
        self.copy_refs_btn.setFixedWidth(120)
        self.copy_refs_btn.setStyleSheet("QPushButton { padding: 4px; }")
        copy_refs_layout.addWidget(self.copy_refs_btn)
        data_layout.addLayout(copy_refs_layout)
        
        self.table_widget = QTableWidget()
        self.table_widget.setColumnCount(7)  # Removed Row# column
        self.table_widget.setHorizontalHeaderLabels([
            "Amount", "Template", "OTR Number", "Unit", "Status", "Reference", "Value Date"
        ])
        self.table_widget.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.table_widget.setAlternatingRowColors(True)
        self.table_widget.setStyleSheet("QTableWidget { gridline-color: #ccc; }")
        
        # Connect double-click event for Value Date column
        self.table_widget.cellDoubleClicked.connect(self._show_calendar)
        
        data_layout.addWidget(self.table_widget)
        
        # Start button with better styling
        self.start_btn = QPushButton("Start Automation")
        self.start_btn.clicked.connect(self._start_automation)
        self.start_btn.setEnabled(False)
        self.start_btn.setStyleSheet("""
            QPushButton {
                padding: 8px;
                font-weight: bold;
                background-color: #4CAF50;
                color: white;
                border-radius: 4px;
            }
            QPushButton:disabled {
                background-color: #cccccc;
            }
            QPushButton:hover {
                background-color: #45a049;
            }
        """)
        self.start_btn.setMinimumHeight(36)  # Make button taller
        
        # Create start button layout with spinner icon
        start_btn_layout = QHBoxLayout()
        self.start_spinner = SpinningIcon(size=24)
        self.start_spinner.setVisible(False)  # Hidden by default
        start_btn_layout.addWidget(self.start_spinner)
        start_btn_layout.addWidget(self.start_btn)
        start_btn_layout.setAlignment(self.start_spinner, Qt.AlignmentFlag.AlignVCenter)
        
        # Add widgets to main layout
        main_layout.addWidget(login_group)
        main_layout.addWidget(excel_group)
        main_layout.addWidget(data_group)
        main_layout.addLayout(start_btn_layout)
        
        # Status bar with better styling
        self.statusBar = QStatusBar()
        self.statusBar.setStyleSheet("QStatusBar { padding: 3px; font-size: 11px; }")
        self.setStatusBar(self.statusBar)
        
        # Create status bar spinner and add it to status bar
        self.status_spinner = SpinningIcon(size=16)
        self.status_spinner.setVisible(False)
        self.statusBar.addPermanentWidget(self.status_spinner)
        self.statusBar.showMessage("Ready")
        
        # Load saved credentials if available
        self._load_credentials()
    
    def _browse_and_load(self):
        file_path, _ = QFileDialog.getOpenFileName(
            self, "Select Excel File", "", "Excel Files (*.xlsx *.xls)"
        )
        
        if not file_path:
            return
            
        self.file_path_input.setText(file_path)
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
                
                row_index += 1
                
            except Exception as e:
                print(f"Error processing row: {e}")
        
        # Update status
        if self.payments_data:
            self.statusBar.showMessage(f"Loaded {len(self.payments_data)} payments")
            self.start_btn.setEnabled(True)
        else:
            self.statusBar.showMessage("No valid payments found in file")
            self.start_btn.setEnabled(False)
    
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
        self.table_widget.setRowCount(0)
        self.payments_data = []
        self.start_btn.setEnabled(False)
        self.statusBar.showMessage("Data cleared")
    
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
            
        # Start immediately without confirmation popup
        # Disable inputs during automation
        self.username_input.setEnabled(False)
        self.password_input.setEnabled(False)
        self.remember_checkbox.setEnabled(False)
        self.browse_btn.setEnabled(False)
        self.clear_btn.setEnabled(False)
        self.start_btn.setEnabled(False)
        
        # Start the spinner animations
        self.start_spinner.setVisible(True)
        self.start_spinner.start_spinning()
        self.status_spinner.setVisible(True)
        self.status_spinner.start_spinning()
        
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
        QApplication.processEvents()  # Process UI events to update immediately
    
    def _update_payment_status(self, row_num, status):
        """Update the status of a specific payment in the table."""
        # Find the row in the table that corresponds to this row_num
        for row_idx in range(self.table_widget.rowCount()):
            table_row_num = self.table_widget.item(row_idx, 0).text()
            if table_row_num == str(row_num):
                # Update the status column (column 4)
                self.table_widget.setItem(row_idx, 4, QTableWidgetItem(status))
                
                # Optionally change row color based on status
                if status == "Completed":
                    # Choose appropriate colors based on dark mode
                    if self.dark_mode:
                        bg_color = QColor(0, 100, 0)  # Darker green for dark mode
                    else:
                        bg_color = QColor(200, 255, 200)  # Light green for light mode
                    
                    # Set background color for completed rows and ensure text is visible
                    for col in range(self.table_widget.columnCount()):
                        item = self.table_widget.item(row_idx, col)
                        if item:
                            item.setBackground(bg_color)
                            item.setForeground(QColor(0, 0, 0))  # Black text for better contrast
                
                elif status == "Error":
                    # Set background color for error rows
                    error_bg = QColor(100, 0, 0) if self.dark_mode else QColor(255, 200, 200)
                    error_text = QColor(255, 255, 255) if self.dark_mode else QColor(0, 0, 0)
                    
                    for col in range(self.table_widget.columnCount()):
                        item = self.table_widget.item(row_idx, col)
                        if item:
                            item.setBackground(error_bg)
                            item.setForeground(error_text)
                break
    
    def _update_payment_reference(self, row_num, reference):
        """Update the reference for a specific payment row in the UI table"""
        self.statusBar.showMessage(f"Reference extracted: {reference} for payment #{row_num}")
        
        # Find the table row corresponding to the payment row number
        for row_idx in range(self.table_widget.rowCount()):
            # Check if this row matches the payment row number
            template_item = self.table_widget.item(row_idx, 1)  # Template column
            if template_item:
                # Find the corresponding payment data
                for payment in self.payments_data:
                    if (payment['row_num'] == row_num and 
                        payment['template'] == template_item.text().strip()):
                        # Update the dedicated reference column (column 5)
                        self.table_widget.setItem(row_idx, 5, QTableWidgetItem(reference))
                        
                        # Update status to show completed
                        self.table_widget.setItem(row_idx, 4, QTableWidgetItem("Completed"))
                        
                        # Choose appropriate colors based on dark mode
                        if self.dark_mode:
                            bg_color = QColor(0, 100, 0)  # Darker green for dark mode
                        else:
                            bg_color = QColor(200, 255, 200)  # Light green for light mode
                        
                        # Set background color for completed rows with reference
                        for col in range(self.table_widget.columnCount()):
                            item = self.table_widget.item(row_idx, col)
                            if item:
                                item.setBackground(bg_color)
                                item.setForeground(QColor(0, 0, 0))  # Black text for better contrast
                        
                        # Process any pending UI events to update the table immediately
                        QApplication.processEvents()
                        return
    
    def _handle_error(self, error_message):
        # Show error in status bar instead of popup
        self.statusBar.showMessage(f"ERROR: {error_message}")
        self._cleanup_worker()
        
    def _handle_finished(self, result):
        if isinstance(result, dict):
            message = result.get("message", "Automation completed")
            payment_references = result.get("payment_references", {})
            
            # Create status message with references
            if payment_references:
                ref_count = len(payment_references)
                status_message = f"{message} - {ref_count} references captured"
            else:
                status_message = message
            
            self.statusBar.showMessage(status_message)
        else:
            self.statusBar.showMessage("Automation completed")
            
        self._cleanup_worker()
        
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
        self.start_btn.setEnabled(True)
        
        # Clean up thread
        if self.worker_thread and self.worker_thread.isRunning():
            self.worker_thread.quit()
            self.worker_thread.wait()
        self.worker_thread = None
        self.worker = None
        
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
        self.copy_refs_btn.setStyleSheet(original_style)

    def apply_style(self):
        if self.dark_mode:
            self.setStyleSheet("""
                /* Main application */
                QMainWindow, QWidget, QDialog { background-color: #2D2D30; color: #E1E1E1; }
                
                /* Group boxes */
                QGroupBox { 
                    border: 1px solid #3F3F46; 
                    border-radius: 5px; 
                    margin-top: 1em; 
                    font-weight: bold; 
                    background-color: #252526; 
                }
                QGroupBox::title { 
                    subcontrol-origin: margin; 
                    left: 10px; 
                    padding: 0 3px; 
                    background-color: #252526; 
                }
                
                /* Input elements */
                QLineEdit, QTextEdit, QPlainTextEdit { 
                    background-color: #1E1E1E; 
                    color: #E1E1E1; 
                    border: 1px solid #3F3F46; 
                    selection-background-color: #264F78;
                    selection-color: #FFFFFF;
                }
                
                /* Buttons */
                QPushButton { 
                    background-color: #0E639C; 
                    color: white; 
                    border: none; 
                    padding: 5px; 
                    border-radius: 3px; 
                }
                QPushButton:hover { background-color: #1177BB; }
                QPushButton:pressed { background-color: #0D5889; }
                QPushButton:disabled { background-color: #333333; color: #666666; }
                
                /* QTableWidget styling */
                QTableWidget { 
                    background-color: #1E1E1E; 
                    alternate-background-color: #252526; 
                    gridline-color: #3F3F46; 
                    selection-background-color: #264F78;
                    selection-color: #FFFFFF;
                    border: 1px solid #3F3F46;
                }
                QTableWidget::item:selected { 
                    background-color: #264F78;
                    color: #FFFFFF;
                }
                
                /* Fix for table corner */
                QTableCornerButton::section { 
                    background-color: #333333; 
                    border: 1px solid #3F3F46;
                }
                
                /* Headers */
                QHeaderView { background-color: #252526; }
                QHeaderView::section { 
                    background-color: #333333; 
                    color: #E1E1E1; 
                    padding: 4px;
                    border: 1px solid #3F3F46;
                }
                
                /* StatusBar */
                QStatusBar { background-color: #007ACC; color: white; }
                
                /* Checkbox */
                QCheckBox { color: #E1E1E1; }
                QCheckBox::indicator { 
                    width: 13px; 
                    height: 13px; 
                    border: 1px solid #5F5F5F;
                    background-color: #1E1E1E;
                }
                QCheckBox::indicator:checked { 
                    background-color: #0E639C; 
                }
                
                /* Scrollbars */
                QScrollBar:vertical {
                    border: none;
                    background: #1E1E1E;
                    width: 10px;
                    margin: 0px;
                }
                QScrollBar::handle:vertical {
                    background: #3F3F46;
                    min-height: 20px;
                    border-radius: 5px;
                }
                QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
                    height: 0px;
                }
                QScrollBar:horizontal {
                    border: none;
                    background: #1E1E1E;
                    height: 10px;
                    margin: 0px;
                }
                QScrollBar::handle:horizontal {
                    background: #3F3F46;
                    min-width: 20px;
                    border-radius: 5px;
                }
                QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {
                    width: 0px;
                }
            """)
        else:
            self.setStyleSheet("")  # Reset to default style

    def toggle_dark_mode(self):
        self.dark_mode = not self.dark_mode
        self.dark_mode_toggle.setText("☀️ Light Mode" if self.dark_mode else "🌙 Dark Mode")
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
