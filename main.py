import os
import logging
import tempfile
from typing import Optional, List

from fastapi import FastAPI, UploadFile, File, HTTPException, Request, Header
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from openai import OpenAI

import config
import ocr
import parser
import anomaly
import storage
import telegram_notifier

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(title="BillMind API", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://localhost:3000",
        "https://*.vercel.app",
        "https://*.netlify.app",
        os.getenv("FRONTEND_URL", "")
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def log_requests(request: Request, call_next):
    """Log all incoming requests."""
    logger.info(f"{request.method} {request.url.path}")
    response = await call_next(request)
    return response


async def verify_api_key(x_api_key: Optional[str] = Header(None)):
    """Verify API key for protected endpoints."""
    if x_api_key != config.API_KEY:
        raise HTTPException(status_code=401, detail="Invalid or missing API key")


class Base64Request(BaseModel):
    image_base64: str
    source: str = "upload"


class StatusUpdateRequest(BaseModel):
    bill_id: str
    status: str


class ChatRequest(BaseModel):
    message: str
    history: List[dict] = []


@app.get("/health")
async def health_check():
    """Health check endpoint - no authentication required."""
    return {
        "status": "ok",
        "message": "BillMind API running"
    }


@app.post("/process-bill")
async def process_bill(
    file: UploadFile = File(...),
    x_api_key: Optional[str] = Header(None)
):
    """
    Process uploaded bill file through complete pipeline.
    
    Steps: OCR -> Parse -> Enrich -> Anomaly Check -> Save
    """
    await verify_api_key(x_api_key)
    
    temp_file_path = None
    
    try:
        logger.info(f"Processing uploaded file: {file.filename}")
        
        with tempfile.NamedTemporaryFile(delete=False, suffix=os.path.splitext(file.filename)[1]) as tmp:
            content = await file.read()
            tmp.write(content)
            temp_file_path = tmp.name
        
        logger.info("Step 1: Extracting text with OCR")
        raw_text = ocr.extract_text(temp_file_path)
        
        if not raw_text or not raw_text.strip():
            raise Exception("No text extracted from file")
        
        logger.info("Step 2: Parsing bill with AI")
        bill_dict = parser.parse_bill(raw_text)
        
        logger.info("Step 3: Enriching bill data")
        bill_dict = parser.enrich_bill(bill_dict)
        
        logger.info("Step 4: Getting existing bills")
        all_bills = storage.storage.get_all_bills()
        
        logger.info("Step 5: Running anomaly detection")
        anomaly_report = anomaly.detector.full_check(bill_dict, all_bills)
        
        logger.info("Step 6: Saving to storage")
        bill_id = storage.storage.save_bill(bill_dict, anomaly_report, source="upload")
        
        logger.info(f"Bill processed successfully: {bill_id}")
        
        logger.info("Step 7: Sending Telegram notification")
        telegram_notifier.send_telegram_notification(bill_dict, anomaly_report)
        
        return {
            "success": True,
            "bill_data": bill_dict,
            "anomaly_report": anomaly_report
        }
        
    except Exception as e:
        logger.error(f"Bill processing failed: {e}")
        return {
            "success": False,
            "error": str(e)
        }
    
    finally:
        if temp_file_path and os.path.exists(temp_file_path):
            os.unlink(temp_file_path)
            logger.debug(f"Cleaned up temp file: {temp_file_path}")


@app.post("/process-bill-base64")
async def process_bill_base64(
    request: Base64Request,
    x_api_key: Optional[str] = Header(None)
):
    """
    Process bill from base64 encoded image.
    
    Steps: Base64 Decode -> OCR -> Parse -> Enrich -> Anomaly Check -> Save
    """
    await verify_api_key(x_api_key)
    
    try:
        logger.info(f"Processing base64 bill from source: {request.source}")
        
        logger.info("Step 1: Decoding base64 and extracting text")
        raw_text = ocr.base64_to_text(request.image_base64)
        
        if not raw_text or not raw_text.strip():
            raise Exception("No text extracted from image")
        
        logger.info("Step 2: Parsing bill with AI")
        bill_dict = parser.parse_bill(raw_text)
        
        logger.info("Step 3: Enriching bill data")
        bill_dict = parser.enrich_bill(bill_dict)
        
        logger.info("Step 4: Getting existing bills")
        all_bills = storage.storage.get_all_bills()
        
        logger.info("Step 5: Running anomaly detection")
        anomaly_report = anomaly.detector.full_check(bill_dict, all_bills)
        
        logger.info("Step 6: Saving to storage")
        bill_id = storage.storage.save_bill(bill_dict, anomaly_report, source=request.source)
        
        logger.info(f"Bill processed successfully: {bill_id}")
        
        logger.info("Step 7: Sending Telegram notification")
        telegram_notifier.send_telegram_notification(bill_dict, anomaly_report)
        
        return {
            "success": True,
            "bill_data": bill_dict,
            "anomaly_report": anomaly_report
        }
        
    except Exception as e:
        logger.error(f"Bill processing failed: {e}")
        return {
            "success": False,
            "error": str(e)
        }


@app.get("/bills")
async def get_all_bills(x_api_key: Optional[str] = Header(None)):
    """Get all bills from storage."""
    await verify_api_key(x_api_key)
    
    try:
        bills = storage.storage.get_all_bills()
        return {"bills": bills}
    except Exception as e:
        logger.error(f"Failed to get bills: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/bills/summary")
async def get_bills_summary(x_api_key: Optional[str] = Header(None)):
    """Get summary statistics of all bills."""
    await verify_api_key(x_api_key)
    
    try:
        summary = storage.storage.get_summary()
        return summary
    except Exception as e:
        logger.error(f"Failed to get summary: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/bills/due-soon")
async def get_due_soon(
    days: int = 7,
    x_api_key: Optional[str] = Header(None)
):
    """Get bills due within specified number of days."""
    await verify_api_key(x_api_key)
    
    try:
        bills = storage.storage.get_upcoming_due(days=days)
        return {"bills": bills}
    except Exception as e:
        logger.error(f"Failed to get due bills: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/bills/anomalies")
async def get_anomalies(x_api_key: Optional[str] = Header(None)):
    """Get all bills flagged as anomalies."""
    await verify_api_key(x_api_key)
    
    try:
        bills = storage.storage.get_anomalies()
        return {"bills": bills}
    except Exception as e:
        logger.error(f"Failed to get anomalies: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.patch("/bills/status")
async def update_bill_status(
    request: StatusUpdateRequest,
    x_api_key: Optional[str] = Header(None)
):
    """Update payment status of a bill."""
    await verify_api_key(x_api_key)
    
    try:
        success = storage.storage.update_status(request.bill_id, request.status)
        return {"success": success}
    except Exception as e:
        logger.error(f"Failed to update status: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/chat")
async def chat_with_ai(
    request: ChatRequest,
    x_api_key: Optional[str] = Header(None)
):
    """
    Chat with BillMind AI assistant about your bills.
    
    The AI has access to your complete bill history and can answer
    questions about spending, categories, anomalies, etc.
    """
    await verify_api_key(x_api_key)
    
    try:
        if not config.OPENAI_API_KEY:
            raise HTTPException(status_code=500, detail="OpenAI API key not configured")
        
        logger.info(f"Chat request: {request.message}")
        
        summary = storage.storage.get_summary()
        all_bills = storage.storage.get_all_bills()
        
        context_data = {
            "summary": summary,
            "recent_bills": all_bills[-10:] if len(all_bills) > 10 else all_bills
        }
        
        system_prompt = f"""You are BillMind AI, a personal finance assistant. You have access to the user's complete bill history and summary data. Answer questions with specific numbers and dates. Be concise and helpful. Here is the data: {context_data}"""
        
        client = OpenAI(api_key=config.OPENAI_API_KEY)
        
        messages = [{"role": "system", "content": system_prompt}]
        
        for msg in request.history:
            messages.append(msg)
        
        messages.append({"role": "user", "content": request.message})
        
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=messages,
            temperature=0.7,
            max_tokens=500
        )
        
        reply = response.choices[0].message.content
        
        logger.info("Chat response generated successfully")
        
        return {"reply": reply}
        
    except Exception as e:
        logger.error(f"Chat failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
