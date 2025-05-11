# universal_file_compressor/compressor_logic.py
import os
import io
from typing import Optional, Tuple, Callable, Dict, Any
from PIL import Image, ImageChops, UnidentifiedImageError # Added UnidentifiedImageError
import pikepdf
from utils import OUTPUT_FOLDER

# --- PDF Compression ---
def recompress_pdf_images(
    pdf: pikepdf.Pdf,
    image_quality: int = 75,
    progress_callback: Optional[Callable[[float, str], None]] = None
) -> int:
    """
    Iterates through images in a PDF, re-compresses them as JPEGs.
    Modifies the Pdf object in place.
    Returns the number of images processed.
    """
    images_processed = 0
    
    # --- More robust image identification and counting ---
    # Iterate through actual image XObjects using a safer approach
    image_xobjects_to_process = []
    for obj in pdf.objects: # Iterate through all objects once
        # Check if it's a stream, then if it has Type and Subtype attributes,
        # then if those attributes match XObject and Image.
        if isinstance(obj, pikepdf.Stream) and \
           hasattr(obj, 'Type') and obj.Type == pikepdf.Name.XObject and \
           hasattr(obj, 'Subtype') and obj.Subtype == pikepdf.Name.Image:
            image_xobjects_to_process.append(obj)

    total_images_estimated = len(image_xobjects_to_process)
    
    if progress_callback and total_images_estimated > 0:
        progress_callback(0, f"Found {total_images_estimated} images to process.")

    for idx, img_xobj in enumerate(image_xobjects_to_process):
        if progress_callback and total_images_estimated > 0:
            progress_callback(
                ((idx + 1) / total_images_estimated) * 100,
                f"Processing image {idx + 1}/{total_images_estimated}"
            )
        
        try:
            pikepdf_image = pikepdf.Image(img_xobj) # Pass the XObject stream directly
            pil_image = pikepdf_image.as_pil_image()

            has_alpha = False
            if pil_image.mode in ('RGBA', 'LA') or (pil_image.mode == 'P' and 'transparency' in pil_image.info):
                 try:
                    alpha = pil_image.getchannel('A')
                    if ImageChops.invert(alpha).getbbox() is not None:
                        has_alpha = True
                 except ValueError:
                    pass # No alpha channel
            
            if has_alpha:
                # print(f"Warning: Image {img_xobj.objgen} has alpha, converting to RGB for JPEG compression.")
                background = Image.new("RGB", pil_image.size, (255, 255, 255))
                background.paste(pil_image, mask=pil_image.split()[3]) 
                pil_image = background
            elif pil_image.mode not in ['RGB', 'L']: # L is grayscale
                pil_image = pil_image.convert('RGB')

            img_byte_arr = io.BytesIO()
            pil_image.save(img_byte_arr, format='JPEG', quality=image_quality, optimize=True, progressive=True)
            img_bytes = img_byte_arr.getvalue()

            # Replace the image stream data in the original XObject
            img_xobj.stream_data = img_bytes
            img_xobj.Filter = pikepdf.Name.DCTDecode # Standard filter for JPEG
            
            # Clear out potentially incompatible decode parameters and masks
            if hasattr(img_xobj, 'DecodeParms'): # Use hasattr for safety
                del img_xobj.DecodeParms
            if hasattr(img_xobj, 'SMask') and has_alpha: # Only remove Smask if alpha was flattened
                del img_xobj.SMask
            # Consider /Mask as well if it exists and becomes incompatible
            # if hasattr(img_xobj, 'Mask') and has_alpha: del img_xobj.Mask # More complex

            images_processed += 1
        except pikepdf.PdfError as pe: # Catch pikepdf specific errors (e.g., unsupported image format within PDF)
            print(f"Skipping image {getattr(img_xobj, 'objgen', 'unknown')} due to pikepdf error: {pe}")
        except UnidentifiedImageError as uie: # Catch Pillow errors for images pikepdf extracts but Pillow can't handle
            print(f"Skipping image {getattr(img_xobj, 'objgen', 'unknown')} as Pillow cannot identify it: {uie}")
        except Exception as e:
            print(f"Skipping image {getattr(img_xobj, 'objgen', 'unknown')} due to general error: {e}")
            import traceback
            traceback.print_exc()
    return images_processed


def compress_pdf(
    input_path: str,
    options: Dict[str, Any],
    progress_callback: Optional[Callable[[float, str], None]] = None
) -> Tuple[Optional[int], Optional[int], Optional[str]]:
    """
    Compresses a PDF file using pikepdf with advanced options.
    options: {
        "recompress_images": bool,
        "image_quality": int (1-95),
        "linearize": bool
    }
    """
    filename = os.path.basename(input_path)
    output_path = os.path.join(OUTPUT_FOLDER, f"compressed_{filename}")

    try:
        original_size = os.path.getsize(input_path)
        
        if progress_callback:
            progress_callback(0, "Loading PDF...")

        pdf = pikepdf.Pdf.open(input_path, allow_overwriting_input=False)

        if options.get("recompress_images", False):
            if progress_callback:
                progress_callback(5, "Starting image re-compression...") # Adjusted start %
            
            def image_progress_wrapper(percent_done, status_msg):
                if progress_callback:
                    total_progress = 5 + (percent_done * 0.75) # Scaled from 5% to 80%
                    progress_callback(total_progress, status_msg)

            num_recompressed = recompress_pdf_images(
                pdf,
                options.get("image_quality", 75),
                image_progress_wrapper
            )
            print(f"Re-compressed {num_recompressed} images in PDF.")
            if progress_callback:
                progress_callback(80, f"Image re-compression complete. Recompressed {num_recompressed} images.")
        
        if progress_callback:
            progress_callback(85, "Optimizing PDF structure...")

        # CORRECTED: Use object_stream_mode instead of object_streams
        pdf.save(
            output_path,
            linearize=options.get("linearize", True),
            object_stream_mode=pikepdf.ObjectStreamMode.generate, # Corrected parameter name
            # For even more aggressive flate compression (can be slower):
            # recompress_flate=True, 
            # deterministic_id=False # Can sometimes save a few bytes by not trying to make IDs deterministic
        )
        
        if progress_callback:
            progress_callback(100, "Compression complete.")

        compressed_size = os.path.getsize(output_path)
        return original_size, compressed_size, output_path
    except Exception as e:
        print(f"Error compressing PDF {input_path}: {e}")
        import traceback
        traceback.print_exc()
        if os.path.exists(output_path):
             try:
                os.remove(output_path)
             except OSError: # e.g. file in use
                print(f"Could not remove partially written file: {output_path}")
        return None, None, None

