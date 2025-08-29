import boto3
import os
import base64
import requests
import openai
from typing import List, Dict, Any
from dotenv import load_dotenv

load_dotenv()

class ConsultationAnalyzer:
    def __init__(self):
        # Initialize S3 client
        self.s3_client = boto3.client(
            's3',
            aws_access_key_id=os.getenv('AWS_ACCESS_KEY_ID'),
            aws_secret_access_key=os.getenv('AWS_SECRET_ACCESS_KEY'),
            region_name=os.getenv('AWS_REGION')
        )
        self.bucket_name = os.getenv('AWS_BUCKET_NAME')
        self.vision_api_key = os.getenv("GOOGLE_VISION_API_KEY")
        self.vision_api_url = f'https://vision.googleapis.com/v1/images:annotate?key={self.vision_api_key}'
        
        # Initialize OpenAI
        openai.api_key = os.getenv("OPENAI_API_KEY")

    async def download_image_from_s3(self, key: str) -> bytes:
        """Download image from S3"""
        try:
            response = self.s3_client.get_object(Bucket=self.bucket_name, Key=key)
            return response['Body'].read()
        except Exception as e:
            print(f"Error downloading image from S3: {e}")
            return None

    async def analyze_image(self, image_content: bytes) -> Dict[str, Any]:
        """Analyze a single image using Google Cloud Vision API"""
        try:
            # Encode image in base64
            content = base64.b64encode(image_content).decode('utf-8')

            # Prepare the request payload
            payload = {
                "requests": [
                    {
                        "image": {"content": content},
                        "features": [{"type": "TEXT_DETECTION"}]
                    }
                ]
            }

            # Make the request to Google Cloud Vision API
            response = requests.post(
                self.vision_api_url,
                json=payload
            )

            # Handle the response
            if response.status_code == 200:
                result = response.json()
                text_annotation = result['responses'][0].get('fullTextAnnotation', {})
                text = text_annotation.get('text', '')
                confidence = text_annotation.get('confidence', 0) if text else 0

                if text:
                    return {
                        "success": True,
                        "text_detected": text,
                        "confidence": confidence
                    }
                else:
                    return {
                        "success": False,
                        "error": "No text found in image",
                        "text_detected": ""
                    }
            else:
                return {
                    "success": False,
                    "error": f"API Error: {response.status_code} - {response.text}",
                    "text_detected": ""
                }

        except Exception as e:
            return {
                "success": False,
                "error": str(e),
                "text_detected": ""
            }

    async def analyze_consultation_images(self, consultation_id: str, image_keys: List[str]) -> Dict[str, Any]:
        """Analyze all images for a consultation and return combined results"""
        results = []
        combined_text = []
        
        for image_key in image_keys:
            # Download image from S3
            image_content = await self.download_image_from_s3(f"{consultation_id}/{image_key}")
            
            if image_content:
                # Analyze image with OCR
                analysis = await self.analyze_image(image_content)
                
                if analysis["success"]:
                    combined_text.append(analysis["text_detected"])
                
                results.append({
                    "image_key": image_key,
                    "analysis": analysis
                })
        
        # Combine all extracted text
        all_text = "\n\n".join(combined_text)
        
        # Analyze combined text with OpenAI
        ai_analysis = await self.analyze_with_openai(all_text)
        
        return {
            "individual_results": results,
            "combined_text": all_text,
            "total_images_analyzed": len(results),
            "hvac_info": ai_analysis.get("analysis", "")
        }

    async def analyze_with_openai(self, text: str) -> Dict[str, Any]:
        """Analyze text using OpenAI to extract specific information"""
        try:
            # If no text provided, return empty result
            if not text or text.strip() == "":
                return {
                    "success": True,
                    "analysis": {
                        "brand": None,
                        "model_number": None,
                        "serial_number": None,
                        "additional_info": None
                    }
                }

            prompt = f"""
            You are an expert HVAC technician with 20+ years of experience reading equipment nameplates and technical documentation. Your job is to extract PRECISE equipment information from HVAC system text data.

            CRITICAL INSTRUCTIONS:
            1. Read EVERY word carefully
            2. Extract EXACT text matches - do NOT paraphrase or summarize
            3. Look for these SPECIFIC patterns:

            BRAND EXTRACTION:
            - "GOODMAN MANUFACTURING CO" → extract "GOODMAN"
            - "LG" → extract "LG" 
            - "CARRIER" → extract "CARRIER"
            - "TRANE" → extract "TRANE"
            - "LENNOX" → extract "LENNOX"
            - "RHEEM" → extract "RHEEM"
            - "YORK" → extract "YORK"
            - "DAIKIN" → extract "DAIKIN"
            - "MITSUBISHI" → extract "MITSUBISHI"

            MODEL NUMBER EXTRACTION:
            - Look for the word "MODEL" followed by the actual model code
            - Extract the COMPLETE alphanumeric code that comes after "MODEL"
            - Example: "MODEL CKJ60-1" → extract "CKJ60-1" (NOT just "NUMBER")
            - Example: "MODEL LAN120HSV5" → extract "LAN120HSV5"

            SERIAL NUMBER EXTRACTION:
            - Look for "SERIAL NO." or "SERIAL NUMBER" or "S/N"
            - Extract the COMPLETE number that follows
            - Example: "SERIAL NO. 0107415182" → extract "0107415182"

            ADDITIONAL INFO EXTRACTION:
            - BTU ratings (9,000 BTU, 12,000 BTU, etc.)
            - Voltage specifications (208/230 volts, etc.)
            - Electrical ratings (RLA, LRA, FLA amperage)
            - Technology features (Inverter, Heat Pump, High Efficiency)
            - Physical specifications (Phase, HP ratings)

            EXAMPLE ANALYSIS OF YOUR TEXT:
            From "GOODMAN MANUFACTURING CO" → brand = "GOODMAN"
            From "MODEL\\nCKJ60-1" → model_number = "CKJ60-1"
            From "SERIAL NO.\\n0107415182" → serial_number = "0107415182"

            YOU MUST respond with ONLY this exact JSON format (no markdown, no explanation):
            {{
                "brand": "GOODMAN",
                "model_number": "CKJ60-1",
                "serial_number": "0107415182",
                "additional_info": "208/230 volts, 1 phase, RLA 25 amps, LRA 169 amps, FLA 1.6 amps, 1/4 HP fan motor, BTU ratings: 9,000-48,000, Inverter Technology, Heat Pump"
            }}

            Now analyze this text and extract the information:
            {text}
            """

            print(f"Sending to OpenAI - Text length: {len(text)}")
            
            response = openai.ChatCompletion.create(
                model="gpt-4o",
                messages=[
                    {"role": "system", "content": "You are an expert HVAC technician who reads equipment nameplates. You MUST extract exact information and respond with ONLY valid JSON. Never use markdown formatting. Be precise and accurate."},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.0,  # Set to 0 for maximum consistency
                max_tokens=500
            )

            # Extract the content from OpenAI's response
            content = response.choices[0].message.content.strip()
            print(f"OpenAI raw response: {content}")

            # Clean up the response if it has markdown formatting
            if content.startswith("```json"):
                content = content.replace("```json", "").replace("```", "").strip()
            elif content.startswith("```"):
                content = content.replace("```", "").strip()

            # Parse JSON response
            import json
            hvac_info = json.loads(content)
            print(f"Parsed HVAC info: {hvac_info}")

            # Ensure all required fields are present
            required_fields = ["brand", "model_number", "serial_number", "additional_info"]
            for field in required_fields:
                if field not in hvac_info:
                    hvac_info[field] = None

            return {
                "success": True,
                "analysis": hvac_info
            }

        except json.JSONDecodeError as e:
            print(f"JSON decode error: {e}")
            print(f"Content that failed to parse: {content}")
            return {
                "success": False,
                "error": f"Failed to parse OpenAI response: {str(e)}",
                "analysis": {
                    "brand": None,
                    "model_number": None,
                    "serial_number": None,
                    "additional_info": None
                }
            }

        except Exception as e:
            print(f"OpenAI API error: {e}")
            return {
                "success": False,
                "error": str(e),
                "analysis": {
                    "brand": None,
                    "model_number": None,
                    "serial_number": None,
                    "additional_info": None
                }
            }


