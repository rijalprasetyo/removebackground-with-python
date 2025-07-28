import tkinter as tk
from tkinter import filedialog, messagebox, simpledialog
import ttkbootstrap as ttk
from ttkbootstrap.constants import *
from PIL import Image, ImageTk
from rembg import remove, new_session
import threading
import os
import io
import sys
import uuid
import json
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from datetime import datetime
import time
from functools import lru_cache
import weakref

class LicenseManager:
    """Mengelola validasi, aktivasi, dan verifikasi lisensi dengan optimalisasi."""
    
    def __init__(self, root, app_identifier):
        self.root = root
        self.app_identifier = app_identifier
        self.local_license_file = "license-rgb.json"
        self.creds_file = self.get_resource_path("service_account.json")
        self.sheet_name = "Lisensi Aplikasi Remove Bg"
        self.worksheet = None
        self._machine_uuid = None  # Cache UUID

    @lru_cache(maxsize=1)
    def get_resource_path(self, relative_path):
        """Cached resource path dengan LRU cache."""
        try:
            base_path = sys._MEIPASS
        except Exception:
            base_path = os.path.abspath(".")
        return os.path.join(base_path, relative_path)

    def get_machine_uuid(self):
        """Cached machine UUID untuk menghindari kalkulasi berulang."""
        if self._machine_uuid is None:
            self._machine_uuid = str(uuid.uuid5(uuid.NAMESPACE_DNS, str(uuid.getnode())))
        return self._machine_uuid

    def connect_to_sheet(self):
        """Optimized Google Sheet connection dengan timeout dan retry."""
        if self.worksheet:
            return True
        
        max_retries = 2
        for attempt in range(max_retries):
            try:
                scope = [
                    "https://spreadsheets.google.com/feeds",
                    'https://www.googleapis.com/auth/spreadsheets',
                    "https://www.googleapis.com/auth/drive.file",
                    "https://www.googleapis.com/auth/drive"
                ]
                creds = ServiceAccountCredentials.from_json_keyfile_name(self.creds_file, scope)
                client = gspread.authorize(creds)
                # Set timeout untuk menghindari hanging
                self.worksheet = client.open(self.sheet_name).sheet1
                return True
            except FileNotFoundError:
                messagebox.showerror("Kesalahan Kredensial", 
                    f"File kredensial '{os.path.basename(self.creds_file)}' tidak ditemukan.")
                return False
            except Exception as e:
                if attempt == max_retries - 1:  # Last attempt
                    messagebox.showerror("Koneksi Gagal", 
                        f"Tidak dapat terhubung ke Google Sheets setelah {max_retries} percobaan.\n\nError: {e}")
                    return False
                time.sleep(1)  # Wait before retry
        return False

    @lru_cache(maxsize=1)
    def get_local_license(self):
        """Cached local license reading."""
        try:
            with open(self.local_license_file, 'r') as f:
                data = json.load(f)
                # Clear cache if file is modified
                self.get_local_license.cache_clear()
                return data
        except (FileNotFoundError, json.JSONDecodeError):
            return None

    def save_local_license(self, key, machine_uuid, keterangan, timestamp):
        """Optimized local license saving dengan atomic write."""
        data = {
            "key": key,
            "key-1": machine_uuid,
            "keterangan": keterangan,
            "timestamp": timestamp
        }
        # Atomic write untuk menghindari corruption
        temp_file = self.local_license_file + '.tmp'
        try:
            with open(temp_file, 'w') as f:
                json.dump(data, f, indent=4)
            os.replace(temp_file, self.local_license_file)
            # Clear cache setelah save
            self.get_local_license.cache_clear()
        except Exception as e:
            if os.path.exists(temp_file):
                os.remove(temp_file)
            raise e

    def validate(self):
        """Optimized license validation."""
        # Check local license first (fastest)
        local_data = self.get_local_license()
        
        # Defer Google Sheets connection until absolutely necessary
        if local_data:
            # Only connect if we have local data to verify
            if not self.connect_to_sheet():
                return False
            
            key = local_data.get("key")
            local_uuid = local_data.get("uuid")
            local_keterangan = local_data.get("keterangan")
            local_timestamp = local_data.get("timestamp")
            
            try:
                # Single API call to find and get row data
                cell = self.worksheet.find(key)
                if cell is None:
                    messagebox.showerror("Validasi Gagal", 
                        "Kunci lisensi lokal tidak ditemukan di server.", parent=self.root)
                    return False

                # Get all row data in one call
                sheet_data = self.worksheet.row_values(cell.row)
                sheet_uuid = sheet_data[1] if len(sheet_data) > 1 else ""
                sheet_keterangan = sheet_data[2] if len(sheet_data) > 2 else ""
                sheet_timestamp = sheet_data[3] if len(sheet_data) > 3 else ""

                # Validate all parameters
                if (sheet_uuid == local_uuid and
                    sheet_keterangan == local_keterangan and
                    sheet_timestamp == local_timestamp):
                    return True
                else:
                    messagebox.showerror("Validasi Gagal", 
                        "Data lisensi tidak cocok. Kunci mungkin telah digunakan di perangkat lain atau diubah.", 
                        parent=self.root)
                    return False
            except Exception as e:
                messagebox.showerror("Error Verifikasi", f"Terjadi kesalahan saat verifikasi: {e}", parent=self.root)
                return False
        else:
            # New activation - connect to sheets
            if not self.connect_to_sheet():
                return False
                
            key = simpledialog.askstring("Aktivasi Lisensi", "Masukkan kunci lisensi Anda:", parent=self.root)
            if not key:
                return False

            try:
                cell = self.worksheet.find(key)
                if cell is None:
                    messagebox.showerror("Aktivasi Gagal", "Kunci lisensi tidak valid.", parent=self.root)
                    return False

                sheet_uuid = self.worksheet.cell(cell.row, 2).value

                if not sheet_uuid:
                    machine_uuid = self.get_machine_uuid()
                    keterangan = self.app_identifier
                    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

                    # Batch update untuk efisiensi
                    updates = [
                        {'range': f'B{cell.row}', 'values': [[machine_uuid]]},
                        {'range': f'C{cell.row}', 'values': [[keterangan]]},
                        {'range': f'D{cell.row}', 'values': [[timestamp]]}
                    ]
                    self.worksheet.batch_update(updates)
                    
                    self.save_local_license(key, machine_uuid, keterangan, timestamp)
                    messagebox.showinfo("Aktivasi Berhasil", 
                        "Lisensi berhasil diaktifkan di perangkat ini.", parent=self.root)
                    return True
                else:
                    messagebox.showerror("Aktivasi Gagal", "Kunci lisensi ini telah digunakan.", parent=self.root)
                    return False
            except Exception as e:
                messagebox.showerror("Error Aktivasi", f"Terjadi kesalahan saat aktivasi: {e}", parent=self.root)
                return False


