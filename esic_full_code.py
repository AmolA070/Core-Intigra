def run_esic_section():
    import streamlit as st
    import pandas as pd
    import fitz  # PyMuPDF
    import re
    import io
    import numpy as np  # For int64 conversion
    import zipfile
    import time
    import boto3
    from botocore.exceptions import NoCredentialsError
    import datetime
 
    # AWS S3 configuration for ESIC uploads
    
    # ----------------------- New Streamlit Layout -----------------------
    st.title("ESIC Statement")
 
    # Step 1: Choose Processing Options
    st.header("Choose Processing Options")
 
    # Get current date details
    now = datetime.datetime.now()
    current_year = now.year
    current_month = now.month
    month_names = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
 
    # Use four columns for options.
    col1, col2, col3, col4 = st.columns([2, 2, 2, 2])
 
    with col1:
        masking_mode = st.radio(
            "Select masking mode:",
            options=["Mask all not relevant", "Highlight Relevant"],
            index=0
        )
 
    with col2:
        page_selection_mode = st.radio(
            "Select Page Mode:",
            options=["All Pages", "Relevant Pages"],
            index=0
        )
 
    with col3:
        # Year selection: restrict to current year (no future year)
        selected_year = st.number_input("Select Year", min_value=1900, max_value=current_year, step=1, value=current_year)
 
    with col4:
        # If the selected year is the current year, only allow months up to the current month.
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

    # --- Step 2 & Step 3: Side-by-Side Columns for File Upload ---
    col_pdf, col_excel = st.columns(2)
 
    with col_pdf:
        st.header("Upload PDF Files")
        pdf_files = st.file_uploader(
            "",
            type="pdf",
            accept_multiple_files=True,
            key="esic_pdf"
        )
 
    with col_excel:
        st.header("Upload Excel File")
        excel_file = st.file_uploader(
            "",
            type=["xlsx", "xls"],
            key="esic_excel"
        )
 
    generate_button = st.button("Generate")
 
    # Step 4: Processing & Download
    st.header("Processing & Download")
 
    # Map the new UI options to the values expected by the processing code:
    mode = "Highlight Relevant" if masking_mode == "Highlight Relevant" else "Mask All Not Relevant"
    page_mode = "Keep the original doc" if page_selection_mode == "All Pages" else "Keep relevant pages"
 
    # Create a progress bar and a status text placeholder
    progress_bar = st.progress(0)
    status_text = st.empty()
 
    # Global statistics dictionary
    stats = {
        "pages_total": 0,
        "pages_processed": 0,
        "highlight": 0,
        "mask": 0,
        "start_time": time.time()
    }
 
    # Initialize an error flag; if any error message is encountered, this will be set to True.
    error_occurred = False
 
    def process_pdf(pdf_file, unit_esino_dict, mode, page_mode, stats, progress_bar, status_text, unit_highlights, unit_matched):
        """
        Processes an uploaded PDF by searching for candidate numbers (10–12 digit numbers)
        and comparing them with ESINO values for each UNIT.
 
        Modes:
          - "Highlight Relevant": Only matching ESINO candidates are highlighted (yellow).
          - "Mask All Not Relevant": Every candidate matching the regex is processed:
                 • If it is in the ESINO list, a white annotation is added (with slight transparency);
                 • Otherwise, a dark gray annotation is added.
 
        Page Modes:
          - "Keep the original doc": Every page is processed.
          - "Keep relevant pages": First and last pages are always processed, while other pages are
                                    processed only if they contain at least one matching candidate.
        """
        esino_regex = re.compile(r"\b\d{10,12}\b")
 
        # Check if pdf_file is a file-like object or a string (file path)
        if hasattr(pdf_file, "getvalue"):
            file_bytes = pdf_file.getvalue()
        else:
            with open(pdf_file, "rb") as f:
                file_bytes = f.read()
 
        doc = fitz.open(stream=file_bytes, filetype="pdf")
        total_pages = doc.page_count
        stats["pages_total"] += total_pages
 
        # Create an output PDF for each UNIT.
        unit_pdfs = {unit: fitz.open() for unit in unit_esino_dict.keys()}
 
        for page in doc:
            # ----- KEEP ALL PAGES MODE -----
            if page_mode == "Keep the original doc":
                for unit, esino_list in unit_esino_dict.items():
                    temp_doc = fitz.open()
                    temp_doc.insert_pdf(doc, from_page=page.number, to_page=page.number)
                    temp_page = temp_doc[0]
                    words = page.get_text("words")
                    if mode == "Mask All Not Relevant":
                        for w in words:
                            word_text = w[4]
                            x0, y0, x1, y1 = w[0]-96, w[1]-5, w[2]+457, w[3]+5
                            rect = fitz.Rect(x0, y0, x1, y1)
                            if esino_regex.fullmatch(word_text):
                                if word_text in esino_list:
                                    annot = temp_page.add_rect_annot(rect)
                                    annot.set_colors(stroke=(1, 1, 1), fill=(1, 1, 1))
                                    annot.set_border(width=1)
                                    annot.set_opacity(0.3)
                                    annot.set_flags(64)  # ANNOT_FLAG_READONLY
                                    annot.update()
                                    stats["highlight"] += 1
                                    unit_highlights[unit] = True
                                    unit_matched[unit].add(word_text)
                                else:
                                    annot = temp_page.add_rect_annot(rect)
                                    annot.set_colors(stroke=(0.5, 0.5, 0.5), fill=(0.5, 0.5, 0.5))
                                    annot.set_border(width=1)
                                    annot.set_opacity(1)
                                    annot.set_flags(64)
                                    annot.update()
                                    stats["mask"] += 1
                    elif mode == "Highlight Relevant":
                        for w in words:
                            word_text = w[4]
                            x0, y0, x1, y1 = w[0]-96, w[1]-5, w[2]+457, w[3]+5
                            rect = fitz.Rect(x0, y0, x1, y1)
                            if esino_regex.fullmatch(word_text) and word_text in esino_list:
                                annot = temp_page.add_rect_annot(rect)
                                annot.set_colors(stroke=(1, 1, 0), fill=(1, 1, 0))
                                annot.set_border(width=1)
                                annot.set_opacity(0.3)
                                annot.set_flags(64)
                                annot.update()
                                stats["highlight"] += 1
                                unit_highlights[unit] = True
                                unit_matched[unit].add(word_text)
                    # Add annotation for the unit name wherever it appears.
                    for r in temp_page.search_for(unit):
                        annot = temp_page.add_rect_annot(r)
                        annot.set_colors(stroke=(0, 0, 1), fill=(0, 0, 1))
                        annot.set_border(width=1)
                        annot.set_opacity(0.3)
                        annot.update()
                    unit_pdfs[unit].insert_pdf(temp_doc)
                    temp_doc.close()
 
            # ----- RELEVANT PAGES ONLY MODE -----
            else:
                if page.number in (0, total_pages - 1):
                    for unit, esino_list in unit_esino_dict.items():
                        temp_doc = fitz.open()
                        temp_doc.insert_pdf(doc, from_page=page.number, to_page=page.number)
                        temp_page = temp_doc[0]
                        words = page.get_text("words")
                        if mode == "Mask All Not Relevant":
                            for w in words:
                                word_text = w[4]
                                x0, y0, x1, y1 = w[0]-96, w[1]-5, w[2]+457, w[3]+5
                                rect = fitz.Rect(x0, y0, x1, y1)
                                if esino_regex.fullmatch(word_text):
                                    if word_text in esino_list:
                                        annot = temp_page.add_rect_annot(rect)
                                        annot.set_colors(stroke=(1, 1, 1), fill=(1, 1, 1))
                                        annot.set_border(width=1)
                                        annot.set_opacity(0.3)
                                        annot.set_flags(64)
                                        annot.update()
                                        stats["highlight"] += 1
                                        unit_highlights[unit] = True
                                        unit_matched[unit].add(word_text)
                                    else:
                                        annot = temp_page.add_rect_annot(rect)
                                        annot.set_colors(stroke=(0.5, 0.5, 0.5), fill=(0.5, 0.5, 0.5))
                                        annot.set_border(width=1)
                                        annot.set_opacity(1)
                                        annot.set_flags(64)
                                        annot.update()
                                        stats["mask"] += 1
                        elif mode == "Highlight Relevant":
                            for w in words:
                                word_text = w[4]
                                x0, y0, x1, y1 = w[0]-96, w[1]-5, w[2]+457, w[3]+5
                                rect = fitz.Rect(x0, y0, x1, y1)
                                if esino_regex.fullmatch(word_text) and word_text in esino_list:
                                    annot = temp_page.add_rect_annot(rect)
                                    annot.set_colors(stroke=(1, 1, 0), fill=(1, 1, 0))
                                    annot.set_border(width=1)
                                    annot.set_opacity(0.3)
                                    annot.set_flags(64)
                                    annot.update()
                                    stats["highlight"] += 1
                                    unit_highlights[unit] = True
                                    unit_matched[unit].add(word_text)
                        for r in temp_page.search_for(unit):
                            annot = temp_page.add_rect_annot(r)
                            annot.set_colors(stroke=(0, 0, 1), fill=(0, 0, 1))
                            annot.set_border(width=1)
                            annot.set_opacity(0.3)
                            annot.update()
                        unit_pdfs[unit].insert_pdf(temp_doc)
                        temp_doc.close()
 
                else:
                    words = page.get_text("words")
                    for unit, esino_list in unit_esino_dict.items():
                        page_has_unit = any(esino_regex.fullmatch(w[4]) and w[4] in esino_list for w in words)
                        if not page_has_unit:
                            continue
 
                        temp_doc = fitz.open()
                        temp_doc.insert_pdf(doc, from_page=page.number, to_page=page.number)
                        temp_page = temp_doc[0]
                        if mode == "Mask All Not Relevant":
                            for w in words:
                                word_text = w[4]
                                x0, y0, x1, y1 = w[0]-96, w[1]-5, w[2]+457, w[3]+5
                                rect = fitz.Rect(x0, y0, x1, y1)
                                if esino_regex.fullmatch(word_text):
                                    if word_text in esino_list:
                                        annot = temp_page.add_rect_annot(rect)
                                        annot.set_colors(stroke=(1, 1, 1), fill=(1, 1, 1))
                                        annot.set_border(width=1)
                                        annot.set_opacity(0.3)
                                        annot.set_flags(64)
                                        annot.update()
                                        stats["highlight"] += 1
                                        unit_highlights[unit] = True
                                        unit_matched[unit].add(word_text)
                                    else:
                                        annot = temp_page.add_rect_annot(rect)
                                        annot.set_colors(stroke=(0.5, 0.5, 0.5), fill=(0.5, 0.5, 0.5))
                                        annot.set_border(width=1)
                                        annot.set_opacity(1)
                                        annot.set_flags(64)
                                        annot.update()
                                        stats["mask"] += 1
                        elif mode == "Highlight Relevant":
                            for w in words:
                                word_text = w[4]
                                x0, y0, x1, y1 = w[0]-96, w[1]-5, w[2]+457, w[3]+5
                                rect = fitz.Rect(x0, y0, x1, y1)
                                if esino_regex.fullmatch(word_text) and word_text in esino_list:
                                    annot = temp_page.add_rect_annot(rect)
                                    annot.set_colors(stroke=(1, 1, 0), fill=(1, 1, 0))
                                    annot.set_border(width=1)
                                    annot.set_opacity(0.3)
                                    annot.set_flags(64)
                                    annot.update()
                                    stats["highlight"] += 1
                                    unit_highlights[unit] = True
                                    unit_matched[unit].add(word_text)
                        for r in temp_page.search_for(unit):
                            annot = temp_page.add_rect_annot(r)
                            annot.set_colors(stroke=(0, 0, 1), fill=(0, 0, 1))
                            annot.set_border(width=1)
                            annot.set_opacity(0.3)
                            annot.update()
                        unit_pdfs[unit].insert_pdf(temp_doc)
                        temp_doc.close()
 
            stats["pages_processed"] += 1
            progress = stats["pages_processed"] / stats["pages_total"]
            progress_bar.progress(progress)
            elapsed = time.time() - stats["start_time"]
            remaining = (elapsed / stats["pages_processed"]) * (stats["pages_total"] - stats["pages_processed"])
            status_text.text(f"Estimated time remaining: {remaining:.1f} seconds.")
 
        return unit_pdfs
 
    # Use the "Generate" button value as our submission trigger.
    submit = generate_button
 
    if submit:
        if selected_month == "-- Select Month --":
            st.error("Please select month before proceeding.")
            st.stop()

        if not selected_month:
            st.error("Please select month before proceeding.")
            st.stop()

        if pdf_files and excel_file:
            # Duplicate PDF check using file names.
            file_names = [pdf.name for pdf in pdf_files]
            if len(file_names) != len(set(file_names)):
                st.error("Duplicate PDF files detected. Please upload only unique PDF files.")
                error_occurred = True
                st.stop()
            try:
                df = pd.read_excel(excel_file)
                df['ESINO'] = df['ESINO'].fillna(0).astype(np.int64).astype(str)
                unit_esino_dict = {}
                for _, row in df.iterrows():
                    unit = row['UNIT']
                    esino = row['ESINO']
                    if unit not in unit_esino_dict:
                        unit_esino_dict[unit] = []
                    unit_esino_dict[unit].append(esino)
                # Track whether each unit gets any highlight annotation
                unit_highlights = {unit: False for unit in unit_esino_dict.keys()}
                # Track matched ESINO numbers for each unit
                unit_matched = {unit: set() for unit in unit_esino_dict.keys()}
            except Exception as e:
                st.error("❌ Error reading Excel file. Please ensure it has 'UNIT' and 'ESINO' columns.")
                st.error(e)
                error_occurred = True
                st.stop()
            else:
                all_unit_files = {}
                for pdf in pdf_files:
                    unit_pdfs = process_pdf(pdf, unit_esino_dict, mode, page_mode, stats, progress_bar, status_text, unit_highlights, unit_matched)
                    for unit, new_doc in unit_pdfs.items():
                        if new_doc.page_count > 0:
                            pdf_bytes = new_doc.write()
                            new_doc.close()
                            all_unit_files.setdefault(unit, []).append(
                                fitz.open(stream=pdf_bytes, filetype="pdf")
                            )
                total_time = time.time() - stats["start_time"]
                # Do not show the "processing completed" message yet.
 
                # Create nested folder structure inside a ZIP.
                unit_zip_data = {}
 
                for unit, doc_list in all_unit_files.items():
                    # Skip units with no highlights
                    if not unit_highlights.get(unit, False):
                        continue
                    if doc_list:
                        merged_pdf = fitz.open()
                        for doc_obj in doc_list:
                            merged_pdf.insert_pdf(doc_obj)
                            doc_obj.close()
                        pdf_bytes = merged_pdf.write()
                        merged_pdf.close()
 
                        # Prepare Excel files for matched/unmatched
                        unit_df = df[df['UNIT'] == unit]
                        matched_df = unit_df[unit_df['ESINO'].isin(unit_matched[unit])]
                        unmatched_df = unit_df[~unit_df['ESINO'].isin(unit_matched[unit])]
 
                        desired_cols = [
                            "SNO", "EMP CODE", "EMP NAME", "BRANCH", "BRANCH 1", "UNIT", "STATE", "ESINO"
                        ]
                        desired_cols_filtered = [col for col in desired_cols if col in df.columns]
                        matched_df = matched_df[desired_cols_filtered]
                        unmatched_df = unmatched_df[desired_cols_filtered]
 
                        match_buffer = io.BytesIO()
                        with pd.ExcelWriter(match_buffer, engine='xlsxwriter') as writer:
                            matched_df.to_excel(writer, index=False)
                        match_buffer.seek(0)
 
                        unmatch_buffer = io.BytesIO()
                        with pd.ExcelWriter(unmatch_buffer, engine='xlsxwriter') as writer:
                            unmatched_df.to_excel(writer, index=False)
                        unmatch_buffer.seek(0)
 
                        unit_zip_buffer = io.BytesIO()
                        with zipfile.ZipFile(unit_zip_buffer, "w", zipfile.ZIP_DEFLATED) as unit_zip:
                            unit_zip.writestr(f"{unit}_ESINO.pdf", pdf_bytes)
                            unit_zip.writestr(f"{unit}_Matched.xlsx", match_buffer.getvalue())
                            unit_zip.writestr(f"{unit}_Unmatched.xlsx", unmatch_buffer.getvalue())
                        unit_zip_buffer.seek(0)
                        unit_zip_data[unit] = unit_zip_buffer.getvalue()
 
                if not unit_zip_data:
                    st.error("Mismatch: PDF & Excel file data not matching. Please upload proper data.")
                    error_occurred = True
                else:
                    zip_buffer_all = io.BytesIO()
                    with zipfile.ZipFile(zip_buffer_all, "w", zipfile.ZIP_DEFLATED) as master_zip:
                        for unit, zip_bytes in unit_zip_data.items():
                            master_zip.writestr(f"{unit}.zip", zip_bytes)
                    zip_buffer_all.seek(0)
 
                    # ---------------- S3 UPLOAD FUNCTIONALITY ----------------
                    try:
                        s3_client = boto3.client(
                            's3',
                            aws_access_key_id=AWS_ACCESS_KEY,
                            aws_secret_access_key=AWS_SECRET_KEY
                        )
                        unit_pdf_data = {}
                        unit_excel_data = {}
                        for unit, zip_data in unit_zip_data.items():
                            zip_file = zipfile.ZipFile(io.BytesIO(zip_data))
                            pdf_bytes = zip_file.read(f"{unit}_ESINO.pdf")
                            matched_bytes = zip_file.read(f"{unit}_Matched.xlsx")
                            unmatched_bytes = zip_file.read(f"{unit}_Unmatched.xlsx")
                            unit_pdf_data[unit] = pdf_bytes
                            unit_excel_data[unit] = (matched_bytes, unmatched_bytes)
                        for unit, pdf_bytes in unit_pdf_data.items():
                            s3_client.upload_fileobj(
                                io.BytesIO(pdf_bytes),
                                S3_BUCKET_NAME,
                                f"{S3_FOLDER}{selected_month}-{selected_year}/{unit}/{unit}_ESINO.pdf"
                            )
                            if unit in unit_excel_data:
                                matched_bytes, unmatched_bytes = unit_excel_data[unit]
                                s3_client.upload_fileobj(
                                    io.BytesIO(matched_bytes),
                                    S3_BUCKET_NAME,
                                    f"{S3_FOLDER}{selected_month}-{selected_year}/{unit}/{unit}_Matched.xlsx"
                                )
                                s3_client.upload_fileobj(
                                    io.BytesIO(unmatched_bytes),
                                    S3_BUCKET_NAME,
                                    f"{S3_FOLDER}{selected_month}-{selected_year}/{unit}/{unit}_Unmatched.xlsx"
                                )
                        st.success(f"Data processed & generated files are archived for future use.")
                    except NoCredentialsError:
                        st.error("AWS credentials not found. Could not upload to S3.")
                        error_occurred = True
                    except Exception as e:
                        st.error(f"Failed to upload to S3: {e}")
                        error_occurred = True
                    # ---------------------------------------------------------
 
                    output_zip_name = f"{selected_month}-{selected_year}.zip"
                    st.download_button(
                        label="Download Output in ZIP",
                        data=zip_buffer_all.getvalue(),
                        file_name=output_zip_name,
                        mime="application/zip"
                    )
        else:
            st.info("ℹ️ Please upload the PDF(s) and the Excel file using the file uploaders above.")
 
        # At the end of processing, show the "Processing completed" status only if no errors occurred.
        if not error_occurred:
            total_time = time.time() - stats["start_time"]
            st.success(f"Processing completed in {total_time:.1f} seconds. Highlight annotations: {stats['highlight']}, Mask annotations: {stats['mask']}.")
 
 