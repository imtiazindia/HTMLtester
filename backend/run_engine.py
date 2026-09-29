from pathlib import Path
import subprocess
import sys

def run(engine, source, output):
    if engine == 'pdf2htmlEX':
        # Extracted AppImages do not have the original install-time share path.
        manifest = next(Path('/opt/pdf2html/squashfs-root').rglob('manifest'))
        subprocess.run(['pdf2htmlEX', '--data-dir', str(manifest.parent), '--embed', 'cfijo', '--dest-dir', str(output.parent),
                        '--process-outline', '0', '--printing', '0', str(source), output.name], check=True)
    elif engine == 'docling':
        from docling.document_converter import DocumentConverter, PdfFormatOption
        from docling.datamodel.base_models import InputFormat
        from docling.datamodel.pipeline_options import PdfPipelineOptions
        from docling.datamodel.accelerator_options import AcceleratorOptions, AcceleratorDevice
        from docling_core.types.doc import ImageRefMode
        options = PdfPipelineOptions(artifacts_path=Path('/opt/models'))
        options.do_ocr = False
        options.generate_picture_images = True
        options.accelerator_options = AcceleratorOptions(num_threads=2, device=AcceleratorDevice.CPU)
        converter = DocumentConverter(format_options={InputFormat.PDF: PdfFormatOption(pipeline_options=options)})
        result = converter.convert(source, max_num_pages=40, max_file_size=20*1024*1024)
        result.document.save_as_html(output, image_mode=ImageRefMode.EMBEDDED)
    elif engine == 'opendataloader':
        import opendataloader_pdf
        opendataloader_pdf.convert(input_path=[str(source)], output_dir=str(output.parent),
                                   format='html', image_output='embedded')
        generated = output.parent / (source.stem + '.html')
        if generated != output:
            generated.replace(output)
    else:
        raise ValueError('Unknown engine')

if __name__ == '__main__':
    run(sys.argv[1], Path(sys.argv[2]), Path(sys.argv[3]))
