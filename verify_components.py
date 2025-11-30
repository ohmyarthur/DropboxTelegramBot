import asyncio
import os
import zipfile
import shutil
from utils.aerofs_helper import write_stream_to_file
from utils.zip_helper import extract_zip

async def mock_stream(data):
    yield data

async def main():
    print("Verifying components...")
    
    # Setup
    test_dir = "test_verification"
    os.makedirs(test_dir, exist_ok=True)
    zip_path = f"{test_dir}/test.zip"
    extract_path = f"{test_dir}/extracted"
    
    # Create a dummy zip in memory
    import io
    b = io.BytesIO()
    with zipfile.ZipFile(b, 'w') as z:
        z.writestr("file1.txt", "Hello World")
        z.writestr("folder/file2.txt", "Nested file")
    zip_data = b.getvalue()
    
    # Test aerofs write
    print("Testing aerofs write...")
    await write_stream_to_file(mock_stream(zip_data), zip_path)
    
    if not os.path.exists(zip_path):
        print("FAIL: Zip file not created.")
        return
    print("PASS: Zip file created.")
    
    # Test zip extraction
    print("Testing zip extraction...")
    await extract_zip(zip_path, extract_path)
    
    if os.path.exists(f"{extract_path}/file1.txt") and os.path.exists(f"{extract_path}/folder/file2.txt"):
        print("PASS: Files extracted correctly.")
    else:
        print("FAIL: Extraction failed.")
        return

    # Cleanup
    shutil.rmtree(test_dir)
    print("Verification complete.")

if __name__ == "__main__":
    asyncio.run(main())
