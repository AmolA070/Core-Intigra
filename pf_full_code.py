def run_pf_section():
    import streamlit as st
    import pandas as pd
    import fitz  # PyMuPDF
    import re
    import io
    import numpy as np  # For int64 conversion
    import zipfile
    import time  # For timing and progress
    import boto3
    from botocore.exceptions import NoCredentialsError
    import datetime
    import os
    from dotenv import load_dotenv
 
 
    load_dotenv()
    AWS_ACCESS_KEY = os.getenv("AWS_ACCESS_KEY")
    AWS_SECRET_KEY = os.getenv("AWS_SECRET_KEY")
    S3_BUCKET_NAME = "sanj0908"
    S3_FOLDER = "PF/"  # Optional folder inside the bucket
 
    # Define a constant for read-only annotations (prevents moving/editing)
    ANNOT_FLAG_READONLY = 64
 
    # ----------------------- Streamlit Layout -----------------------
    st.title("PF Statement")
 
    # Step 2: Processing Options
    st.header("Choose Processing Options")
    # Use 4 columns: first two for processing options, then year and month (with restrictions)
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        mode = st.radio("Select masking mode:", ["Mask all not relevant", "Highlight Relevant"], index=0)
    with col2:
        page_mode = st.radio("Select Page Mode:", ["All Pages", "Relevant Pages"], index=0)
    with col3:
        # Get current date details
        now = datetime.datetime.now()
        current_year = now.year
        current_month = now.month
        # Limit year selection to current year (no future)
        selected_year = st.number_input("Select Year", min_value=1900, max_value=current_year, step=1, value=current_year)
    with col4:
        month_names = ["Jan", "Feb", "Mar", "Apr", "May", "Jun",
                       "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
        # If current year is selected, allow only months up to current month.
        if selected_year == current_year:
            allowed_months = month_names[:current_month]
            default_index = current_month - 1  # pre-select current month
        else:
            allowed_months = month_names
            default_index = 0
        selected_month = st.selectbox(
    "Select Month", 
    ["-- Select Month --"] + allowed_months, 
    index=0
)
 
    # ----------------------- Helper Function -----------------------
    def process_pdf(pdf_file, unit_uan_dict, mode, page_mode, matched_uan_dict):
        doc = fitz.open(stream=pdf_file.read(), filetype="pdf")
        uan_regex = re.compile(r"\b\d{12,15}\b")
        total_pages = doc.page_count
 
        # Create an empty PDF for each unit.
        unit_pdfs = {unit: fitz.open() for unit in unit_uan_dict.keys()}
        unit_modified = {unit: False for unit in unit_uan_dict.keys()}
 
        for page in doc:
            words = page.get_text("words")
            for unit, uan_list in unit_uan_dict.items():
                # For "Relevant Pages" mode, force first and last pages to be considered relevant.
                if page_mode == "Relevant Pages":
                    if page.number in [0, total_pages - 1]:
                        effective_page_has_unit = True
                    else:
                        effective_page_has_unit = any(
                            uan_regex.fullmatch(w[4]) and w[4] in uan_list for w in words
                        )
                else:  # page_mode == "All Pages"
                    effective_page_has_unit = any(
                        uan_regex.fullmatch(w[4]) and w[4] in uan_list for w in words
                    )
 
                # Create a temporary document for the current page.
                temp_doc = fitz.open()
                temp_doc.insert_pdf(doc, from_page=page.number, to_page=page.number)
                temp_page = temp_doc[0]
                modified = False
 
                if page_mode == "Relevant Pages":
                    if effective_page_has_unit:
                        if mode == "Highlight Relevant":
                            for w in words:
                                word_text = w[4]
                                if uan_regex.fullmatch(word_text) and word_text in uan_list:
                                    matched_uan_dict[unit].add(word_text)
                                    # Adjust rectangle dimensions as needed.
                                    x0, y0, x1, y1 = w[0]-5, w[1]-718, w[2]+5, w[3]+38
                                    rect = fitz.Rect(x0, y0, x1, y1)
                                    annot = temp_page.add_rect_annot(rect)
                                    annot.set_colors(stroke=(1, 1, 0), fill=(1, 1, 0))
                                    annot.set_border(width=1)
                                    annot.set_opacity(0.3)
                                    annot.set_flags(ANNOT_FLAG_READONLY)
                                    annot.update()
                                    modified = True
                            # Always include first and last pages.
                            if page.number in [0, total_pages - 1]:
                                modified = True
                        elif mode == "Mask all not relevant":
                            for w in words:
                                word_text = w[4]
                                if uan_regex.fullmatch(word_text):
                                    x0, y0, x1, y1 = w[0]-5, w[1]-718, w[2]+5, w[3]+38
                                    rect = fitz.Rect(x0, y0, x1, y1)
                                    annot = temp_page.add_rect_annot(rect)
                                    if word_text in uan_list:
                                        matched_uan_dict[unit].add(word_text)
                                        annot.set_colors(stroke=(1, 1, 1), fill=(1, 1, 1))
                                        annot.set_opacity(0.3)
                                    else:
                                        annot.set_colors(stroke=(0.5, 0.5, 0.5), fill=(0.5, 0.5, 0.5))
                                        annot.set_opacity(1)
                                    annot.set_border(width=1)
                                    annot.set_flags(ANNOT_FLAG_READONLY)
                                    annot.update()
                                    modified = True
                            if page.number in [0, total_pages - 1]:
                                modified = True
                elif page_mode == "All Pages":
                    if mode == "Highlight Relevant":
                        for w in words:
                            word_text = w[4]
                            if uan_regex.fullmatch(word_text) and word_text in uan_list:
                                matched_uan_dict[unit].add(word_text)
                                x0, y0, x1, y1 = w[0]-5, w[1]-718, w[2]+5, w[3]+38
                                rect = fitz.Rect(x0, y0, x1, y1)
                                annot = temp_page.add_rect_annot(rect)
                                annot.set_colors(stroke=(1, 1, 0), fill=(1, 1, 0))
                                annot.set_border(width=1)
                                annot.set_opacity(0.3)
                                annot.set_flags(ANNOT_FLAG_READONLY)
                                annot.update()
                        modified = True  # Include every page.
                    elif mode == "Mask all not relevant":
                        for w in words:
                            word_text = w[4]
                            if uan_regex.fullmatch(word_text):
                                x0, y0, x1, y1 = w[0]-5, w[1]-718, w[2]+5, w[3]+38
                                rect = fitz.Rect(x0, y0, x1, y1)
                                annot = temp_page.add_rect_annot(rect)
                                if word_text in uan_list:
                                    matched_uan_dict[unit].add(word_text)
                                    annot.set_colors(stroke=(1, 1, 1), fill=(1, 1, 1))
                                    annot.set_opacity(0.3)
                                else:
                                    annot.set_colors(stroke=(0.5, 0.5, 0.5), fill=(0.5, 0.5, 0.5))
                                    annot.set_opacity(1)
                                annot.set_border(width=1)
                                annot.set_flags(ANNOT_FLAG_READONLY)
                                annot.update()
                        modified = True  # Include every page.
 
                if modified:
                    unit_modified[unit] = True
                    unit_pdfs[unit].insert_pdf(temp_doc)
                temp_doc.close()
 
        # Return only those units where at least one page was added.
        return {unit: pdf for unit, pdf in unit_pdfs.items() if unit_modified[unit]}
 
    # ----------------------- Step 1: File Uploads (side-by-side) -----------------------
    col_pdf, col_excel = st.columns(2)
    with col_pdf:
        st.header("Upload PDF Files")
        pdf_files = st.file_uploader("", type="pdf", accept_multiple_files=True, key="pf_pdf")
    with col_excel:
        st.header("Upload Excel File")
        excel_file = st.file_uploader("", type=["xlsx", "xls"], key="pf_excel")
 
    generate_button = st.button("Generate")
 
    # ----------------------- Processing & Download -----------------------
    st.header("Processing & Download")
    if generate_button:
        if selected_month == "-- Select Month --":
            st.error("Please select month before proceeding.")
            st.stop()
        # Check if both PDF(s) and Excel file have been uploaded.
        if pdf_files and excel_file:
            # --- Duplicate PDF check using file names ---
            file_names = [pdf.name for pdf in pdf_files]
            if len(file_names) != len(set(file_names)):
                st.error("Duplicate PDF files detected. Please upload only unique PDF files.")
                return
 
            try:
                df = pd.read_excel(excel_file)
                # Check if required columns are present (use "PF UAN" instead of "UAN")
                if 'UNIT' not in df.columns or 'PF UAN' not in df.columns:
                    st.error("The Excel file must contain 'UNIT' and 'PF UAN' columns. Please upload the proper file.")
                else:
                    # Ensure the PF UAN column is string type.
                    df['PF UAN'] = df['PF UAN'].fillna(0).astype(np.int64).astype(str)
                    # Build a dictionary mapping each UNIT to its list of PF UAN values.
                    unit_uan_dict = {}
                    for _, row in df.iterrows():
                        unit = row['UNIT']
                        uan = row['PF UAN']
                        unit_uan_dict.setdefault(unit, []).append(uan)
 
                    # Initialize a dictionary to track matched UANs per unit.
                    matched_uan_dict = {unit: set() for unit in unit_uan_dict}
 
                    all_unit_files = {}
                    zip_buffer_all = io.BytesIO()
                    progress_bar = st.progress(0)
                    status_text = st.empty()
                    total_files = len(pdf_files)
                    highlight_count = 0
                    mask_count = 0
                    start_time = time.time()
 
                    with zipfile.ZipFile(zip_buffer_all, "w", zipfile.ZIP_DEFLATED) as zip_all:
                        for i, pdf in enumerate(pdf_files):
                            status_text.text(f"🔄 Processing file {i+1} of {total_files}: {pdf.name}")
                            unit_pdfs = process_pdf(pdf, unit_uan_dict, mode, page_mode, matched_uan_dict)
                            for unit, new_doc in unit_pdfs.items():
                                if new_doc.page_count > 0:
                                    # Count annotations for reporting.
                                    def color_match(c1, c2, tol=0.05):
                                        return all(abs(a - b) < tol for a, b in zip(c1, c2))
 
                                    if mode == "Highlight Relevant":
                                        highlight_count += sum(
                                            1
                                            for page in new_doc
                                            for annot in page.annots()
                                            if annot and color_match(annot.colors.get('fill', (0, 0, 0)), (1.0, 1.0, 0.0))
                                        )
                                    elif mode == "Mask all not relevant":
                                        highlight_count += sum(
                                            1
                                            for page in new_doc
                                            for annot in page.annots()
                                            if annot and color_match(annot.colors.get('fill', (0, 0, 0)), (1.0, 1.0, 1.0))
                                        )
                                        mask_count += sum(
                                            1
                                            for page in new_doc
                                            for annot in page.annots()
                                            if annot and color_match(annot.colors.get('fill', (0, 0, 0)), (0.5, 0.5, 0.5))
                                        )
 
                                    pdf_bytes = new_doc.write()
                                    new_doc.close()
                                    zip_all.writestr(f"{unit}_PF.pdf", pdf_bytes)
                                    all_unit_files.setdefault(unit, []).append(
                                        fitz.open(stream=pdf_bytes, filetype="pdf")
                                    )
                            progress_bar.progress((i + 1) / total_files)
 
                    # Additional check: if no files were processed, show an error.
                    if not any(all_unit_files.values()):
                        st.error("Mismatch: PDF & Excel file data not matching. Please upload proper data.")
                    else:
                        unit_zip_data = {}
                        for unit, doc_list in all_unit_files.items():
                            # Only create a ZIP for units that have processed documents and at least one matched UAN.
                            if doc_list and matched_uan_dict[unit]:
                                merged_pdf = fitz.open()
                                for doc_obj in doc_list:
                                    merged_pdf.insert_pdf(doc_obj)
                                    doc_obj.close()
                                merged_bytes = merged_pdf.write()
                                merged_pdf.close()
 
                                zip_buffer = io.BytesIO()
                                with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zipf:
                                    zipf.writestr(f"{unit}_PF.pdf", merged_bytes)
                                    # Prepare matched and unmatched Excel files.
                                    df_unit = df[df['UNIT'] == unit].copy()
                                    df_unit['PF UAN'] = df_unit['PF UAN'].astype(str)
                                    df_match = df_unit[df_unit['PF UAN'].isin(matched_uan_dict[unit])]
                                    df_unmatch = df_unit[~df_unit['PF UAN'].isin(matched_uan_dict[unit])]
 
                                    # Explicitly define the required columns to include in Excel outputs
                                    desired_cols = [
                                        'SNO', 'EMP CODE', 'EMP NAME', 'BRANCH', 'BRANCH 1',
                                        'UNIT', 'STATE', 'PFNO', 'PF UAN'
                                    ]
 
                                    available_cols = [col for col in desired_cols if col in df.columns]
                                    df_match = df_match[available_cols]
                                    df_unmatch = df_unmatch[available_cols]
 
                                    match_buffer = io.BytesIO()
                                    with pd.ExcelWriter(match_buffer, engine='xlsxwriter') as writer:
                                        df_match.to_excel(writer, index=False)
                                    match_buffer.seek(0)
                                    zipf.writestr(f"{unit}_Match.xlsx", match_buffer.getvalue())
 
                                    unmatch_buffer = io.BytesIO()
                                    with pd.ExcelWriter(unmatch_buffer, engine='xlsxwriter') as writer:
                                        df_unmatch.to_excel(writer, index=False)
                                    unmatch_buffer.seek(0)
                                    zipf.writestr(f"{unit}_Unmatch.xlsx", unmatch_buffer.getvalue())
 
                                zip_buffer.seek(0)
                                unit_zip_data[unit] = zip_buffer.getvalue()
 
                        # If no ZIPs were created for any unit, then display an error.
                        if not unit_zip_data:
                            st.error("Mismatch: PDF & Excel file data not matching. Please upload proper data.")
                        else:
                            master_zip_buffer = io.BytesIO()
                            with zipfile.ZipFile(master_zip_buffer, "w", zipfile.ZIP_DEFLATED) as master_zip:
                                for unit, zip_data in unit_zip_data.items():
                                    master_zip.writestr(f"{unit}_PF.zip", zip_data)
 
                            master_zip_buffer.seek(0)
                            master_zip_name = f"{selected_month}-{selected_year}.zip"
                            # Prepare uncompressed versions of PDFs and Excel files for S3 upload
                            unit_pdf_data = {}
                            unit_excel_data = {}
 
                            for unit, zip_data in unit_zip_data.items():
                                zip_file = zipfile.ZipFile(io.BytesIO(zip_data))
                                pdf_bytes = zip_file.read(f"{unit}_PF.pdf")
                                matched_bytes = zip_file.read(f"{unit}_Match.xlsx")
                                unmatched_bytes = zip_file.read(f"{unit}_Unmatch.xlsx")
 
                                unit_pdf_data[unit] = pdf_bytes
                                unit_excel_data[unit] = (matched_bytes, unmatched_bytes)
                            try:
                                s3_client = boto3.client(
                                    's3',
                                    aws_access_key_id=AWS_ACCESS_KEY,
                                    aws_secret_access_key=AWS_SECRET_KEY
                                )
 
                                # Upload individual files for each unit (no zip)
                                for unit, pdf_bytes in unit_pdf_data.items():
                                    s3_client.upload_fileobj(
                                        io.BytesIO(pdf_bytes),
                                        S3_BUCKET_NAME,
                                        f"{S3_FOLDER}{selected_month}-{selected_year}/{unit}/{unit}_Processed.pdf"
                                    )
                                    if unit in unit_excel_data:
                                        matched_bytes, unmatched_bytes = unit_excel_data[unit]
 
                                        s3_client.upload_fileobj(
                                            io.BytesIO(matched_bytes),
                                            S3_BUCKET_NAME,
                                            f"{S3_FOLDER}{selected_month}-{selected_year}/{unit}/{unit}_Match.xlsx"
                                        )
                                        s3_client.upload_fileobj(
                                            io.BytesIO(unmatched_bytes),
                                            S3_BUCKET_NAME,
                                            f"{S3_FOLDER}{selected_month}-{selected_year}/{unit}/{unit}_Unmatch.xlsx"
                                        )
 
                                st.success("Data processed & generated files are archived for future use.")
 
                            except NoCredentialsError:
                                st.error("AWS credentials not found. Could not upload to S3.")
                            except Exception as e:
                                st.error(f"Failed to upload to S3: {e}")
 
                            st.download_button(
                                label="Download Output in ZIP",
                                data=master_zip_buffer.getvalue(),
                                file_name=master_zip_name,
                                mime="application/zip"
                            )
 
                            end_time = time.time()
                            elapsed_time = end_time - start_time
                            st.success(
                                f"Processing completed in {elapsed_time:.2f} seconds. "
                                f"Highlight annotations: {highlight_count}, Mask annotations: {mask_count}."
                            )
 
                    progress_bar.empty()
                    status_text.text("✅ Processing completed.")
            except Exception as e:
                st.error("❌ Error reading Excel file. Please check the file and column names.")
                st.error(e)
        else:
            st.info("Please upload the PDF(s) and Excel file in the sections above.")
 
 
 
 
 