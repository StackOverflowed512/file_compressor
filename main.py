# universal_file_compressor/main.py
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
import os
import threading
import queue # For thread communication
import webbrowser
from typing import Optional, Dict, Any

# Ensure OUTPUT_FOLDER is imported from utils so it's initialized
from utils import get_formatted_size, OUTPUT_FOLDER
from compressor_logic import compress_pdf, compress_image


class FileCompressorApp:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title("Universal File Compressor")
        self.root.geometry("700x700") # Increased size for more options

        self.selected_file_path = tk.StringVar()
        self.file_type: Optional[str] = None # "pdf" or "image"
        self.compression_thread: Optional[threading.Thread] = None
        self.progress_queue = queue.Queue() # For progress updates from thread

        # --- Styles ---
        style = ttk.Style()
        style.theme_use('clam') # More modern theme
        style.configure("TButton", padding=6, relief="flat", font=('Helvetica', 10))
        style.configure("TLabel", padding=2, font=('Helvetica', 10))
        style.configure("Header.TLabel", font=('Helvetica', 14, 'bold'))
        style.configure("Link.TLabel", foreground="blue", font=('Helvetica', 10, 'underline'))

        # --- Main Frame ---
        main_frame = ttk.Frame(root, padding="20")
        main_frame.pack(expand=True, fill=tk.BOTH)

        title_label = ttk.Label(main_frame, text="Universal File Compressor", style="Header.TLabel")
        title_label.pack(pady=(0, 20))

        # --- File Selection ---
        selection_frame = ttk.Frame(main_frame)
        selection_frame.pack(fill=tk.X, pady=10)
        self.select_pdf_button = ttk.Button(selection_frame, text="Select PDF File", command=self.select_pdf)
        self.select_pdf_button.pack(side=tk.LEFT, padx=5, expand=True, fill=tk.X)
        self.select_image_button = ttk.Button(selection_frame, text="Select Image File (JPG, PNG)", command=self.select_image)
        self.select_image_button.pack(side=tk.LEFT, padx=5, expand=True, fill=tk.X)
        
        self.selected_file_label = ttk.Label(main_frame, text="No file selected.", wraplength=650)
        self.selected_file_label.pack(pady=5, fill=tk.X)

        # --- Compression Options ---
        options_outer_frame = ttk.LabelFrame(main_frame, text="Compression Options", padding="10")
        options_outer_frame.pack(fill=tk.X, pady=10)
        
        self.options_frame = ttk.Frame(options_outer_frame) # Inner frame for dynamic options
        self.options_frame.pack(fill=tk.X)

        # --- PDF Options (initially hidden) ---
        self.pdf_options_frame = ttk.Frame(self.options_frame)
        self.pdf_recompress_images_var = tk.BooleanVar(value=True)
        self.pdf_image_quality_var = tk.IntVar(value=75)
        self.pdf_linearize_var = tk.BooleanVar(value=True)

        ttk.Checkbutton(self.pdf_options_frame, text="Re-compress Images in PDF", variable=self.pdf_recompress_images_var, command=self._toggle_pdf_image_quality_slider).grid(row=0, column=0, sticky=tk.W, columnspan=2)
        self.pdf_image_quality_label = ttk.Label(self.pdf_options_frame, text="Image Quality (for PDF images):")
        self.pdf_image_quality_label.grid(row=1, column=0, sticky=tk.W, padx=(20,0))
        self.pdf_image_quality_slider = ttk.Scale(self.pdf_options_frame, from_=10, to=95, orient=tk.HORIZONTAL, variable=self.pdf_image_quality_var, length=200)
        self.pdf_image_quality_slider.grid(row=1, column=1, sticky=tk.EW, padx=5)
        self.pdf_image_quality_value_label = ttk.Label(self.pdf_options_frame, text=f"{self.pdf_image_quality_var.get()}")
        self.pdf_image_quality_value_label.grid(row=1, column=2, sticky=tk.W)
        self.pdf_image_quality_var.trace_add("write", lambda *args: self.pdf_image_quality_value_label.config(text=f"{self.pdf_image_quality_var.get()}"))
        ttk.Checkbutton(self.pdf_options_frame, text="Linearize PDF (for faster web view)", variable=self.pdf_linearize_var).grid(row=2, column=0, sticky=tk.W, columnspan=2)
        
        # --- Image Options (initially hidden) ---
        self.image_options_frame = ttk.Frame(self.options_frame)
        self.jpg_quality_var = tk.IntVar(value=85)
        self.png_compress_level_var = tk.IntVar(value=6)
        self.png_quantize_var = tk.BooleanVar(value=False)
        self.png_quantize_colors_var = tk.IntVar(value=256)

        # JPG Quality
        self.jpg_quality_label = ttk.Label(self.image_options_frame, text="JPG Quality:")
        self.jpg_quality_label.grid(row=0, column=0, sticky=tk.W)
        self.jpg_quality_slider = ttk.Scale(self.image_options_frame, from_=10, to=95, orient=tk.HORIZONTAL, variable=self.jpg_quality_var, length=200)
        self.jpg_quality_slider.grid(row=0, column=1, sticky=tk.EW, padx=5)
        self.jpg_quality_value_label = ttk.Label(self.image_options_frame, text=f"{self.jpg_quality_var.get()}")
        self.jpg_quality_value_label.grid(row=0, column=2, sticky=tk.W)
        self.jpg_quality_var.trace_add("write", lambda *args: self.jpg_quality_value_label.config(text=f"{self.jpg_quality_var.get()}"))

        # PNG Compression Level
        self.png_level_label = ttk.Label(self.image_options_frame, text="PNG Compression Level (0-9):")
        self.png_level_label.grid(row=1, column=0, sticky=tk.W, pady=(10,0))
        self.png_level_slider = ttk.Scale(self.image_options_frame, from_=0, to=9, orient=tk.HORIZONTAL, variable=self.png_compress_level_var, length=200)
        self.png_level_slider.grid(row=1, column=1, sticky=tk.EW, padx=5, pady=(10,0))
        self.png_level_value_label = ttk.Label(self.image_options_frame, text=f"{self.png_compress_level_var.get()}")
        self.png_level_value_label.grid(row=1, column=2, sticky=tk.W, pady=(10,0))
        self.png_compress_level_var.trace_add("write", lambda *args: self.png_level_value_label.config(text=f"{self.png_compress_level_var.get()}"))
        
        # PNG Quantization
        ttk.Checkbutton(self.image_options_frame, text="Quantize PNG (reduce colors)", variable=self.png_quantize_var, command=self._toggle_png_quantize_options).grid(row=2, column=0, sticky=tk.W, columnspan=2, pady=(10,0))
        self.png_quant_colors_label = ttk.Label(self.image_options_frame, text="Number of Colors (2-256):")
        self.png_quant_colors_label.grid(row=3, column=0, sticky=tk.W, padx=(20,0))
        self.png_quant_colors_entry = ttk.Entry(self.image_options_frame, textvariable=self.png_quantize_colors_var, width=5)
        self.png_quant_colors_entry.grid(row=3, column=1, sticky=tk.W, padx=5)
        self.image_options_frame.columnconfigure(1, weight=1) # Allow sliders to expand

        # --- Compress Button & Progress ---
        self.compress_button = ttk.Button(main_frame, text="Compress File", command=self.start_compression_thread, state=tk.DISABLED)
        self.compress_button.pack(pady=15, fill=tk.X)

        self.progress_bar = ttk.Progressbar(main_frame, orient=tk.HORIZONTAL, length=100, mode='determinate')
        self.progress_bar.pack(fill=tk.X, pady=(0, 5))
        self.progress_label = ttk.Label(main_frame, text="")
        self.progress_label.pack(fill=tk.X)

        # --- Output Area ---
        self.output_frame = ttk.LabelFrame(main_frame, text="Compression Results", padding="10")
        self.output_frame.pack(fill=tk.BOTH, expand=True, pady=10)
        self.original_size_label = ttk.Label(self.output_frame, text="Original Size: -")
        self.original_size_label.pack(anchor=tk.W)
        self.compressed_size_label = ttk.Label(self.output_frame, text="Compressed Size: -")
        self.compressed_size_label.pack(anchor=tk.W)
        self.ratio_label = ttk.Label(self.output_frame, text="Compression Ratio: -")
        self.ratio_label.pack(anchor=tk.W)
        self.saved_path_label = ttk.Label(self.output_frame, text="Saved to: -", style="Link.TLabel", cursor="hand2", wraplength=600)
        self.saved_path_label.pack(anchor=tk.W, pady=(5,0))
        self.saved_path_label.bind("<Button-1>", self.open_output_location)
        self.compressed_file_actual_path: Optional[str] = None

        self._update_options_ui() # Initial UI setup for options
        self._toggle_pdf_image_quality_slider()
        self._toggle_png_quantize_options()

        self.root.protocol("WM_DELETE_WINDOW", self.on_closing) # Handle closing while thread runs

    def _toggle_pdf_image_quality_slider(self):
        state = tk.NORMAL if self.pdf_recompress_images_var.get() else tk.DISABLED
        self.pdf_image_quality_slider.config(state=state)
        self.pdf_image_quality_label.config(state=state)
        self.pdf_image_quality_value_label.config(state=state)


    def _toggle_png_quantize_options(self):
        state = tk.NORMAL if self.png_quantize_var.get() else tk.DISABLED
        self.png_quant_colors_label.config(state=state)
        self.png_quant_colors_entry.config(state=state)


    def _update_options_ui(self):
        # Hide all option frames first
        self.pdf_options_frame.pack_forget()
        self.image_options_frame.pack_forget()

        if self.file_type == "pdf":
            self.pdf_options_frame.pack(fill=tk.X, expand=True)
        elif self.file_type == "image":
            self.image_options_frame.pack(fill=tk.X, expand=True)
            ext = ""
            if self.selected_file_path.get():
                 ext = os.path.splitext(self.selected_file_path.get())[1].lower()
            
            is_png = ext == '.png'
            is_jpg = ext in ['.jpg', '.jpeg']

            for widget in [self.jpg_quality_label, self.jpg_quality_slider, self.jpg_quality_value_label]:
                widget.grid_remove() if not is_jpg else widget.grid()
            
            for widget in [self.png_level_label, self.png_level_slider, self.png_level_value_label,
                           self.image_options_frame.grid_slaves(row=2)[0], 
                           self.png_quant_colors_label, self.png_quant_colors_entry]:
                widget.grid_remove() if not is_png else widget.grid()
            
            self._toggle_png_quantize_options() 
        else: 
            pass


    def select_pdf(self):
        filepath = filedialog.askopenfilename(
            title="Select PDF File",
            filetypes=(("PDF files", "*.pdf"), ("All files", "*.*"))
        )
        if filepath:
            self.selected_file_path.set(filepath)
            self.selected_file_label.config(text=f"Selected: {os.path.basename(filepath)}")
            self.file_type = "pdf"
            self.compress_button.config(state=tk.NORMAL)
            self.clear_results()
            self._update_options_ui()

    def select_image(self):
        filepath = filedialog.askopenfilename(
            title="Select Image File",
            filetypes=(("Image files", "*.jpg *.jpeg *.png"), ("All files", "*.*"))
        )
        if filepath:
            ext = os.path.splitext(filepath)[1].lower()
            if ext not in ['.jpg', '.jpeg', '.png']:
                messagebox.showerror("Error", "Unsupported image file type. Please select JPG or PNG.")
                return
            self.selected_file_path.set(filepath)
            self.selected_file_label.config(text=f"Selected: {os.path.basename(filepath)}")
            self.file_type = "image"
            self.compress_button.config(state=tk.NORMAL)
            self.clear_results()
            self._update_options_ui()

    def clear_results(self):
        self.original_size_label.config(text="Original Size: -")
        self.compressed_size_label.config(text="Compressed Size: -")
        self.ratio_label.config(text="Compression Ratio: -")
        self.saved_path_label.config(text="Saved to: -")
        self.compressed_file_actual_path = None
        self.progress_bar["value"] = 0
        self.progress_label.config(text="")

    def update_progress(self, value: float, message: str):
        self.progress_bar["value"] = value
        self.progress_label.config(text=message)
        self.root.update_idletasks()

    def check_progress_queue(self):
        try:
            while True: 
                progress_data = self.progress_queue.get_nowait()
                value, message = progress_data
                self.update_progress(value, message)
        except queue.Empty:
            pass 
        
        if self.compression_thread and self.compression_thread.is_alive():
            self.root.after(100, self.check_progress_queue) 
        else: 
            self.compress_button.config(state=tk.NORMAL)


    def start_compression_thread(self):
        input_path = self.selected_file_path.get()
        if not input_path:
            messagebox.showerror("Error", "No file selected.")
            return

        self.clear_results()
        self.compress_button.config(state=tk.DISABLED)
        self.update_progress(0, "Starting compression...")

        options: Dict[str, Any] = {}
        if self.file_type == "pdf":
            options = {
                "recompress_images": self.pdf_recompress_images_var.get(),
                "image_quality": self.pdf_image_quality_var.get(),
                "linearize": self.pdf_linearize_var.get()
            }
            target_func = compress_pdf
        elif self.file_type == "image":
            options = {
                "jpg_quality": self.jpg_quality_var.get(),
                "png_compress_level": self.png_compress_level_var.get(),
                "png_quantize": self.png_quantize_var.get(),
                "png_quantize_colors": self.png_quantize_colors_var.get()
            }
            if options["png_quantize"]:
                try:
                    colors = int(options["png_quantize_colors"])
                    if not (2 <= colors <= 256):
                        messagebox.showerror("Error", "PNG Quantize colors must be between 2 and 256.")
                        self.compress_button.config(state=tk.NORMAL)
                        return
                    options["png_quantize_colors"] = colors
                except ValueError:
                    messagebox.showerror("Error", "Invalid number for PNG Quantize colors.")
                    self.compress_button.config(state=tk.NORMAL)
                    return
            target_func = compress_image
        else:
            messagebox.showerror("Error", "Unknown file type.")
            self.compress_button.config(state=tk.NORMAL)
            return

        self.compression_thread = threading.Thread(
            target=self.run_compression,
            args=(target_func, input_path, options),
            daemon=True 
        )
        self.compression_thread.start()
        self.root.after(100, self.check_progress_queue)

    def _progress_callback_adapter(self, percent_done: float, status_msg: str):
        self.progress_queue.put((percent_done, status_msg))

    def run_compression(self, target_func, input_path, options):
        original_size, compressed_size, output_path = None, None, None
        try:
            original_size, compressed_size, output_path = target_func(
                input_path, options, progress_callback=self._progress_callback_adapter
            )
            
            self._progress_callback_adapter(100, "Compression complete.")

            if original_size is not None and compressed_size is not None and output_path:
                def update_ui_on_success():
                    self.original_size_label.config(text=f"Original Size: {get_formatted_size(original_size)}")
                    self.compressed_size_label.config(text=f"Compressed Size: {get_formatted_size(compressed_size)}")
                    if original_size > 0:
                        ratio = ((original_size - compressed_size) / original_size) * 100 if original_size >= compressed_size else 0
                        if compressed_size > original_size:
                            ratio_text = f"Increased by {abs(ratio):.2f}% (Compressed larger)"
                        elif ratio == 0 and original_size == compressed_size:
                            ratio_text = "No change in size"
                        else:
                            ratio_text = f"Reduction: {ratio:.2f}%"
                        self.ratio_label.config(text=f"Compression: {ratio_text}")
                    else:
                        self.ratio_label.config(text="Compression: N/A (Original file empty)")
                    
                    self.saved_path_label.config(text=f"Saved to: {os.path.relpath(output_path)}")
                    self.compressed_file_actual_path = os.path.abspath(output_path)
                    messagebox.showinfo("Success", f"File compressed successfully!\nSaved to: {output_path}")
                
                self.root.after(0, update_ui_on_success) 
            else:
                self._progress_callback_adapter(self.progress_bar['value'], "Compression failed. Check console.")
                self.root.after(0, lambda: messagebox.showerror("Error", "Compression failed. See console for details."))

        except Exception as e:
            self._progress_callback_adapter(self.progress_bar['value'], f"Error: {e}")
            print(f"An unexpected error occurred in compression thread: {e}")
            import traceback
            traceback.print_exc()
            self.root.after(0, lambda: messagebox.showerror("Error", f"An unexpected error occurred: {e}"))
        finally:
            self.root.after(0, lambda: self.compress_button.config(state=tk.NORMAL))


    def open_output_location(self, event=None):
        if self.compressed_file_actual_path and os.path.exists(self.compressed_file_actual_path):
            try:
                if os.name == 'nt':
                    webbrowser.open(f'file:///{os.path.dirname(self.compressed_file_actual_path)}')
                else: 
                     webbrowser.open(f"file:///{os.path.dirname(self.compressed_file_actual_path)}")
            except Exception as e:
                messagebox.showerror("Error", f"Could not open output location: {e}")
        elif os.path.exists(OUTPUT_FOLDER):
             try:
                webbrowser.open(f"file:///{os.path.abspath(OUTPUT_FOLDER)}")
             except Exception as e:
                messagebox.showerror("Error", f"Could not open output folder '{OUTPUT_FOLDER}': {e}")
        else:
            messagebox.showinfo("Info", "No compressed file to show or output folder not found.")
            
    def on_closing(self):
        if self.compression_thread and self.compression_thread.is_alive():
            if messagebox.askokcancel("Quit", "A compression task is running. Are you sure you want to quit?"):
                self.root.destroy()
            else:
                return 
        else:
            self.root.destroy()


if __name__ == "__main__":
    try:
        root = tk.Tk()
        app = FileCompressorApp(root)
        root.mainloop()
    except Exception as e:
        print(f"Fatal error on startup: {e}")
        import traceback
        traceback.print_exc()
        try:
            err_root = tk.Tk()
            err_root.withdraw() 
            messagebox.showerror("Startup Error", f"Application failed to start: {e}\n\nPlease check console for details and ensure you have write permissions for the 'compressed' subfolder.")
            err_root.destroy()
        except tk.TclError: 
            pass