# --- Image Compression ---
def compress_image(
    input_path: str,
    options: Dict[str, Any],
    progress_callback: Optional[Callable[[float, str], None]] = None
) -> Tuple[Optional[int], Optional[int], Optional[str]]:
    """
    Compresses an image file (JPG, PNG) using Pillow with advanced options.
    options: {
        "jpg_quality": int (1-95),
        "png_compress_level": int (0-9),
        "png_quantize": bool,
        "png_quantize_colors": int (2-256)
    }
    """
    filename = os.path.basename(input_path)
    name, ext = os.path.splitext(filename)
    output_path = os.path.join(OUTPUT_FOLDER, f"compressed_{name}{ext}")

    try:
        if progress_callback: progress_callback(0, "Loading image...")
        original_size = os.path.getsize(input_path)
        img = Image.open(input_path)
        original_mode = img.mode 

        if progress_callback: progress_callback(20, "Processing image...")

        if img.mode == 'RGBA' and ext.lower() in ['.jpg', '.jpeg']:
            background = Image.new("RGB", img.size, (255, 255, 255))
            background.paste(img, mask=img.split()[3]) 
            img = background
        elif img.mode == 'P' and ext.lower() in ['.jpg', '.jpeg']: 
            img = img.convert('RGB')
        elif img.mode not in ['RGB', 'L'] and ext.lower() in ['.jpg', '.jpeg']: 
            img = img.convert('RGB')

        save_kwargs = {}
        if ext.lower() in ['.jpg', '.jpeg']:
            save_kwargs['format'] = "JPEG"
            save_kwargs['quality'] = options.get("jpg_quality", 85)
            save_kwargs['optimize'] = True
            save_kwargs['progressive'] = True 
        elif ext.lower() == '.png':
            save_kwargs['format'] = "PNG"
            save_kwargs['optimize'] = True
            save_kwargs['compress_level'] = options.get("png_compress_level", 6)
            
            if options.get("png_quantize", False):
                num_colors = options.get("png_quantize_colors", 256)
                if progress_callback: progress_callback(50, f"Quantizing PNG to {num_colors} colors...")
                
                try:
                    if original_mode == 'RGBA' or (original_mode == 'P' and 'transparency' in img.info):
                        if img.mode != 'RGBA': img = img.convert('RGBA')
                        quantized_img = img.quantize(colors=num_colors, method=Image.Quantize.LIBIMAGEQUANT, dither=Image.Dither.FLOYDSTEINBERG)
                    else:
                        if img.mode == 'RGBA': img = img.convert('RGB')
                        quantized_img = img.quantize(colors=num_colors, method=Image.Quantize.LIBIMAGEQUANT, dither=Image.Dither.FLOYDSTEINBERG)
                    img = quantized_img
                except Exception as quant_error: # Pillow might raise various errors if LIBIMAGEQUANT not available/fails
                    print(f"Quantization with LIBIMAGEQUANT failed ({quant_error}), trying default method.")
                    try:
                        # Ensure img is in a suitable mode for default quantize
                        if original_mode == 'RGBA' or (original_mode == 'P' and 'transparency' in img.info):
                             if img.mode != 'RGBA': img = img.convert('RGBA') # Ensure alpha for P mode with transparency
                             quantized_img = img.quantize(colors=num_colors, dither=Image.Dither.FLOYDSTEINBERG)
                        else: # No alpha or P mode without transparency
                             if img.mode == 'RGBA': img = img.convert('RGB') # if it was converted to RGBA for jpg earlier
                             elif img.mode not in ['RGB', 'L', 'P']: img = img.convert('RGB') # General fallback
                             quantized_img = img.quantize(colors=num_colors, dither=Image.Dither.FLOYDSTEINBERG)
                        img = quantized_img
                    except Exception as e:
                        print(f"PNG quantization failed: {e}")
        else:
            print(f"Unsupported image format for compression: {ext}")
            return None, None, None
        
        if progress_callback: progress_callback(80, "Saving compressed image...")
        img.save(output_path, **save_kwargs)
        compressed_size = os.path.getsize(output_path)
        
        if progress_callback: progress_callback(100, "Image compression complete.")
        return original_size, compressed_size, output_path

    except FileNotFoundError:
        print(f"Error: Input file not found at {input_path}")
        return None, None, None
    except UnidentifiedImageError: 
        print(f"Error: Cannot identify image file. It might be corrupted or an unsupported format: {input_path}")
        return None, None, None
    except Exception as e:
        print(f"Error compressing image {input_path}: {e}")
        import traceback
        traceback.print_exc()
        if os.path.exists(output_path):
            try:
                os.remove(output_path)
            except OSError:
                print(f"Could not remove partially written file: {output_path}")
        return None, None, None