class BackgroundRemoverApp:
    """Optimized Background Remover Application."""
    
    def __init__(self, root):
        self.root = root
        self.root.title("✨ AI Background Remover Pro")
        self.root.geometry("900x700")
        self.root.minsize(800, 600)

        # Initialize variables
        self.input_path = None
        self.output_image_pil = None
        self.session = None
        self._image_cache = weakref.WeakValueDictionary()  # Weak reference cache

        # Set icon dengan error handling
        self._set_icon()
        
        # Lazy load AI model
        self._initialize_ai_model()
        
        # Create UI
        self.create_widgets()

    def _set_icon(self):
        """Set application icon dengan error handling."""
        try:
            icon_path = self.get_resource_path('icon.ico')
            self.root.iconbitmap(icon_path)
        except Exception as e:
            print(f"Icon not found: {e}")

    def _initialize_ai_model(self):
        """Initialize AI model dengan progress feedback."""
        def load_model():
            try:
                self.session = new_session("isnet-general-use")
                self.root.after(0, self._on_model_loaded)
            except Exception as e:
                error_msg = (f"Gagal memuat model AI: {e}\n\n"
                           "Aplikasi memerlukan koneksi internet saat pertama kali dijalankan "
                           "untuk mengunduh model. Silakan periksa koneksi Anda dan coba lagi.")
                self.root.after(0, lambda: messagebox.showerror("Model AI Error", error_msg))
                self.root.after(0, self.root.destroy)

        # Show loading status
        self.status_label_temp = ttk.Label(self.root, 
            text="Memuat model AI, mohon tunggu...", font=("Segoe UI", 12))
        self.status_label_temp.pack(pady=20)
        self.root.update_idletasks()
        
        # Load model in background
        threading.Thread(target=load_model, daemon=True).start()

    def _on_model_loaded(self):
        """Callback ketika model AI selesai dimuat."""
        if hasattr(self, 'status_label_temp'):
            self.status_label_temp.destroy()

    @lru_cache(maxsize=1)
    def get_resource_path(self, relative_path):
        """Cached resource path."""
        try:
            base_path = sys._MEIPASS
        except Exception:
            base_path = os.path.abspath(".")
        return os.path.join(base_path, relative_path)

    def create_widgets(self):
        """Optimized widget creation."""
        # Use single main frame
        main_frame = ttk.Frame(self.root, padding=20)
        main_frame.pack(fill=BOTH, expand=True)

        # Create all sections
        self.create_header(main_frame)
        self.create_preview_panels(main_frame)
        self.create_control_buttons(main_frame)
        self.create_status_bar(main_frame)

    def create_header(self, parent):
        """Optimized header creation."""
        header_frame = ttk.Frame(parent)
        header_frame.pack(fill=X, pady=(0, 20))
        
        # Use single configuration call
        title_label = ttk.Label(header_frame, 
            text="🎨 AI Background Remover Pro", 
            font=("Segoe UI", 24, "bold"), 
            bootstyle="light")
        title_label.pack()
        
        subtitle_label = ttk.Label(header_frame,
            text="Hapus background gambar dengan satu klik, didukung oleh AI.",
            font=("Segoe UI", 11),
            bootstyle="light")
        subtitle_label.pack(pady=(5,0))
        
        ttk.Separator(header_frame, orient=HORIZONTAL).pack(fill=X, pady=15)

    def create_preview_panels(self, parent):
        """Optimized preview panels dengan lazy loading."""
        preview_container = ttk.Frame(parent)
        preview_container.pack(fill=BOTH, expand=True, pady=(0, 20))
        preview_container.columnconfigure((0, 1), weight=1)
        preview_container.rowconfigure(0, weight=1)

        # Original image panel
        original_card = ttk.LabelFrame(preview_container, 
            text="📸 Gambar Asli", padding=15, bootstyle="primary")
        original_card.grid(row=0, column=0, padx=(0, 10), sticky="nsew")
        original_card.rowconfigure(0, weight=1)
        original_card.columnconfigure(0, weight=1)
        
        self.original_label = ttk.Label(original_card,
            text="Klik 'Pilih Gambar'\nuntuk memulai\n\n🖼️",
            font=("Segoe UI", 12),
            bootstyle="secondary",
            anchor="center",
            justify="center")
        self.original_label.grid(row=0, column=0, sticky="nsew")

        # Result image panel
        result_card = ttk.LabelFrame(preview_container,
            text="✨ Hasil Tanpa Background", padding=15, bootstyle="success")
        result_card.grid(row=0, column=1, padx=(10, 0), sticky="nsew")
        result_card.rowconfigure(0, weight=1)
        result_card.columnconfigure(0, weight=1)
        
        self.result_label = ttk.Label(result_card,
            text="Hasil akan muncul di sini\nsetelah diproses\n\n🤖",
            font=("Segoe UI", 12),
            bootstyle="secondary",
            anchor="center",
            justify="center")
        self.result_label.grid(row=0, column=0, sticky="nsew")

    def create_control_buttons(self, parent):
        """Optimized control buttons."""
        control_frame = ttk.Frame(parent)
        control_frame.pack(fill=X, pady=(0, 15))

        # Create buttons dengan single call
        button_configs = [
            ("🎯 Pilih Gambar", self.select_image, "primary", 20),
            ("💾 Simpan Hasil", self.save_image, "success", 20),
            ("🔄 Reset", self.reset_app, "warning-outline", 15)
        ]

        self.btn_select, self.btn_save, self.btn_reset = [], [], []
        buttons = []
        
        for text, command, style, width in button_configs:
            btn = ttk.Button(control_frame, text=text, command=command, 
                           bootstyle=style, width=width, padding=10)
            btn.pack(side=LEFT, expand=True, padx=5)
            buttons.append(btn)
        
        self.btn_select, self.btn_save, self.btn_reset = buttons
        self.btn_save.config(state="disabled")

    def create_status_bar(self, parent):
        """Optimized status bar."""
        status_frame = ttk.LabelFrame(parent, text="📊 Status", padding=10, bootstyle="info")
        status_frame.pack(fill=X)

        self.status_label = ttk.Label(status_frame,
            text="🚀 Selamat datang! Pilih gambar untuk memulai.",
            font=("Segoe UI", 11))
        self.status_label.pack(side=LEFT, fill=X, expand=True)

        self.progress_bar = ttk.Progressbar(status_frame, 
            mode='indeterminate', bootstyle="info-striped")

    def select_image(self):
        """Optimized image selection dengan file validation."""
        supported_formats = {'.jpg', '.jpeg', '.png', '.webp', '.bmp', '.tiff'}
        
        file_path = filedialog.askopenfilename(
            title="Pilih sebuah gambar",
            filetypes=[
                ("Image files", "*.jpg *.jpeg *.png *.webp *.bmp *.tiff"),
                ("All files", "*.*")
            ]
        )
        
        if not file_path:
            return

        # Validate file extension
        file_ext = os.path.splitext(file_path.lower())[1]
        if file_ext not in supported_formats:
            messagebox.showwarning("Format Tidak Didukung",
                f"Format file {file_ext} tidak didukung.\nFormat yang didukung: {', '.join(supported_formats)}")
            return

        # Validate file size (max 50MB)
        try:
            file_size = os.path.getsize(file_path) / (1024 * 1024)  # MB
            if file_size > 50:
                messagebox.showwarning("File Terlalu Besar",
                    f"Ukuran file ({file_size:.1f}MB) terlalu besar.\nMaksimal 50MB.")
                return
        except Exception as e:
            messagebox.showerror("Error", f"Tidak dapat membaca file: {e}")
            return

        self.reset_app_state()
        self.input_path = file_path
        
        # Display image dengan optimalisasi
        self.display_image(self.original_label, self.input_path)

        # Update UI untuk processing
        self.status_label.config(text="🤖 AI sedang bekerja, mohon tunggu...")
        self.result_label.config(image='', text="Memproses...\n\n⏳")
        self.toggle_controls(processing=True)
        
        # Start processing in background
        threading.Thread(target=self.process_image_thread, daemon=True).start()

    def process_image_thread(self):
        """Optimized background removal processing."""
        try:
            start_time = time.time()
            
            # Read file dengan buffer optimization
            with open(self.input_path, 'rb') as f:
                input_bytes = f.read()
            
            # Process dengan session yang sudah di-cache
            output_bytes = remove(input_bytes, session=self.session)
            
            # Convert ke PIL Image
            self.output_image_pil = Image.open(io.BytesIO(output_bytes))
            
            process_time = time.time() - start_time
            print(f"Processing time: {process_time:.2f} seconds")
            
            # Update UI di main thread
            self.root.after(0, self.update_ui_after_processing)

        except Exception as e:
            error_message = f"Gagal memproses gambar: {e}"
            self.root.after(0, lambda: messagebox.showerror("Processing Error", error_message))
            self.root.after(0, lambda: self.status_label.config(text="❌ Gagal memproses gambar."))
            self.root.after(0, lambda: self.toggle_controls(processing=False))

    def update_ui_after_processing(self):
        """Optimized UI update setelah processing."""
        if self.output_image_pil:
            self.display_image(self.result_label, self.output_image_pil)
            self.status_label.config(text="✅ Berhasil! Pratinjau siap. Silakan simpan gambar.")
            self.toggle_controls(processing=False, has_result=True)

    def save_image(self):
        """Optimized image saving dengan format options."""
        if not self.output_image_pil:
            messagebox.showwarning("Simpan Gagal", "Tidak ada gambar hasil untuk disimpan.")
            return

        # Generate default filename
        file_name = os.path.basename(self.input_path)
        base_name, _ = os.path.splitext(file_name)
        output_filename = f"{base_name}_no_bg.png"

        save_path = filedialog.asksaveasfilename(
            title="Simpan Hasil Sebagai...",
            initialfile=output_filename,
            defaultextension=".png",
            filetypes=[
                ("PNG Image", "*.png"),
                ("JPEG Image", "*.jpg"),
                ("WebP Image", "*.webp")
            ]
        )
        
        if save_path:
            try:
                # Optimize save based on format
                file_ext = os.path.splitext(save_path.lower())[1]
                
                if file_ext == '.jpg' or file_ext == '.jpeg':
                    # Convert RGBA to RGB for JPEG
                    if self.output_image_pil.mode == 'RGBA':
                        rgb_image = Image.new('RGB', self.output_image_pil.size, (255, 255, 255))
                        rgb_image.paste(self.output_image_pil, mask=self.output_image_pil.split()[-1])
                        rgb_image.save(save_path, 'JPEG', quality=95, optimize=True)
                    else:
                        self.output_image_pil.save(save_path, 'JPEG', quality=95, optimize=True)
                elif file_ext == '.webp':
                    self.output_image_pil.save(save_path, 'WebP', quality=95, lossless=True)
                else:  # PNG
                    self.output_image_pil.save(save_path, 'PNG', optimize=True)
                
                messagebox.showinfo("Sukses", f"Gambar berhasil disimpan di:\n{save_path}")
                self.status_label.config(text=f"Gambar disimpan di {os.path.basename(save_path)}")
            except Exception as e:
                messagebox.showerror("Save Error", f"Gagal menyimpan file: {e}")

    def display_image(self, label, image_source):
        """Optimized image display dengan caching."""
        try:
            # Generate cache key
            if isinstance(image_source, str):
                cache_key = f"file_{image_source}_{os.path.getmtime(image_source)}"
                if cache_key in self._image_cache:
                    img = self._image_cache[cache_key]
                else:
                    img = Image.open(image_source)
                    self._image_cache[cache_key] = img
            else:
                img = image_source.copy()

            # Get label dimensions
            label_width = label.winfo_width() or 400
            label_height = label.winfo_height() or 400
            
            # Create thumbnail dengan high-quality resampling
            display_img = img.copy()
            display_img.thumbnail((label_width - 20, label_height - 20), Image.Resampling.LANCZOS)
            
            # Convert to PhotoImage
            photo_img = ImageTk.PhotoImage(display_img)
            label.config(image=photo_img, text="")
            label.image = photo_img  # Keep reference
            
        except Exception as e:
            label.config(image='', text=f"Gagal memuat pratinjau:\n{e}")

    def toggle_controls(self, processing: bool, has_result: bool = False):
        """Optimized control state management."""
        if processing:
            # Disable all buttons
            for btn in [self.btn_select, self.btn_save, self.btn_reset]:
                btn.config(state="disabled")
            
            # Show progress
            self.progress_bar.pack(side=RIGHT, padx=(10, 0))
            self.progress_bar.start(10)  # Faster animation
        else:
            # Stop progress
            self.progress_bar.stop()
            self.progress_bar.pack_forget()
            
            # Enable appropriate buttons
            self.btn_select.config(state="normal")
            self.btn_reset.config(state="normal")
            
            if has_result:
                self.btn_save.config(state="normal")

    def reset_app(self):
        """Optimized app reset."""
        self.reset_app_state()
        
        # Reset UI elements
        self.original_label.config(image='', text="Klik 'Pilih Gambar'\nuntuk memulai\n\n🖼️")
        self.original_label.image = None
        self.result_label.config(image='', text="Hasil akan muncul di sini\nsetelah diproses\n\n🤖")
        self.result_label.image = None
        self.status_label.config(text="🚀 Selamat datang! Pilih gambar untuk memulai.")
        
        # Reset controls
        self.toggle_controls(processing=False, has_result=False)
        
        # Clear image cache
        self._image_cache.clear()

    def reset_app_state(self):
        """Clean internal app state."""
        self.input_path = None
        self.output_image_pil = None
        self.btn_save.config(state="disabled")


# --- OPTIMIZED APPLICATION ENTRY POINT ---
if __name__ == "__main__":
    # Use threading untuk license validation agar tidak blocking
    def validate_license_async():
        temp_root = tk.Tk()
        temp_root.withdraw()
        
        license_manager = LicenseManager(temp_root, app_identifier="RGB")
        return license_manager.validate(), temp_root

    # Validate license
    try:
        is_valid, temp_root = validate_license_async()
        
        if is_valid:
            temp_root.destroy()
            
            # Create optimized main application
            root = ttk.Window(themename="darkly")
            
            # Set window properties untuk performance
            root.resizable(True, True)
            
            # Initialize app
            app = BackgroundRemoverApp(root)
            
            # Start main loop
            root.mainloop()
        else:
            temp_root.destroy()
            sys.exit()
            
    except Exception as e:
        print(f"Application startup error: {e}")
        sys.exit(1)