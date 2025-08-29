import boto3
from botocore.exceptions import ClientError
import os
import shutil
from dotenv import load_dotenv

load_dotenv()

class S3Service:
    def __init__(self):
        self.s3_client = boto3.client(
            's3',
            aws_access_key_id=os.getenv('AWS_ACCESS_KEY_ID'),
            aws_secret_access_key=os.getenv('AWS_SECRET_ACCESS_KEY'),
            region_name=os.getenv('AWS_REGION')
        )
        self.bucket_name = os.getenv('AWS_BUCKET_NAME')

    async def upload_file(self, file_obj, session_id: str, filename: str):
        """Upload a file to S3 bucket"""
        try:
            # Create folder structure: session_id/filename
            s3_path = f"{session_id}/{filename}"
            
            # Reset file position to beginning
            if hasattr(file_obj, 'seek'):
                file_obj.seek(0)
            
            # Create a temporary file for the upload
            import tempfile
            with tempfile.NamedTemporaryFile(delete=False) as temp_file:
                # If it's a SpooledTemporaryFile (from FastAPI's UploadFile)
                if hasattr(file_obj, 'file'):
                    shutil.copyfileobj(file_obj.file, temp_file)
                else:
                    shutil.copyfileobj(file_obj, temp_file)
                
                temp_file.flush()
                
                # Upload the file
                self.s3_client.upload_file(
                    temp_file.name,
                    self.bucket_name,
                    s3_path
                )
                
            # Clean up the temporary file
            os.unlink(temp_file.name)
            
            # Generate the URL
            url = f"https://{self.bucket_name}.s3.{os.getenv('AWS_REGION')}.amazonaws.com/{s3_path}"
            return url
        
        except ClientError as e:
            print(f"Error uploading to S3: {e}")
            raise
