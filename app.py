from flask import Flask, render_template, request, flash, redirect, url_for, send_from_directory
import os
from werkzeug.utils import secure_filename
from compressor_logic import compress_pdf, compress_image
from utils import get_formatted_size

app = Flask(__name__)
app.secret_key = 'your-secret-key-here'  # Required for flashing messages

# Configure upload and download folders
UPLOAD_FOLDER = 'uploads'
COMPRESSED_FOLDER = 'compressed'
ALLOWED_EXTENSIONS = {'pdf', 'png', 'jpg', 'jpeg'}

# Create folders if they don't exist
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
os.makedirs(COMPRESSED_FOLDER, exist_ok=True)

app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.config['COMPRESSED_FOLDER'] = COMPRESSED_FOLDER

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/upload', methods=['POST'])
def upload_file():
    if 'file' not in request.files:
        flash('No file selected', 'error')
        return redirect(url_for('index'))
    
    file = request.files['file']
    if file.filename == '':
        flash('No file selected', 'error')
        return redirect(url_for('index'))

    if file and allowed_file(file.filename):
        # Secure the filename and save the uploaded file
        filename = secure_filename(file.filename)
        input_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        file.save(input_path)

        try:
            # Prepare compression options based on file type
            options = {}
            file_ext = filename.rsplit('.', 1)[1].lower()
            
            if file_ext == 'pdf':
                options = {
                    'recompress_images': 'recompressImages' in request.form,
                    'image_quality': int(request.form.get('pdfImageQuality', 75)),
                    'linearize': True
                }
                compress_func = compress_pdf
            else:  # Image files
                if file_ext in ['jpg', 'jpeg']:
                    options = {
                        'jpg_quality': int(request.form.get('jpgQuality', 85))
                    }
                else:  # PNG
                    options = {
                        'png_compress_level': int(request.form.get('pngLevel', 6)),
                        'png_quantize': 'pngQuantize' in request.form,
                        'png_quantize_colors': int(request.form.get('pngColors', 256))
                    }
                compress_func = compress_image

            # Perform compression
            original_size, compressed_size, output_path = compress_func(
                input_path, 
                options,
                progress_callback=None  # Web version doesn't need progress updates
            )

            if output_path:
                # Get the filename from the output path
                download_filename = os.path.basename(output_path)
                
                # Calculate compression ratio
                if original_size > 0:
                    ratio = ((original_size - compressed_size) / original_size) * 100
                    if compressed_size > original_size:
                        compression_ratio = f"Increased by {abs(ratio):.2f}% (Compressed larger)"
                    else:
                        compression_ratio = f"Reduced by {ratio:.2f}%"
                else:
                    compression_ratio = "N/A (Original file empty)"

                # Clean up the uploaded file
                os.remove(input_path)

                return render_template('index.html',
                    download_path=download_filename,
                    original_size=get_formatted_size(original_size),
                    compressed_size=get_formatted_size(compressed_size),
                    compression_ratio=compression_ratio
                )

        except Exception as e:
            flash(f'Error during compression: {str(e)}', 'error')
            # Clean up on error
            if os.path.exists(input_path):
                os.remove(input_path)
            return redirect(url_for('index'))

    flash('Invalid file type. Please upload PDF, JPG, or PNG files.', 'error')
    return redirect(url_for('index'))

@app.route('/download/<filename>')
def download_file(filename):
    return send_from_directory(app.config['COMPRESSED_FOLDER'], filename, as_attachment=True)

if __name__ == '__main__':
    app.run(debug=True)