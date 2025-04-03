import streamlit as st
import boto3
from botocore.exceptions import NoCredentialsError, ClientError
import io
import zipfile
from pathlib import Path


//


def get_readable_file_size(size_bytes):
    for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
        if size_bytes < 1024:
            return f"{size_bytes:.2f} {unit}"
        size_bytes /= 1024
    return f"{size_bytes:.2f} PB"

@st.cache_data(show_spinner=False)
def list_s3_objects(prefix):
    s3_client = boto3.client(
        's3',
        aws_access_key_id=AWS_ACCESS_KEY,
        aws_secret_access_key=AWS_SECRET_KEY
    )

    paginator = s3_client.get_paginator('list_objects_v2')
    operation_parameters = {'Bucket': S3_BUCKET_NAME, 'Prefix': prefix, 'Delimiter': '/'}
    folders = []
    files = []

    for page in paginator.paginate(**operation_parameters):
        for common_prefix in page.get('CommonPrefixes', []):
            folders.append(common_prefix['Prefix'])

        for content in page.get('Contents', []):
            if content['Key'] != prefix:
                files.append({
                    'Key': content['Key'],
                    'Size': content['Size'],
                    'Name': Path(content['Key']).name
                })

    return folders, files

@st.cache_data(show_spinner=False)
def get_folder_size_cached(folder_prefix):
    s3_client = boto3.client(
        's3',
        aws_access_key_id=AWS_ACCESS_KEY,
        aws_secret_access_key=AWS_SECRET_KEY
    )
    paginator = s3_client.get_paginator('list_objects_v2')
    total_size = 0
    for page in paginator.paginate(Bucket=S3_BUCKET_NAME, Prefix=folder_prefix):
        for obj in page.get('Contents', []):
            total_size += obj['Size']
    return total_size

def download_folder_zip(s3_client, folder_prefix):
    paginator = s3_client.get_paginator('list_objects_v2')
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, 'w', zipfile.ZIP_DEFLATED) as zipf:
        for page in paginator.paginate(Bucket=S3_BUCKET_NAME, Prefix=folder_prefix):
            for obj in page.get('Contents', []):
                key = obj['Key']
                obj_data = s3_client.get_object(Bucket=S3_BUCKET_NAME, Key=key)
                file_bytes = obj_data['Body'].read()
                filename = key[len(folder_prefix):]
                zipf.writestr(filename, file_bytes)
    buffer.seek(0)
    return buffer

def run_archive_section():
    st.markdown("""
    <style>
    .stButton > button {
        background-color: #004D7C;
        color: white;
        border: none;
        border-radius: 8px;
        padding: 10px 16px;
        font-size: 15px;
        margin: 0px 0;
        width: 100%;
    }
    </style>
""", unsafe_allow_html=True)

    st.subheader("🗄️ Dashboard")
    archive_type = st.radio("Select Statement Type", ["Bank", "PF", "ESIC"], horizontal=True)

    if "s3_path" not in st.session_state:
        st.session_state.s3_path = f"{archive_type}/"

    if archive_type and not st.session_state.s3_path.startswith(archive_type):
        st.session_state.s3_path = f"{archive_type}/"

    s3_client = boto3.client(
        's3',
        aws_access_key_id=AWS_ACCESS_KEY,
        aws_secret_access_key=AWS_SECRET_KEY
    )

    current_path = st.session_state.s3_path
    folders, files = list_s3_objects(current_path)

    st.markdown(f"### 📁 Current Path: {current_path}")
    st.info(f"🔍 Found {len(folders)} folder(s) in {current_path}")

    # 🔍 Search Bar for folders
    search_query = st.text_input("🔎 Search folders", "").strip().lower()

    # 🔙 Back Button
    if current_path != f"{archive_type}/":
        if st.button("🔙 Back"):
            st.session_state.s3_path = '/'.join(current_path.rstrip('/').split('/')[:-1]) + '/'
            st.rerun()

    # 📁 Display Folders
    filtered_folders = [f for f in folders if search_query in Path(f.rstrip('/')).name.lower()]
    selected_folders = []
    selected_files = []

    for folder in sorted(filtered_folders):
        folder_name = Path(folder.rstrip('/')).name
        folder_size = get_folder_size_cached(folder)
        readable_size = get_readable_file_size(folder_size)

        col1, col2, col3 = st.columns([7, 2, 1])
        with col1:
            if st.button(f"📁 {folder_name}", key=folder):
                st.session_state.s3_path = folder
                st.rerun()

        with col2:
            zip_buffer = download_folder_zip(s3_client, folder)
            st.download_button(
                label=f"⬇️ {readable_size}",
                data=zip_buffer,
                file_name=f"{folder_name}.zip",
                mime="application/zip",
                key=folder + "_zip"
            )

        with col3:
            if st.checkbox("", key=folder + "_check"):
                selected_folders.append(folder)

    # 📄 Display Files
    for file in sorted(files, key=lambda x: x['Name']):
        file_size = get_readable_file_size(file['Size'])
        obj_data = s3_client.get_object(Bucket=S3_BUCKET_NAME, Key=file['Key'])
        file_bytes = obj_data['Body'].read()

        col1, col2 = st.columns([9, 1])
        with col1:
            st.download_button(
                label=f"📄 {file['Name']} ({file_size})",
                data=file_bytes,
                file_name=file['Name'],
                mime="application/octet-stream",
                key=file['Key']
            )
        with col2:
            if st.checkbox("", key=file['Key'] + "_check"):
                selected_files.append({
                    'Key': file['Key'],
                    'Name': file['Name'],
                    'Bytes': file_bytes
                })


    if selected_folders or selected_files:
        zip_buffer = io.BytesIO()
        with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zipf:
            for folder in selected_folders:
                for page in s3_client.get_paginator('list_objects_v2').paginate(Bucket=S3_BUCKET_NAME, Prefix=folder):
                    for obj in page.get('Contents', []):
                        key = obj['Key']
                        obj_data = s3_client.get_object(Bucket=S3_BUCKET_NAME, Key=key)
                        file_bytes = obj_data['Body'].read()
                        filename = key[len(folder):]
                        zipf.writestr(f"{Path(folder).name}/{filename}", file_bytes)
            for file in selected_files:
                zipf.writestr(file['Name'], file['Bytes'])
        zip_buffer.seek(0)
        st.download_button(
            label="📦 Download Selected as ZIP",
            data=zip_buffer,
            file_name="selected_items.zip",
            mime="application/zip"
        )
